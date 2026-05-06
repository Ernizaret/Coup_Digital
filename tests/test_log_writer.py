"""Tests for AI_game.log_writer — markdown transcript generation."""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Mock the openai module before importing log_writer (transitive via game_runner)
sys.modules.setdefault("openai", MagicMock())

from AI_game.log_writer import LogWriter


class FakeAgent:
    """Minimal agent stub for log writer tests."""

    def __init__(self, name, model, thoughts=None):
        self.name = name
        self.model = model
        self.private_thoughts = thoughts or []
        self.prompt_tokens = 100
        self.completion_tokens = 50
        self.query_count = 5


class FakePlayer:
    def __init__(self, name):
        self.name = name

    def is_alive(self):
        return True


class FakeGame:
    def __init__(self, players):
        self.players = players


class FakeController:
    def __init__(self, players):
        self.game = FakeGame(players)


class TestLogWriterAccumulation(unittest.TestCase):
    """Test that LogWriter correctly accumulates game events."""

    def setUp(self):
        self.writer = LogWriter()
        self.agents = [
            FakeAgent("Alice", "model-a", thoughts=["I should bluff"]),
            FakeAgent("Bob", "model-b"),
        ]
        self.players = [FakePlayer("Alice"), FakePlayer("Bob")]
        self.controller = FakeController(self.players)

    def test_game_started_records_players(self):
        self.writer.game_started(self.controller, self.agents)
        self.assertEqual(len(self.writer._players), 2)
        self.assertEqual(self.writer._players[0], ("Alice", "model-a"))
        self.assertEqual(self.writer._players[1], ("Bob", "model-b"))

    def test_turn_start_records_line(self):
        self.writer.turn_start("Alice", 1)
        self.assertIn("### Turn 1 — Alice", self.writer._lines[-1])

    def test_agent_response_records_speech_and_action(self):
        self.writer.agent_response("Alice", "Hello!", "Income")
        self.assertIn('"Hello!"', self.writer._lines[-2])
        self.assertIn("**Action:** Income", self.writer._lines[-1])

    def test_game_event_records_text(self):
        self.writer.game_event("Alice takes 1 coin.")
        self.assertIn("[Event] Alice takes 1 coin.", self.writer._lines[-1])

    def test_game_over_stores_winner(self):
        self.writer.game_over("Alice")
        self.assertEqual(self.writer._winner, "Alice")


class TestLogWriterMarkdown(unittest.TestCase):
    """Test the generated markdown content."""

    def setUp(self):
        self.writer = LogWriter()
        self.agents = [
            FakeAgent("Alice", "model-a", thoughts=["Bluff early", "Go aggressive"]),
            FakeAgent("Bob", "model-b"),
        ]
        self.players = [FakePlayer("Alice"), FakePlayer("Bob")]
        self.controller = FakeController(self.players)

        # Simulate a short game
        self.writer.game_started(self.controller, self.agents)
        self.writer.turn_start("Alice", 1)
        self.writer.agent_response("Alice", "Starting calm.", "Income")
        self.writer.game_event("Alice takes 1 coin.")
        self.writer.turn_start("Bob", 2)
        self.writer.agent_response("Bob", "I am the Duke.", "Tax")
        self.writer.game_event("Bob claims Duke and takes 3 coins.")
        self.writer.game_over("Alice")
        self.writer.token_usage(self.agents)

    def test_markdown_contains_header(self):
        md = self.writer._build_markdown("Alice", self.agents)
        self.assertIn("# Coup — AI Game Transcript", md)
        self.assertIn("**Winner:** Alice", md)

    def test_markdown_contains_players(self):
        md = self.writer._build_markdown("Alice", self.agents)
        self.assertIn("Alice (model-a)", md)
        self.assertIn("Bob (model-b)", md)

    def test_markdown_contains_game_log(self):
        md = self.writer._build_markdown("Alice", self.agents)
        self.assertIn("## Game Log", md)
        self.assertIn("### Turn 1 — Alice", md)
        self.assertIn("### Turn 2 — Bob", md)
        self.assertIn('[Event] Alice takes 1 coin.', md)

    def test_markdown_contains_winner_thoughts(self):
        md = self.writer._build_markdown("Alice", self.agents)
        self.assertIn("## Winner's Private Thoughts — Alice", md)
        self.assertIn("Bluff early", md)
        self.assertIn("Go aggressive", md)

    def test_markdown_contains_token_usage(self):
        md = self.writer._build_markdown("Alice", self.agents)
        self.assertIn("## Token Usage", md)
        self.assertIn("**Alice**", md)

    def test_markdown_no_winner_thoughts_if_empty(self):
        # Bob has no thoughts
        md = self.writer._build_markdown("Bob", self.agents)
        self.assertNotIn("## Winner's Private Thoughts", md)


class TestLogWriterWrite(unittest.TestCase):
    """Test that write() creates a file in the correct location."""

    def test_write_creates_file(self):
        writer = LogWriter()
        agents = [
            FakeAgent("Alice", "model-a"),
            FakeAgent("Bob", "model-b"),
        ]
        players = [FakePlayer("Alice"), FakePlayer("Bob")]
        controller = FakeController(players)

        writer.game_started(controller, agents)
        writer.turn_start("Alice", 1)
        writer.agent_response("Alice", "hi", "Income")
        writer.game_event("Alice takes 1 coin.")
        writer.game_over("Alice")
        writer.token_usage(agents)

        # Write to a temp directory instead of the real logs dir
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("AI_game.log_writer.os.path.dirname", return_value=tmpdir):
                writer.write("Alice", agents)

            # Check a file was created in tmpdir/logs/
            logs_dir = os.path.join(tmpdir, "logs")
            self.assertTrue(os.path.isdir(logs_dir))
            files = os.listdir(logs_dir)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].startswith("game_"))
            self.assertTrue(files[0].endswith(".md"))

            # Verify content
            filepath = os.path.join(logs_dir, files[0])
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("# Coup — AI Game Transcript", content)
            self.assertIn("**Winner:** Alice", content)


if __name__ == "__main__":
    unittest.main()
