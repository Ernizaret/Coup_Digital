"""Track AI model win rates and token usage in a CSV file."""

import csv
import os
from datetime import datetime

STATS_FILE = os.path.join(os.path.dirname(__file__), "winrates.csv")
GAME_LOG_FILE = os.path.join(os.path.dirname(__file__), "game_log.csv")
GAME_LOG_2_FILE = os.path.join(os.path.dirname(__file__), "game_log_2.csv")
GAME_LOG_3_FILE = os.path.join(os.path.dirname(__file__), "game_log_3.csv")
FIELDNAMES = [
    "model", "history_depth", "rules", "strategy",
    "games_played", "games_won", "win_rate", "elo",
    "total_tokens", "cached_tokens", "total_queries", "avg_tokens_per_query",
    "bluffs", "bluffs_caught", "bluff_success_rate",
    "challenges_issued", "challenges_correct", "challenge_success_rate",
    "card_guesses_total", "card_guesses_correct", "card_guess_accuracy",
]

ELO_START = 1500.0
ELO_K = 32
_MAX_PLAYERS = 6
_STAT_PAIRS = [
    ("bluffs", "bluffs_caught"),
    ("challenges_issued", "challenges_correct"),
    ("card_guesses_total", "card_guesses_correct"),
]

GAME_LOG_FIELDNAMES = ["timestamp", "seed"]
# Player identity columns (up to 4 players)
for _n in range(1, 5):
    GAME_LOG_FIELDNAMES.append(f"Player {_n}")
GAME_LOG_FIELDNAMES.append("winner_model")
# Behavioral stats grouped by stat type across all players
for _pair in _STAT_PAIRS:
    for _n in range(1, _MAX_PLAYERS + 1):
        for _field in _pair:
            GAME_LOG_FIELDNAMES.append(f"Player {_n} {_field}")

_MODEL_PREFIX_MAP = {
    "google/": "Gemini",
    "openai/": "ChatGPT",
    "x-ai/": "Grok",
    "anthropic/": "Claude",
    "mistralai/": "Mistral",
}

_MODEL_COLUMNS = ["Gemini", "ChatGPT", "Grok", "Claude", "Mistral"]
_PER_PLAYER_FIELDS = [
    "Turn Order", "Rules", "Strategy", "Win",
    "bluffs", "bluffs_caught", "challenges", "challenges_correct",
    "card_guesses_total", "card_guesses_correct",
]

GAME_LOG_2_FIELDNAMES = ["Game #", "Seed"]
for _col_prefix in _MODEL_COLUMNS:
    for _field in _PER_PLAYER_FIELDS:
        GAME_LOG_2_FIELDNAMES.append(f"{_col_prefix} {_field}")

GAME_LOG_3_FIELDNAMES = [
    "Game #", "Seed", "Player", "Turn Order", "Rules", "Strategy", "Win",
    "bluffs", "bluffs_caught", "challenges", "challenges_correct",
    "card_guesses_total", "card_guesses_correct",
]


def _make_key(model, history_depth, rules_summary=False, strategy_guide=False):
    """Create a composite key from model, history_depth, rules, and strategy."""
    rules = "Yes" if rules_summary else "No"
    strategy = "Yes" if strategy_guide else "No"
    return f"{model}|{history_depth}|{rules}|{strategy}"


def _load_stats():
    """Load existing stats from CSV into a dict keyed by model|depth|rules|strategy."""
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
            rules = row.get("rules", "No")
            strategy = row.get("strategy", "No")
            rules_bool = rules == "Yes"
            strategy_bool = strategy == "Yes"
            key = _make_key(row["model"], depth, rules_bool, strategy_bool)
            stats[key] = {
                "model": row["model"],
                "history_depth": depth,
                "rules": rules,
                "strategy": strategy,
                "games_played": int(row["games_played"]),
                "games_won": int(row["games_won"]),
                "elo": float(row["elo"]) if row.get("elo") else ELO_START,
                "total_tokens": int(row.get("total_tokens", 0)),
                "cached_tokens": int(row.get("cached_tokens", 0)),
                "total_queries": int(row.get("total_queries", 0)),
                "bluffs": int(row.get("bluffs") or 0),
                "bluffs_caught": int(row.get("bluffs_caught") or 0),
                "challenges_issued": int(row.get("challenges_issued") or 0),
                "challenges_correct": int(row.get("challenges_correct") or 0),
                "card_guesses_total": int(row.get("card_guesses_total") or 0),
                "card_guesses_correct": int(row.get("card_guesses_correct") or 0),
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
            bluffs = data.get("bluffs", 0)
            bluffs_caught = data.get("bluffs_caught", 0)
            bluff_rate = ((bluffs - bluffs_caught) / bluffs
                          if bluffs > 0 else 0.0)
            ch_issued = data.get("challenges_issued", 0)
            ch_correct = data.get("challenges_correct", 0)
            ch_rate = ch_correct / ch_issued if ch_issued > 0 else 0.0
            cg_total = data.get("card_guesses_total", 0)
            cg_correct = data.get("card_guesses_correct", 0)
            cg_accuracy = (cg_correct / cg_total
                           if cg_total > 0 else 0.0)
            writer.writerow({
                "model": data["model"],
                "history_depth": data["history_depth"],
                "rules": data.get("rules", "No"),
                "strategy": data.get("strategy", "No"),
                "games_played": played,
                "games_won": won,
                "win_rate": f"{rate:.4f}",
                "elo": f"{data.get('elo', ELO_START):.1f}",
                "total_tokens": tokens,
                "cached_tokens": cached,
                "total_queries": queries,
                "avg_tokens_per_query": f"{avg:.1f}",
                "bluffs": bluffs,
                "bluffs_caught": bluffs_caught,
                "bluff_success_rate": f"{bluff_rate:.4f}",
                "challenges_issued": ch_issued,
                "challenges_correct": ch_correct,
                "challenge_success_rate": f"{ch_rate:.4f}",
                "card_guesses_total": cg_total,
                "card_guesses_correct": cg_correct,
                "card_guess_accuracy": f"{cg_accuracy:.4f}",
            })


def _append_game_log(agents, winner_agent, seed):
    """Append a single game entry to the per-game log CSV."""
    file_exists = os.path.exists(GAME_LOG_FILE)
    with open(GAME_LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GAME_LOG_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        row = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "seed": seed if seed is not None else "",
            "winner_model": winner_agent.model,
        }
        # Player identity columns (model + config summary)
        for i, agent in enumerate(agents[:4], start=1):
            depth = getattr(agent, "history_depth", 2)
            rules = getattr(agent, "rules_summary", False)
            strategy = getattr(agent, "strategy_guide", False)
            row[f"Player {i}"] = (
                f"{agent.model}, depth={depth}, "
                f"rules={'Yes' if rules else 'No'}, "
                f"strategy={'Yes' if strategy else 'No'}"
            )
        # Per-player behavioral stats
        for i, agent in enumerate(agents[:_MAX_PLAYERS], start=1):
            prefix = f"Player {i}"
            row[f"{prefix} bluffs"] = getattr(agent, "bluffs", 0)
            row[f"{prefix} bluffs_caught"] = getattr(agent, "bluffs_caught", 0)
            row[f"{prefix} challenges_issued"] = getattr(agent, "challenges_issued", 0)
            row[f"{prefix} challenges_correct"] = getattr(agent, "challenges_correct", 0)
            row[f"{prefix} card_guesses_total"] = getattr(agent, "card_guesses_total", 0)
            row[f"{prefix} card_guesses_correct"] = getattr(agent, "card_guesses_correct", 0)
        writer.writerow(row)


def _append_game_log_2(agents, winner_agent, seed):
    """Append a single game entry to the per-model game_log_2 CSV."""
    # Determine the next Game # by reading existing rows.
    next_game_num = 1
    if os.path.exists(GAME_LOG_2_FILE):
        with open(GAME_LOG_2_FILE, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    num = int(row.get("Game #", 0))
                except (ValueError, TypeError):
                    num = 0
                if num >= next_game_num:
                    next_game_num = num + 1

    # Ensure the file exists and has the correct header.
    file_exists = os.path.exists(GAME_LOG_2_FILE)
    with open(GAME_LOG_2_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GAME_LOG_2_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        row = {
            "Game #": next_game_num,
            "Seed": seed if seed is not None else "",
        }
        for i, agent in enumerate(agents):
            # Map model to column prefix.
            col_prefix = None
            for prefix, name in _MODEL_PREFIX_MAP.items():
                if agent.model.startswith(prefix):
                    col_prefix = name
                    break
            if col_prefix is None:
                # Unknown model provider; skip this agent.
                continue
            row[f"{col_prefix} Turn Order"] = i + 1
            row[f"{col_prefix} Rules"] = (
                1 if getattr(agent, "rules_summary", False) else -1
            )
            row[f"{col_prefix} Strategy"] = (
                1 if getattr(agent, "strategy_guide", False) else -1
            )
            row[f"{col_prefix} Win"] = 1 if agent is winner_agent else 0
            row[f"{col_prefix} bluffs"] = getattr(agent, "bluffs", 0)
            row[f"{col_prefix} bluffs_caught"] = getattr(
                agent, "bluffs_caught", 0
            )
            row[f"{col_prefix} challenges"] = getattr(
                agent, "challenges_issued", 0
            )
            row[f"{col_prefix} challenges_correct"] = getattr(
                agent, "challenges_correct", 0
            )
            row[f"{col_prefix} card_guesses_total"] = getattr(
                agent, "card_guesses_total", 0
            )
            row[f"{col_prefix} card_guesses_correct"] = getattr(
                agent, "card_guesses_correct", 0
            )
        writer.writerow(row)


def _append_game_log_3(agents, winner_agent, seed):
    """Append one row per player to the per-player game_log_3 CSV."""
    next_game_num = 1
    if os.path.exists(GAME_LOG_3_FILE):
        with open(GAME_LOG_3_FILE, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    num = int(row.get("Game #", 0))
                except (ValueError, TypeError):
                    num = 0
                if num >= next_game_num:
                    next_game_num = num + 1

    file_exists = os.path.exists(GAME_LOG_3_FILE)
    with open(GAME_LOG_3_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GAME_LOG_3_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        for i, agent in enumerate(agents):
            # Map model to friendly name.
            player_name = None
            for prefix, name in _MODEL_PREFIX_MAP.items():
                if agent.model.startswith(prefix):
                    player_name = name
                    break
            if player_name is None:
                continue
            writer.writerow({
                "Game #": next_game_num,
                "Seed": seed if seed is not None else "",
                "Player": player_name,
                "Turn Order": i + 1,
                "Rules": 1 if getattr(agent, "rules_summary", False) else -1,
                "Strategy": (
                    1 if getattr(agent, "strategy_guide", False) else -1
                ),
                "Win": 1 if agent is winner_agent else 0,
                "bluffs": getattr(agent, "bluffs", 0),
                "bluffs_caught": getattr(agent, "bluffs_caught", 0),
                "challenges": getattr(agent, "challenges_issued", 0),
                "challenges_correct": getattr(
                    agent, "challenges_correct", 0
                ),
                "card_guesses_total": getattr(
                    agent, "card_guesses_total", 0
                ),
                "card_guesses_correct": getattr(
                    agent, "card_guesses_correct", 0
                ),
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


def record_game(agents, winner_agent, seed=None):
    """Record a completed game for all participating agents.

    Args:
        agents: list of Agent instances that participated.
        winner_agent: the Agent instance that won the game.
        seed: the game seed (integer) for reproducibility tracking.
    """
    stats = _load_stats()

    agent_keys = []
    for agent in agents:
        depth = getattr(agent, "history_depth", 2)
        rules = getattr(agent, "rules_summary", False)
        strategy = getattr(agent, "strategy_guide", False)
        key = _make_key(agent.model, depth, rules, strategy)
        if key not in stats:
            rules_str = "Yes" if rules else "No"
            strategy_str = "Yes" if strategy else "No"
            stats[key] = {
                "model": agent.model, "history_depth": depth,
                "rules": rules_str, "strategy": strategy_str,
                "games_played": 0, "games_won": 0, "elo": ELO_START,
                "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
                "bluffs": 0, "bluffs_caught": 0,
                "challenges_issued": 0, "challenges_correct": 0,
                "card_guesses_total": 0, "card_guesses_correct": 0,
            }
        stats[key]["games_played"] += 1
        stats[key]["total_tokens"] += agent.prompt_tokens + agent.completion_tokens
        stats[key]["cached_tokens"] += agent.cached_tokens
        stats[key]["total_queries"] += agent.query_count
        stats[key]["bluffs"] += getattr(agent, "bluffs", 0)
        stats[key]["bluffs_caught"] += getattr(agent, "bluffs_caught", 0)
        stats[key]["challenges_issued"] += getattr(agent, "challenges_issued", 0)
        stats[key]["challenges_correct"] += getattr(agent, "challenges_correct", 0)
        stats[key]["card_guesses_total"] += getattr(agent, "card_guesses_total", 0)
        stats[key]["card_guesses_correct"] += getattr(agent, "card_guesses_correct", 0)
        agent_keys.append(key)

    # Determine winner key directly from the winner agent
    winner_depth = getattr(winner_agent, "history_depth", 2)
    winner_rules = getattr(winner_agent, "rules_summary", False)
    winner_strategy = getattr(winner_agent, "strategy_guide", False)
    winner_key = _make_key(winner_agent.model, winner_depth,
                           winner_rules, winner_strategy)
    if winner_key not in stats:
        rules_str = "Yes" if winner_rules else "No"
        strategy_str = "Yes" if winner_strategy else "No"
        stats[winner_key] = {
            "model": winner_agent.model, "history_depth": winner_depth,
            "rules": rules_str, "strategy": strategy_str,
            "games_played": 0, "games_won": 0, "elo": ELO_START,
            "total_tokens": 0, "cached_tokens": 0, "total_queries": 0,
            "bluffs": 0, "bluffs_caught": 0,
            "challenges_issued": 0, "challenges_correct": 0,
            "card_guesses_total": 0, "card_guesses_correct": 0,
        }
    stats[winner_key]["games_won"] += 1

    # Compute and apply ELO updates (deduplicate keys for same-model matchups)
    unique_keys = list(dict.fromkeys(agent_keys))
    new_elos = _compute_elo_updates(unique_keys, stats, winner_key)
    for key, new_elo in new_elos.items():
        stats[key]["elo"] = new_elo

    _save_stats(stats)
    _append_game_log(agents, winner_agent, seed)
    _append_game_log_2(agents, winner_agent, seed)
    _append_game_log_3(agents, winner_agent, seed)
