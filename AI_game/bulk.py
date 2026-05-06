"""Headless bulk game runner for AI Coup games.

Usage:
    python -m AI_game.bulk --games 100
    python -m AI_game.bulk --games 50 --agents "Claude,Claude,Gemini,Gemini"
    python -m AI_game.bulk --games 20 --quiet
    python -m AI_game.bulk --games 10 --delay 5
"""

import argparse
import sys
import time

from AI_game.config import (
    load_config, get_available_agents, get_prompt_mode,
    VALID_PROMPT_MODES, DEFAULT_PROMPT_MODE,
)
from AI_game.agent_factory import create_agents_from_names, build_agent_names
from AI_game.game_runner import GameRunner

# ANSI codes for summary output
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Run multiple AI Coup games in bulk (headless, no UI).",
    )
    parser.add_argument(
        "--games", type=int, required=True,
        help="Number of games to run.",
    )
    parser.add_argument(
        "--agents", type=str, default=None,
        help=(
            "Comma-separated list of agent provider names, "
            "e.g. 'Claude,Claude,Gemini,Gemini'. "
            "Duplicates are numbered automatically (Claude, Claude 2, ...). "
            "If omitted, uses all agents defined in ai_config.json."
        ),
    )
    parser.add_argument(
        "--mode", choices=VALID_PROMPT_MODES, default=None,
        help=(
            f"Prompt mode: 'heavy' or 'light'. "
            f"Overrides ai_config.json setting. Default: {DEFAULT_PROMPT_MODE}"
        ),
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-game play-by-play output. Only show progress and summary.",
    )
    parser.add_argument(
        "--delay", type=float, default=0,
        help="Delay in seconds between games (useful for rate-limit avoidance). Default: 0",
    )
    return parser.parse_args()


def _resolve_agent_names(agents_arg, config):
    """Turn the --agents CLI string into a list of display names.

    Args:
        agents_arg: comma-separated string like "Claude,Claude,Gemini" or None.
        config: parsed ai_config.json dict.

    Returns:
        list of display names, e.g. ["Claude", "Claude 2", "Gemini"].

    Raises:
        SystemExit: if validation fails.
    """
    available = get_available_agents(config)

    if agents_arg is None:
        # Default: one of each configured agent
        provider_names = available
    else:
        provider_names = [name.strip() for name in agents_arg.split(",")]

    # Validate that all requested providers exist in the config
    for name in provider_names:
        if name not in available:
            print(
                f"Error: Unknown agent '{name}'. "
                f"Available: {', '.join(available)}",
                file=sys.stderr,
            )
            sys.exit(1)

    if len(provider_names) < 2:
        print("Error: Need at least 2 agents.", file=sys.stderr)
        sys.exit(1)
    if len(provider_names) > 6:
        print("Error: Maximum 6 agents.", file=sys.stderr)
        sys.exit(1)

    return build_agent_names(provider_names)


def _run_bulk(num_games, agent_display_names, config, prompt_mode, quiet, delay):
    """Execute the bulk game loop.

    Returns:
        tuple of (results, errors) where results is a list of result dicts
        from successful games and errors is a list of (game_number, error_str).
    """
    results = []
    errors = []

    print(f"\n{BOLD}{'=' * 60}")
    print("          COUP — BULK AI GAME RUNNER")
    print(f"{'=' * 60}{RESET}")
    print(f"  Games to run:  {num_games}")
    print(f"  Agents:        {', '.join(agent_display_names)}")
    print(f"  Prompt mode:   {prompt_mode}")
    print(f"  Quiet mode:    {'on' if quiet else 'off'}")
    if delay > 0:
        print(f"  Delay:         {delay}s between games")
    print()

    start_time = time.time()

    for game_num in range(1, num_games + 1):
        try:
            # Create fresh agents for each game
            agents = create_agents_from_names(agent_display_names, config)

            runner = GameRunner(agents, prompt_mode=prompt_mode, quiet=quiet)
            result = runner.run()

            if result is not None:
                results.append(result)
                winner = result["winner_name"]
                print(
                    f"  Game {game_num}/{num_games} complete "
                    f"— winner: {BOLD}{winner}{RESET}"
                )
            else:
                errors.append((game_num, "Game ended abnormally (no winner)"))
                print(
                    f"  Game {game_num}/{num_games} "
                    f"{DIM}ABORTED (no winner){RESET}",
                    file=sys.stderr,
                )

        except KeyboardInterrupt:
            print(f"\n\n  Interrupted after {game_num - 1} games.")
            break

        except Exception as e:
            errors.append((game_num, str(e)))
            print(
                f"  Game {game_num}/{num_games} "
                f"{DIM}ERROR: {e}{RESET}",
                file=sys.stderr,
            )

        # Delay between games (skip after the last game)
        if delay > 0 and game_num < num_games:
            time.sleep(delay)

    elapsed = time.time() - start_time
    _print_summary(results, errors, elapsed, prompt_mode)

    return results, errors


def _print_summary(results, errors, elapsed, prompt_mode):
    """Print end-of-run summary report."""
    total_games = len(results) + len(errors)
    successful = len(results)
    failed = len(errors)

    print(f"\n{BOLD}{'=' * 60}")
    print("                  BULK RUN SUMMARY")
    print(f"{'=' * 60}{RESET}")

    print(f"  Total games:     {total_games}")
    print(f"  Successful:      {successful}")
    if failed > 0:
        print(f"  Failed/aborted:  {failed}")
    print(f"  Elapsed time:    {elapsed:.1f}s", end="")
    if successful > 0:
        print(f" ({elapsed / successful:.1f}s avg per game)")
    else:
        print()
    print(f"  Prompt mode:     {prompt_mode}")

    if not results:
        print(f"\n  No successful games to summarize.\n")
        return

    # Win rates by model
    model_stats = {}
    for result in results:
        for agent in result["agents"]:
            model = agent.model
            if model not in model_stats:
                model_stats[model] = {
                    "games": 0, "wins": 0,
                    "total_tokens": 0, "cached_tokens": 0, "queries": 0,
                }
            model_stats[model]["games"] += 1
            model_stats[model]["total_tokens"] += (
                agent.prompt_tokens + agent.completion_tokens
            )
            model_stats[model]["cached_tokens"] += agent.cached_tokens
            model_stats[model]["queries"] += agent.query_count

        winner_model = result["winner_model"]
        if winner_model in model_stats:
            model_stats[winner_model]["wins"] += 1

    print(f"\n  {BOLD}Win Rates:{RESET}")
    for model in sorted(model_stats.keys()):
        s = model_stats[model]
        rate = s["wins"] / s["games"] * 100 if s["games"] > 0 else 0
        print(f"    {model}: {s['wins']}/{s['games']} wins ({rate:.1f}%)")

    # Token usage
    total_tokens = sum(s["total_tokens"] for s in model_stats.values())
    total_cached = sum(s["cached_tokens"] for s in model_stats.values())
    total_queries = sum(s["queries"] for s in model_stats.values())
    avg_tokens_per_game = total_tokens / successful if successful > 0 else 0

    print(f"\n  {BOLD}Token Usage (this run):{RESET}")
    print(f"    Total tokens:       {total_tokens:,}")
    print(f"    Cached tokens:      {total_cached:,}", end="")
    if total_tokens > 0:
        print(f" ({total_cached / total_tokens * 100:.1f}% of total)")
    else:
        print()
    print(f"    Total queries:      {total_queries:,}")
    print(f"    Avg tokens/game:    {avg_tokens_per_game:,.0f}")

    # Per-model token breakdown
    print(f"\n  {BOLD}Per-Model Token Breakdown:{RESET}")
    for model in sorted(model_stats.keys()):
        s = model_stats[model]
        avg_per_query = (
            s["total_tokens"] / s["queries"] if s["queries"] > 0 else 0
        )
        cache_pct = (
            f"{s['cached_tokens'] / s['total_tokens'] * 100:.1f}%"
            if s["total_tokens"] > 0 else "0%"
        )
        print(
            f"    {model}: {s['total_tokens']:,} tokens "
            f"(cached: {s['cached_tokens']:,}, {cache_pct}) "
            f"| {avg_per_query:,.0f} tokens/query over {s['queries']} queries"
        )

    # Errors
    if errors:
        print(f"\n  {BOLD}Errors:{RESET}")
        for game_num, error_msg in errors:
            print(f"    Game {game_num}: {error_msg}")

    print()


def main():
    args = _parse_args()

    # Load config
    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    # Resolve prompt mode: CLI override > config file
    if args.mode is not None:
        prompt_mode = args.mode
    else:
        prompt_mode = get_prompt_mode(config)

    # Resolve agent list
    agent_display_names = _resolve_agent_names(args.agents, config)

    # Run the bulk loop
    _run_bulk(
        num_games=args.games,
        agent_display_names=agent_display_names,
        config=config,
        prompt_mode=prompt_mode,
        quiet=args.quiet,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
