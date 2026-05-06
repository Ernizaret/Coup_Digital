"""Track AI model win rates and token usage in a CSV file."""

import csv
import os

STATS_FILE = os.path.join(os.path.dirname(__file__), "winrates.csv")
FIELDNAMES = [
    "model", "prompt_mode", "games_played", "games_won", "win_rate",
    "total_tokens", "total_queries", "avg_tokens_per_query",
]


def _make_key(model, prompt_mode):
    """Create a composite key from model and prompt_mode."""
    return f"{model}|{prompt_mode}"


def _load_stats():
    """Load existing stats from CSV into a dict keyed by model|prompt_mode."""
    stats = {}
    if not os.path.exists(STATS_FILE):
        return stats
    with open(STATS_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Support legacy rows without prompt_mode (default to "heavy")
            mode = row.get("prompt_mode", "heavy") or "heavy"
            key = _make_key(row["model"], mode)
            stats[key] = {
                "model": row["model"],
                "prompt_mode": mode,
                "games_played": int(row["games_played"]),
                "games_won": int(row["games_won"]),
                "total_tokens": int(row.get("total_tokens", 0)),
                "total_queries": int(row.get("total_queries", 0)),
            }
    return stats


def _save_stats(stats):
    """Write stats dict back to CSV."""
    with open(STATS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for key in sorted(stats.keys()):
            data = stats[key]
            played = data["games_played"]
            won = data["games_won"]
            rate = won / played if played > 0 else 0.0
            queries = data["total_queries"]
            tokens = data["total_tokens"]
            avg = tokens / queries if queries > 0 else 0.0
            writer.writerow({
                "model": data["model"],
                "prompt_mode": data["prompt_mode"],
                "games_played": played,
                "games_won": won,
                "win_rate": f"{rate:.4f}",
                "total_tokens": tokens,
                "total_queries": queries,
                "avg_tokens_per_query": f"{avg:.1f}",
            })


def record_game(agents, winner_model, prompt_mode="heavy"):
    """Record a completed game for all participating agents.

    Args:
        agents: list of Agent instances that participated.
        winner_model: the model string of the winning agent.
        prompt_mode: "heavy" or "light" — which prompt mode was used.
    """
    stats = _load_stats()

    for agent in agents:
        key = _make_key(agent.model, prompt_mode)
        if key not in stats:
            stats[key] = {
                "model": agent.model, "prompt_mode": prompt_mode,
                "games_played": 0, "games_won": 0,
                "total_tokens": 0, "total_queries": 0,
            }
        stats[key]["games_played"] += 1
        stats[key]["total_tokens"] += agent.prompt_tokens + agent.completion_tokens
        stats[key]["total_queries"] += agent.query_count

    winner_key = _make_key(winner_model, prompt_mode)
    if winner_key not in stats:
        stats[winner_key] = {
            "model": winner_model, "prompt_mode": prompt_mode,
            "games_played": 0, "games_won": 0,
            "total_tokens": 0, "total_queries": 0,
        }
    stats[winner_key]["games_won"] += 1

    _save_stats(stats)
