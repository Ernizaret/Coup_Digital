"""Tests for AI_game.log_writer — markdown transcript generation."""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

# Stub out openai before any AI_game imports (not installed in test env)
sys.modules.setdefault("openai", MagicMock())

from AI_game.log_writer import LogWriter


class _FakePlayer:
    """Minimal stand-in for a Player object."""

    def __init__(self, name):
        self.name = name


class _FakeGame:
    """Minimal stand-in for a Game (coup.py) object."""

    def __init__(self, names):
        self.players = [_FakePlayer(n) for n in names]


class _FakeController:
    """Minimal stand-in for a GameController."""

    def __init__(self, names):
        self.game = _FakeGame(names)


class _FakeAgent:
    """Minimal stand-in for an Agent instance."""

    def __init__(self, name, model):
        self.name = name
        self.model = model


class TestLogWriterAccumulation(unittest.TestCase):
    """Test that LogWriter accumulates lines correctly."""

    def setUp(self):
        self.lw = LogWriter()
        self.controller = _FakeController(["Alice", "Bob"])
        self.lw.game_started(self.controller)

    def test_game_started_records_players(self):
        self.assertEqual(self.lw._header_info["players"], ["Alice", "Bob"])

    def test_game_started_records_date(self):
        self.assertIn("-", self.lw._header_info["date"])  # YYYY-MM-DD

    def test_turn_start_adds_heading(self):
        self.lw.turn_start("Alice", 1)
        self.assertTrue(any("Turn 1" in l and "Alice" in l
                            for l in self.lw._lines))

    def test_agent_response_adds_speech_and_action(self):
        self.lw.agent_response("Alice", "Hello!", "Income")
        self.assertTrue(any('"Hello!"' in l for l in self.lw._lines))
        self.assertTrue(any("Income" in l for l in self.lw._lines))

    def test_agent_speech_adds_quote(self):
        self.lw.agent_speech("Bob", "I challenge!")
        self.assertTrue(any("I challenge!" in l for l in self.lw._lines))

    def test_game_event_adds_event_line(self):
        self.lw.game_event("Alice takes 1 coin.")
        self.assertTrue(any("[Event] Alice takes 1 coin." in l
                            for l in self.lw._lines))


class TestSetAgents(unittest.TestCase):
    """Test that set_agents enriches player names with model info."""

    def test_enriches_players_with_model(self):
        lw = LogWriter()
        ctrl = _FakeController(["Alice", "Bob"])
        lw.game_started(ctrl)
        agents = [
            _FakeAgent("Alice", "anthropic/claude"),
            _FakeAgent("Bob", "google/gemini"),
        ]
        lw.set_agents(agents)
        self.assertEqual(lw._header_info["players"], [
            "Alice (anthropic/claude)",
            "Bob (google/gemini)",
        ])


class TestGameOverWritesFile(unittest.TestCase):
    """Test that game_over produces a valid markdown file."""

    def test_writes_transcript_file(self):
        lw = LogWriter()
        ctrl = _FakeController(["Alice", "Bob"])
        lw.game_started(ctrl)
        agents = [
            _FakeAgent("Alice", "model-a"),
            _FakeAgent("Bob", "model-b"),
        ]
        lw.set_agents(agents)

        lw.turn_start("Alice", 1)
        lw.agent_response("Alice", "Let's go!", "Income")
        lw.game_event("Alice takes 1 coin.")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("AI_game.log_writer.LOGS_DIR", tmpdir):
                lw.game_over("Bob", winner_agent=agents[1])

            # Exactly one .md file should have been written
            files = [f for f in os.listdir(tmpdir) if f.endswith(".md")]
            self.assertEqual(len(files), 1)

            with open(os.path.join(tmpdir, files[0]),
                      encoding="utf-8") as f:
                content = f.read()

            # Check key sections
            self.assertIn("# Coup", content)
            self.assertIn("**Winner:** Bob", content)
            self.assertIn("## Game Log", content)
            self.assertIn("Turn 1", content)
            self.assertIn('"Let\'s go!"', content)
            self.assertIn("[Event] Alice takes 1 coin.", content)
            # Private thoughts feature has been removed
            self.assertNotIn("Private Thoughts", content)

    def test_no_thoughts_section(self):
        lw = LogWriter()
        ctrl = _FakeController(["Alice", "Bob"])
        lw.game_started(ctrl)

        winner = _FakeAgent("Alice", "model-a")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("AI_game.log_writer.LOGS_DIR", tmpdir):
                lw.game_over("Alice", winner_agent=winner)

            files = [f for f in os.listdir(tmpdir) if f.endswith(".md")]
            with open(os.path.join(tmpdir, files[0]),
                      encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("Private Thoughts", content)

    def test_game_over_without_agent(self):
        lw = LogWriter()
        ctrl = _FakeController(["Alice"])
        lw.game_started(ctrl)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("AI_game.log_writer.LOGS_DIR", tmpdir):
                lw.game_over("Alice", winner_agent=None)

            files = [f for f in os.listdir(tmpdir) if f.endswith(".md")]
            self.assertEqual(len(files), 1)
            with open(os.path.join(tmpdir, files[0]),
                      encoding="utf-8") as f:
                content = f.read()
            self.assertIn("**Winner:** Alice", content)
            self.assertNotIn("Private Thoughts", content)


if __name__ == "__main__":
    unittest.main()
