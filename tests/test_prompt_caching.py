"""Tests for prompt caching -- build_prompt_sections() and _build_cached_messages()."""

import sys
import unittest
from unittest.mock import MagicMock

# Mock the openai module before importing agents (openai is not installed in test env)
sys.modules.setdefault("openai", MagicMock())

from AI_game.agents import _build_cached_messages, SYSTEM_PROMPT
from AI_game.prompt_builder import build_prompt_sections
from src.controller import GameController, State


def _setup_game(num_players=2, names=None):
    """Create a GameController advanced to CHOOSE_ACTION state."""
    if names is None:
        names = ["Alice", "Bob", "Carol", "Dave"][:num_players]
    ctrl = GameController()
    ctrl.handle_input(str(num_players))
    for name in names:
        ctrl.handle_input(name)
    return ctrl


class TestBuildPromptSections(unittest.TestCase):
    """Test that build_prompt_sections returns correct structure."""

    def setUp(self):
        self.ctrl = _setup_game(2, ["Alice", "Bob"])
        self.player = self.ctrl.game.players[0]
        self.event_log = []

    def test_returns_dict_with_required_keys(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertIsInstance(sections, dict)
        for key in ("identity", "game_log", "decision_prompt"):
            self.assertIn(key, sections)

    def test_identity_contains_player_name(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertIn("Alice", sections["identity"])

    def test_game_log_empty_with_no_events(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertEqual(sections["game_log"], "")

    def test_game_log_includes_events(self):
        self.event_log.append({"type": "event", "text": "Alice took Income"})
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertIn("Alice took Income", sections["game_log"])

    def test_decision_prompt_contains_decision(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertIn("DECIDE", sections["decision_prompt"])


class TestBuildCachedMessages(unittest.TestCase):
    """Test _build_cached_messages() produces correct message structure."""

    def _make_sections(self, identity="IDENTITY", game_log="LOG",
                       decision="DECIDE"):
        return {
            "identity": identity,
            "game_log": game_log,
            "decision_prompt": decision,
        }

    def test_returns_two_messages(self):
        messages = _build_cached_messages(self._make_sections())
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")

    def test_system_message_has_two_content_blocks(self):
        messages = _build_cached_messages(self._make_sections())
        system_content = messages[0]["content"]
        self.assertEqual(len(system_content), 2)
        self.assertEqual(system_content[0]["text"], SYSTEM_PROMPT)
        self.assertEqual(system_content[1]["text"], "IDENTITY")

    def test_identity_has_cache_control(self):
        messages = _build_cached_messages(self._make_sections())
        identity_block = messages[0]["content"][1]
        self.assertIn("cache_control", identity_block)
        self.assertEqual(identity_block["cache_control"], {"type": "ephemeral"})

    def test_system_prompt_has_no_cache_control(self):
        messages = _build_cached_messages(self._make_sections())
        system_block = messages[0]["content"][0]
        self.assertNotIn("cache_control", system_block)

    def test_user_message_without_log_has_one_block(self):
        """When game_log is empty, user message has decision only."""
        messages = _build_cached_messages(self._make_sections(game_log=""))
        user_content = messages[1]["content"]
        self.assertEqual(len(user_content), 1)
        self.assertEqual(user_content[0]["text"], "DECIDE")

    def test_user_message_with_log_has_two_blocks(self):
        """When game_log is non-empty, it becomes an additional block."""
        messages = _build_cached_messages(self._make_sections(game_log="LOG"))
        user_content = messages[1]["content"]
        self.assertEqual(len(user_content), 2)
        self.assertEqual(user_content[0]["text"], "LOG")
        self.assertEqual(user_content[1]["text"], "DECIDE")

    def test_game_log_block_has_cache_control(self):
        messages = _build_cached_messages(self._make_sections())
        game_log_block = messages[1]["content"][0]
        self.assertEqual(game_log_block["cache_control"], {"type": "ephemeral"})

    def test_decision_block_has_no_cache_control(self):
        messages = _build_cached_messages(self._make_sections())
        # Decision is always the last user block
        decision_block = messages[1]["content"][-1]
        self.assertNotIn("cache_control", decision_block)


class TestAgentTrackUsage(unittest.TestCase):
    """Test Agent._track_usage correctly extracts cached_tokens."""

    def test_track_usage_with_cached_tokens(self):
        from unittest.mock import MagicMock, patch
        from AI_game.agents import Agent

        with patch("AI_game.agents.OpenAI"):
            agent = Agent("test", "key", "model")

        usage = MagicMock()
        usage.prompt_tokens = 100
        usage.completion_tokens = 50
        usage.prompt_tokens_details = MagicMock()
        usage.prompt_tokens_details.cached_tokens = 60

        agent._track_usage(usage)

        self.assertEqual(agent.prompt_tokens, 100)
        self.assertEqual(agent.completion_tokens, 50)
        self.assertEqual(agent.cached_tokens, 60)

    def test_track_usage_without_details(self):
        from unittest.mock import MagicMock, patch
        from AI_game.agents import Agent

        with patch("AI_game.agents.OpenAI"):
            agent = Agent("test", "key", "model")

        usage = MagicMock()
        usage.prompt_tokens = 100
        usage.completion_tokens = 50
        # Simulate no prompt_tokens_details attribute
        del usage.prompt_tokens_details

        agent._track_usage(usage)

        self.assertEqual(agent.prompt_tokens, 100)
        self.assertEqual(agent.completion_tokens, 50)
        self.assertEqual(agent.cached_tokens, 0)

    def test_track_usage_none(self):
        from unittest.mock import patch
        from AI_game.agents import Agent

        with patch("AI_game.agents.OpenAI"):
            agent = Agent("test", "key", "model")

        agent._track_usage(None)
        self.assertEqual(agent.prompt_tokens, 0)
        self.assertEqual(agent.completion_tokens, 0)
        self.assertEqual(agent.cached_tokens, 0)


class TestAgentHistoryDepth(unittest.TestCase):
    """Test Agent.history_depth attribute."""

    def test_default_history_depth(self):
        from unittest.mock import patch
        from AI_game.agents import Agent

        with patch("AI_game.agents.OpenAI"):
            agent = Agent("test", "key", "model")

        self.assertEqual(agent.history_depth, 2)

    def test_custom_history_depth(self):
        from unittest.mock import patch
        from AI_game.agents import Agent

        with patch("AI_game.agents.OpenAI"):
            agent = Agent("test", "key", "model", history_depth=5)

        self.assertEqual(agent.history_depth, 5)

    def test_no_private_thoughts_attribute(self):
        from unittest.mock import patch
        from AI_game.agents import Agent

        with patch("AI_game.agents.OpenAI"):
            agent = Agent("test", "key", "model")

        self.assertFalse(hasattr(agent, "private_thoughts"))


if __name__ == "__main__":
    unittest.main()
