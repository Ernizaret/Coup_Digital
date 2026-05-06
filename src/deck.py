import random

class Deck:
    def __init__(self, rng=None):
        self.cards = ["Duke", "Assassin", "Captain", "Contessa", "Ambassador"] * 3
        self._rng = rng if rng is not None else random.Random()

    def draw(self):
        if len(self.cards) > 0:
            return self.cards.pop(self._rng.randint(0, len(self.cards)-1))
        else:
            return None
    
    def return_card(self, card):
        self.cards.append(card)