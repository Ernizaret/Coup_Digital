# Coup_Digital
My attempt at creating a digital version of the game Coup

  How to run

  python -m src.ui

  Verified flows

  - Setup (player count + names) → action selection
  - Income, Foreign Aid (with block), Tax (with challenge)
  - Steal (target + challenge + block), Assassinate, Coup
  - Challenge resolution (both success/failure paths)
  - Block → challenge-on-block (nested continuation)
  - Exchange (draw 2, return 2)
  - Game over + New Game reset