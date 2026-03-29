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
            while True:
                print(f"{player.name}, choose which influence to lose:")
                for i, card in enumerate(player.influence):
                    print(f"  {i + 1}: {card}")
                try:
                    idx = int(input()) - 1
                    if 0 <= idx < len(player.influence):
                        break
                except ValueError:
                    pass
                print("Invalid input. Please try again.")
            lost = player.influence[idx]
        player.lose_influence(lost)
        self.revealed_cards.append(lost)
        print(f"{player.name} lost {lost}.")

    def attempt_block(self, acting_player, target_player, blockable_cards):
        """Prompt eligible players to block an action.
        If target_player is None, any player can block (e.g., Foreign Aid blocked by Duke).
        If target_player is set, only that player can block (e.g., Steal, Assassinate).
        Returns True if the action was successfully blocked."""
        if target_player:
            eligible = [target_player] if target_player.is_alive() else []
        else:
            eligible = [p for p in self.players if p != acting_player and p.is_alive()]

        for player in eligible:
            while True:
                print(f"{player.name}, do you want to block {acting_player.name}'s action?")
                print(f"  0: Don't block")
                for i, card in enumerate(blockable_cards):
                    print(f"  {i + 1}: Block with {card}")
                try:
                    choice = int(input())
                    if 0 <= choice <= len(blockable_cards):
                        break
                except ValueError:
                    pass
                print("Invalid input. Please try again.")
            if choice == 0:
                continue

            claimed_card = blockable_cards[choice - 1]
            print(f"{player.name} claims {claimed_card} to block!")

            # The block itself can be challenged
            block_challenged = self.challenge(player, claimed_card)
            if block_challenged:
                # Block was successfully challenged — action proceeds
                return False
            else:
                # Block stands
                print(f"{acting_player.name}'s action was blocked!")
                return True

        return False

    def challenge(self, acting_player, claimed_card):
        """Prompt all other living players to call BS on the acting player's claim.
        Returns True if the action was blocked by a successful challenge."""
        for player in self.players:
            if player == acting_player or not player.is_alive():
                continue
            while True:
                resp = input(f"{player.name}, do you want to call BS on {acting_player.name}'s {claimed_card}? (y/n): ")
                if resp.lower() in ('y', 'n'):
                    break
                print("Invalid input. Please enter 'y' or 'n'.")
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
        if player.coins > 10:
            print("More than 10 coins. You must Coup.")
            Action(self, player, 7)
            return

        if player.coins < 3:
            max_choice = 5
        elif player.coins < 7:
            max_choice = 6
        else:
            max_choice = 7

        while True:
            print(f"Type 1 to Income")
            print(f"Type 2 to Foreign Aid")
            print(f"Type 3 to Tax")
            print(f"Type 4 to Steal")
            print(f"Type 5 to Exchange")
            if max_choice >= 6:
                print(f"Type 6 to Assassinate")
            if max_choice >= 7:
                print(f"Type 7 to Coup")
            try:
                choice = int(input())
                if 1 <= choice <= max_choice:
                    break
            except ValueError:
                pass
            print("Invalid input. Please try again.")

        Action(self, player, choice)
    
def main():
    players = []
    
    while True:
        print("Please enter number of players (2-6):")
        try:
            num_players = int(input())
            if 2 <= num_players <= 6:
                break
        except ValueError:
            pass
        print("Invalid input. Please enter a number between 2 and 6.")

    for i in range(num_players):
        while True:
            print(f"Please enter name of player {i+1}:")
            name = input().strip()
            if name:
                break
            print("Invalid input. Name cannot be empty. Please try again.")
        player = Player(name)
        players.append(player)
        
    print("Let's deal")
    
    game = Game(players)
    
    print("Initial cards dealt:")
    for player in game.players:
        print(f"{player.name}: {player.influence}")
    for card in game.deck.cards:
        print(f"Court Deck: {card}")

    while True:
        living_players = [p for p in game.players if p.is_alive()]
        if len(living_players) == 1:
            print(f"{living_players[0].name} wins!")
            break
        for player in game.players:
            if player.is_alive():
                game.play_turn(player)
                # Check for winner after each turn
                living_players = [p for p in game.players if p.is_alive()]
                if len(living_players) == 1:
                    break

if __name__ =="__main__":
    main()