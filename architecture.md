**player.py — Player data model**

Pure data container for a single player. Tracks their name, coins (starts at 2), and influence (list of card strings). Provides simple methods: add_influence(), lose_influence(), has_influence(), and is_alive() (true if they still have cards). No game logic, no I/O.

**deck.py — Deck data model**

Represents the court deck: 15 cards (3 each of Duke, Assassin, Captain, Contessa, Ambassador). draw() removes and returns a random card, return_card() puts one back. That's it — just a shuffleable card pile.

**actions.py — Pure action functions**

One function per game action (do_income, do_foreign_aid, do_tax, do_steal, do_exchange_draw, do_exchange_return, etc.). Each takes the game and player (and target where needed) and directly mutates state — adding/removing coins, drawing cards. They contain no decision-making (no challenge/block logic) and no I/O. The controller decides when to call them.

**coup.py — Game state container**

The Game class holds the shared game state: the list of players, the deck, and revealed_cards. It also provides three helper methods that need access to that shared state:
- lose_influence(player, card_name) — removes a specific card from a player and adds it to the revealed pile.
- resolve_challenge(acting_player, claimed_card, challenger) — checks if the acting player actually has the claimed card, handles the card swap if they do, and returns who lost.
- get_valid_targets() / get_living_players() — convenience filters over the player list.

No game loop, no I/O. It's a data container with helpers.

**controller.py — State machine (the brain)**

This is the bridge between the UI and the game logic. GameController replaces the old main() game loop with an event-driven state machine. It tracks which of 11 states the game is in (setup, choose action, choose target, challenge query, block query, lose influence, exchange return, game over, etc.) and exposes exactly two methods:
- get_prompt() — returns (message_string, list_of_options) describing what the UI should display right now.
- handle_input(value) — accepts the player's choice (a button click or text entry), updates game state by calling into coup.py and actions.py, and advances to the next state.

It manages the full flow: turn order, cost deduction, challenge walks (asking each player one by one), block offers, nested challenge-on-block, exchange card returns, and win detection.

**ui.py — Tkinter frontend**

The visual layer. It creates a window with three sections:
1. Player panels (top) — one box per player showing name, coins, and cards. Current player is highlighted in blue, eliminated players are grayed out. A "Revealed" panel shows discarded cards.
2. Prompt area (middle) — displays the current prompt text and dynamically generates buttons from get_prompt() options. Switches to a text entry field during player name setup.
3. Game log (bottom) — scrollable text showing everything that's happened.

On every button click, it calls controller.handle_input(value) then refresh() to re-render everything. It contains zero game logic — it just reads and renders controller state.
