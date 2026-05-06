"""Tests for the prompt builder and response parser."""

import unittest

from src.player import Player
from src.coup import Game
from src.controller import GameController, State
from AI_game.prompt_builder import (
    build_prompt, _identity_section, _game_state_section,
    _history_section, _decision_section, _response_format,
)
from AI_game.response_parser import parse_response, ParseError


def _make_controller():
    """Create a GameController with a 2-player game ready for actions."""
    gc = GameController()
    gc.handle_input("2")
    gc.handle_input("Alice")
    gc.handle_input("Bob")
    return gc


class _StubAgent:
    """Minimal agent stub with history_depth for testing prompts."""

    def __init__(self, history_depth=2):
        self.name = "Alice"
        self.history_depth = history_depth


# ------------------------------------------------------------------
# Identity section
# ------------------------------------------------------------------

class TestIdentitySection(unittest.TestCase):

    def test_two_living_players(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        text = _identity_section(gc, alice)
        self.assertIn("Alice", text)
        self.assertIn("Bob", text)
        self.assertIn("playing Coup against", text)

    def test_excludes_eliminated_players(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        bob.influence = []  # eliminate Bob
        text = _identity_section(gc, alice)
        self.assertNotIn("Bob", text)
        self.assertIn("playing Coup.", text)  # no "against" when alone

    def test_three_players(self):
        gc = GameController()
        gc.handle_input("3")
        gc.handle_input("Alice")
        gc.handle_input("Bob")
        gc.handle_input("Charlie")
        alice = gc.game.players[0]
        text = _identity_section(gc, alice)
        self.assertIn("Bob", text)
        self.assertIn("Charlie", text)


# ------------------------------------------------------------------
# Game state section
# ------------------------------------------------------------------

class TestGameStateSection(unittest.TestCase):

    def test_shows_own_cards_and_coins(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        text = _game_state_section(gc, alice)
        self.assertIn("Your cards:", text)
        self.assertIn("Coins:", text)

    def test_shows_opponent_info(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        text = _game_state_section(gc, alice)
        self.assertIn("Bob:", text)
        self.assertIn("coins", text)
        self.assertIn("card(s)", text)

    def test_does_not_show_own_entry(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        text = _game_state_section(gc, alice)
        # Alice shouldn't appear as a separate opponent entry
        lines = text.split("\n")
        opponent_lines = [l for l in lines if l.strip().startswith("Alice:")]
        self.assertEqual(len(opponent_lines), 0)

    def test_shows_eliminated_player(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        bob = gc.game.players[1]
        bob.influence = []
        text = _game_state_section(gc, alice)
        self.assertIn("ELIMINATED", text)

    def test_shows_revealed_cards(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        gc.game.revealed_cards = ["Duke", "Captain"]
        text = _game_state_section(gc, alice)
        self.assertIn("Revealed:", text)
        self.assertIn("Duke", text)
        self.assertIn("Captain", text)

    def test_no_revealed_cards_omitted(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        text = _game_state_section(gc, alice)
        self.assertNotIn("Revealed:", text)


# ------------------------------------------------------------------
# History section
# ------------------------------------------------------------------

class TestHistorySection(unittest.TestCase):

    def _make_log(self):
        """Build a sample event log spanning multiple turns."""
        return [
            {"type": "event", "text": "Alice chooses Income."},
            {"type": "event", "text": "Alice takes Income. (+1 coin)"},
            {"type": "speech", "player": "Alice", "text": "I'll take income."},
            {"type": "event", "text": "Bob chooses Tax."},
            {"type": "event", "text": "Bob collects Tax. (+3 coins)"},
            {"type": "event", "text": "Alice chooses Steal."},
            {"type": "event", "text": "Target: Bob"},
            {"type": "event", "text": "Alice steals 2 coins from Bob."},
            {"type": "event", "text": "Bob chooses Foreign Aid."},
            {"type": "event", "text": "Bob takes Foreign Aid. (+2 coins)"},
        ]

    def test_depth_zero_returns_empty(self):
        player = Player("Alice")
        result = _history_section(self._make_log(), player, 0)
        self.assertEqual(result, "")

    def test_negative_depth_returns_empty(self):
        player = Player("Alice")
        result = _history_section(self._make_log(), player, -1)
        self.assertEqual(result, "")

    def test_empty_log_returns_empty(self):
        player = Player("Alice")
        result = _history_section([], player, 2)
        self.assertEqual(result, "")

    def test_depth_1_shows_last_turn(self):
        player = Player("Alice")
        log = self._make_log()
        result = _history_section(log, player, 1)
        self.assertIn("Recent:", result)
        # Should include events from Alice's last "chooses" (Steal) onwards
        self.assertIn("Alice chooses Steal", result)
        self.assertIn("steals 2 coins", result)
        # Should NOT include Alice's first turn (Income)
        self.assertNotIn("Alice chooses Income", result)

    def test_depth_2_shows_both_turns(self):
        player = Player("Alice")
        log = self._make_log()
        result = _history_section(log, player, 2)
        # Should include both turns
        self.assertIn("Alice chooses Income", result)
        self.assertIn("Alice chooses Steal", result)

    def test_depth_exceeding_turns_shows_all(self):
        player = Player("Alice")
        log = self._make_log()
        # Alice has 2 turns; asking for 10 should show everything
        result = _history_section(log, player, 10)
        self.assertIn("Alice chooses Income", result)
        self.assertIn("Bob chooses Tax", result)

    def test_player_with_no_turns_shows_all(self):
        player = Player("Charlie")  # not in the log
        log = self._make_log()
        result = _history_section(log, player, 1)
        # Charlie hasn't taken a turn, so show all events
        self.assertIn("Alice chooses Income", result)
        self.assertIn("Bob chooses Tax", result)

    def test_speech_entries_formatted(self):
        player = Player("Alice")
        log = self._make_log()
        result = _history_section(log, player, 10)
        self.assertIn('Alice: "I\'ll take income."', result)


# ------------------------------------------------------------------
# Decision section
# ------------------------------------------------------------------

class TestDecisionSection(unittest.TestCase):

    def test_choose_action_state(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        text = _decision_section(gc, alice)
        self.assertIn("Options:", text)
        self.assertIn("Income", text)

    def test_shows_message(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        text = _decision_section(gc, alice)
        self.assertIn("turn", text.lower())


# ------------------------------------------------------------------
# Response format
# ------------------------------------------------------------------

class TestResponseFormat(unittest.TestCase):

    def test_contains_json_template(self):
        text = _response_format()
        self.assertIn("speech", text)
        self.assertIn("action", text)

    def test_no_private_thought(self):
        text = _response_format()
        self.assertNotIn("private_thought", text)


# ------------------------------------------------------------------
# Full build_prompt integration
# ------------------------------------------------------------------

class TestBuildPrompt(unittest.TestCase):

    def test_no_rules_summary(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        agent = _StubAgent(history_depth=2)
        prompt = build_prompt(gc, alice, agent, [])
        self.assertNotIn("COUP RULES", prompt)
        self.assertNotIn("RULES_SUMMARY", prompt)

    def test_no_private_thought(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        agent = _StubAgent(history_depth=2)
        prompt = build_prompt(gc, alice, agent, [])
        self.assertNotIn("private_thought", prompt)
        self.assertNotIn("private thought", prompt.lower())

    def test_contains_identity_and_state(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        agent = _StubAgent(history_depth=0)
        prompt = build_prompt(gc, alice, agent, [])
        self.assertIn("Alice", prompt)
        self.assertIn("Your cards:", prompt)

    def test_history_depth_zero_omits_history(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        agent = _StubAgent(history_depth=0)
        log = [{"type": "event", "text": "Alice chooses Income."}]
        prompt = build_prompt(gc, alice, agent, log)
        self.assertNotIn("Recent:", prompt)

    def test_sections_separated_by_double_newline(self):
        gc = _make_controller()
        alice = gc.game.players[0]
        agent = _StubAgent(history_depth=0)
        prompt = build_prompt(gc, alice, agent, [])
        self.assertIn("\n\n", prompt)


# ------------------------------------------------------------------
# Response parser
# ------------------------------------------------------------------

class TestResponseParser(unittest.TestCase):

    def test_basic_json(self):
        raw = '{"speech": "hello", "action": "Income"}'
        result = parse_response(raw, ["Income", "Tax"])
        self.assertEqual(result["action"], "Income")
        self.assertEqual(result["speech"], "hello")

    def test_no_private_thought_in_result(self):
        raw = '{"speech": "hi", "action": "Tax", "private_thought": "bluff"}'
        result = parse_response(raw, ["Tax"])
        self.assertNotIn("private_thought", result)

    def test_case_insensitive_match(self):
        raw = '{"speech": "", "action": "income"}'
        result = parse_response(raw, ["Income", "Tax"])
        self.assertEqual(result["action"], "Income")

    def test_markdown_code_block(self):
        raw = 'Here is my response:\n```json\n{"speech": "ok", "action": "Tax"}\n```'
        result = parse_response(raw, ["Tax"])
        self.assertEqual(result["action"], "Tax")

    def test_invalid_json_raises(self):
        with self.assertRaises(ParseError):
            parse_response("not json at all", ["Income"])

    def test_invalid_action_raises(self):
        raw = '{"speech": "", "action": "InvalidAction"}'
        with self.assertRaises(ParseError):
            parse_response(raw, ["Income", "Tax"])

    def test_empty_options_raises(self):
        raw = '{"speech": "", "action": "Income"}'
        with self.assertRaises(ParseError):
            parse_response(raw, [])

    def test_partial_match(self):
        raw = '{"speech": "", "action": "Block with Duke"}'
        result = parse_response(raw, ["Don't block", "Block with Duke"])
        self.assertEqual(result["action"], "Block with Duke")

    def test_missing_speech_defaults_empty(self):
        raw = '{"action": "Income"}'
        result = parse_response(raw, ["Income"])
        self.assertEqual(result["speech"], "")


if __name__ == "__main__":
    unittest.main()
