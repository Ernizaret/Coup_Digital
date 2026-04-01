**player.py — Player data model**



&#x20; Pure data container for a single player. Tracks their name, coins (starts at 2), and influence (list of card strings). Provides simple methods: add\_influence(), lose\_influence(), has\_influence(), and

&#x20; is\_alive() (true if they still have cards). No game logic, no I/O.



**deck.py — Deck data model**



&#x20; Represents the court deck: 15 cards (3 each of Duke, Assassin, Captain, Contessa, Ambassador). draw() removes and returns a random card, return\_card() puts one back. That's it — just a shuffleable card pile.



**actions.py — Pure action functions**



&#x20; One function per game action (do\_income, do\_foreign\_aid, do\_tax, do\_steal, do\_exchange\_draw, do\_exchange\_return, etc.). Each takes the game and player (and target where needed) and directly mutates state —

&#x20; adding/removing coins, drawing cards. They contain no decision-making (no challenge/block logic) and no I/O. The controller decides when to call them.



**coup.py — Game state container**



&#x20; The Game class holds the shared game state: the list of players, the deck, and revealed\_cards. It also provides three helper methods that need access to that shared state:

&#x20; - lose\_influence(player, card\_name) — removes a specific card from a player and adds it to the revealed pile.

&#x20; - resolve\_challenge(acting\_player, claimed\_card, challenger) — checks if the acting player actually has the claimed card, handles the card swap if they do, and returns who lost.

&#x20; - get\_valid\_targets() / get\_living\_players() — convenience filters over the player list.



&#x20; No game loop, no I/O. It's a data container with helpers.



**controller.py — State machine (the brain)**



&#x20; This is the bridge between the UI and the game logic. GameController replaces the old main() game loop with an event-driven state machine. It tracks which of 11 states the game is in (setup, choose action,

&#x20; choose target, challenge query, block query, lose influence, exchange return, game over, etc.) and exposes exactly two methods:

&#x20; - get\_prompt() — returns (message\_string, list\_of\_options) describing what the UI should display right now.

&#x20; - handle\_input(value) — accepts the player's choice (a button click or text entry), updates game state by calling into coup.py and actions.py, and advances to the next state.



&#x20; It manages the full flow: turn order, cost deduction, challenge walks (asking each player one by one), block offers, nested challenge-on-block, exchange card returns, and win detection.



**UI.py — Tkinter frontend**



&#x20; The visual layer. It creates a window with three sections:

&#x20; 1. Player panels (top) — one box per player showing name, coins, and cards. Current player is highlighted in blue, eliminated players are grayed out. A "Revealed" panel shows discarded cards.

&#x20; 2. Prompt area (middle) — displays the current prompt text and dynamically generates buttons from get\_prompt() options. Switches to a text entry field during player name setup.

&#x20; 3. Game log (bottom) — scrollable text showing everything that's happened.



&#x20; On every button click, it calls controller.handle\_input(value) then refresh() to re-render everything. It contains zero game logic — it just reads and renders controller state.

