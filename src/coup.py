##Duke 
##Assassin
##Captain
##Contessa
##Ambassador


from src.player import Player
from src.deck import Deck
from src.actions import Action
    
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
    
    def lose_influence(self, player):
        if len(player.influence) == 1:
            lost = player.influence[0]
        else:
            print(f"{player.name}, choose which influence to lose:")
            for i, card in enumerate(player.influence):
                print(f"  {i + 1}: {card}")
            idx = int(input()) - 1
            lost = player.influence[idx]
        player.lose_influence(lost)
        self.revealed_cards.append(lost)
        print(f"{player.name} lost {lost}.")

    def challenge(self, acting_player, claimed_card):
        """Prompt all other living players to call BS on the acting player's claim.
        Returns True if the action was blocked by a successful challenge."""
        for player in self.players:
            if player == acting_player or not player.is_alive():
                continue
            resp = input(f"{player.name}, do you want to call BS on {acting_player.name}'s {claimed_card}? (y/n): ")
            if resp.lower() == 'y':
                if acting_player.has_influence(claimed_card):
                    print(f"{acting_player.name} reveals {claimed_card}. Challenge fails!")
                    acting_player.lose_influence(claimed_card)
                    self.deck.return_card(claimed_card)
                    acting_player.add_influence(self.deck.draw())
                    self.lose_influence(player)
                    return False
                else:
                    print(f"{acting_player.name} does not have {claimed_card}. Challenge succeeds!")
                    self.lose_influence(acting_player)
                    return True
        return False

    def play_turn(self, player):
        print(f"{player.name}'s turn. Coins: {player.coins}, Influence: {player.influence}")
        if player.coins < 3:
            print("Type 1 to Income"
                  "Type 2 to Foreign Aid"
                  "Type 3 to Tax"
                  "Type 4 to Steal"
                  "Type 5 to Exchange")
            choice = int(input())
        elif player.coins >= 3 and player.coins < 7:
            print("Type 1 to Income"
                  "Type 2 to Foreign Aid"
                  "Type 3 to Tax"
                  "Type 4 to Steal"
                  "Type 5 to Exchange"
                  "Type 6 to Assassinate")
            choice = int(input())
        elif player.coins >= 7 and player.coins <= 10:
            print("Type 1 to Income"
                  "Type 2 to Foreign Aid"
                  "Type 3 to Tax"
                  "Type 4 to Steal"
                  "Type 5 to Exchange"
                  "Type 6 to Assassinate"
                  "Type 7 to Coup")
            choice = int(input())
        elif player.coins > 10:
            print("More than 10 coins. You must Coup.")
            choice = 7
            
        Action(self, player, choice)
    
def main():
    players = []
    
    print("Please enter number of players:")
    num_players = int(input())
    if num_players > 6:
        print("Maximum number of players is 6. Defaulting to 6 players.")
        num_players = 6
        
    if num_players < 1:
        print("Minimum number of players is 1. Defaulting to 1 player.")
        num_players = 1

    for i in range(num_players):
        print(f"Please enter name of player {i+1}:")
        name = input()
        player = Player(name)
        players.append(player)
    for i in range(6-num_players):
        players.append(Player(f"Bot {i+1}"))
        
    print("Let's deal")
    
    game = Game(players)
    
    print("Initial cards dealt:")
    for player in game.players:
        print(f"{player.name}: {player.influence}")
    for card in game.deck.cards:
        print(f"Court Deck: {card}")
        
    
        
if __name__ =="__main__":
    main()