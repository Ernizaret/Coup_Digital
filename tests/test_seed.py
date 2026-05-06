"""Tests for the game seed system — deterministic randomness via seeded PRNG."""

import random
import unittest
from src.player import Player
from src.deck import Deck
from src.coup import Game


class TestDeckWithSeededRNG(unittest.TestCase):
    """Test that Deck with a seeded RNG produces deterministic draws."""

    def test_seeded_deck_deterministic_draws(self):
        """Two decks with the same seeded RNG produce identical draw sequences."""
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        deck1 = Deck(rng=rng1)
        deck2 = Deck(rng=rng2)

        draws1 = [deck1.draw() for _ in range(15)]
        draws2 = [deck2.draw() for _ in range(15)]
        self.assertEqual(draws1, draws2)

    def test_different_seeds_different_draws(self):
        """Two decks with different seeds produce different draw sequences
        (with very high probability)."""
        different_count = 0
        for seed_a, seed_b in [(1, 2), (100, 200), (999, 1000)]:
            rng1 = random.Random(seed_a)
            rng2 = random.Random(seed_b)
            deck1 = Deck(rng=rng1)
            deck2 = Deck(rng=rng2)
            draws1 = [deck1.draw() for _ in range(15)]
            draws2 = [deck2.draw() for _ in range(15)]
            if draws1 != draws2:
                different_count += 1
        # At least 2 out of 3 should be different
        self.assertGreaterEqual(different_count, 2)

    def test_seeded_deck_with_custom_cards(self):
        """Seeded RNG works with custom card lists too."""
        cards = ["Duke", "Captain", "Assassin"]
        rng1 = random.Random(123)
        rng2 = random.Random(123)
        deck1 = Deck(cards=cards, rng=rng1)
        deck2 = Deck(cards=cards, rng=rng2)

        draws1 = [deck1.draw() for _ in range(3)]
        draws2 = [deck2.draw() for _ in range(3)]
        self.assertEqual(draws1, draws2)

    def test_default_deck_uses_random(self):
        """A deck created without rng still works (backwards compatibility)."""
        deck = Deck()
        card = deck.draw()
        self.assertIn(card, ["Duke", "Assassin", "Captain", "Contessa", "Ambassador"])
        self.assertEqual(len(deck.cards), 14)

    def test_return_card_and_redraw_deterministic(self):
        """Return a card and redraw — still deterministic with same seed."""
        rng1 = random.Random(77)
        rng2 = random.Random(77)
        deck1 = Deck(rng=rng1)
        deck2 = Deck(rng=rng2)

        # Draw, return, draw again
        card1_a = deck1.draw()
        card1_b = deck2.draw()
        self.assertEqual(card1_a, card1_b)

        deck1.return_card(card1_a)
        deck2.return_card(card1_b)

        card2_a = deck1.draw()
        card2_b = deck2.draw()
        self.assertEqual(card2_a, card2_b)


class TestGameWithSeed(unittest.TestCase):
    """Test that Game with a seed produces deterministic initial deals."""

    def _make_players(self, names=None):
        names = names or ["Alice", "Bob"]
        return [Player(n) for n in names]

    def test_seed_stored_on_game(self):
        """The seed is stored as game.seed."""
        players = self._make_players()
        game = Game(players, seed=12345)
        self.assertEqual(game.seed, 12345)

    def test_auto_generated_seed(self):
        """When no seed is provided, a seed is auto-generated and stored."""
        players = self._make_players()
        game = Game(players)
        self.assertIsInstance(game.seed, int)
        self.assertGreaterEqual(game.seed, 0)
        self.assertLessEqual(game.seed, 2**32 - 1)

    def test_same_seed_same_deal(self):
        """Two games with the same seed produce identical initial card deals."""
        players1 = self._make_players()
        players2 = self._make_players()
        game1 = Game(players1, seed=42)
        game2 = Game(players2, seed=42)

        for p1, p2 in zip(game1.players, game2.players):
            self.assertEqual(p1.influence, p2.influence)

        self.assertEqual(len(game1.deck.cards), len(game2.deck.cards))
        # The remaining deck cards should be identical
        self.assertEqual(sorted(game1.deck.cards), sorted(game2.deck.cards))

    def test_same_seed_same_deal_three_players(self):
        """Deterministic deals work with more than 2 players."""
        names = ["Alice", "Bob", "Charlie"]
        players1 = [Player(n) for n in names]
        players2 = [Player(n) for n in names]
        game1 = Game(players1, seed=999)
        game2 = Game(players2, seed=999)

        for p1, p2 in zip(game1.players, game2.players):
            self.assertEqual(p1.influence, p2.influence)

    def test_different_seeds_different_deals(self):
        """Two games with different seeds produce different deals
        (with very high probability)."""
        different_count = 0
        for seed_a, seed_b in [(1, 2), (100, 200), (999, 1000)]:
            p1 = self._make_players()
            p2 = self._make_players()
            game1 = Game(p1, seed=seed_a)
            game2 = Game(p2, seed=seed_b)
            hands1 = [p.influence[:] for p in game1.players]
            hands2 = [p.influence[:] for p in game2.players]
            if hands1 != hands2:
                different_count += 1
        self.assertGreaterEqual(different_count, 2)

    def test_backwards_compat_no_seed(self):
        """Game without seed still works and deals cards normally."""
        players = self._make_players()
        game = Game(players)
        for p in game.players:
            self.assertEqual(len(p.influence), 2)
        # 15 - 4 dealt = 11 remaining
        self.assertEqual(len(game.deck.cards), 11)

    def test_skip_deal_with_seed(self):
        """seed + skip_deal: no cards dealt, but seed and rng are set."""
        players = self._make_players()
        game = Game(players, skip_deal=True, seed=42)
        self.assertEqual(game.seed, 42)
        for p in game.players:
            self.assertEqual(len(p.influence), 0)
        self.assertEqual(len(game.deck.cards), 15)

    def test_deck_cards_with_seed(self):
        """seed + deck_cards: custom deck is used with seeded RNG."""
        players = self._make_players()
        custom_cards = ["Duke", "Duke", "Captain", "Captain"]
        game = Game(players, deck_cards=custom_cards, seed=42)
        self.assertEqual(game.seed, 42)
        # All custom cards should have been dealt (4 cards, 2 players)
        self.assertEqual(len(game.deck.cards), 0)
        for p in game.players:
            self.assertEqual(len(p.influence), 2)

    def test_resolve_challenge_deterministic(self):
        """Card replacement after challenge is deterministic with seed."""
        players1 = self._make_players()
        players2 = self._make_players()
        game1 = Game(players1, seed=42)
        game2 = Game(players2, seed=42)

        # Force both games to the same state
        acting1, challenger1 = game1.players
        acting2, challenger2 = game2.players

        # Both should have the same cards
        self.assertEqual(acting1.influence, acting2.influence)
        card = acting1.influence[0]

        # Resolve challenge on both
        result1 = game1.resolve_challenge(acting1, card, challenger1)
        result2 = game2.resolve_challenge(acting2, card, challenger2)

        self.assertEqual(result1[0], result2[0])
        # After challenge, acting player drew a replacement — should be same
        self.assertEqual(acting1.influence, acting2.influence)


class TestGameRNGIsolation(unittest.TestCase):
    """Test that the game's PRNG is isolated from global random state."""

    def test_global_random_does_not_affect_game(self):
        """Seeded game is not affected by global random.random() calls."""
        # Game 1: no global random interference
        players1 = self._make_players()
        game1 = Game(players1, seed=42)

        # Game 2: call global random between construction
        random.seed(999)
        random.random()
        random.random()
        players2 = self._make_players()
        game2 = Game(players2, seed=42)

        for p1, p2 in zip(game1.players, game2.players):
            self.assertEqual(p1.influence, p2.influence)

    def _make_players(self, names=None):
        names = names or ["Alice", "Bob"]
        return [Player(n) for n in names]


if __name__ == "__main__":
    unittest.main()
