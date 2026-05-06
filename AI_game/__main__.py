"""Entry point: python -m AI_game [--seed SEED]"""

import argparse

from AI_game.setup_ui import main as ui_main


def main():
    parser = argparse.ArgumentParser(
        description="Run AI Coup games."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible games."
    )
    args = parser.parse_args()

    ui_main(seed=args.seed)


main()
