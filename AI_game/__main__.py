"""Entry point: python -m AI_game [--mode heavy|light] [--preset NAME]"""

import argparse

from AI_game.config import VALID_PROMPT_MODES, DEFAULT_PROMPT_MODE
from AI_game.setup_ui import main


def _parse_args():
    parser = argparse.ArgumentParser(description="Run AI Coup game")
    parser.add_argument(
        "--mode",
        choices=VALID_PROMPT_MODES,
        default=None,
        help=(
            f"Prompt mode: 'heavy' (full prompts with private thoughts on turn) "
            f"or 'light' (slim prompts always, fewer tokens). "
            f"Overrides the prompt_mode setting in ai_config.json. "
            f"Default: {DEFAULT_PROMPT_MODE}"
        ),
    )
    parser.add_argument(
        "--preset",
        type=str,
        default=None,
        help=(
            "Name of a preset from presets.json to use for custom starting "
            "conditions (hands, coins, deck composition)."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "Integer seed for deterministic randomness. If omitted, a random "
            "seed is generated and displayed so the game can be replayed."
        ),
    )
    return parser.parse_args()


args = _parse_args()
main(prompt_mode_override=args.mode, preset_name=args.preset, seed=args.seed)
