# Testing Guide

This document explains how to run the test suite for the Coup project and how
the tests are organized.

## Prerequisites

The project uses only the Python standard library, so no extra installation is
required. The tests rely on the built-in `unittest` framework — there is no
`pytest`, no fixtures library, and no third-party test runner.

You only need:

- Python 3 (the project was developed against Python 3.13, but any modern 3.x
  should work).
- The repository checked out with the `src/` and `tests/` folders intact.

All commands below should be run from the project root
(`C:\Users\ernes\Code_Projects\Coup`) so that the `src` package is importable.

## Running the Tests

### Run the entire suite

```bash
python -m unittest discover tests
```

`unittest discover` walks the `tests/` directory, finds every file matching
`test_*.py`, and runs every `TestCase` subclass it finds.

For more verbose output (one line per test method, including names):

```bash
python -m unittest discover tests -v
```

### Run a single test file

```bash
python -m unittest tests.test_models
python -m unittest tests.test_actions
python -m unittest tests.test_controller
```

### Run a single test class

```bash
python -m unittest tests.test_controller.TestSetupFlow
```

### Run a single test method

```bash
python -m unittest tests.test_controller.TestSetupFlow.test_initial_state
```

### Run tests directly from a file

Each test file ends with the standard `unittest.main()` guard, so you can also
launch a file directly:

```bash
python -m tests.test_controller
```

## Test Layout

The `tests/` folder mirrors the layered architecture documented in
`CLAUDE.md` and `architecture.md`. Each layer has its own test module.

```
tests/
├── __init__.py          # marks tests as a package
├── test_models.py       # data-model tests (Player, Deck, Game)
├── test_actions.py      # pure action-function tests
└── test_controller.py   # state-machine / game-flow tests
```

The UI layer (`src/ui.py`) is intentionally not unit-tested — it contains no
game logic, only Tkinter rendering that calls into the controller.

### `test_models.py`

Covers the pure state containers in `src/player.py`, `src/deck.py`, and
`src/coup.py`.

| Test class | What it verifies |
|------------|------------------|
| `TestPlayer` | Initial coin/influence values, adding and losing influence, `has_influence`, `is_alive`. |
| `TestDeck` | Initial deck size and composition (3 of each character), `draw`, drawing from an empty deck, `return_card`. |
| `TestGame` | Dealing two cards per player, `lose_influence` moving cards into `revealed_cards`, `resolve_challenge` for both truthful and bluffing players, `get_valid_targets` (excluding self and dead players), `get_living_players`. |

These tests instantiate the model classes directly with no mocking — `Player`,
`Deck`, and `Game` have no I/O, so they can be exercised in isolation. The
`TestGame._make_game` helper creates a fresh `Game` from a list of names; reuse
this pattern when adding new model tests.

### `test_actions.py`

Covers the pure functions in `src/actions.py`. Every action function is tested
in isolation by:

1. Building a fresh `Game` via the shared `ActionTestBase._make_game` helper.
2. Forcing the relevant fields (`coins`, `influence`) to a known state.
3. Calling the action function directly.
4. Asserting the resulting field values.

Action tests should never go through the controller — they verify the raw
mutation behavior so the controller can rely on it.

| Test class | What it verifies |
|------------|------------------|
| `TestDoIncome` | `do_income` adds 1 coin. |
| `TestDoForeignAid` | `do_foreign_aid` adds 2 coins. |
| `TestDoTax` | `do_tax` adds 3 coins. |
| `TestDoSteal` | `do_steal` transfers 2/1/0 coins depending on what the victim has. |
| `TestDoExchange` | `do_exchange_draw` adds two cards to the player's hand; `do_exchange_return` removes a chosen card and puts it back in the deck. |

### `test_controller.py`

This is the largest test module and covers the state machine in
`src/controller.py`. It verifies the end-to-end flow of every action through
the challenge/block/lose-influence pipeline.

The shared helper at the top of the file is the key to keeping these tests
short:

```python
def setup_two_player_game(gc):
    """Run through setup to get a 2-player game ready for actions."""
    gc.handle_input("2")
    gc.handle_input("Alice")
    gc.handle_input("Bob")
```

Use it (or its inline 3-player equivalent) at the start of every controller
test that needs an active game.

| Test class | What it verifies |
|------------|------------------|
| `TestSetupFlow` | Initial state, prompt content, valid/invalid player counts, empty-name rejection, transition into `CHOOSE_ACTION`. |
| `TestIncomeFlow` | Income adds a coin and advances the turn. |
| `TestTaxFlow` | Unchallenged tax, challenged tax with a bluffer, challenged tax with a truthful player. |
| `TestForeignAidFlow` | Unblocked foreign aid, blocked foreign aid (block stands when unchallenged). |
| `TestStealFlow` | Steal walking through challenge → block → execution; steal rejected against a target with 0 coins. |
| `TestCoupFlow` | Coup costs 7, deducts coins immediately, removes Coup from the option list under 7 coins, forces Coup at 10 coins. |
| `TestAssassinateFlow` | Assassinate costs 3, full challenge/block walk, target loses chosen influence. |
| `TestExchangeFlow` | Exchange draws 2 extra cards and walks through `EXCHANGE_RETURN_FIRST` then `EXCHANGE_RETURN_SECOND`. |
| `TestGameOver` | Reaching `GAME_OVER` and the `New Game` reset path. |
| `TestResetMethod` | `gc.reset()` clears every controller field. |
| `TestTurnAdvancement` | Skipping dead players and 3-player turn order. |
| `TestBlockChallengeFlow` | Foreign-aid block challenged when blocker is bluffing vs truthful. |
| `TestGetPrompt` | Lose-influence prompt shows both cards; unknown state returns the fallback message. |
| `TestGetActivePlayer` | `get_active_player` / `get_active_players` return the right player(s) for every state, including simultaneous challenge candidates. |

## Patterns to Follow When Adding Tests

The existing tests establish a few conventions worth preserving:

- **Standard library only.** No `pytest`, no `mock`, no fixtures library.
  Tests subclass `unittest.TestCase` directly.
- **Helpers per file, not shared.** Each test file defines its own helper(s)
  (`_make_game`, `setup_two_player_game`). Don't add a `conftest.py` or a
  shared fixtures module.
- **Force state, don't simulate it.** Tests routinely set
  `player.coins = 5` or `player.influence = ["Duke", "Captain"]` to put the
  game into a known state before exercising a code path. This avoids relying
  on randomness from `Deck.shuffle`.
- **One assertion focus per test.** Each test method targets a single behavior
  with a descriptive name (e.g.,
  `test_steal_from_player_with_one_coin`).
- **Test the layer, not below it.** Action tests call action functions
  directly; controller tests go through `gc.handle_input(...)`. Don't reach
  past the layer you're testing.
- **Walk the state machine via `handle_input`.** Controller tests should drive
  the controller exactly as the UI does — by feeding it strings through
  `handle_input` — and verify the resulting `gc.state`, `gc.current_player`,
  `gc.lose_influence_player`, etc. Avoid calling private `_advance_*` helpers
  from tests.
- **Branch on hand size.** Because some tests don't fix the second card,
  losing-influence steps may auto-resolve (1 card) or require a choice
  (2 cards). Several tests use `if len(player.influence) == 2:` to handle
  both cases — copy this pattern when writing tests that don't lock the hand.

## Adding a New Test

1. Decide which layer the new behavior lives in and open the matching test
   file (`test_models.py`, `test_actions.py`, or `test_controller.py`).
2. Either add a method to an existing `TestCase` class (if it fits the
   theme) or add a new `TestCase` subclass.
3. Reuse the file's helper (`_make_game` or `setup_two_player_game`) to set
   up the game.
4. Force any required state explicitly (`coins`, `influence`).
5. Drive the system under test (call the function for actions/models, or
   `handle_input` for controller flows).
6. Assert on the observable state afterwards.
7. Run the new test in isolation first, then run the whole suite to make
   sure nothing else regressed:

   ```bash
   python -m unittest tests.test_controller.TestNewThing.test_new_behavior
   python -m unittest discover tests
   ```

## Troubleshooting

- **`ModuleNotFoundError: No module named 'src'`** — you're not in the project
  root. `cd` to `C:\Users\ernes\Code_Projects\Coup` and re-run the command.
- **A test that involves losing influence behaves differently between runs** —
  the test probably depends on the randomly-dealt second card. Lock the hand
  with `player.influence = ["Duke", "Captain"]` before the action runs.
- **A controller test hangs on a prompt you didn't expect** — print
  `gc.state` and `gc.get_prompt()` after the last `handle_input` to see
  which state the machine is actually in. The state is often
  `CHALLENGE_QUERY` or `BLOCK_QUERY` when you forgot to answer one of the
  reactive prompts.
