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

    def __init__(self, model, prompt_tokens=0, completion_tokens=0,
                 cached_tokens=0, query_count=0, history_depth=2):
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cached_tokens = cached_tokens
        self.query_count = query_count
        self.history_depth = history_depth


class TestMakeKey(unittest.TestCase):
    def test_combines_model_and_depth(self):
        self.assertEqual(_make_key("gpt-4", 3), "gpt-4|3")

    def test_different_depths_differ(self):
        self.assertNotEqual(
            _make_key("gpt-4", 3),
            _make_key("gpt-4", 5),
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
                "model-a|3": {
                    "model": "model-a",
                    "history_depth": 3,
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
            self.assertEqual(loaded["model-a|3"]["games_played"], 10)
            self.assertEqual(loaded["model-a|3"]["games_won"], 4)
            self.assertEqual(loaded["model-a|3"]["total_tokens"], 5000)
            self.assertEqual(loaded["model-a|3"]["cached_tokens"], 2000)
        finally:
            os.remove(path)

    def test_win_rate_calculated_on_save(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            stats = {
                "model-a|3": {
                    "model": "model-a",
                    "history_depth": 3,
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
                FakeAgent("model-a", prompt_tokens=100, completion_tokens=50,
                          query_count=5, history_depth=3),
                FakeAgent("model-b", prompt_tokens=200, completion_tokens=100,
                          query_count=8, history_depth=3),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, "model-a", history_depth=3)
                stats = _load_stats()

            self.assertEqual(stats["model-a|3"]["games_played"], 1)
            self.assertEqual(stats["model-a|3"]["games_won"], 1)
            self.assertEqual(stats["model-a|3"]["total_tokens"], 150)

            self.assertEqual(stats["model-b|3"]["games_played"], 1)
            self.assertEqual(stats["model-b|3"]["games_won"], 0)
            self.assertEqual(stats["model-b|3"]["total_tokens"], 300)
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
                FakeAgent("model-a", prompt_tokens=10, completion_tokens=5,
                          query_count=2, history_depth=5),
                FakeAgent("model-b", prompt_tokens=20, completion_tokens=10,
                          query_count=3, history_depth=5),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, "model-a", history_depth=5)
                # Reset token counts for second game
                agents[0].prompt_tokens = 10
                agents[0].completion_tokens = 5
                agents[0].query_count = 2
                agents[1].prompt_tokens = 20
                agents[1].completion_tokens = 10
                agents[1].query_count = 3
                record_game(agents, "model-b", history_depth=5)
                stats = _load_stats()

            self.assertEqual(stats["model-a|5"]["games_played"], 2)
            self.assertEqual(stats["model-a|5"]["games_won"], 1)
            self.assertEqual(stats["model-b|5"]["games_played"], 2)
            self.assertEqual(stats["model-b|5"]["games_won"], 1)
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
                FakeAgent("model-a", prompt_tokens=10, completion_tokens=5,
                          query_count=2, history_depth=3),
                FakeAgent("model-b", prompt_tokens=20, completion_tokens=10,
                          query_count=3, history_depth=3),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, "model-a", history_depth=3)
                # Reset token counts for second game with different depth
                agents[0].prompt_tokens = 10
                agents[0].completion_tokens = 5
                agents[0].query_count = 2
                agents[0].history_depth = 5
                agents[1].prompt_tokens = 20
                agents[1].completion_tokens = 10
                agents[1].query_count = 3
                agents[1].history_depth = 5
                record_game(agents, "model-b", history_depth=5)
                stats = _load_stats()

            # Depth 3 row
            self.assertEqual(stats["model-a|3"]["games_played"], 1)
            self.assertEqual(stats["model-a|3"]["games_won"], 1)
            # Depth 5 row (separate)
            self.assertEqual(stats["model-a|5"]["games_played"], 1)
            self.assertEqual(stats["model-a|5"]["games_won"], 0)
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
            "a|2": {"elo": 1500.0},
            "b|2": {"elo": 1500.0},
        }
        result = _compute_elo_updates(["a|2", "b|2"], stats, "a|2")
        self.assertAlmostEqual(result["a|2"], 1516.0, places=1)
        self.assertAlmostEqual(result["b|2"], 1484.0, places=1)

    def test_elo_conservation(self):
        """Total ELO must be conserved (zero-sum)."""
        stats = {
            "a|2": {"elo": 1600.0},
            "b|2": {"elo": 1500.0},
            "c|2": {"elo": 1400.0},
        }
        keys = ["a|2", "b|2", "c|2"]
        total_before = sum(stats[k]["elo"] for k in keys)
        result = _compute_elo_updates(keys, stats, "c|2")
        total_after = sum(result[k] for k in keys)
        self.assertAlmostEqual(total_before, total_after, places=5)

    def test_underdog_wins_gains_more(self):
        """A lower-rated player winning should gain more than 16."""
        stats = {
            "a|2": {"elo": 1300.0},
            "b|2": {"elo": 1700.0},
        }
        result = _compute_elo_updates(["a|2", "b|2"], stats, "a|2")
        gain = result["a|2"] - 1300.0
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
                FakeAgent("model-a", history_depth=2),
                FakeAgent("model-b", history_depth=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, "model-a")
                stats = _load_stats()
            # Both should have ELO near 1500 (winner slightly above, loser below)
            self.assertAlmostEqual(
                stats["model-a|2"]["elo"] + stats["model-b|2"]["elo"],
                3000.0, places=5,
            )
        finally:
            self._cleanup(path, log_path)

    def test_winner_elo_increases_loser_decreases(self):
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent("model-a", history_depth=2),
                FakeAgent("model-b", history_depth=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, "model-a")
                stats = _load_stats()
            self.assertGreater(stats["model-a|2"]["elo"], ELO_START)
            self.assertLess(stats["model-b|2"]["elo"], ELO_START)
        finally:
            self._cleanup(path, log_path)

    def test_four_player_pairwise(self):
        """In a 4-player game, losers only lose relative to winner, not each other."""
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent("model-a", history_depth=2),
                FakeAgent("model-b", history_depth=2),
                FakeAgent("model-c", history_depth=2),
                FakeAgent("model-d", history_depth=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, "model-a")
                stats = _load_stats()
            # Winner gains
            self.assertGreater(stats["model-a|2"]["elo"], ELO_START)
            # All losers have equal ELO change (they all drew against each other)
            loser_elos = [stats[f"model-{x}|2"]["elo"] for x in "bcd"]
            self.assertAlmostEqual(loser_elos[0], loser_elos[1], places=5)
            self.assertAlmostEqual(loser_elos[1], loser_elos[2], places=5)
            # Total approximately conserved (CSV rounds ELO to 1 decimal)
            total = stats["model-a|2"]["elo"] + sum(loser_elos)
            self.assertAlmostEqual(total, 4 * ELO_START, delta=0.5)
        finally:
            self._cleanup(path, log_path)

    def test_elo_persists_across_games(self):
        path, log_path = self._make_temp_paths()
        try:
            agents = [
                FakeAgent("model-a", history_depth=2),
                FakeAgent("model-b", history_depth=2),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, "model-a")
                stats1 = _load_stats()
                elo_a_after_1 = stats1["model-a|2"]["elo"]
                # Second game, model-a wins again
                agents[0].prompt_tokens = 0
                agents[0].completion_tokens = 0
                agents[0].query_count = 0
                agents[1].prompt_tokens = 0
                agents[1].completion_tokens = 0
                agents[1].query_count = 0
                record_game(agents, "model-a")
                stats2 = _load_stats()
            # ELO should have continued from previous value, not reset
            self.assertGreater(stats2["model-a|2"]["elo"], elo_a_after_1)
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
            self.assertAlmostEqual(stats["old-model|2"]["elo"], ELO_START)
        finally:
            self._cleanup(path, log_path)


if __name__ == "__main__":
    unittest.main()
