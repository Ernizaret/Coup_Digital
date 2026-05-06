"""Build minimal prompts for AI agents based on current game state."""

from src.controller import State


def build_prompt(controller, player, agent, event_log):
    """Build a prompt string for an AI agent given the current game state.

    Args:
        controller: GameController instance
        player: Player object for this agent
        agent: Agent instance (for history_depth)
        event_log: list of {"type": "event"/"speech", ...} dicts
    """
    sections = [
        _identity_section(controller, player),
        _game_state_section(controller, player),
        _history_section(event_log, player, agent.history_depth),
        _decision_section(controller, player),
        _response_format(),
    ]
    return "\n\n".join(s for s in sections if s)


def _identity_section(controller, player):
    """One-line identity statement."""
    others = [p.name for p in controller.game.players
              if p != player and p.is_alive()]
    if others:
        return f"You are {player.name} playing Coup against {', '.join(others)}."
    return f"You are {player.name} playing Coup."


def _game_state_section(controller, player):
    """Current game state: your cards, all players' coins/influence, revealed cards."""
    game = controller.game
    lines = [f"Your cards: {', '.join(player.influence)} | Coins: {player.coins}"]

    for p in game.players:
        if p == player:
            continue
        if p.is_alive():
            lines.append(f"  {p.name}: {p.coins} coins, {len(p.influence)} card(s)")
        else:
            lines.append(f"  {p.name}: ELIMINATED")

    if game.revealed_cards:
        lines.append(f"Revealed: {', '.join(game.revealed_cards)}")

    return "\n".join(lines)


def _history_section(event_log, player, history_depth):
    """Recent log entries, sliced by turn boundaries.

    A "turn boundary" is identified by log entries containing "chooses"
    (which marks the start of each player's action). We count back
    history_depth turn boundaries from the end to determine the slice.

    history_depth=0 means no history.
    history_depth=1 means events since the last time it was this player's turn.
    history_depth=2 means events since two turns ago for this player.
    etc.
    """
    if history_depth <= 0 or not event_log:
        return ""

    # Find indices of turn starts for THIS player (marked by "chooses" events)
    player_turn_indices = []
    for i, entry in enumerate(event_log):
        if (entry["type"] == "event"
                and f"{player.name} chooses" in entry.get("text", "")):
            player_turn_indices.append(i)

    if not player_turn_indices:
        # Player hasn't taken a turn yet -- show all events
        recent = event_log
    elif history_depth >= len(player_turn_indices):
        # Want more history than available -- show everything
        recent = event_log
    else:
        # Slice from N turns back
        start_idx = player_turn_indices[-history_depth]
        recent = event_log[start_idx:]

    lines = ["Recent:"]
    for entry in recent:
        if entry["type"] == "event":
            lines.append(f"  {entry['text']}")
        elif entry["type"] == "speech":
            lines.append(f"  {entry['player']}: \"{entry['text']}\"")
    return "\n".join(lines)


def _decision_section(controller, player):
    """Tell the agent what decision to make and list valid options."""
    message, options = controller.get_prompt(player)
    lines = [message]
    if options:
        lines.append(f"Options: {options}")
    return "\n".join(lines)


def _response_format():
    """JSON response format -- action and speech only."""
    return (
        'Respond with JSON only:\n'
        '{"speech": "your statement", "action": "chosen option"}'
    )
