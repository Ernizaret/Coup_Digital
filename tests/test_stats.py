"""Tests for AI_game.stats — win rate tracking and CSV persistence."""

import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from AI_game.stats import (
    _make_key, _load_stats, _save_stats, record_game, FIELDNAMES,
)


class FakeAgent:
    """Minimal agent stub for testing record_game."""

    def __init__(self, model, prompt_tokens=0, completion_tokens=0,
                 cached_tokens=0, query_count=0):
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cached_tokens = cached_tokens
        self.query_count = query_count


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
                FakeAgent("model-a", prompt_tokens=100, completion_tokens=50, query_count=5),
                FakeAgent("model-b", prompt_tokens=200, completion_tokens=100, query_count=8),
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
                FakeAgent("model-a", prompt_tokens=10, completion_tokens=5, query_count=2),
                FakeAgent("model-b", prompt_tokens=20, completion_tokens=10, query_count=3),
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
                FakeAgent("model-a", prompt_tokens=10, completion_tokens=5, query_count=2),
                FakeAgent("model-b", prompt_tokens=20, completion_tokens=10, query_count=3),
            ]
            with patch("AI_game.stats.STATS_FILE", path), \
                 patch("AI_game.stats.GAME_LOG_FILE", log_path):
                record_game(agents, "model-a", history_depth=3)
                # Reset token counts for second game with different depth
                agents[0].prompt_tokens = 10
                agents[0].completion_tokens = 5
                agents[0].query_count = 2
                agents[1].prompt_tokens = 20
                agents[1].completion_tokens = 10
                agents[1].query_count = 3
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


if __name__ == "__main__":
    unittest.main()
