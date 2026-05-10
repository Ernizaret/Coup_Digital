"""Tests for CSV-based bulk game configuration parsing (AI_game.bulk._parse_csv)."""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

# Mock the openai module before importing bulk (openai is not installed in test env)
sys.modules.setdefault("openai", MagicMock())

from AI_game.bulk import _parse_csv


# A minimal config dict mimicking ai_config.json structure
SAMPLE_CONFIG = {
    "api_key": "test-key",
    "agents": {
        "Claude": "anthropic/claude-opus-4.6-fast",
        "Gemini": "google/gemini-2.0-flash-001",
        "ChatGPT": "openai/gpt-4o",
    },
}


def _write_csv(path, lines):
    """Write CSV lines (list of strings) to a file."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")


class TestParseCsvModelColumns(unittest.TestCase):
    """Test _parse_csv with 'Player N Model' column naming (model identifiers)."""

    def test_basic_two_player_game(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy",
                "1,12345,2,"
                "anthropic/claude-opus-4.6-fast,5,1,0,"
                "openai/gpt-4o,3,0,1",
            ])
            games = _parse_csv(path, SAMPLE_CONFIG)

        self.assertEqual(len(games), 1)
        g = games[0]
        self.assertEqual(g["game_num"], 1)
        self.assertEqual(g["seed"], 12345)
        self.assertEqual(g["survey_interval"], 2)
        self.assertEqual(len(g["players"]), 2)

        p1 = g["players"][0]
        self.assertEqual(p1["name"], "Claude")
        self.assertEqual(p1["model"], "anthropic/claude-opus-4.6-fast")
        self.assertEqual(p1["history_depth"], 5)
        self.assertTrue(p1["rules_summary"])
        self.assertFalse(p1["strategy_guide"])

        p2 = g["players"][1]
        self.assertEqual(p2["name"], "ChatGPT")
        self.assertEqual(p2["model"], "openai/gpt-4o")
        self.assertEqual(p2["history_depth"], 3)
        self.assertFalse(p2["rules_summary"])
        self.assertTrue(p2["strategy_guide"])

    def test_multiple_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy",
                "1,100,,"
                "anthropic/claude-opus-4.6-fast,2,0,0,"
                "openai/gpt-4o,2,0,0",
                "2,200,,"
                "google/gemini-2.0-flash-001,4,1,1,"
                "anthropic/claude-opus-4.6-fast,6,0,0",
            ])
            games = _parse_csv(path, SAMPLE_CONFIG)

        self.assertEqual(len(games), 2)
        self.assertEqual(games[0]["game_num"], 1)
        self.assertEqual(games[0]["seed"], 100)
        self.assertEqual(games[1]["game_num"], 2)
        self.assertEqual(games[1]["seed"], 200)

    def test_empty_seed_becomes_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy",
                "1,,,"
                "anthropic/claude-opus-4.6-fast,2,0,0,"
                "openai/gpt-4o,2,0,0",
            ])
            games = _parse_csv(path, SAMPLE_CONFIG)

        self.assertIsNone(games[0]["seed"])

    def test_empty_survey_interval_becomes_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy",
                "1,42,,"
                "anthropic/claude-opus-4.6-fast,2,0,0,"
                "openai/gpt-4o,2,0,0",
            ])
            games = _parse_csv(path, SAMPLE_CONFIG)

        self.assertIsNone(games[0]["survey_interval"])

    def test_duplicate_models_auto_numbered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy,"
                "Player 3 Model,Player 3 History,Player 3 Rules,Player 3 Strategy",
                "1,99,,"
                "anthropic/claude-opus-4.6-fast,2,0,0,"
                "anthropic/claude-opus-4.6-fast,3,0,0,"
                "openai/gpt-4o,2,0,0",
            ])
            games = _parse_csv(path, SAMPLE_CONFIG)

        names = [p["name"] for p in games[0]["players"]]
        self.assertEqual(names, ["Claude", "Claude 2", "ChatGPT"])

    def test_display_name_in_model_column_accepted(self):
        """Model column can also contain display names like 'Claude'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy",
                "1,42,,"
                "Claude,2,0,0,"
                "ChatGPT,2,0,0",
            ])
            games = _parse_csv(path, SAMPLE_CONFIG)

        self.assertEqual(games[0]["players"][0]["name"], "Claude")
        self.assertEqual(games[0]["players"][0]["model"],
                         "anthropic/claude-opus-4.6-fast")

    def test_default_history_depth_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy",
                "1,42,,"
                "anthropic/claude-opus-4.6-fast,,0,0,"
                "openai/gpt-4o,,0,0",
            ])
            games = _parse_csv(path, SAMPLE_CONFIG)

        self.assertEqual(games[0]["players"][0]["history_depth"], 2)
        self.assertEqual(games[0]["players"][1]["history_depth"], 2)


class TestParseCsvNameColumns(unittest.TestCase):
    """Test _parse_csv with 'Player N Name' column naming (display names)."""

    def test_name_columns_resolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Name,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Name,Player 2 History,Player 2 Rules,Player 2 Strategy",
                "1,42,3,"
                "Claude,5,1,0,"
                "Gemini,3,0,1",
            ])
            games = _parse_csv(path, SAMPLE_CONFIG)

        self.assertEqual(len(games), 1)
        p1 = games[0]["players"][0]
        self.assertEqual(p1["name"], "Claude")
        self.assertEqual(p1["model"], "anthropic/claude-opus-4.6-fast")
        p2 = games[0]["players"][1]
        self.assertEqual(p2["name"], "Gemini")
        self.assertEqual(p2["model"], "google/gemini-2.0-flash-001")


class TestParseCsvValidation(unittest.TestCase):
    """Test _parse_csv validation and error handling."""

    def test_file_not_found_exits(self):
        with self.assertRaises(SystemExit):
            _parse_csv("/nonexistent/path/games.csv", SAMPLE_CONFIG)

    def test_empty_csv_exits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy",
            ])
            with self.assertRaises(SystemExit):
                _parse_csv(path, SAMPLE_CONFIG)

    def test_unknown_model_exits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy",
                "1,42,,"
                "unknown/model-xyz,2,0,0,"
                "openai/gpt-4o,2,0,0",
            ])
            with self.assertRaises(SystemExit):
                _parse_csv(path, SAMPLE_CONFIG)

    def test_unknown_name_exits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Name,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Name,Player 2 History,Player 2 Rules,Player 2 Strategy",
                "1,42,,"
                "UnknownBot,2,0,0,"
                "Claude,2,0,0",
            ])
            with self.assertRaises(SystemExit):
                _parse_csv(path, SAMPLE_CONFIG)

    def test_one_player_exits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy",
                "1,42,,"
                "anthropic/claude-opus-4.6-fast,2,0,0,"
                ",,,",
            ])
            with self.assertRaises(SystemExit):
                _parse_csv(path, SAMPLE_CONFIG)

    def test_game_num_fallback_to_row_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "games.csv")
            _write_csv(path, [
                "Game #,Seed,Survey Interval,"
                "Player 1 Model,Player 1 History,Player 1 Rules,Player 1 Strategy,"
                "Player 2 Model,Player 2 History,Player 2 Rules,Player 2 Strategy",
                ",42,,"
                "anthropic/claude-opus-4.6-fast,2,0,0,"
                "openai/gpt-4o,2,0,0",
            ])
            games = _parse_csv(path, SAMPLE_CONFIG)

        # Falls back to row index (1) when Game # is empty
        self.assertEqual(games[0]["game_num"], 1)


class TestParseCsvExampleFile(unittest.TestCase):
    """Test that the example CSV file in the repo parses correctly."""

    def test_example_csv_parses(self):
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "AI_game", "Input_games_example.csv",
        )
        if not os.path.exists(csv_path):
            self.skipTest("Example CSV not found")

        # The example uses models from the real config, so we need a
        # config that matches the models in the example file
        config = {
            "api_key": "test-key",
            "agents": {
                "ChatGPT": "openai/gpt-4o",
                "Claude": "anthropic/claude-opus-4.6-fast",
                "Gemini": "google/gemini-2.0-flash-001",
                "Grok": "x-ai/grok-4.3",
            },
        }
        games = _parse_csv(csv_path, config)

        self.assertEqual(len(games), 2)
        # Game 1 has 4 players
        self.assertEqual(len(games[0]["players"]), 4)
        self.assertEqual(games[0]["seed"], 2625633111)
        self.assertEqual(games[0]["survey_interval"], 2)
        # Game 2 has 4 players
        self.assertEqual(len(games[1]["players"]), 4)
        self.assertEqual(games[1]["seed"], 2608373111)
        self.assertEqual(games[1]["survey_interval"], 4)


if __name__ == "__main__":
    unittest.main()
