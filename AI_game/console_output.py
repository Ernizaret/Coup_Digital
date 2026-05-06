"""Formatted terminal output for spectating AI Coup games."""

import sys

# ANSI color codes per agent
AGENT_COLORS = {
    "ChatGPT": "\033[32m",     # green
    "Claude": "\033[35m",      # magenta
    "Gemini": "\033[34m",      # blue
    "Perplexity": "\033[33m",  # yellow
}
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _color_for(name):
    """Get ANSI color for an agent name (checks prefix for numbered agents)."""
    for provider, color in AGENT_COLORS.items():
        if name == provider or name.startswith(provider + " "):
            return color
    return ""


def _colored(name, text):
    """Wrap text in the agent's color."""
    color = _color_for(name)
    if color:
        return f"{color}{text}{RESET}"
    return text


class ConsoleOutput:
    """Handles all terminal output for spectating an AI Coup game."""

    def game_started(self, controller):
        """Print game start banner and player list."""
        print(f"\n{BOLD}{'=' * 60}")
        print("              COUP — AI AGENT BATTLE")
        print(f"{'=' * 60}{RESET}\n")
        for p in controller.game.players:
            name_str = _colored(p.name, p.name)
            print(f"  {name_str}: {', '.join(p.influence)} ({p.coins} coins)")
        print()

    def turn_start(self, player_name, turn_number):
        """Print turn separator."""
        print(f"{DIM}{'—' * 60}{RESET}")
        name_str = _colored(player_name, player_name)
        print(f"{BOLD}Turn {turn_number} — {name_str}'s turn{RESET}")

    def agent_thinking(self, name):
        """Show that an agent is thinking."""
        name_str = _colored(name, name)
        print(f"  {name_str} is thinking...", end="", flush=True)

    def agent_done(self):
        """Clear the thinking indicator."""
        print(f"\r  {'':40}\r", end="", flush=True)

    def agent_response(self, name, speech, action):
        """Show an agent's speech and chosen action."""
        name_str = _colored(name, name)
        print(f"  {name_str}: \"{speech}\"")
        print(f"    -> Action: {BOLD}{action}{RESET}")

    def agent_speech(self, name, speech):
        """Show just a speech bubble (for non-action prompts)."""
        name_str = _colored(name, name)
        print(f"  {name_str}: \"{speech}\"")

    def game_event(self, text):
        """Print a game event from the controller log."""
        print(f"  {DIM}[Event]{RESET} {text}")

    def agent_error(self, name, attempt, error_msg):
        """Show a retry warning."""
        name_str = _colored(name, name)
        print(f"  {DIM}[Retry {attempt}] {name_str}: {error_msg}{RESET}",
              file=sys.stderr)

    def agent_fallback(self, name, action):
        """Show that an agent fell back to a default action."""
        name_str = _colored(name, name)
        print(f"  {DIM}[Fallback] {name_str} defaulting to: {action}{RESET}")

    def game_state_summary(self, controller):
        """Print compact state table after each turn."""
        print(f"  {DIM}Status:", end="")
        for p in controller.game.players:
            if p.is_alive():
                print(f" {p.name}({p.coins}c/{len(p.influence)}i)", end="")
            else:
                print(f" {p.name}(OUT)", end="")
        print(f"{RESET}")

    def game_over(self, winner_name):
        """Print game over banner."""
        winner_str = _colored(winner_name, winner_name)
        print(f"\n{BOLD}{'=' * 60}")
        print(f"  GAME OVER — {winner_str} WINS!")
        print(f"{'=' * 60}{RESET}\n")

    def token_usage(self, agents):
        """Print token usage summary for each agent."""
        print(f"{BOLD}Token Usage:{RESET}")
        for agent in agents:
            total = agent.prompt_tokens + agent.completion_tokens
            ratio = total / agent.query_count if agent.query_count else 0
            name_str = _colored(agent.name, agent.name)
            print(f"  {name_str}: {total:,} tokens "
                  f"({agent.prompt_tokens:,} prompt + "
                  f"{agent.completion_tokens:,} completion) "
                  f"| {ratio:,.0f} tokens/query over {agent.query_count} queries")
        print()

    def batch_progress(self, game_num, total, winner_name):
        """Print progress line after each game in a batch run."""
        winner_str = _colored(winner_name, winner_name)
        print(f"  Game {game_num}/{total} complete — winner: {winner_str}")

    def batch_summary(self, results, agents):
        """Print win rates and cumulative token usage after a batch run.

        Args:
            results: list of winner names (one per game).
            agents: list of all Agent instances across all games.
        """
        from collections import Counter

        print(f"\n{BOLD}{'=' * 60}")
        print("              BATCH RESULTS")
        print(f"{'=' * 60}{RESET}\n")

        wins = Counter(results)
        total = len(results)

        print(f"  {total} games played:\n")
        for name, count in wins.most_common():
            rate = count / total * 100
            name_str = _colored(name, name)
            bar = "█" * int(rate / 5)
            print(f"  {name_str}: {count} wins ({rate:.1f}%) {bar}")

        print(f"\n{BOLD}Token Usage (cumulative):{RESET}")
        # Aggregate by agent name
        agent_totals = {}
        for agent in agents:
            if agent.name not in agent_totals:
                agent_totals[agent.name] = {"tokens": 0, "queries": 0}
            agent_totals[agent.name]["tokens"] += (
                agent.prompt_tokens + agent.completion_tokens
            )
            agent_totals[agent.name]["queries"] += agent.query_count

        for name, data in agent_totals.items():
            name_str = _colored(name, name)
            avg = data["tokens"] / data["queries"] if data["queries"] else 0
            print(
                f"  {name_str}: {data['tokens']:,} tokens "
                f"| {data['queries']} queries "
                f"| {avg:,.0f} tokens/query"
            )
        print()
