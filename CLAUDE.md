# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Digital implementation of the card game Coup, built in Python with a Tkinter GUI. Uses only the Python standard library (tkinter, random, enum).

## Running the Game

```bash
python -m src.ui
```

No build step, no external dependencies, no test framework currently.

## Architecture

The codebase follows strict separation of concerns across five layers in `src/`:

1. **Data Models** (`player.py`, `deck.py`, `coup.py`) — Pure state containers with no game logic or I/O. `coup.py` holds shared game state (players, deck, revealed cards) and helper methods like `resolve_challenge()`.

2. **Action Functions** (`actions.py`) — One pure function per game action (`do_income`, `do_steal`, etc.). They mutate state directly but contain no decision-making or I/O. The controller decides when to call them.

3. **Controller** (`controller.py`) — The brain. An event-driven state machine with 11 states (setup, choose action, challenge query, block query, lose influence, exchange return, game over, etc.). Exposes exactly two methods:
   - `get_prompt()` → `(message, options)` for the UI to display
   - `handle_input(value)` — accepts player choice, updates state, advances to next state

4. **UI** (`ui.py`) — Tkinter frontend that renders controller state. Contains zero game logic — just calls `handle_input()` on button clicks then refreshes.

### Key Design Rules

- **Models never contain game logic.** Logic lives in controller and actions.
- **UI never contains game logic.** It only reads and renders controller state.
- **Actions never make decisions.** They execute; the controller orchestrates.
- **Costs deducted immediately** (Assassinate=3, Coup=7) before challenge/block resolution.
- **Challenge walk pattern**: iterates through eligible players with QUERY state for each.
- **ACTION_INFO dict** in controller defines metadata (claimed_card, blockable_cards, needs_target, cost) for each action.
