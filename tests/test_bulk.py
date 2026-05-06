"""Tests for AI_game.bulk — bulk runner argument parsing and agent resolution."""

import sys
import unittest
from unittest.mock import MagicMock

# Mock the openai module before importing bulk
sys.modules.setdefault("openai", MagicMock())

from AI_game.bulk import _resolve_agent_names


class TestResolveAgentNames(unittest.TestCase):
    def setUp(self):
        self.config = {
            "api_key": "test-key",
            "agents": {
                "Claude": "anthropic/claude-sonnet",
                "Gemini": "google/gemini-flash",
                "ChatGPT": "openai/gpt-4o",
            },
        }

    def test_explicit_agents(self):
        names = _resolve_agent_names(self.config, "Claude,Gemini")
        self.assertEqual(names, ["Claude", "Gemini"])

    def test_explicit_with_spaces(self):
        names = _resolve_agent_names(self.config, "Claude , Gemini , ChatGPT")
        self.assertEqual(names, ["Claude", "Gemini", "ChatGPT"])

    def test_duplicates_allowed(self):
        names = _resolve_agent_names(self.config, "Claude,Claude,Gemini")
        self.assertEqual(names, ["Claude", "Claude", "Gemini"])

    def test_none_returns_all(self):
        names = _resolve_agent_names(self.config, None)
        self.assertEqual(names, ["Claude", "Gemini", "ChatGPT"])

    def test_unknown_agent_raises(self):
        with self.assertRaises(ValueError):
            _resolve_agent_names(self.config, "Unknown,Claude")


if __name__ == "__main__":
    unittest.main()
