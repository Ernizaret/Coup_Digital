"""Tests for the overhauled prompt builder -- minimal token usage approach."""

import sys
import unittest
from unittest.mock import MagicMock

# Mock the openai module before importing agents (openai is not installed in test env)
sys.modules.setdefault("openai", MagicMock())

from AI_game.prompt_builder import (
    build_prompt_sections,
    build_prompt,
    _identity_section,
    _game_state_section,
    _turn_history_section,
    _decision_section,
    _response_format,
)
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
        self.ctrl = _setup_game(3, ["Alice", "Bob", "Carol"])
        self.player = self.ctrl.game.players[0]
        self.event_log = []

    def test_returns_dict_with_required_keys(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertIsInstance(sections, dict)
        for key in ("identity", "game_log", "decision_prompt"):
            self.assertIn(key, sections)

    def test_no_rules_summary_by_default(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        # rules_summary key is present but should be empty when disabled
        self.assertEqual(sections.get("rules_summary", ""), "")

    def test_no_strategy_guide_by_default(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        # strategy_guide key is present but should be empty when disabled
        self.assertEqual(sections.get("strategy_guide", ""), "")

    def test_no_private_thoughts_key(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertNotIn("private_thoughts", sections)

    def test_no_rules_text_in_any_section(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        all_text = " ".join(sections.values())
        self.assertNotIn("COUP RULES", all_text)
        self.assertNotIn("RULES_SUMMARY", all_text)

    def test_no_private_thought_text_in_any_section(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        all_text = " ".join(sections.values())
        self.assertNotIn("private_thought", all_text)
        self.assertNotIn("PRIVATE", all_text)

    def test_decision_prompt_contains_decide(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log
        )
        self.assertIn("DECIDE", sections["decision_prompt"])

    def test_game_log_empty_when_no_events(self):
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log, history_depth=2
        )
        self.assertEqual(sections["game_log"], "")

    def test_game_log_empty_when_history_depth_zero(self):
        self.event_log.append({"type": "event", "text": "Alice took Income"})
        sections = build_prompt_sections(
            self.ctrl, self.player, self.event_log, history_depth=0
        )
        self.assertEqual(sections["game_log"], "")


class TestIdentitySection(unittest.TestCase):
    """Test identity line formatting."""

    def test_two_player_identity(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        player = ctrl.game.players[0]
        result = _identity_section(ctrl, player)
        self.assertIn("You are Alice", result)
        self.assertIn("Bob", result)
        self.assertNotIn("Alice", result.split("against")[1].split(",")[0].strip()
                         if "against" in result else "Alice")

    def test_three_player_identity(self):
        ctrl = _setup_game(3, ["Alice", "Bob", "Carol"])
        player = ctrl.game.players[0]
        result = _identity_section(ctrl, player)
        self.assertIn("You are Alice", result)
        self.assertIn("Bob", result)
        self.assertIn("Carol", result)

    def test_identity_excludes_eliminated(self):
        ctrl = _setup_game(3, ["Alice", "Bob", "Carol"])
        # Eliminate Bob
        bob = ctrl.game.players[1]
        bob.influence = []
        player = ctrl.game.players[0]
        result = _identity_section(ctrl, player)
        self.assertIn("You are Alice", result)
        self.assertNotIn("Bob", result)
        self.assertIn("Carol", result)


class TestGameStateSection(unittest.TestCase):
    """Test game state formatting."""

    def test_shows_own_card_names(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        player = ctrl.game.players[0]
        result = _game_state_section(ctrl, player)
        # The player's actual cards should be shown
        for card in player.influence:
            self.assertIn(card, result)
        self.assertIn("(you)", result)

    def test_shows_other_card_count(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        player = ctrl.game.players[0]
        result = _game_state_section(ctrl, player)
        # Bob should show card count, not card names
        self.assertIn("2 card(s)", result)

    def test_shows_coins(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        player = ctrl.game.players[0]
        result = _game_state_section(ctrl, player)
        self.assertIn("coins=2", result)

    def test_shows_revealed_cards(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        ctrl.game.revealed_cards = ["Duke", "Captain"]
        player = ctrl.game.players[0]
        result = _game_state_section(ctrl, player)
        self.assertIn("Revealed: Duke, Captain", result)

    def test_no_revealed_section_when_empty(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        ctrl.game.revealed_cards = []
        player = ctrl.game.players[0]
        result = _game_state_section(ctrl, player)
        self.assertNotIn("Revealed:", result)

    def test_eliminated_player_shown(self):
        ctrl = _setup_game(3, ["Alice", "Bob", "Carol"])
        ctrl.game.players[1].influence = []
        player = ctrl.game.players[0]
        result = _game_state_section(ctrl, player)
        self.assertIn("Bob: ELIMINATED", result)


class TestTurnHistorySection(unittest.TestCase):
    """Test turn history with various history_depth values."""

    def _make_player(self, name):
        class FakePlayer:
            pass
        p = FakePlayer()
        p.name = name
        return p

    def test_depth_zero_returns_empty(self):
        player = self._make_player("Alice")
        event_log = [
            {"type": "event", "text": "Alice took Income",
             "turn_boundary": False},
        ]
        result = _turn_history_section(event_log, player, 0)
        self.assertEqual(result, "")

    def test_no_events_returns_empty(self):
        player = self._make_player("Alice")
        result = _turn_history_section([], player, 2)
        self.assertEqual(result, "")

    def test_events_without_boundaries_includes_all(self):
        player = self._make_player("Alice")
        event_log = [
            {"type": "event", "text": "Alice took Income"},
            {"type": "event", "text": "Bob took Tax"},
        ]
        result = _turn_history_section(event_log, player, 2)
        self.assertIn("Alice took Income", result)
        self.assertIn("Bob took Tax", result)

    def test_speech_events_formatted(self):
        player = self._make_player("Alice")
        event_log = [
            {"type": "speech", "player": "Bob", "text": "I have Duke"},
        ]
        result = _turn_history_section(event_log, player, 2)
        self.assertIn('Bob: "I have Duke"', result)

    def test_depth_one_slices_correctly(self):
        player = self._make_player("Alice")
        event_log = [
            {"type": "event", "text": "", "turn_boundary": True,
             "turn_player": "Alice", "turn_number": 1},
            {"type": "event", "text": "Alice took Income"},
            {"type": "event", "text": "Bob took Tax"},
            {"type": "event", "text": "", "turn_boundary": True,
             "turn_player": "Alice", "turn_number": 2},
            {"type": "event", "text": "Alice used Steal"},
        ]
        result = _turn_history_section(event_log, player, 1)
        # Should only include from the last turn boundary
        self.assertNotIn("Alice took Income", result)
        self.assertIn("Alice used Steal", result)

    def test_depth_two_includes_both_turns(self):
        player = self._make_player("Alice")
        event_log = [
            {"type": "event", "text": "", "turn_boundary": True,
             "turn_player": "Alice", "turn_number": 1},
            {"type": "event", "text": "Alice took Income"},
            {"type": "event", "text": "Bob took Tax"},
            {"type": "event", "text": "", "turn_boundary": True,
             "turn_player": "Alice", "turn_number": 2},
            {"type": "event", "text": "Alice used Steal"},
        ]
        result = _turn_history_section(event_log, player, 2)
        # Should include events from both turns
        self.assertIn("Alice took Income", result)
        self.assertIn("Bob took Tax", result)
        self.assertIn("Alice used Steal", result)

    def test_boundaries_for_other_player_ignored(self):
        player = self._make_player("Alice")
        event_log = [
            {"type": "event", "text": "", "turn_boundary": True,
             "turn_player": "Bob", "turn_number": 1},
            {"type": "event", "text": "Bob took Income"},
            {"type": "event", "text": "", "turn_boundary": True,
             "turn_player": "Alice", "turn_number": 1},
            {"type": "event", "text": "Alice took Tax"},
        ]
        result = _turn_history_section(event_log, player, 1)
        # Only Alice's boundary matters for slicing
        self.assertIn("Alice took Tax", result)

    def test_turn_boundary_markers_not_in_output(self):
        player = self._make_player("Alice")
        event_log = [
            {"type": "event", "text": "", "turn_boundary": True,
             "turn_player": "Alice", "turn_number": 1},
            {"type": "event", "text": "Alice took Income"},
        ]
        result = _turn_history_section(event_log, player, 2)
        # The boundary marker line (empty text) should not appear
        lines = result.strip().split("\n")
        for line in lines:
            if line.strip() and line.strip() != "HISTORY:":
                self.assertNotEqual(line.strip(), "")


class TestResponseFormat(unittest.TestCase):
    """Test response format instructions."""

    def test_contains_json_keyword(self):
        result = _response_format()
        self.assertIn("JSON", result)

    def test_contains_action_field(self):
        result = _response_format()
        self.assertIn('"action"', result)

    def test_contains_speech_field(self):
        result = _response_format()
        self.assertIn('"speech"', result)

    def test_no_private_thought_field(self):
        result = _response_format()
        self.assertNotIn("private_thought", result)


class TestBuildPromptFlat(unittest.TestCase):
    """Test the flat prompt string builder."""

    def test_contains_identity(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        player = ctrl.game.players[0]
        flat = build_prompt(ctrl, player, [])
        self.assertIn("You are Alice", flat)

    def test_contains_state(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        player = ctrl.game.players[0]
        flat = build_prompt(ctrl, player, [])
        self.assertIn("STATE:", flat)

    def test_contains_decision(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        player = ctrl.game.players[0]
        flat = build_prompt(ctrl, player, [])
        self.assertIn("DECIDE:", flat)

    def test_no_rules_in_flat(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        player = ctrl.game.players[0]
        flat = build_prompt(ctrl, player, [])
        self.assertNotIn("COUP RULES", flat)

    def test_no_private_thoughts_in_flat(self):
        ctrl = _setup_game(2, ["Alice", "Bob"])
        player = ctrl.game.players[0]
        flat = build_prompt(ctrl, player, [])
        self.assertNotIn("PRIVATE", flat)
        self.assertNotIn("private_thought", flat)


if __name__ == "__main__":
    unittest.main()
