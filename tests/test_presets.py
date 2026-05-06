"""Tests for AI_game.presets — preset loading, validation, and application."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.player import Player
from src.deck import Deck
from src.coup import Game
from AI_game.presets import (
    load_presets,
    get_preset,
    validate_preset,
    apply_preset,
    build_preset_game,
    _compute_auto_deck,
    VALID_CARDS,
    CARDS_PER_TYPE,
    TOTAL_CARDS,
)


class TestDeckCustomCards(unittest.TestCase):
    """Test the Deck class with the new optional cards parameter."""

    def test_default_deck(self):
        d = Deck()
        self.assertEqual(len(d.cards), 15)
        for card in VALID_CARDS:
            self.assertEqual(d.cards.count(card), 3)

    def test_custom_deck(self):
        custom = ["Duke", "Duke", "Captain"]
        d = Deck(cards=custom)
        self.assertEqual(d.cards, ["Duke", "Duke", "Captain"])

    def test_empty_custom_deck(self):
        d = Deck(cards=[])
        self.assertEqual(d.cards, [])

    def test_custom_deck_is_copy(self):
        """Modifying the original list should not affect the deck."""
        custom = ["Duke", "Captain"]
        d = Deck(cards=custom)
        custom.append("Contessa")
        self.assertEqual(len(d.cards), 2)


class TestGameSkipDeal(unittest.TestCase):
    """Test the Game class with the new skip_deal parameter."""

    def test_normal_deal(self):
        players = [Player("A"), Player("B")]
        game = Game(players)
        for p in game.players:
            self.assertEqual(len(p.influence), 2)
        self.assertEqual(len(game.deck.cards), 11)

    def test_skip_deal(self):
        players = [Player("A"), Player("B")]
        game = Game(players, skip_deal=True)
        for p in game.players:
            self.assertEqual(len(p.influence), 0)
        self.assertEqual(len(game.deck.cards), 15)

    def test_skip_deal_with_custom_deck(self):
        players = [Player("A"), Player("B")]
        custom_deck = ["Duke", "Duke", "Captain"]
        game = Game(players, skip_deal=True, deck_cards=custom_deck)
        for p in game.players:
            self.assertEqual(len(p.influence), 0)
        self.assertEqual(game.deck.cards, ["Duke", "Duke", "Captain"])


class TestComputeAutoDeck(unittest.TestCase):
    """Test the auto-deck computation helper."""

    def test_no_cards_dealt(self):
        deck = _compute_auto_deck([])
        self.assertEqual(len(deck), 15)
        for card in VALID_CARDS:
            self.assertEqual(deck.count(card), 3)

    def test_two_cards_dealt(self):
        deck = _compute_auto_deck(["Duke", "Assassin"])
        self.assertEqual(len(deck), 13)
        self.assertEqual(deck.count("Duke"), 2)
        self.assertEqual(deck.count("Assassin"), 2)
        self.assertEqual(deck.count("Captain"), 3)

    def test_four_cards_dealt(self):
        deck = _compute_auto_deck(["Duke", "Duke", "Captain", "Contessa"])
        self.assertEqual(len(deck), 11)
        self.assertEqual(deck.count("Duke"), 1)
        self.assertEqual(deck.count("Captain"), 2)
        self.assertEqual(deck.count("Contessa"), 2)

    def test_max_of_one_type(self):
        deck = _compute_auto_deck(["Duke", "Duke", "Duke"])
        self.assertEqual(len(deck), 12)
        self.assertEqual(deck.count("Duke"), 0)

    def test_too_many_of_one_type_raises(self):
        with self.assertRaises(ValueError):
            _compute_auto_deck(["Duke", "Duke", "Duke", "Duke"])


class TestValidatePreset(unittest.TestCase):
    """Test preset validation logic."""

    def test_valid_two_player_preset(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 3},
            },
            "deck": "auto",
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertEqual(errors, [])

    def test_valid_preset_without_deck_key(self):
        """deck defaults to 'auto' when omitted."""
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 3},
            },
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertEqual(errors, [])

    def test_valid_one_card_hand(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke"], "coins": 5},
                "Bob": {"hand": ["Assassin"], "coins": 5},
            },
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertEqual(errors, [])

    def test_empty_hand_invalid(self):
        preset = {
            "players": {
                "Alice": {"hand": [], "coins": 2},
                "Bob": {"hand": ["Duke", "Captain"], "coins": 2},
            },
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertTrue(any("1 or 2 cards" in e for e in errors))

    def test_three_card_hand_invalid(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain", "Assassin"], "coins": 2},
                "Bob": {"hand": ["Contessa"], "coins": 2},
            },
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertTrue(any("1 or 2 cards" in e for e in errors))

    def test_invalid_card_name(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Wizard"], "coins": 2},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 2},
            },
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertTrue(any("Wizard" in e for e in errors))

    def test_negative_coins(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": -1},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 2},
            },
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertTrue(any("non-negative" in e for e in errors))

    def test_float_coins_invalid(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2.5},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 2},
            },
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertTrue(any("non-negative integer" in e for e in errors))

    def test_card_type_exceeds_three(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Duke"], "coins": 2},
                "Bob": {"hand": ["Duke", "Captain"], "coins": 2},
            },
            "deck": ["Duke", "Assassin"],  # This puts Duke at 4 total
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertTrue(any("Duke" in e and "4 times" in e for e in errors))

    def test_card_type_exactly_three_is_valid(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Duke"], "coins": 2},
                "Bob": {"hand": ["Duke", "Captain"], "coins": 2},
            },
            "deck": "auto",
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertEqual(errors, [])

    def test_total_cards_exceeds_fifteen(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 2},
            },
            "deck": ["Duke", "Duke", "Captain", "Captain", "Assassin",
                     "Assassin", "Contessa", "Contessa", "Ambassador",
                     "Ambassador", "Ambassador", "Ambassador"],  # 12 + 4 = 16
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertTrue(any("exceeds maximum" in e for e in errors))

    def test_extra_player_in_preset(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 2},
                "Charlie": {"hand": ["Duke", "Duke"], "coins": 2},
            },
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertTrue(any("not in the game" in e for e in errors))

    def test_player_not_in_preset_is_okay(self):
        """Players not defined in preset just get no custom settings."""
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
            },
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertEqual(errors, [])

    def test_invalid_deck_value(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
            },
            "deck": "custom",
        }
        errors = validate_preset(preset, ["Alice"])
        self.assertTrue(any("'auto' or a list" in e for e in errors))

    def test_invalid_card_in_deck(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke"], "coins": 2},
            },
            "deck": ["Duke", "Wizard"],
        }
        errors = validate_preset(preset, ["Alice"])
        self.assertTrue(any("Wizard" in e for e in errors))

    def test_hand_not_a_list(self):
        preset = {
            "players": {
                "Alice": {"hand": "Duke", "coins": 2},
            },
        }
        errors = validate_preset(preset, ["Alice"])
        self.assertTrue(any("must be a list" in e for e in errors))

    def test_explicit_deck_list_valid(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 2},
            },
            "deck": ["Duke", "Duke", "Captain", "Captain", "Assassin",
                     "Assassin", "Contessa", "Contessa", "Ambassador",
                     "Ambassador", "Ambassador"],
        }
        errors = validate_preset(preset, ["Alice", "Bob"])
        self.assertEqual(errors, [])


class TestApplyPreset(unittest.TestCase):
    """Test applying presets to Game objects."""

    def test_apply_basic_preset(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 5},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 3},
            },
            "deck": "auto",
        }
        players = [Player("Alice"), Player("Bob")]
        game = Game(players, skip_deal=True)
        apply_preset(preset, game, ["Alice", "Bob"])

        self.assertEqual(game.players[0].influence, ["Duke", "Captain"])
        self.assertEqual(game.players[0].coins, 5)
        self.assertEqual(game.players[1].influence, ["Assassin", "Contessa"])
        self.assertEqual(game.players[1].coins, 3)
        # Auto deck: 15 - 4 = 11
        self.assertEqual(len(game.deck.cards), 11)

    def test_apply_preset_auto_deck_composition(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Duke"], "coins": 2},
                "Bob": {"hand": ["Duke", "Captain"], "coins": 2},
            },
        }
        players = [Player("Alice"), Player("Bob")]
        game = Game(players, skip_deal=True)
        apply_preset(preset, game, ["Alice", "Bob"])

        # All 3 Dukes dealt, 1 Captain dealt
        self.assertEqual(game.deck.cards.count("Duke"), 0)
        self.assertEqual(game.deck.cards.count("Captain"), 2)
        self.assertEqual(len(game.deck.cards), 11)

    def test_apply_preset_explicit_deck(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
            },
            "deck": ["Assassin", "Contessa"],
        }
        players = [Player("Alice")]
        game = Game(players, skip_deal=True)
        apply_preset(preset, game, ["Alice"])

        self.assertEqual(game.deck.cards, ["Assassin", "Contessa"])

    def test_apply_preset_one_card_hand(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke"], "coins": 10},
                "Bob": {"hand": ["Assassin"], "coins": 10},
            },
        }
        players = [Player("Alice"), Player("Bob")]
        game = Game(players, skip_deal=True)
        apply_preset(preset, game, ["Alice", "Bob"])

        self.assertEqual(len(game.players[0].influence), 1)
        self.assertEqual(game.players[0].influence, ["Duke"])
        self.assertEqual(game.players[0].coins, 10)
        self.assertEqual(len(game.players[1].influence), 1)

    def test_apply_preset_default_coins(self):
        """If coins not specified, default to 2."""
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"]},
            },
        }
        players = [Player("Alice")]
        game = Game(players, skip_deal=True)
        apply_preset(preset, game, ["Alice"])

        self.assertEqual(game.players[0].coins, 2)

    def test_apply_invalid_preset_raises(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain", "Assassin"], "coins": 2},
            },
        }
        players = [Player("Alice")]
        game = Game(players, skip_deal=True)
        with self.assertRaises(ValueError) as ctx:
            apply_preset(preset, game, ["Alice"])
        self.assertIn("Invalid preset", str(ctx.exception))

    def test_player_not_in_preset_untouched(self):
        """Players not defined in the preset keep default state."""
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 5},
            },
        }
        players = [Player("Alice"), Player("Bob")]
        game = Game(players, skip_deal=True)
        apply_preset(preset, game, ["Alice", "Bob"])

        self.assertEqual(game.players[0].influence, ["Duke", "Captain"])
        self.assertEqual(game.players[0].coins, 5)
        # Bob not in preset: hand empty, coins = default 2
        self.assertEqual(game.players[1].influence, [])
        self.assertEqual(game.players[1].coins, 2)


class TestBuildPresetGame(unittest.TestCase):
    """Test the convenience function that builds a complete preset game."""

    def test_build_preset_game(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 5},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 3},
            },
        }
        game = build_preset_game(preset, ["Alice", "Bob"])

        self.assertEqual(len(game.players), 2)
        self.assertEqual(game.players[0].name, "Alice")
        self.assertEqual(game.players[0].influence, ["Duke", "Captain"])
        self.assertEqual(game.players[0].coins, 5)
        self.assertEqual(game.players[1].name, "Bob")
        self.assertEqual(game.players[1].influence, ["Assassin", "Contessa"])
        self.assertEqual(game.players[1].coins, 3)
        self.assertEqual(len(game.deck.cards), 11)


class TestLoadPresets(unittest.TestCase):
    """Test loading presets from a JSON file."""

    def _write_presets(self, data, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_load_valid_presets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "presets.json")
            self._write_presets({
                "presets": {
                    "test_preset": {
                        "description": "A test preset",
                        "players": {
                            "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
                        },
                    },
                },
            }, path)
            with patch("AI_game.presets._find_presets_path", return_value=path):
                presets = load_presets()
            self.assertIn("test_preset", presets)
            self.assertEqual(
                presets["test_preset"]["description"], "A test preset"
            )

    def test_missing_presets_file_raises(self):
        with patch("AI_game.presets._find_presets_path",
                    return_value="/nonexistent/presets.json"):
            with self.assertRaises(FileNotFoundError):
                load_presets()

    def test_invalid_presets_key_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "presets.json")
            self._write_presets({"presets": "not_a_dict"}, path)
            with patch("AI_game.presets._find_presets_path", return_value=path):
                with self.assertRaises(ValueError):
                    load_presets()


class TestGetPreset(unittest.TestCase):
    """Test getting a single preset by name."""

    def _write_presets(self, data, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_get_existing_preset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "presets.json")
            self._write_presets({
                "presets": {
                    "my_preset": {
                        "players": {"A": {"hand": ["Duke"], "coins": 2}},
                    },
                },
            }, path)
            with patch("AI_game.presets._find_presets_path", return_value=path):
                preset = get_preset("my_preset")
            self.assertIn("players", preset)

    def test_get_nonexistent_preset_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "presets.json")
            self._write_presets({"presets": {"other": {}}}, path)
            with patch("AI_game.presets._find_presets_path", return_value=path):
                with self.assertRaises(ValueError) as ctx:
                    get_preset("missing")
                self.assertIn("missing", str(ctx.exception))
                self.assertIn("other", str(ctx.exception))


class TestPresetIntegrationWithGame(unittest.TestCase):
    """Integration tests: presets with the actual Game and controller flow."""

    def test_preset_game_cards_total_correct(self):
        """All cards in hands + deck should account for the full 15-card set."""
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Assassin"], "coins": 2},
                "Bob": {"hand": ["Captain", "Contessa"], "coins": 2},
            },
        }
        game = build_preset_game(preset, ["Alice", "Bob"])

        all_cards = []
        for p in game.players:
            all_cards.extend(p.influence)
        all_cards.extend(game.deck.cards)

        self.assertEqual(len(all_cards), 15)
        for card in VALID_CARDS:
            self.assertEqual(all_cards.count(card), 3)

    def test_preset_game_one_card_per_player(self):
        """When players have 1 card each, remaining cards total correctly."""
        preset = {
            "players": {
                "Alice": {"hand": ["Duke"], "coins": 5},
                "Bob": {"hand": ["Assassin"], "coins": 5},
            },
        }
        game = build_preset_game(preset, ["Alice", "Bob"])

        all_cards = []
        for p in game.players:
            all_cards.extend(p.influence)
        all_cards.extend(game.deck.cards)

        self.assertEqual(len(all_cards), 15)

    def test_three_player_preset(self):
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 2},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 3},
                "Charlie": {"hand": ["Ambassador", "Duke"], "coins": 4},
            },
        }
        game = build_preset_game(preset, ["Alice", "Bob", "Charlie"])

        self.assertEqual(len(game.players), 3)
        self.assertEqual(game.players[2].name, "Charlie")
        self.assertEqual(game.players[2].influence, ["Ambassador", "Duke"])
        self.assertEqual(game.players[2].coins, 4)
        # 15 - 6 = 9 cards in deck
        self.assertEqual(len(game.deck.cards), 9)

    def test_preset_game_plays_normally(self):
        """A preset game should work with the normal Game methods."""
        preset = {
            "players": {
                "Alice": {"hand": ["Duke", "Captain"], "coins": 7},
                "Bob": {"hand": ["Assassin", "Contessa"], "coins": 2},
            },
        }
        game = build_preset_game(preset, ["Alice", "Bob"])

        # Verify game methods work
        targets = game.get_valid_targets(game.players[0])
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].name, "Bob")

        living = game.get_living_players()
        self.assertEqual(len(living), 2)

        # Simulate losing influence
        game.lose_influence(game.players[1], "Assassin")
        self.assertEqual(game.players[1].influence, ["Contessa"])
        self.assertIn("Assassin", game.revealed_cards)


if __name__ == "__main__":
    unittest.main()
