##Actions:
##Income: Gain 1 coin.
##Foreign Aid: Gain 2 coins.
##Coup: Spend 7 coins to remove an influence from another player.
##Tax: Gain 3 coins.
##Assassinate: Spend 3 coins to remove an influence from another player.
##Steal: Remove at most 2 coins from another player. Gain coins equal to amount removed from another player.
##Exchange: Gain two influence. Lose two influence of your choosing.

class Action:
    def __init__(self, game, player, choice):
        self.game = game
        actions = {1: self.income,
                  2: self.foreign_aid,
                  3: self.tax,
                  4: self.steal,
                  5: self.exchange,
                  6: self.assassinate,
                  7: self.coup}
        action = actions.get(choice)
        if action:
            action(player)

    def income(self, player):
        print(f"{player.name} takes Income.")
        player.coins += 1

    def foreign_aid(self, player):
        print(f"{player.name} attempts to take Foreign Aid.")
        player.coins += 2

    def tax(self, player):
        claimed_card = "Duke"
        print(f"{player.name} claims {claimed_card}.")
        blocked = self.game.challenge(player, claimed_card)
        if not blocked:
            player.coins += 3

    def steal(self, player):
        claimed_card = "Captain"
        print(f"{player.name} claims {claimed_card}.")

        print("Choose a player to steal from:")
        for i, p in enumerate(self.game.players):
            if p != player and p.is_alive():
                print(f"{i}: {p.name} (Coins: {p.coins})")
        target_index = int(input())
        target_player = self.game.players[target_index]

        if target_player.coins == 0:
            print(f"{target_player.name} has no coins to steal. Please choose another player.")
            return

        blocked = self.game.challenge(player, claimed_card)
        if not blocked:
            if target_player.coins == 1: stolen_coins = 1
            else: stolen_coins = 2

            target_player.coins -= stolen_coins
            player.coins += stolen_coins
            print(f"{player.name} stole {stolen_coins} coins from {target_player.name}.")

    def exchange(self, player):
        claimed_card = "Ambassador"
        print(f"{player.name} claims {claimed_card}.")

        blocked = self.game.challenge(player, claimed_card)
        if not blocked:
            player.add_influence(self.game.deck.draw())
            player.add_influence(self.game.deck.draw())

            print("Choose two cards to return:")
            for i, card in enumerate(player.influence):
                print(f"{i}: {card}")

            lose_index_1 = int(input())
            lost_card_1 = player.influence[lose_index_1]
            player.lose_influence(lost_card_1)
            self.game.deck.return_card(lost_card_1)
            print(f"{lost_card_1} has been returned to the court deck.")

            for i, card in enumerate(player.influence):
                print(f"{i}: {card}")

            lose_index_2 = int(input())
            lost_card_2 = player.influence[lose_index_2]
            player.lose_influence(lost_card_2)
            self.game.deck.return_card(lost_card_2)
            print(f"{lost_card_2} has been returned to the court deck.")

    def assassinate(self, player):
        player.coins -= 3
        claimed_card = "Assassin"
        print(f"{player.name} claims {claimed_card}.")

        print("Choose a player to assassinate:")
        for i, p in enumerate(self.game.players):
            if p != player and p.is_alive():
                print(f"{i}: {p.name}")
        target_index = int(input())
        target_player = self.game.players[target_index]

        blocked = self.game.challenge(player, claimed_card)
        if not blocked:
            self.game.lose_influence(target_player)

    def coup(self, player):
        player.coins -= 7

        print("Choose a player to coup:")
        for i, p in enumerate(self.game.players):
            if p != player and p.is_alive():
                print(f"{i}: {p.name}")
        target_index = int(input())
        target_player = self.game.players[target_index]

        self.game.lose_influence(target_player)
