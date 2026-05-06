"""Markdown transcript writer for AI Coup games."""

import os
from datetime import datetime


class LogWriter:
    """Accumulates game events and writes a markdown transcript at game end."""

    def __init__(self):
        self._lines = []
        self._date = datetime.now()
        self._players = []  # list of (name, model) tuples
        self._winner = None
        self._current_turn = None

    def game_started(self, controller, agents):
        """Record game start with player info.

        Args:
            controller: GameController instance (for player state)
            agents: list of Agent instances (for model info)
        """
        agent_map = {a.name: a for a in agents}
        for p in controller.game.players:
            agent = agent_map.get(p.name)
            model = agent.model if agent else "unknown"
            self._players.append((p.name, model))

    def turn_start(self, player_name, turn_number):
        """Record a new turn beginning."""
        self._current_turn = (player_name, turn_number)
        self._lines.append(f"\n### Turn {turn_number} — {player_name}")

    def agent_response(self, name, speech, action):
        """Record an agent's speech and chosen action."""
        self._lines.append(f'> "{speech}"')
        self._lines.append(f"**Action:** {action}")

    def game_event(self, text):
        """Record a game event."""
        self._lines.append(f"[Event] {text}")

    def game_over(self, winner_name):
        """Record game over."""
        self._winner = winner_name

    def token_usage(self, agents):
        """Record token usage — stored for inclusion at end of transcript."""
        self._token_lines = []
        for agent in agents:
            total = agent.prompt_tokens + agent.completion_tokens
            ratio = total / agent.query_count if agent.query_count else 0
            self._token_lines.append(
                f"- **{agent.name}** ({agent.model}): {total:,} tokens "
                f"({agent.prompt_tokens:,} prompt + "
                f"{agent.completion_tokens:,} completion) "
                f"| {ratio:,.0f} tokens/query over {agent.query_count} queries"
            )

    def write(self, winner_name, agents):
        """Write the full markdown transcript to AI_game/logs/.

        Args:
            winner_name: name of the winning player
            agents: list of Agent instances (for private thoughts)
        """
        logs_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(logs_dir, exist_ok=True)

        timestamp = self._date.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"game_{timestamp}.md"
        filepath = os.path.join(logs_dir, filename)

        content = self._build_markdown(winner_name, agents)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def _build_markdown(self, winner_name, agents):
        """Assemble the full markdown transcript."""
        parts = []

        # Header
        date_str = self._date.strftime("%Y-%m-%d %H:%M:%S")
        players_str = ", ".join(
            f"{name} ({model})" for name, model in self._players
        )

        parts.append("# Coup — AI Game Transcript")
        parts.append(f"**Date:** {date_str}")
        parts.append(f"**Players:** {players_str}")
        parts.append(f"**Winner:** {winner_name}")
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append("## Game Log")

        # Game events
        for line in self._lines:
            parts.append(line)

        # Winner's private thoughts
        agent_map = {a.name: a for a in agents}
        winner_agent = agent_map.get(winner_name)
        if winner_agent and winner_agent.private_thoughts:
            parts.append("")
            parts.append("---")
            parts.append("")
            parts.append(f"## Winner's Private Thoughts — {winner_name}")
            for i, thought in enumerate(winner_agent.private_thoughts, 1):
                parts.append(f"- Turn {i}: {thought}")

        # Token usage
        if hasattr(self, "_token_lines") and self._token_lines:
            parts.append("")
            parts.append("---")
            parts.append("")
            parts.append("## Token Usage")
            for line in self._token_lines:
                parts.append(line)

        parts.append("")  # trailing newline
        return "\n".join(parts)
