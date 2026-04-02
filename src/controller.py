"""State-machine controller that bridges the Coup game logic and the UI."""

from enum import Enum, auto
from src.player import Player
from src.coup import Game
from src import actions


class State(Enum):
    SETUP_PLAYER_COUNT = auto()
    SETUP_PLAYER_NAME = auto()
    CHOOSE_ACTION = auto()
    CHOOSE_TARGET = auto()
    CHALLENGE_QUERY = auto()
    BLOCK_QUERY = auto()
    CHALLENGE_BLOCK_QUERY = auto()
    LOSE_INFLUENCE = auto()
    EXCHANGE_RETURN_FIRST = auto()
    EXCHANGE_RETURN_SECOND = auto()
    GAME_OVER = auto()


# Action metadata: (name, claimed_card, blockable_cards, needs_target, cost)
ACTION_INFO = {
    "Income":      (None, None, False, 0),
    "Foreign Aid": (None, ["Duke"], False, 0),
    "Tax":         ("Duke", None, False, 0),
    "Steal":       ("Captain", ["Ambassador", "Captain"], True, 0),
    "Exchange":    ("Ambassador", None, False, 0),
    "Assassinate": ("Assassin", ["Contessa"], True, 3),
    "Coup":        (None, None, True, 7),
}


class GameController:
    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all controller state to start a fresh game."""
        self.state = State.SETUP_PLAYER_COUNT
        self.game = None
        self.log = []

        # Setup tracking
        self.num_players = 0
        self.player_names = []

        # Turn tracking
        self.current_player_index = 0
        self.current_player = None

        # Pending action state
        self.pending_action = None       # action name string
        self.pending_target = None       # target Player
        self.pending_claimed_card = None
        self.pending_blockable_cards = None

        # Challenge/block walk state
        self.challenge_candidates = []   # players who can challenge
        self.challenge_index = 0         # which candidate we're asking

        self.block_candidates = []       # players who can block
        self.block_index = 0

        # For block challenges
        self.blocker = None
        self.block_claimed_card = None

        # For lose_influence — who needs to lose and what to do after
        self.lose_influence_player = None
        self.after_lose_influence = None  # callback string

    def _log(self, msg):
        self.log.append(msg)

    # ------------------------------------------------------------------
    # get_prompt() — returns (message, options) for the UI to render
    # ------------------------------------------------------------------
    def get_prompt(self):
        if self.state == State.SETUP_PLAYER_COUNT:
            return ("How many players? (2-6)", ["2", "3", "4", "5", "6"])

        elif self.state == State.SETUP_PLAYER_NAME:
            idx = len(self.player_names) + 1
            return (f"Enter name for Player {idx}:", None)

        elif self.state == State.CHOOSE_ACTION:
            p = self.current_player
            available = []
            for name, (claimed, blockable, needs_target, cost) in ACTION_INFO.items():
                if cost > p.coins:
                    continue
                available.append(name)
            if p.coins >= 10:
                available = ["Coup"]
                return (f"{p.name}'s turn (Coins: {p.coins}). You must Coup!",
                        available)
            return (f"{p.name}'s turn (Coins: {p.coins}). Choose an action:",
                    available)

        elif self.state == State.CHOOSE_TARGET:
            targets = self.game.get_valid_targets(self.current_player)
            options = [f"{t.name}" for t in targets]
            verb = self.pending_action.lower()
            return (f"Choose a target to {verb}:", options)

        elif self.state == State.CHALLENGE_QUERY:
            candidate = self.challenge_candidates[self.challenge_index]
            return (f"{candidate.name}: Challenge {self.current_player.name}'s "
                    f"{self.pending_claimed_card}?",
                    ["Yes", "No"])

        elif self.state == State.BLOCK_QUERY:
            candidate = self.block_candidates[self.block_index]
            cards = self.pending_blockable_cards
            options = ["Don't block"] + [f"Block with {c}" for c in cards]
            return (f"{candidate.name}: Block {self.current_player.name}'s "
                    f"{self.pending_action}?",
                    options)

        elif self.state == State.CHALLENGE_BLOCK_QUERY:
            candidate = self.challenge_candidates[self.challenge_index]
            return (f"{candidate.name}: Challenge {self.blocker.name}'s "
                    f"{self.block_claimed_card} block?",
                    ["Yes", "No"])

        elif self.state == State.LOSE_INFLUENCE:
            p = self.lose_influence_player
            if len(p.influence) == 1:
                # Auto-lose the only card
                card = p.influence[0]
                return (f"{p.name} must lose their {card}.", [card])
            else:
                options = list(p.influence)
                return (f"{p.name}, choose which influence to lose:", options)

        elif self.state == State.EXCHANGE_RETURN_FIRST:
            p = self.current_player
            return (f"{p.name}, choose first card to return:",
                    list(p.influence))

        elif self.state == State.EXCHANGE_RETURN_SECOND:
            p = self.current_player
            return (f"{p.name}, choose second card to return:",
                    list(p.influence))

        elif self.state == State.GAME_OVER:
            winner = self.game.get_living_players()[0]
            return (f"{winner.name} wins!", ["New Game"])

        return ("Unknown state", [])

    # ------------------------------------------------------------------
    # handle_input(value) — the UI calls this when a button is clicked
    # ------------------------------------------------------------------
    def handle_input(self, value):
        if self.state == State.SETUP_PLAYER_COUNT:
            self._handle_setup_count(value)
        elif self.state == State.SETUP_PLAYER_NAME:
            self._handle_setup_name(value)
        elif self.state == State.CHOOSE_ACTION:
            self._handle_choose_action(value)
        elif self.state == State.CHOOSE_TARGET:
            self._handle_choose_target(value)
        elif self.state == State.CHALLENGE_QUERY:
            self._handle_challenge_query(value)
        elif self.state == State.BLOCK_QUERY:
            self._handle_block_query(value)
        elif self.state == State.CHALLENGE_BLOCK_QUERY:
            self._handle_challenge_block_query(value)
        elif self.state == State.LOSE_INFLUENCE:
            self._handle_lose_influence(value)
        elif self.state == State.EXCHANGE_RETURN_FIRST:
            self._handle_exchange_return_first(value)
        elif self.state == State.EXCHANGE_RETURN_SECOND:
            self._handle_exchange_return_second(value)
        elif self.state == State.GAME_OVER:
            self._handle_game_over(value)

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_setup_count(self, value):
        try:
            n = int(value)
            if 2 <= n <= 6:
                self.num_players = n
                self.player_names = []
                self.state = State.SETUP_PLAYER_NAME
                return
        except ValueError:
            pass
        self._log("Please enter a number between 2 and 6.")

    def _handle_setup_name(self, value):
        name = value.strip()
        if not name:
            self._log("Name cannot be empty.")
            return
        self.player_names.append(name)
        if len(self.player_names) == self.num_players:
            # All names collected — start the game
            players = [Player(n) for n in self.player_names]
            self.game = Game(players)
            self._log("Game started! Cards dealt.")
            for p in self.game.players:
                self._log(f"  {p.name}: {', '.join(p.influence)}")
            self.current_player_index = 0
            self.current_player = self.game.players[0]
            self.state = State.CHOOSE_ACTION
        # else stay in SETUP_PLAYER_NAME for next player

    def _handle_choose_action(self, value):
        action_name = value
        if action_name not in ACTION_INFO:
            return

        claimed, blockable, needs_target, cost = ACTION_INFO[action_name]
        p = self.current_player

        # Validate cost
        if cost > p.coins:
            self._log(f"Not enough coins for {action_name}.")
            return

        # Deduct cost immediately (Assassinate / Coup)
        if cost > 0:
            p.coins -= cost

        self.pending_action = action_name
        self.pending_claimed_card = claimed
        self.pending_blockable_cards = blockable
        self.pending_target = None

        self._log(f"{p.name} chooses {action_name}.")

        if needs_target:
            self.state = State.CHOOSE_TARGET
        elif claimed:
            # Challengeable action (Tax, Exchange) — go to challenge
            self._start_challenge()
        elif blockable:
            # Blockable but not challengeable (Foreign Aid)
            self._start_block()
        else:
            # Income — just do it
            self._execute_action()

    def _handle_choose_target(self, value):
        targets = self.game.get_valid_targets(self.current_player)
        target = None
        for t in targets:
            if t.name == value:
                target = t
                break
        if target is None:
            return

        self.pending_target = target
        self._log(f"Target: {target.name}")

        # Steal target with 0 coins — disallow
        if self.pending_action == "Steal" and target.coins == 0:
            self._log(f"{target.name} has no coins to steal. Choose another target.")
            return

        claimed = self.pending_claimed_card
        if claimed:
            self._start_challenge()
        elif self.pending_blockable_cards:
            self._start_block()
        else:
            # Coup — no challenge or block
            self._execute_action()

    # ------ Challenge flow ------

    def _start_challenge(self):
        """Begin walking through players to see if anyone challenges."""
        acting = self.current_player
        self.challenge_candidates = [
            p for p in self.game.players
            if p != acting and p.is_alive()
        ]
        self.challenge_index = 0
        if not self.challenge_candidates:
            self._after_challenge_passed()
        else:
            self.state = State.CHALLENGE_QUERY

    def _handle_challenge_query(self, value):
        if value == "Yes":
            challenger = self.challenge_candidates[self.challenge_index]
            self._resolve_action_challenge(challenger)
        elif value == "No":
            self.challenge_index += 1
            if self.challenge_index >= len(self.challenge_candidates):
                self._after_challenge_passed()
            # else stay in CHALLENGE_QUERY for next candidate
        # else ignore invalid input

    def _resolve_action_challenge(self, challenger):
        succeeded, loser = self.game.resolve_challenge(
            self.current_player, self.pending_claimed_card, challenger)

        if succeeded:
            # Challenge succeeded — acting player was bluffing
            self._log(f"{challenger.name} challenges — "
                      f"{self.current_player.name} does NOT have "
                      f"{self.pending_claimed_card}! Challenge succeeds!")
            # The loser (acting player) must lose influence
            self._enter_lose_influence(loser, "action_challenged_success")
        else:
            # Challenge failed — acting player had the card
            self._log(f"{challenger.name} challenges — "
                      f"{self.current_player.name} reveals "
                      f"{self.pending_claimed_card}! Challenge fails!")
            # The challenger must lose influence
            self._enter_lose_influence(loser, "action_challenged_fail")

    def _after_challenge_passed(self):
        """No one challenged (or challenge failed and we continue). Move to block or execute."""
        if self.pending_blockable_cards:
            self._start_block()
        else:
            self._execute_action()

    # ------ Block flow ------

    def _start_block(self):
        """Begin walking through eligible players to see if anyone blocks."""
        acting = self.current_player
        target = self.pending_target

        if target:
            # Only the target can block (Steal, Assassinate)
            self.block_candidates = [target] if target.is_alive() else []
        else:
            # Anyone can block (Foreign Aid)
            self.block_candidates = [
                p for p in self.game.players
                if p != acting and p.is_alive()
            ]

        self.block_index = 0
        if not self.block_candidates:
            self._execute_action()
        else:
            self.state = State.BLOCK_QUERY

    def _handle_block_query(self, value):
        if value == "Don't block":
            self.block_index += 1
            if self.block_index >= len(self.block_candidates):
                # No one blocked
                self._execute_action()
            # else stay in BLOCK_QUERY for next candidate
        elif value.startswith("Block with "):
            card = value[len("Block with "):]
            blocker = self.block_candidates[self.block_index]
            self.blocker = blocker
            self.block_claimed_card = card
            self._log(f"{blocker.name} blocks with {card}!")
            # The block can now be challenged
            self._start_challenge_block()

    # ------ Challenge-on-block flow ------

    def _start_challenge_block(self):
        """Walk through players to see if anyone challenges the block."""
        self.challenge_candidates = [
            p for p in self.game.players
            if p != self.blocker and p.is_alive()
        ]
        self.challenge_index = 0
        if not self.challenge_candidates:
            # No one can challenge the block — block stands
            self._block_stands()
        else:
            self.state = State.CHALLENGE_BLOCK_QUERY

    def _handle_challenge_block_query(self, value):
        if value == "Yes":
            challenger = self.challenge_candidates[self.challenge_index]
            self._resolve_block_challenge(challenger)
        elif value == "No":
            self.challenge_index += 1
            if self.challenge_index >= len(self.challenge_candidates):
                self._block_stands()
            # else stay in CHALLENGE_BLOCK_QUERY for next candidate

    def _resolve_block_challenge(self, challenger):
        succeeded, loser = self.game.resolve_challenge(
            self.blocker, self.block_claimed_card, challenger)

        if succeeded:
            # Block challenge succeeded — blocker was bluffing, action goes through
            self._log(f"{challenger.name} challenges the block — "
                      f"{self.blocker.name} does NOT have "
                      f"{self.block_claimed_card}! Block fails!")
            self._enter_lose_influence(loser, "block_challenged_success")
        else:
            # Block challenge failed — blocker had the card, block stands
            self._log(f"{challenger.name} challenges the block — "
                      f"{self.blocker.name} reveals "
                      f"{self.block_claimed_card}! Block holds!")
            self._enter_lose_influence(loser, "block_challenged_fail")

    def _block_stands(self):
        self._log(f"{self.current_player.name}'s {self.pending_action} was blocked!")
        self._advance_turn()

    # ------ Lose influence flow ------

    def _enter_lose_influence(self, player, after):
        """Transition to LOSE_INFLUENCE. `after` describes what to do next."""
        self.lose_influence_player = player
        self.after_lose_influence = after

        if len(player.influence) == 0:
            # Already dead — skip
            self._after_lose_influence_done()
            return

        if len(player.influence) == 1:
            # Only one card — auto-lose it
            card = player.influence[0]
            self.game.lose_influence(player, card)
            self._log(f"{player.name} loses {card}.")
            self._after_lose_influence_done()
            return

        self.state = State.LOSE_INFLUENCE

    def _handle_lose_influence(self, value):
        p = self.lose_influence_player
        if value in p.influence:
            self.game.lose_influence(p, value)
            self._log(f"{p.name} loses {value}.")
            self._after_lose_influence_done()

    def _after_lose_influence_done(self):
        """Route to the correct continuation after someone lost influence."""
        if self._check_game_over():
            return

        after = self.after_lose_influence

        if after == "action_challenged_success":
            # Acting player was caught bluffing — action cancelled, next turn
            self._advance_turn()

        elif after == "action_challenged_fail":
            # Challenger lost — action continues (go to block or execute)
            self._after_challenge_passed()

        elif after == "block_challenged_success":
            # Blocker was caught bluffing — action goes through
            self._execute_action()

        elif after == "block_challenged_fail":
            # Block challenge failed — block holds, action cancelled
            self._block_stands()

        elif after == "action_effect":
            # Someone lost influence as part of the action effect (assassinate/coup)
            self._advance_turn()

        else:
            self._advance_turn()

    # ------ Execute action ------

    def _execute_action(self):
        p = self.current_player
        action = self.pending_action

        if action == "Income":
            actions.do_income(self.game, p)
            self._log(f"{p.name} takes Income. (+1 coin)")
            self._advance_turn()

        elif action == "Foreign Aid":
            actions.do_foreign_aid(self.game, p)
            self._log(f"{p.name} takes Foreign Aid. (+2 coins)")
            self._advance_turn()

        elif action == "Tax":
            actions.do_tax(self.game, p)
            self._log(f"{p.name} collects Tax. (+3 coins)")
            self._advance_turn()

        elif action == "Steal":
            target = self.pending_target
            stolen = actions.do_steal(self.game, p, target)
            self._log(f"{p.name} steals {stolen} coins from {target.name}.")
            self._advance_turn()

        elif action == "Assassinate":
            target = self.pending_target
            if not target.is_alive():
                self._log(f"{target.name} is already out.")
                self._advance_turn()
                return
            self._log(f"{p.name} assassinates {target.name}!")
            self._enter_lose_influence(target, "action_effect")

        elif action == "Coup":
            target = self.pending_target
            self._log(f"{p.name} launches a Coup against {target.name}!")
            self._enter_lose_influence(target, "action_effect")

        elif action == "Exchange":
            actions.do_exchange_draw(self.game, p)
            self._log(f"{p.name} draws 2 cards for Exchange.")
            self.state = State.EXCHANGE_RETURN_FIRST

    # ------ Exchange return flow ------

    def _handle_exchange_return_first(self, value):
        p = self.current_player
        if value in p.influence:
            actions.do_exchange_return(self.game, p, value)
            self._log(f"{p.name} returns a card to the deck.")
            self.state = State.EXCHANGE_RETURN_SECOND

    def _handle_exchange_return_second(self, value):
        p = self.current_player
        if value in p.influence:
            actions.do_exchange_return(self.game, p, value)
            self._log(f"{p.name} returns a card to the deck.")
            self._advance_turn()

    # ------ Turn management ------

    def _advance_turn(self):
        if self._check_game_over():
            return

        # Clear pending state
        self.pending_action = None
        self.pending_target = None
        self.pending_claimed_card = None
        self.pending_blockable_cards = None
        self.blocker = None
        self.block_claimed_card = None

        # Move to the next living player
        n = len(self.game.players)
        idx = self.current_player_index
        for _ in range(n):
            idx = (idx + 1) % n
            if self.game.players[idx].is_alive():
                break

        self.current_player_index = idx
        self.current_player = self.game.players[idx]
        self.state = State.CHOOSE_ACTION

    def _check_game_over(self):
        if self.game is None:
            return False
        living = self.game.get_living_players()
        if len(living) <= 1:
            if living:
                self._log(f"{living[0].name} wins the game!")
            self.state = State.GAME_OVER
            return True
        return False

    def _handle_game_over(self, value):
        if value == "New Game":
            self.reset()
