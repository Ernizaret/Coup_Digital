from src.player import Player
from src.deck import Deck


class Game:
    def __init__(self, players):
        self.players = players
        self.deck = Deck()
        self.revealed_cards = []
        self.deal_initial_cards()

    def deal_initial_cards(self):
        for player in self.players:
            card1 = self.deck.draw()
            card2 = self.deck.draw()
            player.add_influence(card1)
            player.add_influence(card2)

    def lose_influence(self, player, card_name):
        """Remove a specific card from a player's influence and reveal it."""
        player.lose_influence(card_name)
        self.revealed_cards.append(card_name)

    def resolve_challenge(self, acting_player, claimed_card, challenger):
        """Resolve a challenge. Returns (challenge_succeeded, loser).

        If the acting player has the card: challenge fails, challenger loses.
        The acting player's card is returned to the deck and they draw a new one.

        If the acting player doesn't have the card: challenge succeeds, acting player loses.
        """
        if acting_player.has_influence(claimed_card):
            # Challenge fails — acting player had the card
            acting_player.lose_influence(claimed_card)
            self.deck.return_card(claimed_card)
            acting_player.add_influence(self.deck.draw())
            return (False, challenger)
        else:
            # Challenge succeeds — acting player was bluffing
            return (True, acting_player)

    def get_valid_targets(self, acting_player):
        """Return list of living players other than the acting player."""
        return [p for p in self.players if p != acting_player and p.is_alive()]

    def get_living_players(self):
        """Return list of all living players."""
        return [p for p in self.players if p.is_alive()]
