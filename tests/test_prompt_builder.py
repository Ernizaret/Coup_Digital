"""Tests for AI_game.prompt_builder — prompt construction and modes."""

import sys
import unittest
from unittest.mock import MagicMock

# Mock the openai module before importing prompt_builder (transitive via agents)
sys.modules.setdefault("openai", MagicMock())

from AI_game.prompt_builder import build_prompt, RULES_SUMMARY
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
        names = ["Alice", "Bob"][:num_players]
    ctrl = GameController()
    ctrl.handle_input(str(num_players))
    for name in names:
        ctrl.handle_input(name)
    return ctrl


class TestBuildPromptHeavyMode(unittest.TestCase):
    def setUp(self):
        self.ctrl = _setup_game()
        self.player = self.ctrl.game.players[0]
        self.agent = FakeAgent("Alice", thoughts=["I should bluff"])
        self.event_log = []

    def test_includes_rules(self):
        prompt = build_prompt(self.ctrl, self.player, self.agent, self.event_log)
        self.assertIn("COUP RULES:", prompt)

    def test_includes_private_thoughts(self):
        prompt = build_prompt(self.ctrl, self.player, self.agent, self.event_log)
        self.assertIn("I should bluff", prompt)

    def test_includes_game_state(self):
        prompt = build_prompt(self.ctrl, self.player, self.agent, self.event_log)
        self.assertIn("CURRENT GAME STATE:", prompt)

    def test_includes_decision(self):
        prompt = build_prompt(self.ctrl, self.player, self.agent, self.event_log)
        self.assertIn("DECISION REQUIRED:", prompt)

    def test_choose_action_uses_full_format(self):
        prompt = build_prompt(self.ctrl, self.player, self.agent, self.event_log)
        self.assertIn("private_thought", prompt)


class TestBuildPromptLightMode(unittest.TestCase):
    def setUp(self):
        self.ctrl = _setup_game()
        self.player = self.ctrl.game.players[0]
        self.agent = FakeAgent("Alice", thoughts=["secret thought"])
        self.event_log = []

    def test_omits_rules(self):
        prompt = build_prompt(
            self.ctrl, self.player, self.agent, self.event_log, prompt_mode="light"
        )
        self.assertNotIn("COUP RULES:", prompt)

    def test_omits_private_thoughts(self):
        prompt = build_prompt(
            self.ctrl, self.player, self.agent, self.event_log, prompt_mode="light"
        )
        self.assertNotIn("secret thought", prompt)

    def test_includes_private_info_basic(self):
        prompt = build_prompt(
            self.ctrl, self.player, self.agent, self.event_log, prompt_mode="light"
        )
        self.assertIn("YOUR PRIVATE INFO:", prompt)
        self.assertIn("Your cards:", prompt)

    def test_uses_slim_format(self):
        prompt = build_prompt(
            self.ctrl, self.player, self.agent, self.event_log, prompt_mode="light"
        )
        self.assertNotIn("private_thought", prompt)

    def test_still_includes_decision(self):
        prompt = build_prompt(
            self.ctrl, self.player, self.agent, self.event_log, prompt_mode="light"
        )
        self.assertIn("DECISION REQUIRED:", prompt)


class TestBuildPromptEventLog(unittest.TestCase):
    def setUp(self):
        self.ctrl = _setup_game()
        self.player = self.ctrl.game.players[0]
        self.agent = FakeAgent("Alice")

    def test_empty_log(self):
        prompt = build_prompt(self.ctrl, self.player, self.agent, [])
        self.assertIn("Game just started", prompt)

    def test_events_included(self):
        log = [{"type": "event", "text": "Alice took Income"}]
        prompt = build_prompt(self.ctrl, self.player, self.agent, log)
        self.assertIn("Alice took Income", prompt)

    def test_speech_included(self):
        log = [{"type": "speech", "player": "Bob", "text": "I have the Duke"}]
        prompt = build_prompt(self.ctrl, self.player, self.agent, log)
        self.assertIn("I have the Duke", prompt)


if __name__ == "__main__":
    unittest.main()
