"""Core orchestration loop: drives GameController with AI agents."""

from src.controller import GameController, State
from src.coup import Game
from src.deck import Deck
from AI_game.prompt_builder import build_prompt
from AI_game.response_parser import parse_response, ParseError
from AI_game.console_output import ConsoleOutput
from AI_game.stats import record_game

MAX_RETRIES = 3


class GameRunner:
    """Runs a complete Coup game with AI agents."""

    def __init__(self, agents, preset=None):
        """Initialize with a list of Agent instances in turn order.

        Args:
            agents: list of Agent instances (2-6 agents)
            preset: optional validated preset dict to apply custom start conditions
        """
        self.agents = agents
        self.preset = preset
        self.controller = GameController()
        self.output = ConsoleOutput()
        self.event_log = []       # list of {"type": "event"/"speech", ...}
        self._log_cursor = 0      # tracks how far we've consumed controller.log
        self._turn_number = 0

    def run(self):
        """Run the full game from setup to game over."""
        self._setup_game()
        self.output.game_started(self.controller)
        self._game_loop()

    def _setup_game(self):
        """Programmatically feed setup inputs to bypass the UI setup states.

        If a preset is configured, applies custom start conditions (hands,
        coins, deck) after the standard setup creates the Game object.
        """
        if self.preset is not None:
            self._setup_game_with_preset()
        else:
            self._setup_game_standard()

        self._consume_log()

    def _setup_game_standard(self):
        """Standard setup: feed player count and names to the controller."""
        # Step 1: Set player count
        self.controller.handle_input(str(len(self.agents)))

        # Step 2: Set each player name
        for agent in self.agents:
            self.controller.handle_input(agent.name)

    def _setup_game_with_preset(self):
        """Setup with preset: create a pre-configured Game and inject it."""
        from AI_game.presets import apply_preset

        players, deck_cards = apply_preset(self.preset, self.agents)
        deck = Deck(cards=deck_cards)

        # For players that have no hand specified in preset, deal from deck
        players_cfg = self.preset.get("players", {})
        for player in players:
            cfg = players_cfg.get(player.name, {})
            if cfg.get("hand") is None:
                # Deal 2 cards from the deck as normal
                card1 = deck.draw()
                card2 = deck.draw()
                if card1:
                    player.add_influence(card1)
                if card2:
                    player.add_influence(card2)

        game = Game(players, deck=deck, skip_deal=True)

        # Inject the game into the controller, bypassing setup states
        self.controller.game = game
        self.controller.num_players = len(players)
        self.controller.player_names = [p.name for p in players]
        self.controller.current_player_index = 0
        self.controller.current_player = game.players[0]
        self.controller.state = State.CHOOSE_ACTION
        self.controller._log("Game started with preset! Cards dealt.")

    def _build_agent_map(self):
        """Map player names to Agent instances."""
        return {agent.name: agent for agent in self.agents}

    def _game_loop(self):
        """Main game loop — query agents until game over."""
        agent_map = self._build_agent_map()
        last_turn_player = None

        while self.controller.state != State.GAME_OVER:
            player = self.controller.get_active_player()
            if player is None:
                break

            # Track turn transitions
            if (self.controller.state == State.CHOOSE_ACTION
                    and player != last_turn_player):
                self._turn_number += 1
                self.output.turn_start(player.name, self._turn_number)
                last_turn_player = player

            agent = agent_map.get(player.name)
            if agent is None:
                break

            message, options = self.controller.get_prompt(player)

            if options is None:
                # Text entry state — shouldn't happen after setup
                break

            action, speech = self._query_agent(agent, player, options)

            # Record speech and send to controller chat
            if speech:
                self.event_log.append({
                    "type": "speech",
                    "player": player.name,
                    "text": speech,
                })
                self.controller.send_chat(player.name, speech)
                self.output.agent_response(player.name, speech, action)
            else:
                self.output.agent_response(player.name, "(silent)", action)

            # Execute the action
            self.controller.handle_input(action, player)
            self._consume_log()

            # Print game state after each full turn
            if self.controller.state == State.CHOOSE_ACTION:
                self.output.game_state_summary(self.controller)

        # Game over
        if self.controller.state == State.GAME_OVER:
            self._consume_log()
            winner = self.controller.game.get_living_players()[0]
            self.output.game_over(winner.name)
            self.output.token_usage(self.agents)
            # Record stats — find the winning agent's model
            agent_map = self._build_agent_map()
            winner_agent = agent_map[winner.name]
            record_game(self.agents, winner_agent.model)

    def _query_agent(self, agent, player, options):
        """Build prompt, query agent, parse response. Retry on failure.

        Returns (action, speech) tuple.
        """
        prompt = build_prompt(self.controller, player, agent, self.event_log)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self.output.agent_thinking(agent.name)
                raw = agent.query(prompt)
                self.output.agent_done()

                result = parse_response(raw, options)

                # Store private thought if provided
                private = result.get("private_thought", "")
                if private:
                    agent.add_thought(private)

                return result["action"], result["speech"]

            except ParseError as e:
                self.output.agent_done()
                self.output.agent_error(agent.name, attempt, str(e))
            except Exception as e:
                self.output.agent_done()
                self.output.agent_error(agent.name, attempt, f"API error: {e}")

        # All retries exhausted — fall back to first valid option
        fallback = options[0]
        self.output.agent_fallback(agent.name, fallback)
        return fallback, ""

    def _consume_log(self):
        """Transfer new controller log entries into event_log and print them."""
        while self._log_cursor < len(self.controller.log):
            text = self.controller.log[self._log_cursor]
            self.event_log.append({"type": "event", "text": text})
            self.output.game_event(text)
            self._log_cursor += 1
