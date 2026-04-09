# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Digital implementation of the card game Coup, built in Python with a Tkinter GUI. Uses only the Python standard library (tkinter, random, enum).

## Running the Game

```bash
python -m src.ui
```

No build step, no external dependencies.

## Testing

Tests use the standard `unittest` framework (no pytest, no fixtures beyond helpers in each test file).

```bash
# Run all tests
python -m unittest discover tests

# Run a single test file
python -m unittest tests.test_controller

# Run a single test case or method
python -m unittest tests.test_controller.TestSetupFlow.test_initial_state
```

## Architecture

The codebase follows strict separation of concerns across five layers in `src/`:

1. **Data Models** (`player.py`, `deck.py`, `coup.py`) — Pure state containers with no game logic or I/O. `coup.py` holds shared game state (players, deck, revealed cards) and helper methods like `resolve_challenge()`.

2. **Action Functions** (`actions.py`) — One pure function per game action (`do_income`, `do_steal`, etc.). They mutate state directly but contain no decision-making or I/O. The controller decides when to call them.

3. **Controller** (`controller.py`) — The brain. An event-driven state machine with 11 states (setup, choose action, challenge query, block query, lose influence, exchange return, game over, etc.). Exposes three methods the UI relies on:
   - `get_prompt(player=None)` → `(message, options)` for the UI to display
   - `handle_input(value, player=None)` — accepts a player's choice, updates state, advances to the next state
   - `get_active_player()` / `get_active_players()` — returns who currently owes input (single for sequential states, list for simultaneous states)

4. **UI** (`ui.py`) — Multi-window Tkinter frontend: one `SetupWindow` during pre-game, then one private window per player once the game starts (so each player only sees their own cards). Contains zero game logic — it just calls `handle_input()` on button clicks then refreshes every window.

### Key Design Rules

- **Models never contain game logic.** Logic lives in controller and actions.
- **UI never contains game logic.** It only reads and renders controller state.
- **Actions never make decisions.** They execute; the controller orchestrates.
- **Costs deducted immediately** (Assassinate=3, Coup=7) before challenge/block resolution.
- **Simultaneous challenge/block**: All eligible non-acting players are prompted at once. The controller tracks `challenge_candidates`/`block_candidates` lists and `challenge_responded`/`block_responded` sets; as soon as anyone challenges or blocks, resolution proceeds. If everyone declines, the action continues. The same state (`CHALLENGE_QUERY`, `BLOCK_QUERY`, `CHALLENGE_BLOCK_QUERY`) is reused for every candidate — the UI uses `get_active_players()` to know which windows should be enabled.
- **`after_lose_influence` callback pattern**: Because losing influence is an interruption (a separate state), the controller stashes a string tag (`"action_challenged_success"`, `"action_challenged_fail"`, `"block_challenged_success"`, `"block_challenged_fail"`, `"action_effect"`) in `self.after_lose_influence` before entering `LOSE_INFLUENCE`. `_after_lose_influence_done()` dispatches on this tag to route back into the correct continuation (advance turn, continue action, execute action, or block-stands).
- **ACTION_INFO dict** in `controller.py` is the single source of truth for each action's metadata: `(claimed_card, blockable_cards, needs_target, cost)`. Add new actions here first.
