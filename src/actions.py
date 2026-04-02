"""Pure action functions for Coup. No I/O — just mutate game state."""


def do_income(game, player):
    player.coins += 1


def do_foreign_aid(game, player):
    player.coins += 2


def do_tax(game, player):
    player.coins += 3


def do_steal(game, player, target):
    stolen = min(2, target.coins)
    target.coins -= stolen
    player.coins += stolen
    return stolen



def do_exchange_draw(game, player):
    """Draw 2 cards from the deck into the player's hand."""
    player.add_influence(game.deck.draw())
    player.add_influence(game.deck.draw())


def do_exchange_return(game, player, card_name):
    """Return one card from the player's hand to the deck."""
    player.lose_influence(card_name)
    game.deck.return_card(card_name)
