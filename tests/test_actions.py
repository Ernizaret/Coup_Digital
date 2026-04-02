"""Tests for pure action functions."""

import unittest
from src.player import Player
from src.coup import Game
from src import actions


class ActionTestBase(unittest.TestCase):
    def _make_game(self, names=None):
        names = names or ["Alice", "Bob"]
        players = [Player(n) for n in names]
        return Game(players)


class TestDoIncome(ActionTestBase):
    def test_adds_one_coin(self):
        game = self._make_game()
        p = game.players[0]
        p.coins = 5
        actions.do_income(game, p)
        self.assertEqual(p.coins, 6)


class TestDoForeignAid(ActionTestBase):
    def test_adds_two_coins(self):
        game = self._make_game()
        p = game.players[0]
        p.coins = 0
        actions.do_foreign_aid(game, p)
        self.assertEqual(p.coins, 2)


class TestDoTax(ActionTestBase):
    def test_adds_three_coins(self):
        game = self._make_game()
        p = game.players[0]
        p.coins = 1
        actions.do_tax(game, p)
        self.assertEqual(p.coins, 4)


class TestDoSteal(ActionTestBase):
    def test_steal_two_coins(self):
        game = self._make_game()
        thief = game.players[0]
        victim = game.players[1]
        thief.coins = 0
        victim.coins = 5
        stolen = actions.do_steal(game, thief, victim)
        self.assertEqual(stolen, 2)
        self.assertEqual(thief.coins, 2)
        self.assertEqual(victim.coins, 3)

    def test_steal_from_player_with_one_coin(self):
        game = self._make_game()
        thief = game.players[0]
        victim = game.players[1]
        thief.coins = 0
        victim.coins = 1
        stolen = actions.do_steal(game, thief, victim)
        self.assertEqual(stolen, 1)
        self.assertEqual(thief.coins, 1)
        self.assertEqual(victim.coins, 0)

    def test_steal_from_player_with_zero_coins(self):
        game = self._make_game()
        thief = game.players[0]
        victim = game.players[1]
        thief.coins = 3
        victim.coins = 0
        stolen = actions.do_steal(game, thief, victim)
        self.assertEqual(stolen, 0)
        self.assertEqual(thief.coins, 3)
        self.assertEqual(victim.coins, 0)


class TestDoExchange(ActionTestBase):
    def test_exchange_draw_adds_two_cards(self):
        game = self._make_game()
        p = game.players[0]
        initial_count = len(p.influence)
        actions.do_exchange_draw(game, p)
        self.assertEqual(len(p.influence), initial_count + 2)

    def test_exchange_return_removes_card(self):
        game = self._make_game()
        p = game.players[0]
        p.influence = ["Duke", "Captain", "Contessa", "Ambassador"]
        deck_size = len(game.deck.cards)
        actions.do_exchange_return(game, p, "Captain")
        self.assertEqual(len(p.influence), 3)
        self.assertNotIn("Captain", p.influence)
        self.assertEqual(len(game.deck.cards), deck_size + 1)


if __name__ == "__main__":
    unittest.main()
