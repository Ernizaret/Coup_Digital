"""Entry point: python -m AI_game [--preset PRESET_NAME] [--count N]"""

import argparse
import sys

from AI_game.config import load_config, get_available_agents
from AI_game.agents import create_agent


def run_with_preset(preset_name, count=1):
    """Run AI game(s) using a named preset configuration.

    Args:
        preset_name: Name of a preset from presets.json.
        count: Number of games to run back-to-back.
    """
    from AI_game.presets import load_presets_file, get_preset, validate_preset
    from AI_game.game_runner import GameRunner
    from AI_game.console_output import ConsoleOutput

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

    if count == 1:
        # Single game — original behavior
        agents = []
        for name in player_names:
            model = None
            for provider in agents_cfg:
                if name == provider or name.startswith(provider + " "):
                    model = agents_cfg[provider]
                    break
            if model is None:
                print(f"Error: No agent config found for player '{name}'.")
                print(f"Available agents in ai_config.json: "
                      f"{list(agents_cfg.keys())}")
                sys.exit(1)
            agents.append(create_agent(name, api_key, model))

        runner = GameRunner(agents, preset=preset)
        runner.run()
    else:
        # Batch run — create fresh agents per game
        output = ConsoleOutput()
        results = []
        all_agents = []

        for game_num in range(1, count + 1):
            fresh_agents = []
            for name in player_names:
                model = None
                for provider in agents_cfg:
                    if name == provider or name.startswith(provider + " "):
                        model = agents_cfg[provider]
                        break
                if model is None:
                    print(f"Error: No agent config found for player '{name}'.")
                    print(f"Available agents in ai_config.json: "
                          f"{list(agents_cfg.keys())}")
                    sys.exit(1)
                fresh_agents.append(create_agent(name, api_key, model))

            runner = GameRunner(fresh_agents, preset=preset)
            runner.run()

            winner = runner.controller.game.get_living_players()[0]
            results.append(winner.name)
            all_agents.extend(fresh_agents)
            output.batch_progress(game_num, count, winner.name)

        output.batch_summary(results, all_agents)


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
        help="Name of a preset from presets.json to use for custom start "
             "conditions."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of games to run back-to-back (requires --preset)."
    )
    args = parser.parse_args()

    if args.count > 1 and not args.preset:
        parser.error("--count requires --preset to be specified.")

    if args.preset:
        run_with_preset(args.preset, count=args.count)
    else:
        run_with_ui()


main()
