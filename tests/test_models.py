"""Tests for data model classes: Player, Deck, Game."""

import unittest
from src.player import Player
from src.deck import Deck
from src.coup import Game


class TestPlayer(unittest.TestCase):
    def test_initial_state(self):
        p = Player("Alice")
        self.assertEqual(p.name, "Alice")
        self.assertEqual(p.coins, 2)
        self.assertEqual(p.influence, [])

    def test_add_influence(self):
        p = Player("Alice")
        p.add_influence("Duke")
        self.assertEqual(p.influence, ["Duke"])
        p.add_influence("Captain")
        self.assertEqual(p.influence, ["Duke", "Captain"])

    def test_lose_influence(self):
        p = Player("Alice")
        p.add_influence("Duke")
        p.add_influence("Captain")
        p.lose_influence("Duke")
        self.assertEqual(p.influence, ["Captain"])

    def test_lose_influence_not_held(self):
        p = Player("Alice")
        p.add_influence("Duke")
        p.lose_influence("Captain")
        self.assertEqual(p.influence, ["Duke"])

    def test_has_influence(self):
        p = Player("Alice")
        p.add_influence("Duke")
        self.assertTrue(p.has_influence("Duke"))
        self.assertFalse(p.has_influence("Captain"))

    def test_is_alive(self):
        p = Player("Alice")
        self.assertFalse(p.is_alive())
        p.add_influence("Duke")
        self.assertTrue(p.is_alive())
        p.lose_influence("Duke")
        self.assertFalse(p.is_alive())


class TestDeck(unittest.TestCase):
    def test_initial_size(self):
        d = Deck()
        self.assertEqual(len(d.cards), 15)

    def test_initial_composition(self):
        d = Deck()
        for card in ["Duke", "Assassin", "Captain", "Contessa", "Ambassador"]:
            self.assertEqual(d.cards.count(card), 3)

    def test_draw_reduces_size(self):
        d = Deck()
        card = d.draw()
        self.assertIsNotNone(card)
        self.assertEqual(len(d.cards), 14)

    def test_draw_returns_valid_card(self):
        d = Deck()
        card = d.draw()
        self.assertIn(card, ["Duke", "Assassin", "Captain", "Contessa", "Ambassador"])

    def test_draw_empty_deck(self):
        d = Deck()
        d.cards = []
        self.assertIsNone(d.draw())

    def test_return_card(self):
        d = Deck()
        d.cards = []
        d.return_card("Duke")
        self.assertEqual(d.cards, ["Duke"])


class TestGame(unittest.TestCase):
    def _make_game(self, names=None):
        names = names or ["Alice", "Bob"]
        players = [Player(n) for n in names]
        return Game(players)

    def test_deal_initial_cards(self):
        game = self._make_game()
        for p in game.players:
            self.assertEqual(len(p.influence), 2)
        # 15 - 4 dealt = 11 remaining
        self.assertEqual(len(game.deck.cards), 11)

    def test_deal_three_players(self):
        game = self._make_game(["A", "B", "C"])
        for p in game.players:
            self.assertEqual(len(p.influence), 2)
        self.assertEqual(len(game.deck.cards), 9)

    def test_lose_influence(self):
        game = self._make_game()
        p = game.players[0]
        card = p.influence[0]
        game.lose_influence(p, card)
        self.assertEqual(len(p.influence), 1)
        self.assertIn(card, game.revealed_cards)

    def test_resolve_challenge_player_has_card(self):
        game = self._make_game()
        acting = game.players[0]
        challenger = game.players[1]
        # Force a known card
        acting.influence = ["Duke", "Captain"]
        deck_size_before = len(game.deck.cards)

        succeeded, loser = game.resolve_challenge(acting, "Duke", challenger)
        self.assertFalse(succeeded)
        self.assertIs(loser, challenger)
        # Acting player returned Duke and drew a new card — still has 2 cards
        self.assertEqual(len(acting.influence), 2)
        # Deck size unchanged (returned 1, drew 1)
        self.assertEqual(len(game.deck.cards), deck_size_before)

    def test_resolve_challenge_player_bluffing(self):
        game = self._make_game()
        acting = game.players[0]
        challenger = game.players[1]
        acting.influence = ["Captain", "Contessa"]

        succeeded, loser = game.resolve_challenge(acting, "Duke", challenger)
        self.assertTrue(succeeded)
        self.assertIs(loser, acting)
        # No card swap happens
        self.assertEqual(acting.influence, ["Captain", "Contessa"])

    def test_get_valid_targets(self):
        game = self._make_game(["A", "B", "C"])
        acting = game.players[0]
        targets = game.get_valid_targets(acting)
        self.assertEqual(len(targets), 2)
        self.assertNotIn(acting, targets)

    def test_get_valid_targets_excludes_dead(self):
        game = self._make_game(["A", "B", "C"])
        game.players[1].influence = []
        targets = game.get_valid_targets(game.players[0])
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].name, "C")

    def test_get_living_players(self):
        game = self._make_game(["A", "B", "C"])
        game.players[1].influence = []
        living = game.get_living_players()
        self.assertEqual(len(living), 2)
        names = [p.name for p in living]
        self.assertIn("A", names)
        self.assertIn("C", names)


if __name__ == "__main__":
    unittest.main()
