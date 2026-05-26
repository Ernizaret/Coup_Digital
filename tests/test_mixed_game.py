"""Tests for mixed human/AI game support.

Tests cover:
- Player.is_ai integration with Game and GameController
- _get_card_options() lazy loader
- AI orchestration helpers (consume_log, turn boundaries)
"""

import unittest
from src.player import Player
from src.coup import Game
from src.controller import GameController, State


class TestPlayerIsAiWithGame(unittest.TestCase):
    """Test that is_ai attribute works correctly with the Game model."""

    def test_game_with_mixed_players(self):
        players = [Player("Alice"), Player("Claude", is_ai=True)]
        game = Game(players)
        self.assertFalse(game.players[0].is_ai)
        self.assertTrue(game.players[1].is_ai)
        # Both players get dealt cards normally
        self.assertEqual(len(game.players[0].influence), 2)
        self.assertEqual(len(game.players[1].influence), 2)

    def test_game_operations_unaffected_by_is_ai(self):
        players = [Player("Alice"), Player("Claude", is_ai=True)]
        game = Game(players, seed=42)
        ai = game.players[1]
        card = ai.influence[0]
        game.lose_influence(ai, card)
        self.assertEqual(len(ai.influence), 1)
        self.assertIn(card, game.revealed_cards)

    def test_get_valid_targets_includes_ai(self):
        players = [Player("Alice"), Player("Claude", is_ai=True)]
        game = Game(players)
        targets = game.get_valid_targets(game.players[0])
        self.assertEqual(len(targets), 1)
        self.assertTrue(targets[0].is_ai)

    def test_get_living_players_includes_ai(self):
        players = [
            Player("Alice"),
            Player("Claude", is_ai=True),
            Player("Bob"),
        ]
        game = Game(players)
        living = game.get_living_players()
        self.assertEqual(len(living), 3)
        ai_players = [p for p in living if p.is_ai]
        self.assertEqual(len(ai_players), 1)


class TestControllerWithAiPlayers(unittest.TestCase):
    """Test that the controller works with AI-flagged players."""

    def _setup_mixed_game(self, seed=42):
        """Set up a game with one human and one AI player."""
        ctrl = GameController(seed=seed)
        ctrl.handle_input("2")
        ctrl.handle_input("Alice")
        ctrl.handle_input("Claude")
        # Mark second player as AI
        ctrl.game.players[1].is_ai = True
        return ctrl

    def test_setup_with_ai_flag(self):
        ctrl = self._setup_mixed_game()
        self.assertEqual(ctrl.state, State.CHOOSE_ACTION)
        self.assertFalse(ctrl.game.players[0].is_ai)
        self.assertTrue(ctrl.game.players[1].is_ai)

    def test_get_active_player_returns_ai(self):
        ctrl = self._setup_mixed_game()
        # Force AI player's turn
        ctrl.current_player_index = 1
        ctrl.current_player = ctrl.game.players[1]
        active = ctrl.get_active_player()
        self.assertIs(active, ctrl.game.players[1])
        self.assertTrue(active.is_ai)

    def test_get_active_players_includes_ai(self):
        ctrl = self._setup_mixed_game()
        ctrl.current_player_index = 1
        ctrl.current_player = ctrl.game.players[1]
        actives = ctrl.get_active_players()
        self.assertEqual(len(actives), 1)
        self.assertTrue(actives[0].is_ai)

    def test_handle_input_works_for_ai_player(self):
        ctrl = self._setup_mixed_game()
        # Let first player (human) take income
        ctrl.handle_input("Income", ctrl.game.players[0])
        # Now it should be AI's turn
        self.assertEqual(ctrl.state, State.CHOOSE_ACTION)
        self.assertIs(ctrl.current_player, ctrl.game.players[1])
        self.assertTrue(ctrl.current_player.is_ai)
        # AI takes income too
        ctrl.handle_input("Income", ctrl.game.players[1])
        # Back to human's turn
        self.assertIs(ctrl.current_player, ctrl.game.players[0])
        self.assertFalse(ctrl.current_player.is_ai)

    def test_challenge_query_with_mixed_players(self):
        ctrl = self._setup_mixed_game()
        # Human player claims Tax (Duke)
        ctrl.handle_input("Tax", ctrl.game.players[0])
        # AI player should be the challenge candidate
        self.assertEqual(ctrl.state, State.CHALLENGE_QUERY)
        candidates = ctrl.get_active_players()
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].is_ai)

    def test_block_query_with_ai_blocker(self):
        ctrl = self._setup_mixed_game()
        # Human takes Foreign Aid
        ctrl.handle_input("Foreign Aid", ctrl.game.players[0])
        # AI should be the block candidate
        self.assertEqual(ctrl.state, State.BLOCK_QUERY)
        candidates = ctrl.get_active_players()
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].is_ai)


class TestControllerThreePlayerMixed(unittest.TestCase):
    """Test controller with a mix of 2 humans and 1 AI."""

    def _setup_game(self):
        ctrl = GameController(seed=42)
        ctrl.handle_input("3")
        ctrl.handle_input("Alice")
        ctrl.handle_input("Claude")
        ctrl.handle_input("Bob")
        ctrl.game.players[1].is_ai = True
        return ctrl

    def test_three_player_setup(self):
        ctrl = self._setup_game()
        self.assertEqual(len(ctrl.game.players), 3)
        self.assertFalse(ctrl.game.players[0].is_ai)
        self.assertTrue(ctrl.game.players[1].is_ai)
        self.assertFalse(ctrl.game.players[2].is_ai)

    def test_simultaneous_challenge_with_mixed(self):
        ctrl = self._setup_game()
        # Player 0 claims Tax
        ctrl.handle_input("Tax", ctrl.game.players[0])
        self.assertEqual(ctrl.state, State.CHALLENGE_QUERY)
        # Both AI and human should be candidates
        candidates = ctrl.get_active_players()
        self.assertEqual(len(candidates), 2)
        ai_candidates = [p for p in candidates if p.is_ai]
        human_candidates = [p for p in candidates if not p.is_ai]
        self.assertEqual(len(ai_candidates), 1)
        self.assertEqual(len(human_candidates), 1)


class TestGetCardOptions(unittest.TestCase):
    """Test the _get_card_options lazy loader."""

    def test_returns_list_with_random_first(self):
        from src.ui import _get_card_options
        options = _get_card_options()
        self.assertIsInstance(options, list)
        self.assertEqual(options[0], "Random")
        self.assertGreater(len(options), 1)

    def test_contains_all_card_types(self):
        from src.ui import _get_card_options
        options = _get_card_options()
        for card in ["Duke", "Assassin", "Captain", "Contessa", "Ambassador"]:
            self.assertIn(card, options)

    def test_returns_same_list_on_second_call(self):
        from src.ui import _get_card_options
        first = _get_card_options()
        second = _get_card_options()
        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
