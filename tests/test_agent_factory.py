"""Tests for AI_game.agent_factory — shared agent creation helpers."""

import sys
import unittest
from unittest.mock import patch, MagicMock

# Stub out openai before any AI_game imports (not installed in test env)
sys.modules.setdefault("openai", MagicMock())

from AI_game.agent_factory import build_agent_names, create_agents_from_names


class TestBuildAgentNames(unittest.TestCase):
    """Test display-name numbering for duplicate providers."""

    def test_no_duplicates(self):
        self.assertEqual(
            build_agent_names(["Claude", "Gemini"]),
            ["Claude", "Gemini"],
        )

    def test_two_of_same(self):
        self.assertEqual(
            build_agent_names(["Claude", "Claude"]),
            ["Claude", "Claude 2"],
        )

    def test_three_of_same(self):
        self.assertEqual(
            build_agent_names(["Claude", "Claude", "Claude"]),
            ["Claude", "Claude 2", "Claude 3"],
        )

    def test_mixed_duplicates(self):
        self.assertEqual(
            build_agent_names(["Claude", "Gemini", "Claude", "Gemini"]),
            ["Claude", "Gemini", "Claude 2", "Gemini 2"],
        )

    def test_single_agent(self):
        self.assertEqual(build_agent_names(["Claude"]), ["Claude"])

    def test_empty_list(self):
        self.assertEqual(build_agent_names([]), [])


class TestCreateAgentsFromNames(unittest.TestCase):
    """Test create_agents_from_names with mocked create_agent."""

    def setUp(self):
        self.config = {
            "api_key": "test-key",
            "agents": {
                "Claude": "anthropic/claude-3.5-sonnet",
                "Gemini": "google/gemini-pro",
            },
        }

    @patch("AI_game.agent_factory.create_agent")
    @patch("AI_game.agent_factory.get_available_agents",
           return_value=["Claude", "Gemini"])
    def test_creates_agents_in_order(self, mock_avail, mock_create):
        mock_create.side_effect = lambda name, key, model, **kw: MagicMock(
            name=name, model=model
        )
        agents = create_agents_from_names(["Claude", "Gemini"], self.config)
        self.assertEqual(len(agents), 2)
        mock_create.assert_any_call(
            "Claude", "test-key", "anthropic/claude-3.5-sonnet",
            history_depth=2, rules_summary=False, strategy_guide=False
        )
        mock_create.assert_any_call(
            "Gemini", "test-key", "google/gemini-pro",
            history_depth=2, rules_summary=False, strategy_guide=False
        )

    @patch("AI_game.agent_factory.create_agent")
    @patch("AI_game.agent_factory.get_available_agents",
           return_value=["Claude", "Gemini"])
    def test_numbered_name_maps_to_provider(self, mock_avail, mock_create):
        mock_create.side_effect = lambda name, key, model, **kw: MagicMock(
            name=name, model=model
        )
        agents = create_agents_from_names(
            ["Claude", "Claude 2"], self.config
        )
        self.assertEqual(len(agents), 2)
        # Both should use the Claude model
        calls = mock_create.call_args_list
        self.assertEqual(calls[0][0][2], "anthropic/claude-3.5-sonnet")
        self.assertEqual(calls[1][0][2], "anthropic/claude-3.5-sonnet")

    @patch("AI_game.agent_factory.get_available_agents",
           return_value=["Claude", "Gemini"])
    def test_unknown_agent_raises(self, mock_avail):
        with self.assertRaises(ValueError) as ctx:
            create_agents_from_names(["Unknown"], self.config)
        self.assertIn("Unknown", str(ctx.exception))


class TestBulkResolveAgentNames(unittest.TestCase):
    """Test _resolve_agent_names from the bulk runner."""

    def setUp(self):
        self.config = {
            "api_key": "test-key",
            "agents": {
                "Claude": "model-a",
                "Gemini": "model-b",
            },
        }

    @patch("AI_game.bulk.get_available_agents",
           return_value=["Claude", "Gemini"])
    def test_default_uses_all_agents(self, mock_avail):
        from AI_game.bulk import _resolve_agent_names
        names = _resolve_agent_names(None, self.config)
        self.assertEqual(names, ["Claude", "Gemini"])

    @patch("AI_game.bulk.get_available_agents",
           return_value=["Claude", "Gemini"])
    def test_custom_agents_string(self, mock_avail):
        from AI_game.bulk import _resolve_agent_names
        names = _resolve_agent_names("Claude,Claude,Gemini", self.config)
        self.assertEqual(names, ["Claude", "Claude 2", "Gemini"])

    @patch("AI_game.bulk.get_available_agents",
           return_value=["Claude", "Gemini"])
    def test_unknown_agent_exits(self, mock_avail):
        from AI_game.bulk import _resolve_agent_names
        with self.assertRaises(SystemExit):
            _resolve_agent_names("Unknown", self.config)

    @patch("AI_game.bulk.get_available_agents",
           return_value=["Claude", "Gemini"])
    def test_too_few_agents_exits(self, mock_avail):
        from AI_game.bulk import _resolve_agent_names
        with self.assertRaises(SystemExit):
            _resolve_agent_names("Claude", self.config)

    @patch("AI_game.bulk.get_available_agents",
           return_value=["Claude", "Gemini"])
    def test_too_many_agents_exits(self, mock_avail):
        from AI_game.bulk import _resolve_agent_names
        agents_str = ",".join(["Claude"] * 7)
        with self.assertRaises(SystemExit):
            _resolve_agent_names(agents_str, self.config)


if __name__ == "__main__":
    unittest.main()
