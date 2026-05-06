"""Tests for AI_game.config — configuration loading and agent creation."""

import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock the openai module before importing config (openai is not installed in test env)
sys.modules.setdefault("openai", MagicMock())

from AI_game.config import get_available_agents, create_agents_from_config


class TestGetAvailableAgents(unittest.TestCase):
    def test_returns_agent_names(self):
        config = {"agents": {"Claude": "model-a", "Gemini": "model-b"}}
        self.assertEqual(get_available_agents(config), ["Claude", "Gemini"])

    def test_empty_agents(self):
        config = {"agents": {}}
        self.assertEqual(get_available_agents(config), [])

    def test_missing_agents_key(self):
        config = {}
        self.assertEqual(get_available_agents(config), [])


class TestCreateAgentsFromConfig(unittest.TestCase):
    def setUp(self):
        self.config = {
            "api_key": "test-key",
            "agents": {
                "Claude": "anthropic/claude-sonnet",
                "Gemini": "google/gemini-flash",
            },
        }

    def test_single_of_each(self):
        agents = create_agents_from_config(self.config, ["Claude", "Gemini"])
        self.assertEqual(len(agents), 2)
        self.assertEqual(agents[0].name, "Claude")
        self.assertEqual(agents[1].name, "Gemini")
        self.assertEqual(agents[0].model, "anthropic/claude-sonnet")
        self.assertEqual(agents[1].model, "google/gemini-flash")

    def test_numbered_suffixes_for_duplicates(self):
        agents = create_agents_from_config(
            self.config, ["Claude", "Claude", "Claude"]
        )
        self.assertEqual(len(agents), 3)
        self.assertEqual(agents[0].name, "Claude")
        self.assertEqual(agents[1].name, "Claude 2")
        self.assertEqual(agents[2].name, "Claude 3")

    def test_mixed_duplicates(self):
        agents = create_agents_from_config(
            self.config, ["Claude", "Gemini", "Claude"]
        )
        self.assertEqual(agents[0].name, "Claude")
        self.assertEqual(agents[1].name, "Gemini")
        self.assertEqual(agents[2].name, "Claude 2")

    def test_unknown_agent_raises(self):
        with self.assertRaises(ValueError):
            create_agents_from_config(self.config, ["Unknown"])

    def test_all_agents_have_correct_api_key(self):
        agents = create_agents_from_config(self.config, ["Claude", "Gemini"])
        for agent in agents:
            self.assertEqual(agent.api_key, "test-key")


if __name__ == "__main__":
    unittest.main()
