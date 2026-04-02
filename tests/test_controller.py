"""Tests for the GameController state machine."""

import unittest
from src.controller import GameController, State


def setup_two_player_game(gc):
    """Run through setup to get a 2-player game ready for actions."""
    gc.handle_input("2")
    gc.handle_input("Alice")
    gc.handle_input("Bob")


class TestSetupFlow(unittest.TestCase):
    def test_initial_state(self):
        gc = GameController()
        self.assertEqual(gc.state, State.SETUP_PLAYER_COUNT)

    def test_get_prompt_player_count(self):
        gc = GameController()
        msg, options = gc.get_prompt()
        self.assertIn("How many", msg)
        self.assertEqual(options, ["2", "3", "4", "5", "6"])

    def test_select_player_count(self):
        gc = GameController()
        gc.handle_input("3")
        self.assertEqual(gc.state, State.SETUP_PLAYER_NAME)
        self.assertEqual(gc.num_players, 3)

    def test_invalid_player_count_stays(self):
        gc = GameController()
        gc.handle_input("7")
        self.assertEqual(gc.state, State.SETUP_PLAYER_COUNT)

    def test_non_numeric_player_count(self):
        gc = GameController()
        gc.handle_input("abc")
        self.assertEqual(gc.state, State.SETUP_PLAYER_COUNT)
        self.assertTrue(any("number" in m.lower() for m in gc.log))

    def test_enter_names_transitions_to_game(self):
        gc = GameController()
        setup_two_player_game(gc)
        self.assertEqual(gc.state, State.CHOOSE_ACTION)
        self.assertIsNotNone(gc.game)
        self.assertEqual(len(gc.game.players), 2)

    def test_empty_name_rejected(self):
        gc = GameController()
        gc.handle_input("2")
        gc.handle_input("")
        self.assertEqual(gc.state, State.SETUP_PLAYER_NAME)
        self.assertEqual(len(gc.player_names), 0)

    def test_first_player_is_current(self):
        gc = GameController()
        setup_two_player_game(gc)
        self.assertEqual(gc.current_player.name, "Alice")
        self.assertEqual(gc.current_player_index, 0)


class TestIncomeFlow(unittest.TestCase):
    def test_income_adds_coin_and_advances(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        initial_coins = alice.coins
        gc.handle_input("Income")
        self.assertEqual(alice.coins, initial_coins + 1)
        self.assertEqual(gc.state, State.CHOOSE_ACTION)
        self.assertEqual(gc.current_player.name, "Bob")


class TestTaxFlow(unittest.TestCase):
    def test_tax_unchallenged(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        initial_coins = alice.coins
        gc.handle_input("Tax")
        # Bob is asked to challenge
        self.assertEqual(gc.state, State.CHALLENGE_QUERY)
        gc.handle_input("No")
        # No one else to challenge, tax executes
        self.assertEqual(alice.coins, initial_coins + 3)
        self.assertEqual(gc.current_player.name, "Bob")

    def test_tax_challenged_bluffing(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        alice.influence = ["Captain", "Contessa"]
        gc.handle_input("Tax")
        self.assertEqual(gc.state, State.CHALLENGE_QUERY)
        gc.handle_input("Yes")
        # Alice was bluffing (no Duke), challenge succeeds
        # Alice has 2 cards so she must choose which to lose
        self.assertEqual(gc.state, State.LOSE_INFLUENCE)
        self.assertIs(gc.lose_influence_player, alice)
        gc.handle_input("Captain")
        # Action cancelled, turn advances to Bob
        self.assertEqual(gc.current_player.name, "Bob")

    def test_tax_challenged_truthful(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        alice.influence = ["Duke", "Captain"]
        gc.handle_input("Tax")
        self.assertEqual(gc.state, State.CHALLENGE_QUERY)
        initial_coins = alice.coins
        gc.handle_input("Yes")
        # Alice had Duke, challenge fails. Bob auto-loses if 1 card, or chooses
        if len(bob.influence) == 1:
            # Auto-lose, then tax executes
            self.assertEqual(alice.coins, initial_coins + 3)
        else:
            # Bob chooses which influence to lose
            self.assertEqual(gc.state, State.LOSE_INFLUENCE)
            self.assertIs(gc.lose_influence_player, bob)
            card = bob.influence[0]
            gc.handle_input(card)
            self.assertEqual(alice.coins, initial_coins + 3)


class TestForeignAidFlow(unittest.TestCase):
    def test_foreign_aid_unblocked(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        initial_coins = alice.coins
        gc.handle_input("Foreign Aid")
        # Bob is asked to block
        self.assertEqual(gc.state, State.BLOCK_QUERY)
        gc.handle_input("Don't block")
        self.assertEqual(alice.coins, initial_coins + 2)
        self.assertEqual(gc.current_player.name, "Bob")

    def test_foreign_aid_blocked(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        initial_coins = alice.coins
        gc.handle_input("Foreign Aid")
        self.assertEqual(gc.state, State.BLOCK_QUERY)
        gc.handle_input("Block with Duke")
        # Alice is asked to challenge the block
        self.assertEqual(gc.state, State.CHALLENGE_BLOCK_QUERY)
        gc.handle_input("No")
        # Block stands, action cancelled
        self.assertEqual(alice.coins, initial_coins)
        self.assertEqual(gc.current_player.name, "Bob")


class TestStealFlow(unittest.TestCase):
    def test_steal_unchallenged_unblocked(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        bob.coins = 5
        gc.handle_input("Steal")
        self.assertEqual(gc.state, State.CHOOSE_TARGET)
        gc.handle_input("Bob")
        # Challenge query
        self.assertEqual(gc.state, State.CHALLENGE_QUERY)
        gc.handle_input("No")
        # Block query (Bob can block with Ambassador or Captain)
        self.assertEqual(gc.state, State.BLOCK_QUERY)
        gc.handle_input("Don't block")
        self.assertEqual(alice.coins, 4)  # 2 start + 2 stolen
        self.assertEqual(bob.coins, 3)

    def test_steal_zero_coins_rejected(self):
        gc = GameController()
        setup_two_player_game(gc)
        bob = gc.game.players[1]
        bob.coins = 0
        gc.handle_input("Steal")
        self.assertEqual(gc.state, State.CHOOSE_TARGET)
        gc.handle_input("Bob")
        # Should stay on target selection
        self.assertEqual(gc.state, State.CHOOSE_TARGET)


class TestCoupFlow(unittest.TestCase):
    def test_coup_requires_seven_coins(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        alice.coins = 6
        msg, options = gc.get_prompt()
        self.assertNotIn("Coup", options)

    def test_coup_deducts_and_targets(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        alice.coins = 7
        gc.handle_input("Coup")
        self.assertEqual(alice.coins, 0)
        self.assertEqual(gc.state, State.CHOOSE_TARGET)
        gc.handle_input("Bob")
        # Bob loses influence (auto if 1 card, choose if 2)
        if len(bob.influence) == 2:
            self.assertEqual(gc.state, State.LOSE_INFLUENCE)
            gc.handle_input(bob.influence[0])
        self.assertEqual(len(bob.influence), 1)

    def test_forced_coup_at_ten_coins(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        alice.coins = 10
        msg, options = gc.get_prompt()
        self.assertEqual(options, ["Coup"])
        self.assertIn("must Coup", msg)


class TestAssassinateFlow(unittest.TestCase):
    def test_assassinate_costs_three(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        alice.coins = 3
        gc.handle_input("Assassinate")
        self.assertEqual(alice.coins, 0)

    def test_assassinate_unchallenged_unblocked(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        alice.coins = 3
        bob.influence = ["Duke", "Captain"]
        gc.handle_input("Assassinate")
        gc.handle_input("Bob")
        # Challenge walk
        self.assertEqual(gc.state, State.CHALLENGE_QUERY)
        gc.handle_input("No")
        # Block query (Contessa)
        self.assertEqual(gc.state, State.BLOCK_QUERY)
        gc.handle_input("Don't block")
        # Bob must lose influence
        self.assertEqual(gc.state, State.LOSE_INFLUENCE)
        gc.handle_input("Duke")
        self.assertEqual(bob.influence, ["Captain"])


class TestExchangeFlow(unittest.TestCase):
    def test_exchange_unchallenged(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        gc.handle_input("Exchange")
        # Challenge walk
        self.assertEqual(gc.state, State.CHALLENGE_QUERY)
        gc.handle_input("No")
        # Exchange draw happened, now return first card
        self.assertEqual(gc.state, State.EXCHANGE_RETURN_FIRST)
        self.assertEqual(len(alice.influence), 4)
        card1 = alice.influence[0]
        gc.handle_input(card1)
        self.assertEqual(gc.state, State.EXCHANGE_RETURN_SECOND)
        self.assertEqual(len(alice.influence), 3)
        card2 = alice.influence[0]
        gc.handle_input(card2)
        self.assertEqual(len(alice.influence), 2)
        self.assertEqual(gc.current_player.name, "Bob")


class TestGameOver(unittest.TestCase):
    def test_game_over_when_one_player_left(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        # Give Alice enough to coup, make Bob have 1 card
        alice.coins = 7
        bob.influence = ["Duke"]
        gc.handle_input("Coup")
        gc.handle_input("Bob")
        # Bob auto-loses his only card
        self.assertEqual(gc.state, State.GAME_OVER)
        msg, options = gc.get_prompt()
        self.assertIn("Alice", msg)
        self.assertIn("wins", msg)
        self.assertEqual(options, ["New Game"])

    def test_new_game_resets(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        alice.coins = 7
        bob.influence = ["Duke"]
        gc.handle_input("Coup")
        gc.handle_input("Bob")
        self.assertEqual(gc.state, State.GAME_OVER)
        gc.handle_input("New Game")
        self.assertEqual(gc.state, State.SETUP_PLAYER_COUNT)
        self.assertIsNone(gc.game)
        self.assertEqual(gc.log, [])


class TestResetMethod(unittest.TestCase):
    def test_reset_clears_all_state(self):
        gc = GameController()
        setup_two_player_game(gc)
        gc.handle_input("Income")
        # Now some state is set
        self.assertIsNotNone(gc.game)
        self.assertTrue(len(gc.log) > 0)
        gc.reset()
        self.assertEqual(gc.state, State.SETUP_PLAYER_COUNT)
        self.assertIsNone(gc.game)
        self.assertEqual(gc.log, [])
        self.assertIsNone(gc.current_player)
        self.assertIsNone(gc.pending_action)


class TestTurnAdvancement(unittest.TestCase):
    def test_skips_dead_players(self):
        gc = GameController()
        gc.handle_input("3")
        gc.handle_input("Alice")
        gc.handle_input("Bob")
        gc.handle_input("Charlie")
        # Kill Bob
        gc.game.players[1].influence = []
        # Alice takes income, should skip Bob and go to Charlie
        gc.handle_input("Income")
        self.assertEqual(gc.current_player.name, "Charlie")

    def test_three_player_turn_order(self):
        gc = GameController()
        gc.handle_input("3")
        gc.handle_input("Alice")
        gc.handle_input("Bob")
        gc.handle_input("Charlie")
        self.assertEqual(gc.current_player.name, "Alice")
        gc.handle_input("Income")
        self.assertEqual(gc.current_player.name, "Bob")
        gc.handle_input("Income")
        self.assertEqual(gc.current_player.name, "Charlie")
        gc.handle_input("Income")
        self.assertEqual(gc.current_player.name, "Alice")


class TestBlockChallengeFlow(unittest.TestCase):
    def test_foreign_aid_block_challenged_blocker_bluffing(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        bob.influence = ["Captain", "Assassin"]
        initial_coins = alice.coins
        gc.handle_input("Foreign Aid")
        gc.handle_input("Block with Duke")
        # Alice asked to challenge the block
        self.assertEqual(gc.state, State.CHALLENGE_BLOCK_QUERY)
        gc.handle_input("Yes")
        # Bob was bluffing (no Duke), block fails
        # Bob loses influence (has 2, must choose)
        self.assertEqual(gc.state, State.LOSE_INFLUENCE)
        self.assertIs(gc.lose_influence_player, bob)
        gc.handle_input("Captain")
        # Block failed, action goes through
        self.assertEqual(alice.coins, initial_coins + 2)

    def test_foreign_aid_block_challenged_blocker_truthful(self):
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        bob.influence = ["Duke", "Assassin"]
        initial_coins = alice.coins
        gc.handle_input("Foreign Aid")
        gc.handle_input("Block with Duke")
        self.assertEqual(gc.state, State.CHALLENGE_BLOCK_QUERY)
        gc.handle_input("Yes")
        # Bob had Duke, challenge fails. Alice loses influence, block stands
        if len(alice.influence) == 2:
            self.assertEqual(gc.state, State.LOSE_INFLUENCE)
            gc.handle_input(alice.influence[0])
        # Block holds — no coins gained
        self.assertEqual(alice.coins, initial_coins)


class TestGetPrompt(unittest.TestCase):
    def test_lose_influence_single_card_auto_selects(self):
        """When a player has 1 card, get_prompt still shows it as the only option."""
        gc = GameController()
        setup_two_player_game(gc)
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        bob.influence = ["Duke", "Captain"]
        alice.coins = 3
        alice.influence = ["Assassin", "Contessa"]
        gc.handle_input("Assassinate")
        gc.handle_input("Bob")
        # Bob challenges
        gc.handle_input("No")
        # Bob doesn't block
        gc.handle_input("Don't block")
        # Bob must lose influence — has 2 cards, so choose
        self.assertEqual(gc.state, State.LOSE_INFLUENCE)
        msg, options = gc.get_prompt()
        self.assertEqual(set(options), {"Duke", "Captain"})

    def test_unknown_state_returns_fallback(self):
        gc = GameController()
        gc.state = None  # Force an unrecognized state
        msg, options = gc.get_prompt()
        self.assertEqual(msg, "Unknown state")


if __name__ == "__main__":
    unittest.main()
