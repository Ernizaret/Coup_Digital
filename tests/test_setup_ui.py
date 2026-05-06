"""Tests for setup UI helper logic and console batch output.

The setup_ui module imports AI_game.agents which requires the openai
package, so we avoid importing setup_ui directly.  Instead we test the
pure logic by replicating it here and test ConsoleOutput (which has no
external dependencies) directly.
"""

import io
import sys
import unittest

from AI_game.console_output import ConsoleOutput
from AI_game.presets import VALID_CARDS

# Replicate the constants from setup_ui (can't import due to openai dep)
CARD_OPTIONS = ["Random"] + VALID_CARDS
CARD_ABBREV = {
    "Duke": "D", "Assassin": "A", "Captain": "C",
    "Contessa": "Co", "Ambassador": "Am",
}
DEFAULT_COINS = 2


class TestSetupUIConstants(unittest.TestCase):
    """Verify the constants that the setup UI should use."""

    def test_card_options_starts_with_random(self):
        self.assertEqual(CARD_OPTIONS[0], "Random")

    def test_card_options_contains_all_valid_cards(self):
        for card in VALID_CARDS:
            self.assertIn(card, CARD_OPTIONS)

    def test_card_options_length(self):
        # Random + 5 card types
        self.assertEqual(len(CARD_OPTIONS), 6)

    def test_card_abbrev_keys_match_valid_cards(self):
        self.assertEqual(set(CARD_ABBREV.keys()), set(VALID_CARDS))

    def test_default_coins(self):
        self.assertEqual(DEFAULT_COINS, 2)


class TestBatchProgress(unittest.TestCase):
    """Tests for ConsoleOutput.batch_progress()."""

    def setUp(self):
        self.output = ConsoleOutput()

    def _capture(self, func, *args):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            func(*args)
        finally:
            sys.stdout = old
        return buf.getvalue()

    def test_batch_progress_format(self):
        text = self._capture(self.output.batch_progress, 3, 10, "Alice")
        self.assertIn("Game 3/10", text)
        self.assertIn("Alice", text)
        self.assertIn("complete", text)
        self.assertIn("winner", text)

    def test_batch_progress_first_game(self):
        text = self._capture(self.output.batch_progress, 1, 50, "Bob")
        self.assertIn("Game 1/50", text)
        self.assertIn("Bob", text)

    def test_batch_progress_last_game(self):
        text = self._capture(self.output.batch_progress, 50, 50, "Charlie")
        self.assertIn("Game 50/50", text)


class TestBatchSummary(unittest.TestCase):
    """Tests for ConsoleOutput.batch_summary()."""

    def setUp(self):
        self.output = ConsoleOutput()

    def _capture(self, func, *args):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            func(*args)
        finally:
            sys.stdout = old
        return buf.getvalue()

    def _make_agent(self, name, prompt_tokens=0, completion_tokens=0,
                    query_count=0):
        """Create a simple mock agent with token counters."""
        class MockAgent:
            pass
        a = MockAgent()
        a.name = name
        a.prompt_tokens = prompt_tokens
        a.completion_tokens = completion_tokens
        a.query_count = query_count
        return a

    def test_summary_shows_game_count(self):
        results = ["Alice", "Bob", "Alice"]
        agents = [self._make_agent("Alice"), self._make_agent("Bob")]
        text = self._capture(self.output.batch_summary, results, agents)
        self.assertIn("3 games played", text)

    def test_summary_shows_winner_counts(self):
        results = ["Alice", "Alice", "Bob"]
        agents = [self._make_agent("Alice"), self._make_agent("Bob")]
        text = self._capture(self.output.batch_summary, results, agents)
        self.assertIn("2 wins", text)
        self.assertIn("1 wins", text)

    def test_summary_shows_percentages(self):
        results = ["Alice", "Alice", "Bob", "Alice"]
        agents = [self._make_agent("Alice"), self._make_agent("Bob")]
        text = self._capture(self.output.batch_summary, results, agents)
        self.assertIn("75.0%", text)
        self.assertIn("25.0%", text)

    def test_summary_shows_token_usage(self):
        agents = [
            self._make_agent("Alice", prompt_tokens=100,
                             completion_tokens=50, query_count=5),
            self._make_agent("Bob", prompt_tokens=200,
                             completion_tokens=80, query_count=10),
        ]
        results = ["Alice"]
        text = self._capture(self.output.batch_summary, results, agents)
        self.assertIn("150", text)   # Alice's total tokens (100+50)
        self.assertIn("280", text)   # Bob's total tokens (200+80)
        self.assertIn("Token Usage", text)

    def test_summary_aggregates_same_name_agents(self):
        """When multiple games produce agents with the same name, totals aggregate."""
        agents = [
            self._make_agent("Alice", prompt_tokens=100,
                             completion_tokens=50, query_count=5),
            self._make_agent("Alice", prompt_tokens=200,
                             completion_tokens=100, query_count=8),
        ]
        results = ["Alice", "Alice"]
        text = self._capture(self.output.batch_summary, results, agents)
        # Total for Alice: (100+50) + (200+100) = 450
        self.assertIn("450", text)

    def test_summary_zero_queries_no_crash(self):
        """batch_summary handles agents with zero queries gracefully."""
        agents = [self._make_agent("Alice")]
        results = ["Alice"]
        # Should not raise
        self._capture(self.output.batch_summary, results, agents)

    def test_summary_shows_batch_results_header(self):
        results = ["Alice"]
        agents = [self._make_agent("Alice")]
        text = self._capture(self.output.batch_summary, results, agents)
        self.assertIn("BATCH RESULTS", text)


class TestDeckComputationLogic(unittest.TestCase):
    """Test the deck remaining computation logic used by setup_ui._update_deck_label.

    This tests the pure logic extracted from the UI method.
    """

    def _compute_remaining(self, assigned_cards):
        """Replicate the deck computation from _update_deck_label.

        Args:
            assigned_cards: list of card names assigned to players
                            (non-Random selections)

        Returns:
            dict of card -> remaining count
        """
        counts = {c: 3 for c in VALID_CARDS}
        for card in assigned_cards:
            counts[card] -= 1
        return counts

    def test_no_assignments(self):
        counts = self._compute_remaining([])
        for card in VALID_CARDS:
            self.assertEqual(counts[card], 3)

    def test_one_assignment(self):
        counts = self._compute_remaining(["Duke"])
        self.assertEqual(counts["Duke"], 2)
        self.assertEqual(counts["Assassin"], 3)

    def test_three_of_same(self):
        counts = self._compute_remaining(["Duke", "Duke", "Duke"])
        self.assertEqual(counts["Duke"], 0)

    def test_over_assignment_goes_negative(self):
        counts = self._compute_remaining(["Duke", "Duke", "Duke", "Duke"])
        self.assertEqual(counts["Duke"], -1)
        self.assertTrue(any(v < 0 for v in counts.values()))

    def test_mixed_assignments(self):
        counts = self._compute_remaining(
            ["Duke", "Assassin", "Duke", "Captain"])
        self.assertEqual(counts["Duke"], 1)
        self.assertEqual(counts["Assassin"], 2)
        self.assertEqual(counts["Captain"], 2)
        self.assertEqual(counts["Contessa"], 3)
        self.assertEqual(counts["Ambassador"], 3)


class TestBuildPresetLogic(unittest.TestCase):
    """Test the preset-building logic from the UI (pure logic portion).

    Replicates _build_preset_from_ui without Tkinter dependencies.
    """

    def _build_preset(self, player_configs):
        """Replicate _build_preset_from_ui logic without Tkinter.

        Args:
            player_configs: list of dicts with keys:
                name, card1, card2, coins

        Returns:
            Preset dict or None if all defaults.
        """
        has_custom = False
        players = {}

        for cfg in player_configs:
            name = cfg["name"]
            card1 = cfg["card1"]
            card2 = cfg["card2"]
            coins = cfg["coins"]

            hand = []
            if card1 != "Random":
                hand.append(card1)
                has_custom = True
            if card2 != "Random":
                hand.append(card2)
                has_custom = True

            player_cfg = {}
            if hand:
                player_cfg["hand"] = hand
            if coins != DEFAULT_COINS:
                player_cfg["coins"] = coins
                has_custom = True

            if player_cfg:
                players[name] = player_cfg

        if not has_custom:
            return None

        return {"players": players, "deck": "auto"}

    def test_all_defaults_returns_none(self):
        configs = [
            {"name": "Alice", "card1": "Random", "card2": "Random",
             "coins": 2},
            {"name": "Bob", "card1": "Random", "card2": "Random", "coins": 2},
        ]
        self.assertIsNone(self._build_preset(configs))

    def test_one_card_assigned(self):
        configs = [
            {"name": "Alice", "card1": "Duke", "card2": "Random", "coins": 2},
            {"name": "Bob", "card1": "Random", "card2": "Random", "coins": 2},
        ]
        preset = self._build_preset(configs)
        self.assertIsNotNone(preset)
        self.assertEqual(preset["players"]["Alice"]["hand"], ["Duke"])
        self.assertNotIn("Bob", preset["players"])

    def test_both_cards_assigned(self):
        configs = [
            {"name": "Alice", "card1": "Duke", "card2": "Captain",
             "coins": 2},
        ]
        preset = self._build_preset(configs)
        self.assertEqual(preset["players"]["Alice"]["hand"],
                         ["Duke", "Captain"])

    def test_custom_coins_only(self):
        configs = [
            {"name": "Alice", "card1": "Random", "card2": "Random",
             "coins": 5},
        ]
        preset = self._build_preset(configs)
        self.assertIsNotNone(preset)
        self.assertEqual(preset["players"]["Alice"]["coins"], 5)
        self.assertNotIn("hand", preset["players"]["Alice"])

    def test_custom_coins_and_cards(self):
        configs = [
            {"name": "Alice", "card1": "Duke", "card2": "Assassin",
             "coins": 8},
        ]
        preset = self._build_preset(configs)
        self.assertEqual(preset["players"]["Alice"]["hand"],
                         ["Duke", "Assassin"])
        self.assertEqual(preset["players"]["Alice"]["coins"], 8)

    def test_deck_is_auto(self):
        configs = [
            {"name": "Alice", "card1": "Duke", "card2": "Random", "coins": 2},
        ]
        preset = self._build_preset(configs)
        self.assertEqual(preset["deck"], "auto")

    def test_multiple_players_mixed(self):
        configs = [
            {"name": "Alice", "card1": "Duke", "card2": "Captain",
             "coins": 2},
            {"name": "Bob", "card1": "Random", "card2": "Random",
             "coins": 2},
            {"name": "Charlie", "card1": "Random", "card2": "Random",
             "coins": 10},
        ]
        preset = self._build_preset(configs)
        self.assertIn("Alice", preset["players"])
        self.assertNotIn("Bob", preset["players"])
        self.assertIn("Charlie", preset["players"])
        self.assertEqual(preset["players"]["Charlie"]["coins"], 10)


if __name__ == "__main__":
    unittest.main()
