"""Bulk game runner: run many AI games back-to-back in light mode.

Usage:
    python -m AI_game.bulk --games 100
    python -m AI_game.bulk --games 50 --agents "Claude,Claude,Gemini,Gemini"
    python -m AI_game.bulk --games 20 --quiet --delay 2.0
"""

import argparse
import time
import traceback

from AI_game.config import load_config, get_available_agents, create_agents_from_config
from AI_game.game_runner import GameRunner
from AI_game.console_output import ConsoleOutput, QuietOutput


def _parse_args():
    """Parse command-line arguments for the bulk runner."""
    parser = argparse.ArgumentParser(
        description="Run multiple AI Coup games in bulk (light mode)."
    )
    parser.add_argument(
        "--games", type=int, required=True,
        help="Number of games to run."
    )
    parser.add_argument(
        "--agents", type=str, default=None,
        help="Comma-separated agent names from config (e.g. 'Claude,Claude,Gemini,Gemini'). "
             "Defaults to all agents in ai_config.json."
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-game play-by-play; only show results and summary."
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds to wait between games (default: 1.0)."
    )
    return parser.parse_args()


def _resolve_agent_names(config, agents_arg):
    """Determine agent provider names for each game.

    Args:
        config: loaded config dict.
        agents_arg: comma-separated string from CLI, or None.

    Returns:
        list of provider name strings (e.g. ["Claude", "Claude", "Gemini"]).
    """
    if agents_arg:
        names = [n.strip() for n in agents_arg.split(",")]
        # Validate each name against available agents
        available = get_available_agents(config)
        for name in names:
            if name not in available:
                raise ValueError(
                    f"Unknown agent '{name}'. Available: {available}"
                )
        return names
    else:
        # Default: use all agents from config
        return get_available_agents(config)


def _print_summary(results, total_games, games_failed, agent_names):
    """Print final summary report after all games."""
    print(f"\n{'=' * 60}")
    print("           BULK RUN SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total games played: {total_games}")
    print(f"  Games completed:    {total_games - games_failed}")
    print(f"  Games failed:       {games_failed}")

    # Win rates per model
    print(f"\n  Win Rates:")
    model_wins = {}
    model_games = {}
    for result in results:
        if result is None:
            continue
        winner_model = result["winner_model"]
        for model in result["models_in_game"]:
            model_games[model] = model_games.get(model, 0) + 1
        model_wins[winner_model] = model_wins.get(winner_model, 0) + 1

    for model in sorted(model_games.keys()):
        wins = model_wins.get(model, 0)
        played = model_games[model]
        rate = wins / played if played > 0 else 0.0
        print(f"    {model}: {wins}/{played} wins ({rate:.1%})")

    # Token usage
    total_tokens = sum(r["total_tokens"] for r in results if r is not None)
    completed = total_games - games_failed
    avg_tokens = total_tokens / completed if completed > 0 else 0
    print(f"\n  Total tokens consumed: {total_tokens:,}")
    print(f"  Average tokens/game:   {avg_tokens:,.0f}")
    print(f"{'=' * 60}\n")


def run_bulk(num_games, config, agent_names, quiet=False, delay=1.0):
    """Run multiple games and collect results.

    Args:
        num_games: number of games to run.
        config: loaded config dict.
        agent_names: list of provider names for each game.
        quiet: if True, suppress play-by-play output.
        delay: seconds to pause between games.

    Returns:
        tuple of (results list, games_failed count).
    """
    results = []
    games_failed = 0

    for i in range(1, num_games + 1):
        try:
            # Create fresh agents for each game
            agents = create_agents_from_config(config, agent_names)

            # Choose output mode
            output = QuietOutput() if quiet else ConsoleOutput()

            # Create and run game
            runner = GameRunner(agents, prompt_mode="light", output=output)
            runner.run()

            # Collect result data
            winner = runner.controller.game.get_living_players()[0]
            agent_map = {a.name: a for a in agents}
            winner_agent = agent_map[winner.name]

            game_tokens = sum(
                a.prompt_tokens + a.completion_tokens for a in agents
            )
            models_in_game = list(set(a.model for a in agents))

            results.append({
                "winner_name": winner.name,
                "winner_model": winner_agent.model,
                "total_tokens": game_tokens,
                "models_in_game": models_in_game,
            })

            print(f"Game {i}/{num_games} complete — winner: {winner.name} "
                  f"({game_tokens:,} tokens)")

        except Exception as e:
            games_failed += 1
            results.append(None)
            print(f"Game {i}/{num_games} FAILED: {e}")
            traceback.print_exc()

        # Delay between games (skip after last game)
        if i < num_games:
            time.sleep(delay)

    return results, games_failed


def main():
    """Entry point for the bulk runner."""
    args = _parse_args()

    # Load config
    config = load_config()

    # Resolve agent names
    agent_names = _resolve_agent_names(config, args.agents)

    if len(agent_names) < 2:
        print("Error: Need at least 2 agents to play. "
              "Specify --agents or add more to ai_config.json.")
        return

    print(f"Starting bulk run: {args.games} games")
    print(f"Agents: {', '.join(agent_names)}")
    print(f"Mode: light prompts | Delay: {args.delay}s | "
          f"Quiet: {args.quiet}")
    print(f"{'=' * 60}\n")

    results, games_failed = run_bulk(
        num_games=args.games,
        config=config,
        agent_names=agent_names,
        quiet=args.quiet,
        delay=args.delay,
    )

    _print_summary(results, args.games, games_failed, agent_names)


if __name__ == "__main__":
    main()
