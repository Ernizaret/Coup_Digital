"""Markdown transcript writer for AI Coup games.

Accumulates game events during play and writes a complete markdown transcript
file to AI_game/logs/ when the game ends.
"""

import os
from datetime import datetime

# Directory where transcript files are stored
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")


class LogWriter:
    """Accumulates game events and writes a markdown transcript at game end.

    Mirrors the relevant ConsoleOutput method signatures so GameRunner can
    call both outputs at the same event points.
    """

    def __init__(self):
        self._lines = []          # accumulated markdown lines
        self._header_info = {}    # populated in game_started()
        self._timestamp = datetime.now()

    def game_started(self, controller, prompt_mode="heavy", seed=None):
        """Record header info (date, players, models, seed).

        The header is written to the file later in game_over() once we
        know the winner.
        """
        players = []
        for p in controller.game.players:
            players.append(p.name)
        self._header_info = {
            "date": self._timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "players": players,
            "prompt_mode": prompt_mode,
            "seed": seed,
        }

    def turn_start(self, player_name, turn_number):
        """Start a new turn section in the transcript."""
        self._lines.append("")
        self._lines.append(f"### Turn {turn_number} \u2014 {player_name}")

    def agent_response(self, name, speech, action):
        """Record an agent's speech and chosen action."""
        self._lines.append(f"> \"{speech}\"")
        self._lines.append(f"**Action:** {action}")

    def agent_speech(self, name, speech):
        """Record a speech-only line (for challenges, blocks, etc.)."""
        self._lines.append(f"> {name}: \"{speech}\"")

    def game_event(self, text):
        """Record a game event from the controller log."""
        self._lines.append(f"[Event] {text}")

    def game_over(self, winner_name, winner_agent=None):
        """Assemble and write the complete markdown transcript to disk.

        Args:
            winner_name: display name of the winning player.
            winner_agent: the winning Agent instance (used to read
                private_thoughts and model). May be None if unavailable.
        """
        # Build the agent info string: "Name (model)" for each player
        agents_info = self._header_info.get("players", [])
        agent_model_map = {}
        if winner_agent is not None:
            # We'll get model info from the agents list passed later;
            # for now just store the winner's model.
            agent_model_map[winner_agent.name] = winner_agent.model

        # Assemble the full document
        doc = []
        doc.append("# Coup \u2014 AI Game Transcript")
        doc.append(f"**Date:** {self._header_info.get('date', 'unknown')}")

        # Seed line
        seed = self._header_info.get("seed")
        if seed is not None:
            doc.append(f"**Seed:** {seed}")

        # Players line
        players_str = ", ".join(agents_info)
        doc.append(f"**Players:** {players_str}")
        doc.append(f"**Winner:** {winner_name}")
        doc.append("")
        doc.append("---")
        doc.append("")
        doc.append("## Game Log")

        # Append the accumulated game lines
        doc.extend(self._lines)

        # Winner's private thoughts
        if winner_agent is not None and winner_agent.private_thoughts:
            doc.append("")
            doc.append("---")
            doc.append("")
            doc.append(f"## Winner's Private Thoughts \u2014 {winner_name}")
            for thought in winner_agent.private_thoughts:
                doc.append(f"- {thought}")

        doc.append("")  # trailing newline

        # Write to disk
        self._write_file("\n".join(doc))

    def set_agents(self, agents):
        """Store agent list so we can include model info in the header.

        Call this right after game_started() so the player line includes
        model identifiers.
        """
        agent_map = {a.name: a for a in agents}
        # Rebuild players list with model info
        enriched = []
        for name in self._header_info.get("players", []):
            agent = agent_map.get(name)
            if agent:
                enriched.append(f"{name} ({agent.model})")
            else:
                enriched.append(name)
        self._header_info["players"] = enriched

    def _write_file(self, content):
        """Write the markdown content to a timestamped file in the logs dir."""
        os.makedirs(LOGS_DIR, exist_ok=True)
        filename = f"game_{self._timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.md"
        filepath = os.path.join(LOGS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
