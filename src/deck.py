import random

class Deck:
    def __init__(self):
        self.cards = ["Duke", "Assassin", "Captain", "Contessa", "Ambassador"] * 3
    
    def draw(self):
        if len(self.cards) > 0:
            return self.cards.pop(random.randint(0, len(self.cards)-1))
        else:
            return None
    
    def return_card(self, card):
        self.cards.append(card)