"""Entry point: python -m AI_game [--preset PRESET_NAME]"""

import argparse
import sys

from AI_game.config import load_config, get_available_agents
from AI_game.agents import create_agent


def run_with_preset(preset_name):
    """Run a single AI game using a named preset configuration."""
    from AI_game.presets import load_presets_file, get_preset, validate_preset
    from AI_game.game_runner import GameRunner

    # Load AI config for API key and agent models
    config = load_config()
    agents_cfg = config["agents"]
    api_key = config["api_key"]

    # Load and validate the preset
    presets_data = load_presets_file()
    preset = get_preset(presets_data, preset_name)
    validate_preset(preset)

    # Create agents for each player defined in the preset
    players_cfg = preset.get("players", {})
    turn_order = preset.get("turn_order")
    if turn_order is not None:
        player_names = turn_order
    else:
        player_names = list(players_cfg.keys())

    agents = []
    for name in player_names:
        # Find matching agent config — strip number suffix for lookup
        model = None
        for provider in agents_cfg:
            if name == provider or name.startswith(provider + " "):
                model = agents_cfg[provider]
                break
        if model is None:
            print(f"Error: No agent config found for player '{name}'.")
            print(f"Available agents in ai_config.json: {list(agents_cfg.keys())}")
            sys.exit(1)
        agents.append(create_agent(name, api_key, model))

    # Run the game with the preset
    runner = GameRunner(agents, preset=preset)
    runner.run()


def run_with_ui():
    """Run the interactive agent setup UI."""
    from AI_game.setup_ui import main
    main()


def main():
    parser = argparse.ArgumentParser(
        description="Run AI Coup games with optional preset configurations."
    )
    parser.add_argument(
        "--preset",
        type=str,
        default=None,
        help="Name of a preset from presets.json to use for custom start conditions."
    )
    args = parser.parse_args()

    if args.preset:
        run_with_preset(args.preset)
    else:
        run_with_ui()


main()
