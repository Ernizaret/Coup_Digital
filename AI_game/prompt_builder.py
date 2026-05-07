"""Build minimal, token-efficient prompts for AI agents based on current game state."""

from src.controller import State, ACTION_INFO


def build_prompt_sections(controller, player, event_log, history_depth=2):
    """Build structured prompt sections for an AI agent given the current game state.

    Returns a dict with keys:
        - "identity": str -- identity line (cacheable, never changes)
        - "game_log": str -- turn history based on history_depth (grows only)
        - "decision_prompt": str -- game state + decision + response format (changes each query)

    Args:
        controller: GameController instance
        player: Player object for this agent
        event_log: list of {"type": "event"/"speech", ..., "turn": int} dicts
        history_depth: int -- how many turns of history to include (0 = none)
    """
    identity = _identity_section(controller, player)
    game_log = _turn_history_section(event_log, player, history_depth)

    decision_parts = [
        _game_state_section(controller, player),
        _decision_section(controller, player),
        _response_format(),
    ]
    decision_prompt = "\n".join(decision_parts)

    return {
        "identity": identity,
        "game_log": game_log,
        "decision_prompt": decision_prompt,
    }


def build_prompt(controller, player, event_log, history_depth=2):
    """Build a flat prompt string for an AI agent given the current game state.

    This is a convenience wrapper around build_prompt_sections() that returns
    a single concatenated string.

    Args:
        controller: GameController instance
        player: Player object for this agent
        event_log: list of {"type": "event"/"speech", ..., "turn": int} dicts
        history_depth: int -- how many turns of history to include (0 = none)
    """
    sections = build_prompt_sections(controller, player, event_log, history_depth)
    parts = [sections["identity"]]
    if sections["game_log"]:
        parts.append(sections["game_log"])
    parts.append(sections["decision_prompt"])
    return "\n".join(parts)


def _identity_section(controller, player):
    """Identity line: who the agent is and who they're playing against."""
    game = controller.game
    others = [p.name for p in game.players if p != player and p.is_alive()]
    if others:
        return f"You are {player.name}, playing Coup against {', '.join(others)}."
    return f"You are {player.name}, playing Coup."


def _game_state_section(controller, player):
    """Current game state: card counts, coins, revealed cards, own hand."""
    game = controller.game
    lines = ["STATE:"]

    for p in game.players:
        if not p.is_alive():
            lines.append(f"  {p.name}: ELIMINATED")
        elif p == player:
            cards = ", ".join(p.influence)
            lines.append(f"  {p.name} (you): cards=[{cards}], coins={p.coins}")
        else:
            lines.append(
                f"  {p.name}: {len(p.influence)} card(s), coins={p.coins}"
            )

    if game.revealed_cards:
        lines.append(f"Revealed: {', '.join(game.revealed_cards)}")

    return "\n".join(lines)


def _turn_history_section(event_log, player, history_depth):
    """Return the last N turns of log history for this player.

    A 'turn' is all events between consecutive CHOOSE_ACTION states for this
    player (i.e., from the start of one of their turns to the start of the next).

    history_depth=0 means no history at all.
    """
    if history_depth <= 0 or not event_log:
        return ""

    # Find turn boundaries for this player
    # Each entry with turn_boundary=True for this player marks a new turn
    turn_starts = []
    for i, entry in enumerate(event_log):
        if entry.get("turn_boundary") and entry.get("turn_player") == player.name:
            turn_starts.append(i)

    if not turn_starts:
        # No turn boundaries found -- include all events if history_depth > 0
        recent = event_log
    else:
        # We want events from the last N turns (not including the current turn)
        # The last turn_start is the current turn, so look back from there
        start_idx = max(0, len(turn_starts) - history_depth)
        slice_from = turn_starts[start_idx]
        recent = event_log[slice_from:]

    if not recent:
        return ""

    lines = ["HISTORY:"]
    for entry in recent:
        if entry.get("turn_boundary"):
            continue  # skip boundary markers themselves
        if entry["type"] == "event":
            lines.append(f"  {entry['text']}")
        elif entry["type"] == "speech":
            lines.append(f"  {entry['player']}: \"{entry['text']}\"")
    return "\n".join(lines)


def _decision_section(controller, player):
    """State-specific instructions telling the agent what decision to make."""
    message, options = controller.get_prompt(player)

    lines = ["DECIDE:", message]

    if options:
        lines.append(f"Options: {options}")
        lines.append("Pick one exactly as listed.")

    return "\n".join(lines)


def _response_format():
    """Response format instructions -- JSON with action and speech only."""
    return (
        '\nRESPOND IN JSON:\n'
        '{"speech": "your public statement to go with your action. please be concise and keep it short.", "action": "your choice"}'
    )
