"""Tests for the periodic card-guess survey feature.

Covers:
- Multiset matching scoring logic (score_card_guesses)
- Survey response parsing (_parse_survey_response)
- Survey prompt building (build_survey_prompt_sections)
- Round tracking and survey triggering in GameRunner
- Stats CSV integration for card guess columns
"""

import csv
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from unittest.mock import MagicMock, patch

# Mock openai before importing any AI_game modules
sys.modules.setdefault("openai", MagicMock())

from AI_game.game_runner import (
    GameRunner,
    score_card_guesses,
    _parse_survey_response,
    DEFAULT_SURVEY_INTERVAL,
)
from AI_game.prompt_builder import (
    build_survey_prompt_sections,
    _survey_section,
    _survey_response_format,
    VALID_CARD_TYPES,
)
from AI_game.stats import (
    _load_stats, _save_stats, record_game, FIELDNAMES,
)
from src.controller import GameController, State


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeAgent:
    """Minimal agent stub for testing."""

    def __init__(self, name="Agent", model="test-model", history_depth=2):
        self.name = name
        self.model = model
        self.history_depth = history_depth
        self.rules_summary = False
        self.strategy_guide = False
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0
        self.query_count = 0
        self.bluffs = 0
        self.bluffs_caught = 0
        self.challenges_issued = 0
        self.challenges_correct = 0
        self.card_guesses_total = 0
        self.card_guesses_correct = 0
        self._survey_response = '{}'

    def query_structured(self, prompt_sections):
        return '{"action": "Income", "speech": ""}'

    def query_survey(self, prompt_sections):
        return self._survey_response


def _setup_game(num_players=2, names=None):
    """Create a GameController advanced to CHOOSE_ACTION state."""
    if names is None:
        names = ["Alice", "Bob", "Carol", "Dave"][:num_players]
    ctrl = GameController()
    ctrl.handle_input(str(num_players))
    for name in names:
        ctrl.handle_input(name)
    return ctrl


# ===========================================================================
# Score Card Guesses (multiset matching)
# ===========================================================================

class TestScoreCardGuesses(unittest.TestCase):
    """Test the multiset matching scoring function."""

    def test_exact_match_two_cards(self):
        """All guesses correct for a 2-card hand."""
        correct, total = score_card_guesses(
            ["Duke", "Captain"], ["Duke", "Captain"]
        )
        self.assertEqual(correct, 2)
        self.assertEqual(total, 2)

    def test_exact_match_one_card(self):
        """Single card hand, correct guess."""
        correct, total = score_card_guesses(["Duke"], ["Duke"])
        self.assertEqual(correct, 1)
        self.assertEqual(total, 1)

    def test_no_match(self):
        """No cards guessed correctly."""
        correct, total = score_card_guesses(
            ["Duke", "Assassin"], ["Captain", "Contessa"]
        )
        self.assertEqual(correct, 0)
        self.assertEqual(total, 2)

    def test_partial_match(self):
        """One card correct, one wrong."""
        correct, total = score_card_guesses(
            ["Duke", "Captain"], ["Duke", "Assassin"]
        )
        self.assertEqual(correct, 1)
        self.assertEqual(total, 2)

    def test_duplicate_actual_cards_exact(self):
        """Player holds two of the same card, guesser gets both right."""
        correct, total = score_card_guesses(
            ["Duke", "Duke"], ["Duke", "Duke"]
        )
        self.assertEqual(correct, 2)
        self.assertEqual(total, 2)

    def test_duplicate_actual_one_guessed(self):
        """Player holds {Duke, Duke}, guesser guesses {Duke, Captain} -> 1/2."""
        correct, total = score_card_guesses(
            ["Duke", "Captain"], ["Duke", "Duke"]
        )
        self.assertEqual(correct, 1)
        self.assertEqual(total, 2)

    def test_duplicate_guess_one_actual(self):
        """Player holds {Duke, Captain}, guesser guesses {Duke, Duke} -> 1/2."""
        correct, total = score_card_guesses(
            ["Duke", "Duke"], ["Duke", "Captain"]
        )
        self.assertEqual(correct, 1)
        self.assertEqual(total, 2)

    def test_order_irrelevant(self):
        """Order of guesses and actual cards shouldn't matter."""
        correct1, total1 = score_card_guesses(
            ["Captain", "Duke"], ["Duke", "Captain"]
        )
        correct2, total2 = score_card_guesses(
            ["Duke", "Captain"], ["Captain", "Duke"]
        )
        self.assertEqual(correct1, 2)
        self.assertEqual(correct2, 2)
        self.assertEqual(total1, total2)

    def test_empty_actual(self):
        """No actual cards (should not happen in practice but handle gracefully)."""
        correct, total = score_card_guesses(["Duke"], [])
        self.assertEqual(correct, 0)
        self.assertEqual(total, 0)

    def test_empty_guesses(self):
        """No guesses provided."""
        correct, total = score_card_guesses([], ["Duke", "Captain"])
        self.assertEqual(correct, 0)
        self.assertEqual(total, 2)

    def test_more_guesses_than_actual(self):
        """Extra guesses beyond actual card count don't inflate score."""
        correct, total = score_card_guesses(
            ["Duke", "Duke", "Captain"], ["Duke", "Captain"]
        )
        self.assertEqual(correct, 2)
        self.assertEqual(total, 2)

    def test_single_card_wrong(self):
        """Single card hand, wrong guess."""
        correct, total = score_card_guesses(["Assassin"], ["Duke"])
        self.assertEqual(correct, 0)
        self.assertEqual(total, 1)


# ===========================================================================
# Parse Survey Response
# ===========================================================================

class TestParseSurveyResponse(unittest.TestCase):
    """Test parsing of AI survey responses."""

    def test_valid_json_with_guesses_key(self):
        raw = json.dumps({
            "guesses": {
                "Alice": ["Duke", "Captain"],
                "Bob": ["Assassin"],
            }
        })
        result = _parse_survey_response(raw)
        self.assertEqual(result["Alice"], ["Duke", "Captain"])
        self.assertEqual(result["Bob"], ["Assassin"])

    def test_flat_dict_without_guesses_key(self):
        """Accept a flat dict (no 'guesses' wrapper)."""
        raw = json.dumps({
            "Alice": ["Duke", "Captain"],
            "Bob": ["Contessa"],
        })
        result = _parse_survey_response(raw)
        self.assertEqual(result["Alice"], ["Duke", "Captain"])
        self.assertEqual(result["Bob"], ["Contessa"])

    def test_invalid_card_names_filtered(self):
        """Card names not in VALID_CARD_TYPES should be filtered out."""
        raw = json.dumps({
            "guesses": {
                "Alice": ["Duke", "InvalidCard"],
            }
        })
        result = _parse_survey_response(raw)
        self.assertEqual(result["Alice"], ["Duke"])

    def test_invalid_json_returns_empty(self):
        result = _parse_survey_response("this is not json at all")
        self.assertEqual(result, {})

    def test_json_in_code_block(self):
        raw = '```json\n{"guesses": {"Alice": ["Duke"]}}\n```'
        result = _parse_survey_response(raw)
        self.assertEqual(result["Alice"], ["Duke"])

    def test_single_card_as_string(self):
        """Accept a single card name as a string instead of a list."""
        raw = json.dumps({"guesses": {"Alice": "Duke"}})
        result = _parse_survey_response(raw)
        self.assertEqual(result["Alice"], ["Duke"])

    def test_empty_guesses_dict(self):
        raw = json.dumps({"guesses": {}})
        result = _parse_survey_response(raw)
        self.assertEqual(result, {})

    def test_non_dict_guesses_value(self):
        """If 'guesses' value is not a dict, return empty."""
        raw = json.dumps({"guesses": "invalid"})
        result = _parse_survey_response(raw)
        self.assertEqual(result, {})


# ===========================================================================
# Survey Prompt Builder
# ===========================================================================

class TestSurveyPromptBuilder(unittest.TestCase):
    """Test building of survey prompts."""

    def setUp(self):
        self.ctrl = _setup_game(3, ["Alice", "Bob", "Carol"])
        self.player = self.ctrl.game.players[0]  # Alice
        self.event_log = []

    def test_returns_dict_with_required_keys(self):
        sections = build_survey_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        for key in ("identity", "rules_summary", "strategy_guide",
                     "game_log", "decision_prompt"):
            self.assertIn(key, sections)

    def test_decision_prompt_contains_survey(self):
        sections = build_survey_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertIn("SURVEY", sections["decision_prompt"])

    def test_decision_prompt_does_not_contain_decide(self):
        sections = build_survey_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertNotIn("DECIDE", sections["decision_prompt"])

    def test_decision_prompt_contains_state(self):
        sections = build_survey_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertIn("STATE:", sections["decision_prompt"])

    def test_survey_section_lists_opponents(self):
        result = _survey_section(self.ctrl, self.player)
        self.assertIn("Bob", result)
        self.assertIn("Carol", result)
        self.assertNotIn("Alice", result)

    def test_survey_section_shows_card_counts(self):
        result = _survey_section(self.ctrl, self.player)
        self.assertIn("2 hidden cards", result)

    def test_survey_section_single_card_player(self):
        """Player with 1 card should show '1 hidden card'."""
        bob = self.ctrl.game.players[1]
        bob.influence = ["Duke"]  # Only 1 card
        result = _survey_section(self.ctrl, self.player)
        self.assertIn("Bob (1 hidden card): guess 1 card", result)

    def test_survey_section_excludes_eliminated(self):
        """Eliminated players should not appear in the survey."""
        bob = self.ctrl.game.players[1]
        bob.influence = []  # Eliminated
        result = _survey_section(self.ctrl, self.player)
        self.assertNotIn("Bob", result)
        self.assertIn("Carol", result)

    def test_survey_section_lists_valid_cards(self):
        result = _survey_section(self.ctrl, self.player)
        for card in VALID_CARD_TYPES:
            self.assertIn(card, result)

    def test_survey_response_format_contains_json(self):
        result = _survey_response_format()
        self.assertIn("JSON", result)
        self.assertIn("guesses", result)

    def test_rules_summary_included_when_enabled(self):
        sections = build_survey_prompt_sections(
            self.ctrl, self.player, self.event_log, rules_summary=True
        )
        self.assertIn("Be conservative with your challenges", sections["rules_summary"])

    def test_rules_summary_empty_when_disabled(self):
        sections = build_survey_prompt_sections(
            self.ctrl, self.player, self.event_log, rules_summary=False
        )
        self.assertEqual(sections["rules_summary"], "")

    def test_strategy_guide_included_when_enabled(self):
        sections = build_survey_prompt_sections(
            self.ctrl, self.player, self.event_log, strategy_guide=True
        )
        self.assertIn("STRATEGY GUIDE", sections["strategy_guide"])


# ===========================================================================
# Round Tracking in GameRunner
# ===========================================================================

class TestRoundTracking(unittest.TestCase):
    """Test that GameRunner correctly tracks full rounds."""

    def test_initial_round_counter(self):
        agents = [FakeAgent("Alice"), FakeAgent("Bob")]
        runner = GameRunner(agents, quiet=True, log=False, survey_interval=0)
        runner._setup_game()
        self.assertEqual(runner._round_number, 0)
        self.assertEqual(runner._round_turn_count, 0)

    def test_survey_interval_default(self):
        agents = [FakeAgent("Alice"), FakeAgent("Bob")]
        runner = GameRunner(agents, quiet=True, log=False)
        self.assertEqual(runner.survey_interval, DEFAULT_SURVEY_INTERVAL)

    def test_survey_interval_custom(self):
        agents = [FakeAgent("Alice"), FakeAgent("Bob")]
        runner = GameRunner(agents, quiet=True, log=False, survey_interval=3)
        self.assertEqual(runner.survey_interval, 3)

    def test_survey_interval_zero_disables(self):
        agents = [FakeAgent("Alice"), FakeAgent("Bob")]
        runner = GameRunner(agents, quiet=True, log=False, survey_interval=0)
        self.assertEqual(runner.survey_interval, 0)

    def test_counters_reset_on_setup(self):
        agents = [FakeAgent("Alice"), FakeAgent("Bob")]
        agents[0].card_guesses_total = 10
        agents[0].card_guesses_correct = 5
        runner = GameRunner(agents, quiet=True, log=False, survey_interval=0)
        runner._setup_game()
        self.assertEqual(agents[0].card_guesses_total, 0)
        self.assertEqual(agents[0].card_guesses_correct, 0)


# ===========================================================================
# Survey Scoring Integration
# ===========================================================================

class TestSurveyScoringIntegration(unittest.TestCase):
    """Test the _run_survey method's scoring logic."""

    def test_run_survey_scores_correctly(self):
        """Verify _run_survey accumulates correct/total on agents."""
        agents = [FakeAgent("Alice"), FakeAgent("Bob")]
        runner = GameRunner(agents, quiet=True, log=False, survey_interval=0)
        runner._setup_game()

        ctrl = runner.controller
        alice_player = ctrl.game.players[0]
        bob_player = ctrl.game.players[1]

        # Set known hands
        alice_player.influence = ["Duke", "Captain"]
        bob_player.influence = ["Assassin", "Contessa"]

        agent_map = runner._build_agent_map()
        player_agents = runner._build_player_agent_map()

        # Alice guesses Bob has Assassin and Duke (1 correct out of 2)
        agents[0]._survey_response = json.dumps({
            "guesses": {"Bob": ["Assassin", "Duke"]}
        })
        # Bob guesses Alice has Duke and Captain (2 correct out of 2)
        agents[1]._survey_response = json.dumps({
            "guesses": {"Alice": ["Duke", "Captain"]}
        })

        runner._run_survey(agent_map, player_agents)

        # Alice: 1 correct out of 2
        self.assertEqual(agents[0].card_guesses_total, 2)
        self.assertEqual(agents[0].card_guesses_correct, 1)

        # Bob: 2 correct out of 2
        self.assertEqual(agents[1].card_guesses_total, 2)
        self.assertEqual(agents[1].card_guesses_correct, 2)

    def test_run_survey_missing_opponent_guess(self):
        """If an agent doesn't guess for an opponent, count as all wrong."""
        agents = [FakeAgent("Alice"), FakeAgent("Bob"), FakeAgent("Carol")]
        runner = GameRunner(agents, quiet=True, log=False, survey_interval=0)
        runner._setup_game()

        ctrl = runner.controller
        alice_player = ctrl.game.players[0]
        bob_player = ctrl.game.players[1]
        carol_player = ctrl.game.players[2]

        alice_player.influence = ["Duke", "Captain"]
        bob_player.influence = ["Assassin", "Contessa"]
        carol_player.influence = ["Ambassador", "Duke"]

        agent_map = runner._build_agent_map()
        player_agents = runner._build_player_agent_map()

        # Alice only guesses Bob, not Carol
        agents[0]._survey_response = json.dumps({
            "guesses": {"Bob": ["Assassin", "Contessa"]}
        })
        # Bob guesses both
        agents[1]._survey_response = json.dumps({
            "guesses": {
                "Alice": ["Duke", "Captain"],
                "Carol": ["Ambassador", "Duke"],
            }
        })
        # Carol guesses both
        agents[2]._survey_response = json.dumps({
            "guesses": {
                "Alice": ["Duke", "Assassin"],
                "Bob": ["Assassin", "Contessa"],
            }
        })

        runner._run_survey(agent_map, player_agents)

        # Alice: guessed Bob correctly (2/2) + missed Carol entirely (0/2)
        self.assertEqual(agents[0].card_guesses_total, 4)
        self.assertEqual(agents[0].card_guesses_correct, 2)

    def test_run_survey_api_failure_skips_agent(self):
        """If survey query raises an exception, that agent is skipped."""
        agents = [FakeAgent("Alice"), FakeAgent("Bob")]
        runner = GameRunner(agents, quiet=True, log=False, survey_interval=0)
        runner._setup_game()

        agent_map = runner._build_agent_map()
        player_agents = runner._build_player_agent_map()

        # Make Alice's survey raise an exception
        def raise_error(_):
            raise RuntimeError("API failure")
        agents[0].query_survey = raise_error

        # Bob returns valid guesses
        agents[1]._survey_response = json.dumps({
            "guesses": {"Alice": ["Duke", "Captain"]}
        })

        runner._run_survey(agent_map, player_agents)

        # Alice should have no survey data (skipped)
        self.assertEqual(agents[0].card_guesses_total, 0)
        self.assertEqual(agents[0].card_guesses_correct, 0)

        # Bob should have guesses recorded
        self.assertGreater(agents[1].card_guesses_total, 0)

    def test_run_survey_accumulates_across_surveys(self):
        """Verify stats accumulate when survey runs multiple times."""
        agents = [FakeAgent("Alice"), FakeAgent("Bob")]
        runner = GameRunner(agents, quiet=True, log=False, survey_interval=0)
        runner._setup_game()

        ctrl = runner.controller
        alice_player = ctrl.game.players[0]
        bob_player = ctrl.game.players[1]

        alice_player.influence = ["Duke", "Captain"]
        bob_player.influence = ["Assassin", "Contessa"]

        agent_map = runner._build_agent_map()
        player_agents = runner._build_player_agent_map()

        # First survey
        agents[0]._survey_response = json.dumps({
            "guesses": {"Bob": ["Assassin", "Duke"]}
        })
        agents[1]._survey_response = json.dumps({
            "guesses": {"Alice": ["Duke", "Captain"]}
        })
        runner._run_survey(agent_map, player_agents)

        # Second survey
        agents[0]._survey_response = json.dumps({
            "guesses": {"Bob": ["Assassin", "Contessa"]}
        })
        agents[1]._survey_response = json.dumps({
            "guesses": {"Alice": ["Assassin", "Contessa"]}
        })
        runner._run_survey(agent_map, player_agents)

        # Alice: survey 1 = 1/2, survey 2 = 2/2 => total 3/4
        self.assertEqual(agents[0].card_guesses_total, 4)
        self.assertEqual(agents[0].card_guesses_correct, 3)

        # Bob: survey 1 = 2/2, survey 2 = 0/2 => total 2/4
        self.assertEqual(agents[1].card_guesses_total, 4)
        self.assertEqual(agents[1].card_guesses_correct, 2)


# ===========================================================================
# Stats CSV Integration
# ===========================================================================

class TestCardGuessStatsCSV(unittest.TestCase):
    """Test that card guess stats are correctly persisted in the CSV."""

    def _make_temp_paths(self):
        f1 = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        f2 = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        path, log_path = f1.name, f2.name
        f1.close()
        f2.close()
        os.remove(path)
        os.remove(log_path)
        return path, log_path

    def _cleanup(self, *paths):
        for p in paths:
            if os.path.exists(p):
                os.remove(p)

    def test_new_columns_in_fieldnames(self):
        """Verify all 3 new columns are in FIELDNAMES."""
        self.assertIn("card_guesses_total", FIELDNAMES)
        self.assertIn("card_guesses_correct", FIELDNAMES)
        self.assertIn("card_guess_accuracy", FIELDNAMES)

    def test_card_guess_accuracy_calculated_on_save(self):
        """card_guess_accuracy = card_guesses_correct / card_guesses_total."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|2|No|No": {
                    "model": "model-a", "history_depth": 2,
                    "games_played": 5, "games_won": 2,
                    "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
                    "bluffs": 0, "bluffs_caught": 0,
                    "challenges_issued": 0, "challenges_correct": 0,
                    "card_guesses_total": 20, "card_guesses_correct": 15,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
            # 15 / 20 = 0.75
            self.assertEqual(row["card_guess_accuracy"], "0.7500")
        finally:
            os.remove(path)

    def test_card_guess_accuracy_zero_when_no_guesses(self):
        """card_guess_accuracy should be 0.0 when card_guesses_total == 0."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|2|No|No": {
                    "model": "model-a", "history_depth": 2,
                    "games_played": 5, "games_won": 2,
                    "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
                    "bluffs": 0, "bluffs_caught": 0,
                    "challenges_issued": 0, "challenges_correct": 0,
                    "card_guesses_total": 0, "card_guesses_correct": 0,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
            self.assertEqual(row["card_guess_accuracy"], "0.0000")
        finally:
            os.remove(path)

    def test_card_guess_stats_round_trip(self):
        """Card guess counters survive save then load."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|2|No|No": {
                    "model": "model-a", "history_depth": 2,
                    "games_played": 5, "games_won": 2,
                    "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
                    "bluffs": 0, "bluffs_caught": 0,
                    "challenges_issued": 0, "challenges_correct": 0,
                    "card_guesses_total": 30, "card_guesses_correct": 18,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
                loaded = _load_stats()
            self.assertEqual(loaded["model-a|2|No|No"]["card_guesses_total"], 30)
            self.assertEqual(loaded["model-a|2|No|No"]["card_guesses_correct"], 18)
        finally:
            os.remove(path)

    def test_record_game_accumulates_card_guess_stats(self):
        """record_game should accumulate card guess counters across games."""
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent(model="model-a", history_depth=2),
                FakeAgent(model="model-b", history_depth=2),
            ]
            agents[0].card_guesses_total = 10
            agents[0].card_guesses_correct = 7
            agents[1].card_guesses_total = 10
            agents[1].card_guesses_correct = 5

            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0])

                # Second game
                agents[0].prompt_tokens = 0
                agents[0].completion_tokens = 0
                agents[0].query_count = 0
                agents[0].card_guesses_total = 8
                agents[0].card_guesses_correct = 6
                agents[1].prompt_tokens = 0
                agents[1].completion_tokens = 0
                agents[1].query_count = 0
                agents[1].card_guesses_total = 8
                agents[1].card_guesses_correct = 3

                record_game(agents, agents[1])
                stats = _load_stats()

            # model-a: 10+8=18 total, 7+6=13 correct
            self.assertEqual(stats["model-a|2|No|No"]["card_guesses_total"], 18)
            self.assertEqual(stats["model-a|2|No|No"]["card_guesses_correct"], 13)

            # model-b: 10+8=18 total, 5+3=8 correct
            self.assertEqual(stats["model-b|2|No|No"]["card_guesses_total"], 18)
            self.assertEqual(stats["model-b|2|No|No"]["card_guesses_correct"], 8)
        finally:
            self._cleanup(path, log_path)

    def test_legacy_rows_without_card_guess_columns_default_to_zero(self):
        """CSV rows without card_guess columns should default to 0."""
        path, log_path = self._make_temp_paths()
        try:
            legacy_fields = [
                "model", "history_depth", "games_played", "games_won",
                "win_rate", "elo", "total_tokens", "cached_tokens",
                "total_queries", "avg_tokens_per_query",
                "bluffs", "bluffs_caught", "bluff_success_rate",
                "challenges_issued", "challenges_correct",
                "challenge_success_rate",
            ]
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=legacy_fields)
                writer.writeheader()
                writer.writerow({
                    "model": "old-model", "history_depth": 2,
                    "games_played": 5, "games_won": 2,
                    "win_rate": "0.4000", "elo": "1500.0",
                    "total_tokens": 1000, "cached_tokens": 0,
                    "total_queries": 10, "avg_tokens_per_query": "100.0",
                    "bluffs": 0, "bluffs_caught": 0,
                    "bluff_success_rate": "0.0000",
                    "challenges_issued": 0, "challenges_correct": 0,
                    "challenge_success_rate": "0.0000",
                })
            with patch("AI_game.stats.STATS_FILE", path):
                stats = _load_stats()
            self.assertEqual(stats["old-model|2|No|No"]["card_guesses_total"], 0)
            self.assertEqual(stats["old-model|2|No|No"]["card_guesses_correct"], 0)
        finally:
            self._cleanup(path, log_path)


if __name__ == "__main__":
    unittest.main()
