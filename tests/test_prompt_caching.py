"""Tests for prompt caching — build_prompt_sections() and _build_cached_messages()."""

import sys
import unittest
from unittest.mock import MagicMock

# Mock the openai module before importing agents (openai is not installed in test env)
sys.modules.setdefault("openai", MagicMock())

from AI_game.agents import _build_cached_messages, SYSTEM_PROMPT
from AI_game.prompt_builder import (
    build_prompt_sections,
    build_prompt,
    RULES_SUMMARY,
    RULES_SUMMARY_LIGHT,
)
from src.controller import GameController, State


class FakeAgent:
    """Minimal agent stub for prompt builder tests."""

    def __init__(self, name="Alice", thoughts=None):
        self.name = name
        self.private_thoughts = thoughts or []

    def get_thoughts_text(self):
        if not self.private_thoughts:
            return "None yet."
        return "\n".join(f"- {t}" for t in self.private_thoughts)


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
        self.agent = FakeAgent("Alice")
        self.event_log = []

    def test_returns_dict_with_required_keys(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.agent, self.event_log
        )
        self.assertIsInstance(sections, dict)
        for key in ("rules_summary", "private_thoughts", "game_log", "decision_prompt"):
            self.assertIn(key, sections)

    def test_heavy_mode_uses_full_rules(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.agent, self.event_log, prompt_mode="heavy"
        )
        self.assertEqual(sections["rules_summary"], RULES_SUMMARY)

    def test_light_mode_uses_light_rules(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.agent, self.event_log, prompt_mode="light"
        )
        self.assertEqual(sections["rules_summary"], RULES_SUMMARY_LIGHT)

    def test_heavy_mode_includes_private_thoughts(self):
        self.agent.private_thoughts = ["I should bluff Duke"]
        sections = build_prompt_sections(
            self.ctrl, self.player, self.agent, self.event_log, prompt_mode="heavy"
        )
        self.assertIn("I should bluff Duke", sections["private_thoughts"])

    def test_light_mode_omits_private_thoughts(self):
        self.agent.private_thoughts = ["I should bluff Duke"]
        sections = build_prompt_sections(
            self.ctrl, self.player, self.agent, self.event_log, prompt_mode="light"
        )
        self.assertEqual(sections["private_thoughts"], "")

    def test_game_log_empty(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.agent, self.event_log
        )
        self.assertIn("Game just started", sections["game_log"])

    def test_game_log_includes_events(self):
        self.event_log.append({"type": "event", "text": "Alice took Income"})
        sections = build_prompt_sections(
            self.ctrl, self.player, self.agent, self.event_log
        )
        self.assertIn("Alice took Income", sections["game_log"])

    def test_decision_prompt_contains_decision(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.agent, self.event_log
        )
        self.assertIn("DECISION REQUIRED", sections["decision_prompt"])

    def test_build_prompt_flat_contains_all_sections(self):
        """build_prompt() returns a flat string containing all section content."""
        self.agent.private_thoughts = ["thought1"]
        self.event_log.append({"type": "event", "text": "test event"})
        flat = build_prompt(
            self.ctrl, self.player, self.agent, self.event_log, prompt_mode="heavy"
        )
        self.assertIn("COUP RULES", flat)
        self.assertIn("thought1", flat)
        self.assertIn("test event", flat)
        self.assertIn("DECISION REQUIRED", flat)


class TestBuildCachedMessages(unittest.TestCase):
    """Test _build_cached_messages() produces correct message structure."""

    def _make_sections(self, private_thoughts="", game_log="LOG", decision="DECIDE"):
        return {
            "rules_summary": "RULES",
            "private_thoughts": private_thoughts,
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
        self.assertEqual(system_content[1]["text"], "RULES")

    def test_rules_summary_has_cache_control(self):
        messages = _build_cached_messages(self._make_sections())
        rules_block = messages[0]["content"][1]
        self.assertIn("cache_control", rules_block)
        self.assertEqual(rules_block["cache_control"], {"type": "ephemeral"})

    def test_system_prompt_has_no_cache_control(self):
        messages = _build_cached_messages(self._make_sections())
        system_block = messages[0]["content"][0]
        self.assertNotIn("cache_control", system_block)

    def test_user_message_without_thoughts_has_two_blocks(self):
        """When private_thoughts is empty, user message has game_log + decision only."""
        messages = _build_cached_messages(self._make_sections(private_thoughts=""))
        user_content = messages[1]["content"]
        self.assertEqual(len(user_content), 2)
        self.assertEqual(user_content[0]["text"], "LOG")
        self.assertEqual(user_content[1]["text"], "DECIDE")

    def test_user_message_with_thoughts_has_three_blocks(self):
        """When private_thoughts is non-empty, it becomes an additional block."""
        messages = _build_cached_messages(
            self._make_sections(private_thoughts="THOUGHTS")
        )
        user_content = messages[1]["content"]
        self.assertEqual(len(user_content), 3)
        self.assertEqual(user_content[0]["text"], "THOUGHTS")
        self.assertEqual(user_content[1]["text"], "LOG")
        self.assertEqual(user_content[2]["text"], "DECIDE")

    def test_thoughts_block_has_cache_control(self):
        messages = _build_cached_messages(
            self._make_sections(private_thoughts="THOUGHTS")
        )
        thoughts_block = messages[1]["content"][0]
        self.assertEqual(thoughts_block["cache_control"], {"type": "ephemeral"})

    def test_game_log_block_has_cache_control(self):
        messages = _build_cached_messages(self._make_sections())
        # Without thoughts, game_log is the first user block
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


if __name__ == "__main__":
    unittest.main()
