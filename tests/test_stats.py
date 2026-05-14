"""Tests for AI_game.stats — win rate tracking and CSV persistence."""

import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from AI_game.stats import (
    _make_key, _load_stats, _save_stats, record_game, FIELDNAMES,
    _compute_elo_updates, ELO_START, ELO_K,
)


class FakeAgent:
    """Minimal agent stub for testing record_game."""

    def __init__(self, name="?", model="model", prompt_tokens=0,
                 completion_tokens=0, cached_tokens=0, query_count=0,
                 history_depth=2, bluffs=0, bluffs_caught=0,
                 challenges_issued=0, challenges_correct=0,
                 rules_summary=False, strategy_guide=False):
        self.name = name
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cached_tokens = cached_tokens
        self.query_count = query_count
        self.history_depth = history_depth
        self.bluffs = bluffs
        self.bluffs_caught = bluffs_caught
        self.challenges_issued = challenges_issued
        self.challenges_correct = challenges_correct
        self.rules_summary = rules_summary
        self.strategy_guide = strategy_guide


class TestMakeKey(unittest.TestCase):
    def test_combines_model_depth_rules_strategy(self):
        self.assertEqual(_make_key("gpt-4", 3), "gpt-4|3|No|No")

    def test_different_depths_differ(self):
        self.assertNotEqual(
            _make_key("gpt-4", 3),
            _make_key("gpt-4", 5),
        )

    def test_rules_summary_in_key(self):
        self.assertEqual(
            _make_key("gpt-4", 3, rules_summary=True),
            "gpt-4|3|Yes|No",
        )

    def test_strategy_guide_in_key(self):
        self.assertEqual(
            _make_key("gpt-4", 3, strategy_guide=True),
            "gpt-4|3|No|Yes",
        )

    def test_both_rules_and_strategy_in_key(self):
        self.assertEqual(
            _make_key("gpt-4", 3, rules_summary=True, strategy_guide=True),
            "gpt-4|3|Yes|Yes",
        )

    def test_different_rules_differ(self):
        self.assertNotEqual(
            _make_key("gpt-4", 3, rules_summary=False),
            _make_key("gpt-4", 3, rules_summary=True),
        )

    def test_different_strategy_differ(self):
        self.assertNotEqual(
            _make_key("gpt-4", 3, strategy_guide=False),
            _make_key("gpt-4", 3, strategy_guide=True),
        )


class TestLoadSaveRoundTrip(unittest.TestCase):
    """Test CSV round-trip: save then load."""

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            os.remove(path)  # ensure it doesn't exist
            with patch("AI_game.stats.STATS_FILE", path):
                stats = _load_stats()
            self.assertEqual(stats, {})
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|3|No|No": {
                    "model": "model-a",
                    "history_depth": 3,
                    "rules": "No",
                    "strategy": "No",
                    "games_played": 10,
                    "games_won": 4,
                    "total_tokens": 5000,
                    "cached_tokens": 2000,
                    "total_queries": 50,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
                loaded = _load_stats()
            self.assertEqual(loaded["model-a|3|No|No"]["games_played"], 10)
            self.assertEqual(loaded["model-a|3|No|No"]["games_won"], 4)
            self.assertEqual(loaded["model-a|3|No|No"]["total_tokens"], 5000)
            self.assertEqual(loaded["model-a|3|No|No"]["cached_tokens"], 2000)
        finally:
            os.remove(path)

    def test_win_rate_calculated_on_save(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|3|No|No": {
                    "model": "model-a",
                    "history_depth": 3,
                    "rules": "No",
                    "strategy": "No",
                    "games_played": 10,
                    "games_won": 3,
                    "total_tokens": 0,
                    "cached_tokens": 0,
                    "total_queries": 0,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
            self.assertEqual(row["win_rate"], "0.3000")
        finally:
            os.remove(path)


class TestRecordGame(unittest.TestCase):
    """Test record_game updates stats correctly."""

    def test_records_new_game(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f2:
            log_path = f2.name
        try:
            os.remove(path)
            os.remove(log_path)
            agents = [
                FakeAgent(model="model-a", prompt_tokens=100,
                          completion_tokens=50, query_count=5,
                          history_depth=3),
                FakeAgent(model="model-b", prompt_tokens=200,
                          completion_tokens=100, query_count=8,
                          history_depth=3),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0])
                stats = _load_stats()

            self.assertEqual(stats["model-a|3|No|No"]["games_played"], 1)
            self.assertEqual(stats["model-a|3|No|No"]["games_won"], 1)
            self.assertEqual(stats["model-a|3|No|No"]["total_tokens"], 150)

            self.assertEqual(stats["model-b|3|No|No"]["games_played"], 1)
            self.assertEqual(stats["model-b|3|No|No"]["games_won"], 0)
            self.assertEqual(stats["model-b|3|No|No"]["total_tokens"], 300)
        finally:
            if os.path.exists(path):
                os.remove(path)
            if os.path.exists(log_path):
                os.remove(log_path)

    def test_accumulates_across_games(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f2:
            log_path = f2.name
        try:
            os.remove(path)
            os.remove(log_path)
            agents = [
                FakeAgent(model="model-a", prompt_tokens=10,
                          completion_tokens=5, query_count=2,
                          history_depth=5),
                FakeAgent(model="model-b", prompt_tokens=20,
                          completion_tokens=10, query_count=3,
                          history_depth=5),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0])
                # Reset token counts for second game
                agents[0].prompt_tokens = 10
                agents[0].completion_tokens = 5
                agents[0].query_count = 2
                agents[1].prompt_tokens = 20
                agents[1].completion_tokens = 10
                agents[1].query_count = 3
                record_game(agents, agents[1])
                stats = _load_stats()

            self.assertEqual(stats["model-a|5|No|No"]["games_played"], 2)
            self.assertEqual(stats["model-a|5|No|No"]["games_won"], 1)
            self.assertEqual(stats["model-b|5|No|No"]["games_played"], 2)
            self.assertEqual(stats["model-b|5|No|No"]["games_won"], 1)
        finally:
            if os.path.exists(path):
                os.remove(path)
            if os.path.exists(log_path):
                os.remove(log_path)

    def test_different_depths_separate_rows(self):
        """Two agents with same model but different history_depth get separate rows."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f2:
            log_path = f2.name
        try:
            os.remove(path)
            os.remove(log_path)
            agents = [
                FakeAgent(model="model-a", prompt_tokens=10,
                          completion_tokens=5, query_count=2,
                          history_depth=3),
                FakeAgent(model="model-b", prompt_tokens=20,
                          completion_tokens=10, query_count=3,
                          history_depth=3),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0])
                # Reset token counts for second game with different depth
                agents[0].prompt_tokens = 10
                agents[0].completion_tokens = 5
                agents[0].query_count = 2
                agents[0].history_depth = 5
                agents[1].prompt_tokens = 20
                agents[1].completion_tokens = 10
                agents[1].query_count = 3
                agents[1].history_depth = 5
                record_game(agents, agents[1])
                stats = _load_stats()

            # Depth 3 row
            self.assertEqual(stats["model-a|3|No|No"]["games_played"], 1)
            self.assertEqual(stats["model-a|3|No|No"]["games_won"], 1)
            # Depth 5 row (separate)
            self.assertEqual(stats["model-a|5|No|No"]["games_played"], 1)
            self.assertEqual(stats["model-a|5|No|No"]["games_won"], 0)
        finally:
            if os.path.exists(path):
                os.remove(path)
            if os.path.exists(log_path):
                os.remove(log_path)


    def test_same_model_different_depths(self):
        """Four agents with same model but different depths: win goes to correct depth."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f2:
            log_path = f2.name
        try:
            os.remove(path)
            os.remove(log_path)
            agents = [
                FakeAgent(name="G1", model="gemini", history_depth=1),
                FakeAgent(name="G2", model="gemini", history_depth=2),
                FakeAgent(name="G3", model="gemini", history_depth=3),
                FakeAgent(name="G4", model="gemini", history_depth=4),
            ]
            # Agent with depth=3 wins
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[2])
                stats = _load_stats()

            # Each depth should have 1 game played
            for d in range(1, 5):
                self.assertEqual(stats[f"gemini|{d}|No|No"]["games_played"], 1)

            # Only depth=3 should have the win
            self.assertEqual(stats["gemini|1|No|No"]["games_won"], 0)
            self.assertEqual(stats["gemini|2|No|No"]["games_won"], 0)
            self.assertEqual(stats["gemini|3|No|No"]["games_won"], 1)
            self.assertEqual(stats["gemini|4|No|No"]["games_won"], 0)

            # Winner Elo should be highest
            self.assertGreater(
                stats["gemini|3|No|No"]["elo"], stats["gemini|1|No|No"]["elo"]
            )
        finally:
            if os.path.exists(path):
                os.remove(path)
            if os.path.exists(log_path):
                os.remove(log_path)


class TestComputeEloUpdates(unittest.TestCase):
    """Test the pairwise ELO calculation."""

    def test_two_player_equal_elo(self):
        """Equal ELO: winner gets +16, loser gets -16 (K=32, 2 players)."""
        stats = {
            "a|2|No|No": {"elo": 1500.0},
            "b|2|No|No": {"elo": 1500.0},
        }
        result = _compute_elo_updates(
            ["a|2|No|No", "b|2|No|No"], stats, "a|2|No|No")
        self.assertAlmostEqual(result["a|2|No|No"], 1516.0, places=1)
        self.assertAlmostEqual(result["b|2|No|No"], 1484.0, places=1)

    def test_elo_conservation(self):
        """Total ELO must be conserved (zero-sum)."""
        stats = {
            "a|2|No|No": {"elo": 1600.0},
            "b|2|No|No": {"elo": 1500.0},
            "c|2|No|No": {"elo": 1400.0},
        }
        keys = ["a|2|No|No", "b|2|No|No", "c|2|No|No"]
        total_before = sum(stats[k]["elo"] for k in keys)
        result = _compute_elo_updates(keys, stats, "c|2|No|No")
        total_after = sum(result[k] for k in keys)
        self.assertAlmostEqual(total_before, total_after, places=5)

    def test_underdog_wins_gains_more(self):
        """A lower-rated player winning should gain more than 16."""
        stats = {
            "a|2|No|No": {"elo": 1300.0},
            "b|2|No|No": {"elo": 1700.0},
        }
        result = _compute_elo_updates(
            ["a|2|No|No", "b|2|No|No"], stats, "a|2|No|No")
        gain = result["a|2|No|No"] - 1300.0
        self.assertGreater(gain, 16.0)


class TestEloRating(unittest.TestCase):
    """Integration tests for ELO in record_game."""

    def _make_temp_paths(self):
        """Create temp file paths for stats and game log."""
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

    def test_new_entries_start_at_1500(self):
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent(model="model-a", history_depth=2),
                FakeAgent(model="model-b", history_depth=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0])
                stats = _load_stats()
            # Both should have ELO near 1500 (winner slightly above, loser below)
            self.assertAlmostEqual(
                stats["model-a|2|No|No"]["elo"] + stats["model-b|2|No|No"]["elo"],
                3000.0, places=5,
            )
        finally:
            self._cleanup(path, log_path)

    def test_winner_elo_increases_loser_decreases(self):
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent(model="model-a", history_depth=2),
                FakeAgent(model="model-b", history_depth=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0])
                stats = _load_stats()
            self.assertGreater(stats["model-a|2|No|No"]["elo"], ELO_START)
            self.assertLess(stats["model-b|2|No|No"]["elo"], ELO_START)
        finally:
            self._cleanup(path, log_path)

    def test_four_player_pairwise(self):
        """In a 4-player game, losers only lose relative to winner, not each other."""
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent(model="model-a", history_depth=2),
                FakeAgent(model="model-b", history_depth=2),
                FakeAgent(model="model-c", history_depth=2),
                FakeAgent(model="model-d", history_depth=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0])
                stats = _load_stats()
            # Winner gains
            self.assertGreater(stats["model-a|2|No|No"]["elo"], ELO_START)
            # All losers have equal ELO change (they all drew against each other)
            loser_elos = [stats[f"model-{x}|2|No|No"]["elo"] for x in "bcd"]
            self.assertAlmostEqual(loser_elos[0], loser_elos[1], places=5)
            self.assertAlmostEqual(loser_elos[1], loser_elos[2], places=5)
            # Total approximately conserved (CSV rounds ELO to 1 decimal)
            total = stats["model-a|2|No|No"]["elo"] + sum(loser_elos)
            self.assertAlmostEqual(total, 4 * ELO_START, delta=0.5)
        finally:
            self._cleanup(path, log_path)

    def test_elo_persists_across_games(self):
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent(model="model-a", history_depth=2),
                FakeAgent(model="model-b", history_depth=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0])
                stats1 = _load_stats()
                elo_a_after_1 = stats1["model-a|2|No|No"]["elo"]
                # Second game, model-a wins again
                agents[0].prompt_tokens = 0
                agents[0].completion_tokens = 0
                agents[0].query_count = 0
                agents[1].prompt_tokens = 0
                agents[1].completion_tokens = 0
                agents[1].query_count = 0
                record_game(agents, agents[0])
                stats2 = _load_stats()
            # ELO should have continued from previous value, not reset
            self.assertGreater(stats2["model-a|2|No|No"]["elo"], elo_a_after_1)
        finally:
            self._cleanup(path, log_path)

    def test_legacy_rows_default_to_1500(self):
        """CSV rows without an elo column should default to 1500."""
        path, log_path = self._make_temp_paths()
        try:
            # Write a CSV without the elo column
            legacy_fields = [
                "model", "history_depth", "games_played", "games_won",
                "win_rate", "total_tokens", "cached_tokens",
                "total_queries", "avg_tokens_per_query",
            ]
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=legacy_fields)
                writer.writeheader()
                writer.writerow({
                    "model": "old-model", "history_depth": 2,
                    "games_played": 5, "games_won": 2,
                    "win_rate": "0.4000",
                    "total_tokens": 1000, "cached_tokens": 0,
                    "total_queries": 10, "avg_tokens_per_query": "100.0",
                })
            with patch("AI_game.stats.STATS_FILE", path):
                stats = _load_stats()
            self.assertAlmostEqual(
                stats["old-model|2|No|No"]["elo"], ELO_START)
        finally:
            self._cleanup(path, log_path)

    def test_legacy_rows_without_bluff_columns_default_to_zero(self):
        """CSV rows without bluff/challenge columns should default to 0."""
        path, log_path = self._make_temp_paths()
        try:
            # Write a CSV without the bluff/challenge columns
            legacy_fields = [
                "model", "history_depth", "games_played", "games_won",
                "win_rate", "elo", "total_tokens", "cached_tokens",
                "total_queries", "avg_tokens_per_query",
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
                })
            with patch("AI_game.stats.STATS_FILE", path):
                stats = _load_stats()
            self.assertEqual(stats["old-model|2|No|No"]["bluffs"], 0)
            self.assertEqual(stats["old-model|2|No|No"]["bluffs_caught"], 0)
            self.assertEqual(stats["old-model|2|No|No"]["challenges_issued"], 0)
            self.assertEqual(stats["old-model|2|No|No"]["challenges_correct"], 0)
        finally:
            self._cleanup(path, log_path)


class TestBluffChallengeStats(unittest.TestCase):
    """Tests for bluff and challenge statistics in stats CSV."""

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

    def test_bluff_success_rate_calculated_on_save(self):
        """bluff_success_rate = (bluffs - bluffs_caught) / bluffs."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|2|No|No": {
                    "model": "model-a", "history_depth": 2,
                    "rules": "No", "strategy": "No",
                    "games_played": 5, "games_won": 2,
                    "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
                    "bluffs": 10, "bluffs_caught": 3,
                    "challenges_issued": 0, "challenges_correct": 0,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
            # (10 - 3) / 10 = 0.7
            self.assertEqual(row["bluff_success_rate"], "0.7000")
        finally:
            os.remove(path)

    def test_bluff_success_rate_zero_when_no_bluffs(self):
        """bluff_success_rate should be 0.0 when bluffs == 0."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|2|No|No": {
                    "model": "model-a", "history_depth": 2,
                    "rules": "No", "strategy": "No",
                    "games_played": 5, "games_won": 2,
                    "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
                    "bluffs": 0, "bluffs_caught": 0,
                    "challenges_issued": 0, "challenges_correct": 0,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
            self.assertEqual(row["bluff_success_rate"], "0.0000")
        finally:
            os.remove(path)

    def test_challenge_success_rate_calculated_on_save(self):
        """challenge_success_rate = challenges_correct / challenges_issued."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|2|No|No": {
                    "model": "model-a", "history_depth": 2,
                    "rules": "No", "strategy": "No",
                    "games_played": 5, "games_won": 2,
                    "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
                    "bluffs": 0, "bluffs_caught": 0,
                    "challenges_issued": 8, "challenges_correct": 5,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
            # 5 / 8 = 0.625
            self.assertEqual(row["challenge_success_rate"], "0.6250")
        finally:
            os.remove(path)

    def test_challenge_success_rate_zero_when_none_issued(self):
        """challenge_success_rate should be 0.0 when challenges_issued == 0."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|2|No|No": {
                    "model": "model-a", "history_depth": 2,
                    "rules": "No", "strategy": "No",
                    "games_played": 5, "games_won": 2,
                    "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
                    "bluffs": 0, "bluffs_caught": 0,
                    "challenges_issued": 0, "challenges_correct": 0,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
            self.assertEqual(row["challenge_success_rate"], "0.0000")
        finally:
            os.remove(path)

    def test_bluff_stats_round_trip(self):
        """Bluff/challenge counters survive save then load."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|2|No|No": {
                    "model": "model-a", "history_depth": 2,
                    "rules": "No", "strategy": "No",
                    "games_played": 5, "games_won": 2,
                    "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
                    "bluffs": 12, "bluffs_caught": 4,
                    "challenges_issued": 7, "challenges_correct": 3,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
                loaded = _load_stats()
            self.assertEqual(loaded["model-a|2|No|No"]["bluffs"], 12)
            self.assertEqual(loaded["model-a|2|No|No"]["bluffs_caught"], 4)
            self.assertEqual(loaded["model-a|2|No|No"]["challenges_issued"], 7)
            self.assertEqual(loaded["model-a|2|No|No"]["challenges_correct"], 3)
        finally:
            os.remove(path)

    def test_record_game_accumulates_bluff_stats(self):
        """record_game should accumulate bluff/challenge counters across games."""
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent(model="model-a", history_depth=2,
                          bluffs=3, bluffs_caught=1,
                          challenges_issued=2, challenges_correct=1),
                FakeAgent(model="model-b", history_depth=2,
                          bluffs=1, bluffs_caught=0,
                          challenges_issued=4, challenges_correct=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0])

                # Simulate second game with new per-game counts
                agents[0].prompt_tokens = 0
                agents[0].completion_tokens = 0
                agents[0].query_count = 0
                agents[0].bluffs = 2
                agents[0].bluffs_caught = 2
                agents[0].challenges_issued = 1
                agents[0].challenges_correct = 0

                agents[1].prompt_tokens = 0
                agents[1].completion_tokens = 0
                agents[1].query_count = 0
                agents[1].bluffs = 0
                agents[1].bluffs_caught = 0
                agents[1].challenges_issued = 3
                agents[1].challenges_correct = 1

                record_game(agents, agents[1])
                stats = _load_stats()

            # model-a: 3+2=5 bluffs, 1+2=3 caught, 2+1=3 issued, 1+0=1 correct
            self.assertEqual(stats["model-a|2|No|No"]["bluffs"], 5)
            self.assertEqual(stats["model-a|2|No|No"]["bluffs_caught"], 3)
            self.assertEqual(stats["model-a|2|No|No"]["challenges_issued"], 3)
            self.assertEqual(stats["model-a|2|No|No"]["challenges_correct"], 1)

            # model-b: 1+0=1 bluffs, 0+0=0 caught, 4+3=7 issued, 2+1=3 correct
            self.assertEqual(stats["model-b|2|No|No"]["bluffs"], 1)
            self.assertEqual(stats["model-b|2|No|No"]["bluffs_caught"], 0)
            self.assertEqual(stats["model-b|2|No|No"]["challenges_issued"], 7)
            self.assertEqual(stats["model-b|2|No|No"]["challenges_correct"], 3)
        finally:
            self._cleanup(path, log_path)

    def test_new_columns_in_fieldnames(self):
        """Verify all bluff/challenge columns are in FIELDNAMES."""
        self.assertIn("bluffs", FIELDNAMES)
        self.assertIn("bluffs_caught", FIELDNAMES)
        self.assertIn("bluff_success_rate", FIELDNAMES)
        self.assertIn("challenges_issued", FIELDNAMES)
        self.assertIn("challenges_correct", FIELDNAMES)
        self.assertIn("challenge_success_rate", FIELDNAMES)


class TestRulesStrategyColumns(unittest.TestCase):
    """Verify rules and strategy columns appear in FIELDNAMES."""

    def test_rules_column_in_fieldnames(self):
        self.assertIn("rules", FIELDNAMES)

    def test_strategy_column_in_fieldnames(self):
        self.assertIn("strategy", FIELDNAMES)

    def test_rules_strategy_after_depth_before_games(self):
        """rules and strategy columns appear after history_depth, before games_played."""
        depth_idx = FIELDNAMES.index("history_depth")
        rules_idx = FIELDNAMES.index("rules")
        strategy_idx = FIELDNAMES.index("strategy")
        played_idx = FIELDNAMES.index("games_played")
        self.assertGreater(rules_idx, depth_idx)
        self.assertGreater(strategy_idx, depth_idx)
        self.assertLess(rules_idx, played_idx)
        self.assertLess(strategy_idx, played_idx)


class TestExpandedKeyLogic(unittest.TestCase):
    """Tests for rules_summary and strategy_guide in composite key."""

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

    def test_different_rules_produce_separate_rows(self):
        """Same model+depth but different rules_summary should produce separate rows."""
        path, log_path = self._make_temp_paths()
        try:
            agent_no_rules = FakeAgent(model="gpt-4", history_depth=2,
                                       rules_summary=False)
            agent_with_rules = FakeAgent(model="gpt-4", history_depth=2,
                                         rules_summary=True)
            agents_game1 = [agent_no_rules,
                            FakeAgent(model="other", history_depth=2)]
            agents_game2 = [agent_with_rules,
                            FakeAgent(model="other", history_depth=2)]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents_game1, agents_game1[0])
                record_game(agents_game2, agents_game2[0])
                stats = _load_stats()

            self.assertIn("gpt-4|2|No|No", stats)
            self.assertIn("gpt-4|2|Yes|No", stats)
            self.assertEqual(stats["gpt-4|2|No|No"]["games_played"], 1)
            self.assertEqual(stats["gpt-4|2|Yes|No"]["games_played"], 1)
        finally:
            self._cleanup(path, log_path)

    def test_different_strategy_produce_separate_rows(self):
        """Same model+depth but different strategy_guide should produce separate rows."""
        path, log_path = self._make_temp_paths()
        try:
            agent_no_strat = FakeAgent(model="gpt-4", history_depth=2,
                                       strategy_guide=False)
            agent_with_strat = FakeAgent(model="gpt-4", history_depth=2,
                                         strategy_guide=True)
            agents_game1 = [agent_no_strat,
                            FakeAgent(model="other", history_depth=2)]
            agents_game2 = [agent_with_strat,
                            FakeAgent(model="other", history_depth=2)]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents_game1, agents_game1[0])
                record_game(agents_game2, agents_game2[0])
                stats = _load_stats()

            self.assertIn("gpt-4|2|No|No", stats)
            self.assertIn("gpt-4|2|No|Yes", stats)
            self.assertEqual(stats["gpt-4|2|No|No"]["games_played"], 1)
            self.assertEqual(stats["gpt-4|2|No|Yes"]["games_played"], 1)
        finally:
            self._cleanup(path, log_path)

    def test_all_four_combos_separate_rows(self):
        """All four (rules, strategy) combos for same model+depth produce separate rows."""
        path, log_path = self._make_temp_paths()
        try:
            combos = [
                (False, False),
                (True, False),
                (False, True),
                (True, True),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                for rules, strategy in combos:
                    agents = [
                        FakeAgent(model="gpt-4", history_depth=2,
                                  rules_summary=rules, strategy_guide=strategy),
                        FakeAgent(model="other", history_depth=2),
                    ]
                    record_game(agents, agents[0])
                stats = _load_stats()

            self.assertIn("gpt-4|2|No|No", stats)
            self.assertIn("gpt-4|2|Yes|No", stats)
            self.assertIn("gpt-4|2|No|Yes", stats)
            self.assertIn("gpt-4|2|Yes|Yes", stats)
            for key in ["gpt-4|2|No|No", "gpt-4|2|Yes|No",
                         "gpt-4|2|No|Yes", "gpt-4|2|Yes|Yes"]:
                self.assertEqual(stats[key]["games_played"], 1)
                self.assertEqual(stats[key]["games_won"], 1)
        finally:
            self._cleanup(path, log_path)

    def test_rules_strategy_round_trip(self):
        """rules and strategy values survive save then load."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|2|Yes|Yes": {
                    "model": "model-a", "history_depth": 2,
                    "rules": "Yes", "strategy": "Yes",
                    "games_played": 5, "games_won": 2,
                    "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
                    "bluffs": 0, "bluffs_caught": 0,
                    "challenges_issued": 0, "challenges_correct": 0,
                    "card_guesses_total": 0, "card_guesses_correct": 0,
                },
            }
            with patch("AI_game.stats.STATS_FILE", path):
                _save_stats(stats)
                loaded = _load_stats()
            self.assertEqual(loaded["model-a|2|Yes|Yes"]["rules"], "Yes")
            self.assertEqual(loaded["model-a|2|Yes|Yes"]["strategy"], "Yes")
            self.assertEqual(loaded["model-a|2|Yes|Yes"]["games_played"], 5)
        finally:
            os.remove(path)

    def test_rules_strategy_in_csv_output(self):
        """Saved CSV should contain rules and strategy columns with Yes/No values."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|2|Yes|No": {
                    "model": "model-a", "history_depth": 2,
                    "rules": "Yes", "strategy": "No",
                    "games_played": 3, "games_won": 1,
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
            self.assertEqual(row["rules"], "Yes")
            self.assertEqual(row["strategy"], "No")
        finally:
            os.remove(path)

    def test_game_log_records_winner_rules_and_strategy(self):
        """game_log.csv should include rules and strategy in player identity."""
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent(model="model-a", history_depth=2,
                          rules_summary=True, strategy_guide=True),
                FakeAgent(model="model-b", history_depth=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0], seed=42)
            with open(log_path, newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
            self.assertIn("rules=Yes", row["Player 1"])
            self.assertIn("strategy=Yes", row["Player 1"])
            self.assertIn("rules=No", row["Player 2"])
            self.assertIn("strategy=No", row["Player 2"])
        finally:
            self._cleanup(path, log_path)

    def test_game_log_records_no_rules_no_strategy(self):
        """game_log.csv should record No when rules/strategy are disabled."""
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent(model="model-a", history_depth=2,
                          rules_summary=False, strategy_guide=False),
                FakeAgent(model="model-b", history_depth=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0], seed=99)
            with open(log_path, newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
            self.assertIn("rules=No", row["Player 1"])
            self.assertIn("strategy=No", row["Player 1"])
        finally:
            self._cleanup(path, log_path)

    def test_agent_without_rules_strategy_defaults_to_false(self):
        """Agents missing rules_summary/strategy_guide attrs default to No."""
        path, log_path = self._make_temp_paths()
        try:
            # Create agent without rules_summary/strategy_guide attributes
            agent = FakeAgent(model="model-a", history_depth=2)
            del agent.rules_summary
            del agent.strategy_guide
            agents = [agent, FakeAgent(model="model-b", history_depth=2)]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, agents[0])
                stats = _load_stats()
            # Should default to No|No
            self.assertIn("model-a|2|No|No", stats)
            self.assertEqual(stats["model-a|2|No|No"]["rules"], "No")
            self.assertEqual(stats["model-a|2|No|No"]["strategy"], "No")
        finally:
            self._cleanup(path, log_path)


if __name__ == "__main__":
    unittest.main()
