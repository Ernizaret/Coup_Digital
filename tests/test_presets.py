"""Tests for AI_game preset loading, validation, and application."""

import unittest
import json
import os
import tempfile

from AI_game.presets import (
    load_presets_file,
    get_preset,
    validate_preset,
    compute_remaining_deck,
    apply_preset,
    PresetError,
    VALID_CARDS,
    STANDARD_DECK,
)
from src.player import Player
from src.deck import Deck
from src.coup import Game


class TestLoadPresetsFile(unittest.TestCase):
    """Tests for loading the presets JSON file."""

    def test_load_valid_file(self):
        data = {
            "presets": {
                "test": {
                    "players": {"A": {"hand": ["Duke", "Duke"], "coins": 2}},
                    "deck": "auto"
                }
            }
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            path = f.name
        try:
            result = load_presets_file(path)
            self.assertEqual(result, data)
        finally:
            os.unlink(path)

    def test_load_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_presets_file("/nonexistent/path/presets.json")

    def test_load_invalid_json(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("not valid json{{{")
            path = f.name
        try:
            with self.assertRaises(json.JSONDecodeError):
                load_presets_file(path)
        finally:
            os.unlink(path)


class TestGetPreset(unittest.TestCase):
    """Tests for retrieving a named preset."""

    def test_get_existing_preset(self):
        data = {
            "presets": {
                "mirror": {"players": {"A": {"hand": ["Duke", "Duke"]}}}
            }
        }
        result = get_preset(data, "mirror")
        self.assertEqual(result["players"]["A"]["hand"], ["Duke", "Duke"])

    def test_get_nonexistent_preset(self):
        data = {"presets": {"mirror": {}}}
        with self.assertRaises(PresetError) as ctx:
            get_preset(data, "does_not_exist")
        self.assertIn("does_not_exist", str(ctx.exception))
        self.assertIn("mirror", str(ctx.exception))

    def test_get_preset_empty_presets(self):
        data = {"presets": {}}
        with self.assertRaises(PresetError):
            get_preset(data, "anything")


class TestValidatePreset(unittest.TestCase):
    """Tests for preset validation logic."""

    def _valid_preset(self):
        return {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 3},
            },
            "deck": "auto"
        }

    def test_valid_preset_passes(self):
        # Should not raise
        validate_preset(self._valid_preset())

    def test_valid_preset_no_deck_key(self):
        preset = self._valid_preset()
        del preset["deck"]
        # Should not raise — deck defaults to auto
        validate_preset(preset)

    def test_valid_preset_explicit_deck(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Duke"], "coins": 2},
            },
            "deck": ["Captain", "Captain", "Captain"]
        }
        validate_preset(preset)

    def test_empty_players(self):
        with self.assertRaises(PresetError) as ctx:
            validate_preset({"players": {}})
        self.assertIn("at least one player", str(ctx.exception))

    def test_no_players_key(self):
        with self.assertRaises(PresetError):
            validate_preset({})

    def test_invalid_card_in_hand(self):
        preset = {
            "players": {"Alice": {"hand": ["Duke", "InvalidCard"]}}
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("InvalidCard", str(ctx.exception))

    def test_hand_too_many_cards(self):
        preset = {
            "players": {"Alice": {"hand": ["Duke", "Duke", "Duke"]}}
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("1 or 2 cards", str(ctx.exception))

    def test_hand_empty(self):
        preset = {
            "players": {"Alice": {"hand": []}}
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("1 or 2 cards", str(ctx.exception))

    def test_hand_not_a_list(self):
        preset = {
            "players": {"Alice": {"hand": "Duke"}}
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("must be a list", str(ctx.exception))

    def test_negative_coins(self):
        preset = {
            "players": {"Alice": {"hand": ["Duke", "Duke"], "coins": -1}}
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("non-negative integer", str(ctx.exception))

    def test_coins_not_integer(self):
        preset = {
            "players": {"Alice": {"hand": ["Duke", "Duke"], "coins": 2.5}}
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("non-negative integer", str(ctx.exception))

    def test_card_exceeds_max_count(self):
        # 4 Dukes total (exceeds max of 3)
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Duke"]},
                "Bob": {"hand": ["Duke", "Duke"]},
            }
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("Duke", str(ctx.exception))
        self.assertIn("4 times", str(ctx.exception))

    def test_total_cards_exceed_15(self):
        # This would require a specially crafted invalid deck
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Duke"]},
            },
            "deck": ["Captain"] * 14  # 2 + 14 = 16 > 15
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("exceeds 15", str(ctx.exception))

    def test_card_exceeds_max_in_deck(self):
        # 3 Dukes in hand + 1 Duke in deck = 4 > 3
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Duke"]},
                "Bob": {"hand": ["Duke", "Captain"]},
            },
            "deck": ["Duke"]
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("Duke", str(ctx.exception))

    def test_single_influence_valid(self):
        preset = {
            "players": {"Alice": {"hand": ["Duke"], "coins": 5}}
        }
        # Should not raise — 1 card is valid
        validate_preset(preset)

    def test_no_hand_specified_valid(self):
        # Players without hand key are valid (will be dealt randomly)
        preset = {
            "players": {"Alice": {"coins": 5}}
        }
        validate_preset(preset)

    def test_invalid_card_in_deck(self):
        preset = {
            "players": {"Alice": {"hand": ["Duke", "Duke"]}},
            "deck": ["FakeCard"]
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("FakeCard", str(ctx.exception))

    def test_deck_not_list_or_auto(self):
        preset = {
            "players": {"Alice": {"hand": ["Duke", "Duke"]}},
            "deck": 42
        }
        with self.assertRaises(PresetError) as ctx:
            validate_preset(preset)
        self.assertIn("list of card names", str(ctx.exception))


class TestComputeRemainingDeck(unittest.TestCase):
    """Tests for computing the remaining deck after dealing."""

    def test_auto_two_players(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"]},
                "Bob": {"hand": ["Assassin", "Contessa"]},
            },
            "deck": "auto"
        }
        remaining = compute_remaining_deck(preset)
        # 15 - 4 = 11 cards remaining
        self.assertEqual(len(remaining), 11)
        # Check specific removals
        all_cards = remaining + ["Duke", "Captain", "Assassin", "Contessa"]
        for card in VALID_CARDS:
            self.assertEqual(all_cards.count(card), 3)

    def test_auto_single_influence(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke"]},
            },
        }
        remaining = compute_remaining_deck(preset)
        self.assertEqual(len(remaining), 14)
        self.assertEqual(remaining.count("Duke"), 2)

    def test_explicit_deck(self):
        deck_list = ["Duke", "Duke", "Captain"]
        preset = {
            "players": {"Alice": {"hand": ["Duke", "Captain"]}},
            "deck": deck_list
        }
        remaining = compute_remaining_deck(preset)
        self.assertEqual(remaining, ["Duke", "Duke", "Captain"])

    def test_auto_no_hands(self):
        preset = {
            "players": {"Alice": {"coins": 5}},
        }
        remaining = compute_remaining_deck(preset)
        self.assertEqual(len(remaining), 15)

    def test_auto_impossible_card_combination(self):
        # More of a card than exists in the standard deck
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Duke"]},
                "Bob": {"hand": ["Duke", "Duke"]},
            },
        }
        with self.assertRaises(PresetError) as ctx:
            compute_remaining_deck(preset)
        self.assertIn("not available", str(ctx.exception))


class TestApplyPreset(unittest.TestCase):
    """Tests for applying a preset to create game objects."""

    def _make_mock_agent(self, name):
        """Create a simple mock agent with just a name attribute."""
        class MockAgent:
            def __init__(self, name):
                self.name = name
        return MockAgent(name)

    def test_apply_basic_preset(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 5},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 3},
            },
            "deck": "auto"
        }
        agents = [self._make_mock_agent("Alice"), self._make_mock_agent("Bob")]
        players, deck_cards = apply_preset(preset, agents)

        self.assertEqual(len(players), 2)
        self.assertEqual(players[0].name, "Alice")
        self.assertEqual(players[0].influence, ["Duke", "Captain"])
        self.assertEqual(players[0].coins, 5)
        self.assertEqual(players[1].name, "Bob")
        self.assertEqual(players[1].influence, ["Assassin", "Contessa"])
        self.assertEqual(players[1].coins, 3)
        self.assertEqual(len(deck_cards), 11)

    def test_apply_preset_default_coins(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"]},
            },
        }
        agents = [self._make_mock_agent("Alice")]
        players, deck_cards = apply_preset(preset, agents)
        # Default coins is 2 (from Player.__init__)
        self.assertEqual(players[0].coins, 2)

    def test_apply_preset_custom_turn_order(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 2},
            },
            "turn_order": ["Bob", "Alice"],
        }
        agents = [self._make_mock_agent("Alice"), self._make_mock_agent("Bob")]
        players, deck_cards = apply_preset(preset, agents)

        # Bob should be first in turn order
        self.assertEqual(players[0].name, "Bob")
        self.assertEqual(players[1].name, "Alice")

    def test_apply_preset_missing_agent(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"]},
                "Charlie": {"hand": ["Assassin", "Contessa"]},
            },
        }
        agents = [self._make_mock_agent("Alice"), self._make_mock_agent("Bob")]
        with self.assertRaises(PresetError) as ctx:
            apply_preset(preset, agents)
        self.assertIn("Charlie", str(ctx.exception))

    def test_apply_preset_no_hand_leaves_empty(self):
        preset = {
            "players": {
                "Alice": {"coins": 5},
            },
        }
        agents = [self._make_mock_agent("Alice")]
        players, deck_cards = apply_preset(preset, agents)
        # No hand assigned — influence is empty (GameRunner will deal)
        self.assertEqual(players[0].influence, [])
        self.assertEqual(players[0].coins, 5)


class TestDeckWithCards(unittest.TestCase):
    """Tests for the modified Deck constructor accepting a cards list."""

    def test_custom_cards(self):
        cards = ["Duke", "Duke", "Captain"]
        d = Deck(cards=cards)
        self.assertEqual(len(d.cards), 3)
        self.assertEqual(d.cards.count("Duke"), 2)
        self.assertEqual(d.cards.count("Captain"), 1)

    def test_custom_cards_not_modified(self):
        """Ensure the original list is not modified."""
        cards = ["Duke", "Captain"]
        d = Deck(cards=cards)
        d.draw()
        # Original list should still have 2 items
        self.assertEqual(len(cards), 2)

    def test_empty_cards(self):
        d = Deck(cards=[])
        self.assertEqual(len(d.cards), 0)
        self.assertIsNone(d.draw())

    def test_default_still_works(self):
        d = Deck()
        self.assertEqual(len(d.cards), 15)


class TestGameSkipDeal(unittest.TestCase):
    """Tests for the modified Game constructor with skip_deal."""

    def test_skip_deal_preserves_hands(self):
        p1 = Player("Alice")
        p1.add_influence("Duke")
        p1.add_influence("Captain")
        p2 = Player("Bob")
        p2.add_influence("Assassin")
        p2.add_influence("Contessa")

        deck = Deck(cards=["Ambassador", "Ambassador", "Ambassador"])
        game = Game([p1, p2], deck=deck, skip_deal=True)

        self.assertEqual(p1.influence, ["Duke", "Captain"])
        self.assertEqual(p2.influence, ["Assassin", "Contessa"])
        self.assertEqual(len(game.deck.cards), 3)

    def test_skip_deal_false_still_deals(self):
        p1 = Player("Alice")
        p2 = Player("Bob")
        game = Game([p1, p2], skip_deal=False)
        self.assertEqual(len(p1.influence), 2)
        self.assertEqual(len(p2.influence), 2)

    def test_custom_deck_used(self):
        p1 = Player("Alice")
        p2 = Player("Bob")
        custom_cards = ["Duke"] * 4 + ["Captain"] * 4
        deck = Deck(cards=custom_cards)
        game = Game([p1, p2], deck=deck, skip_deal=False)
        # After dealing 4 cards, 4 remain
        self.assertEqual(len(game.deck.cards), 4)
        for p in game.players:
            self.assertEqual(len(p.influence), 2)


if __name__ == "__main__":
    unittest.main()
