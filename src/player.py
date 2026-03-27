class Player:
    def __init__(self, name):
        self.name = name
        self.coins = 2
        self.influence = []
    
    def add_influence(self, card):
        self.influence.append(card)
    
    def lose_influence(self, card):
        if card in self.influence:
            self.influence.remove(card)
    
    def has_influence(self, card):
        return card in self.influence
    
    def is_alive(self):
        return len(self.influence) > 0