"""Entry point: python -m AI_game [--mode heavy|light]"""

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
    return parser.parse_args()


args = _parse_args()
main(prompt_mode_override=args.mode)
