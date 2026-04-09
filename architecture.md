# Architecture

## Program Overview

Coup is a bluffing card game where players take economic and aggressive actions (Income, Foreign Aid, Tax, Steal, Assassinate, Coup, Exchange) backed by claims about the two hidden "influence" cards they hold. Any claim can be challenged, and most actions can be blocked by players claiming a counter-card. Lying is legal — but being caught costs you a card, and losing both cards eliminates you. The last player with influence wins.

This project is a local, hot-seat digital implementation. The game runs as a Python program with a Tkinter GUI: one **setup window** collects the number of players and their names, then spawns **one window per player** so each player can see only their own cards while everyone shares a common game log. All game logic lives in a central `GameController` state machine, and every button press flows through its `handle_input()` method. The program uses only the Python standard library — no external dependencies.

Entry point: `python -m src.ui`

## Layered Design

The code is split into five clean layers. Each layer only depends on the ones below it:

```
ui.py            <- Tkinter frontend (rendering only)
  ↓
controller.py    <- state machine (game flow, decisions)
  ↓
actions.py       <- pure action functions (state mutations)
  ↓
coup.py          <- shared game state + helpers
  ↓
player.py, deck.py  <- leaf data models
```

---

## `src/player.py` — Player data model

Pure data container for a single player. Tracks their `name`, `coins` (starts at 2), and `influence` (list of card-name strings — typically two face-down cards in hand). Provides simple methods: `add_influence()`, `lose_influence()`, `has_influence()`, and `is_alive()` (true if they still have any cards). No game logic, no I/O.

## `src/deck.py` — Deck data model

Represents the court deck: 15 cards (3 each of Duke, Assassin, Captain, Contessa, Ambassador). `draw()` removes and returns a random card (uniform over remaining cards — equivalent to drawing from a shuffled deck). `return_card()` puts one back. That's it — just a shuffleable card pile.

## `src/actions.py` — Pure action functions

One function per mechanical game action:

- `do_income(game, player)` — +1 coin
- `do_foreign_aid(game, player)` — +2 coins
- `do_tax(game, player)` — +3 coins
- `do_steal(game, player, target)` — moves up to 2 coins from target to player, returns the amount stolen
- `do_exchange_draw(game, player)` — draws 2 cards from the deck into the player's hand
- `do_exchange_return(game, player, card_name)` — returns one named card from the player's hand to the deck

Each takes the game and player (and target where needed) and directly mutates state. They contain no decision-making (no challenge/block logic, no turn management) and no I/O. The controller decides when to call them. Assassinate and Coup don't have action functions here because their only mechanical effect is "cause the target to lose influence", which the controller handles directly through the lose-influence flow.

## `src/coup.py` — Game state container

The `Game` class holds the shared game state: the list of `players`, the `deck`, and `revealed_cards` (the face-up discard pile). On construction it deals two cards to each player. It also provides four helper methods that need access to that shared state:

- `deal_initial_cards()` — called once at startup
- `lose_influence(player, card_name)` — removes a specific card from a player and appends it to the revealed pile
- `resolve_challenge(acting_player, claimed_card, challenger)` — checks if the acting player actually has the claimed card; if yes, it returns the revealed card to the deck and the acting player draws a replacement (the card shuffle rule), and returns `(False, challenger)`; if no, returns `(True, acting_player)`. The caller uses the returned `loser` to drive the lose-influence flow.
- `get_valid_targets(acting_player)` / `get_living_players()` — convenience filters over the player list

No game loop, no I/O. It's a data container with helpers.

## `src/controller.py` — State machine (the brain)

This is the bridge between the UI and the game logic. `GameController` is an event-driven state machine tracking which of 11 states the game is in (`SETUP_PLAYER_COUNT`, `SETUP_PLAYER_NAME`, `CHOOSE_ACTION`, `CHOOSE_TARGET`, `CHALLENGE_QUERY`, `BLOCK_QUERY`, `CHALLENGE_BLOCK_QUERY`, `LOSE_INFLUENCE`, `EXCHANGE_RETURN_FIRST`, `EXCHANGE_RETURN_SECOND`, `GAME_OVER`).

It exposes three methods the UI relies on:

- `get_prompt(player=None)` — returns `(message_string, list_of_options)` describing what should be displayed right now. Takes an optional `player` so the prompt can be personalized for a specific recipient during simultaneous queries.
- `handle_input(value, player=None)` — accepts a player's choice (button click or text entry), updates game state by calling into `coup.py` and `actions.py`, and advances to the next state.
- `get_active_player()` / `get_active_players()` — returns who currently owes input. Sequential states (e.g. `CHOOSE_ACTION`) have a single active player; simultaneous states return the full list of candidates who haven't responded yet.

A module-level `ACTION_INFO` dict is the single source of truth for each action's metadata: `(claimed_card, blockable_cards, needs_target, cost)`. The controller reads this dict to decide whether to route through target-selection, a challenge query, a block query, or straight to execution.

The controller manages the full flow: turn order, cost deduction (Assassinate=3 and Coup=7 are deducted immediately, before any challenge resolves), **simultaneous challenge/block queries** (every eligible opponent is prompted at once and resolution proceeds as soon as anyone reacts), nested challenge-on-block (when a block itself gets challenged), exchange card returns, and win detection.

Because losing influence is an interruption that can happen for many different reasons, the controller uses an **`after_lose_influence` callback-tag pattern**: before transitioning into `LOSE_INFLUENCE`, it stashes a string describing why (`"action_challenged_success"`, `"action_challenged_fail"`, `"block_challenged_success"`, `"block_challenged_fail"`, `"action_effect"`). When the player finishes losing their card, `_after_lose_influence_done()` dispatches on this tag to route back into the correct continuation — advance the turn, continue the action, execute it, or declare the block stands.

## `src/ui.py` — Multi-window Tkinter frontend

The visual layer. It creates two kinds of windows:

1. **`SetupWindow`** — the root `tk.Tk()` window used only during setup. It shows a prompt label, dynamically-generated buttons (for the player-count choice), and a text-entry field (for each player's name). Once the game starts, it withdraws itself and spawns the per-player windows.
2. **`PlayerWindow`** — one `tk.Toplevel` per player, offset on-screen so they don't stack. Each player window is **privacy-aware**: it shows that player's own cards face-up, but only card counts (not identities) for every other player. Each window has three sections:
   - **Player panels** (top) — one box per player showing name, coins, and either their cards (if it's the owner's window) or "N cards" (for opponents). The current player is highlighted in blue, eliminated players are grayed out, and a "Revealed" panel shows the discarded cards.
   - **Prompt area** (middle) — shows either a personalized prompt and buttons when this player needs to act, or a "Waiting for X, Y to respond..." message when others are active. This is driven by `controller.get_active_players()`.
   - **Game log** (bottom) — a scrollable text widget that mirrors `controller.log`.

Every button click calls `controller.handle_input(value, self.player)`, then `app.refresh_all_player_windows()` re-renders every open window so everyone sees the updated state simultaneously. The UI contains zero game logic — it just reads and renders controller state. When the game ends and the player chooses "New Game", the setup window is re-shown and all player windows are closed.

## `tests/` — Unit tests

Uses the standard-library `unittest` framework — no pytest, no external fixtures. Three test files mirror the layers:

- `test_models.py` — tests `Player`, `Deck`, and `Game` (data models + the `resolve_challenge` helper).
- `test_actions.py` — tests the pure action functions for correct state mutations.
- `test_controller.py` — tests the state machine: setup flow, action selection, challenge/block resolution, lose-influence continuations, turn advancement, and game-over detection.

Run the full suite with `python -m unittest discover tests`.
