"""Track AI model win rates and token usage in a CSV file."""

import csv
import os
from datetime import datetime

STATS_FILE = os.path.join(os.path.dirname(__file__), "winrates.csv")
GAME_LOG_FILE = os.path.join(os.path.dirname(__file__), "game_log.csv")
FIELDNAMES = [
    "model", "history_depth", "games_played", "games_won", "win_rate", "elo",
    "total_tokens", "cached_tokens", "total_queries", "avg_tokens_per_query",
]

ELO_START = 1500.0
ELO_K = 32
GAME_LOG_FIELDNAMES = [
    "timestamp", "seed", "winner_model", "history_depth", "players",
]


def _make_key(model, history_depth):
    """Create a composite key from model and history_depth."""
    return f"{model}|{history_depth}"


def _load_stats():
    """Load existing stats from CSV into a dict keyed by model|history_depth."""
    stats = {}
    if not os.path.exists(STATS_FILE):
        return stats
    with open(STATS_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Support legacy rows that have prompt_mode instead of history_depth
            if "history_depth" in row and row["history_depth"] is not None:
                depth = row["history_depth"]
            else:
                depth = "unknown"
            key = _make_key(row["model"], depth)
            stats[key] = {
                "model": row["model"],
                "history_depth": depth,
                "games_played": int(row["games_played"]),
                "games_won": int(row["games_won"]),
                "elo": float(row["elo"]) if row.get("elo") else ELO_START,
                "total_tokens": int(row.get("total_tokens", 0)),
                "cached_tokens": int(row.get("cached_tokens", 0)),
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
            cached = data["cached_tokens"]
            avg = tokens / queries if queries > 0 else 0.0
            writer.writerow({
                "model": data["model"],
                "history_depth": data["history_depth"],
                "games_played": played,
                "games_won": won,
                "win_rate": f"{rate:.4f}",
                "elo": f"{data.get('elo', ELO_START):.1f}",
                "total_tokens": tokens,
                "cached_tokens": cached,
                "total_queries": queries,
                "avg_tokens_per_query": f"{avg:.1f}",
            })


def _append_game_log(agents, winner_model, history_depth, seed):
    """Append a single game entry to the per-game log CSV."""
    file_exists = os.path.exists(GAME_LOG_FILE)
    with open(GAME_LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GAME_LOG_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        players = ", ".join(
            f"{getattr(a, 'name', '?')} ({a.model})" for a in agents
        )
        writer.writerow({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "seed": seed if seed is not None else "",
            "winner_model": winner_model,
            "history_depth": history_depth,
            "players": players,
        })


def _compute_elo_updates(agent_keys, stats, winner_key):
    """Compute new ELO ratings using pairwise multi-player approach.

    Winner "beats" each loser (score=1 vs 0).
    Losers "draw" against each other (score=0.5 vs 0.5).

    Args:
        agent_keys: list of unique keys for participating agents.
        stats: the full stats dict (must already contain entries for all keys).
        winner_key: the key of the winning agent.

    Returns:
        dict mapping each key to its new ELO rating.
    """
    num_opponents = len(agent_keys) - 1
    if num_opponents <= 0:
        return {k: stats[k]["elo"] for k in agent_keys}

    new_elos = {}
    for key in agent_keys:
        elo = stats[key]["elo"]
        delta = 0.0
        for opp_key in agent_keys:
            if opp_key == key:
                continue
            opp_elo = stats[opp_key]["elo"]
            expected = 1.0 / (1.0 + 10.0 ** ((opp_elo - elo) / 400.0))
            # Determine actual score for this pair
            if key == winner_key:
                actual = 1.0
            elif opp_key == winner_key:
                actual = 0.0
            else:
                actual = 0.5
            delta += (ELO_K / num_opponents) * (actual - expected)
        new_elos[key] = elo + delta
    return new_elos


def record_game(agents, winner_model, history_depth=2, seed=None):
    """Record a completed game for all participating agents.

    Args:
        agents: list of Agent instances that participated.
        winner_model: the model string of the winning agent.
        history_depth: fallback history depth (used if agent lacks the attribute).
        seed: the game seed (integer) for reproducibility tracking.
    """
    stats = _load_stats()

    agent_keys = []
    for agent in agents:
        depth = getattr(agent, "history_depth", history_depth)
        key = _make_key(agent.model, depth)
        if key not in stats:
            stats[key] = {
                "model": agent.model, "history_depth": depth,
                "games_played": 0, "games_won": 0, "elo": ELO_START,
                "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
            }
        stats[key]["games_played"] += 1
        stats[key]["total_tokens"] += agent.prompt_tokens + agent.completion_tokens
        stats[key]["cached_tokens"] += agent.cached_tokens
        stats[key]["total_queries"] += agent.query_count
        agent_keys.append(key)

    # Determine winner key using the winner agent's history_depth
    winner_agent = next(
        (a for a in agents if a.model == winner_model), None
    )
    winner_depth = getattr(winner_agent, "history_depth", history_depth)
    winner_key = _make_key(winner_model, winner_depth)
    if winner_key not in stats:
        stats[winner_key] = {
            "model": winner_model, "history_depth": winner_depth,
            "games_played": 0, "games_won": 0, "elo": ELO_START,
            "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
        }
    stats[winner_key]["games_won"] += 1

    # Compute and apply ELO updates (deduplicate keys for same-model matchups)
    unique_keys = list(dict.fromkeys(agent_keys))
    new_elos = _compute_elo_updates(unique_keys, stats, winner_key)
    for key, new_elo in new_elos.items():
        stats[key]["elo"] = new_elo

    _save_stats(stats)
    _append_game_log(agents, winner_model, winner_depth, seed)
