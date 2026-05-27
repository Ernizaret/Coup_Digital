"""
Build JSON data files for the AI Coup Arena website.

Reads from AI_game/ CSV and markdown files, produces:
  - website/data/winrates.json
  - website/data/logs_index.json

Usage:
    python scripts/build_site_data.py
"""

import csv
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AI_GAME = ROOT / "AI_game"
WEBSITE_DATA = ROOT / "website" / "data"


def build_winrates_json():
    """Convert winrates.csv to winrates.json."""
    src = AI_GAME / "winrates.csv"
    rows = []
    with open(src, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip completely empty rows
            if not row.get("model"):
                continue
            # Convert numeric fields
            converted = {}
            for key, val in row.items():
                if key == "model":
                    converted[key] = val
                else:
                    try:
                        # Try int first, then float
                        if "." in val:
                            converted[key] = float(val)
                        else:
                            converted[key] = int(val)
                    except (ValueError, TypeError):
                        converted[key] = val
            rows.append(converted)

    WEBSITE_DATA.mkdir(parents=True, exist_ok=True)
    out = WEBSITE_DATA / "winrates.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    print(f"Wrote {len(rows)} rows to {out}")


def parse_log_header(filepath):
    """Extract metadata from a game log markdown file header."""
    meta = {
        "filename": filepath.name,
        "date": None,
        "players": [],
        "winner": None,
        "turns": 0,
    }

    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    # Extract date
    m = re.search(r"\*\*Date:\*\*\s*(.+)", content)
    if m:
        meta["date"] = m.group(1).strip()

    # Extract players — format: "Name (model/id), Name2 (model/id2)"
    m = re.search(r"\*\*Players:\*\*\s*(.+)", content)
    if m:
        players_str = m.group(1).strip()
        # Parse "Name (model)" entries
        player_entries = re.findall(r"(\w+)\s*\(([^)]+)\)", players_str)
        meta["players"] = [
            {"name": name, "model": model} for name, model in player_entries
        ]

    # Extract winner
    m = re.search(r"\*\*Winner:\*\*\s*(.+)", content)
    if m:
        meta["winner"] = m.group(1).strip()

    # Count turns — "### Turn N"
    turns = re.findall(r"### Turn \d+", content)
    meta["turns"] = len(turns)

    # Check if a review exists for this game
    date_part = filepath.stem.replace("game_", "")
    review_path = AI_GAME / "review" / f"review_{date_part}.md"
    meta["has_review"] = review_path.exists()

    return meta


def build_logs_index_json():
    """Parse all game log files and build an index manifest."""
    logs_dir = AI_GAME / "logs"
    if not logs_dir.exists():
        print(f"Logs directory not found: {logs_dir}")
        return

    log_files = sorted(logs_dir.glob("game_*.md"))
    print(f"Found {len(log_files)} game log files")

    entries = []
    for i, lf in enumerate(log_files):
        meta = parse_log_header(lf)
        if meta:
            entries.append(meta)
        if (i + 1) % 100 == 0:
            print(f"  Parsed {i + 1}/{len(log_files)}...")

    # Sort by date descending (most recent first)
    entries.sort(key=lambda x: x.get("date") or "", reverse=True)

    WEBSITE_DATA.mkdir(parents=True, exist_ok=True)
    out = WEBSITE_DATA / "logs_index.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    print(f"Wrote {len(entries)} log entries to {out}")


if __name__ == "__main__":
    print("Building winrates.json...")
    build_winrates_json()
    print()
    print("Building logs_index.json...")
    build_logs_index_json()
    print()
    print("Done!")
