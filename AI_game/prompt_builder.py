"""Build context-rich prompts for AI agents based on current game state."""

from src.controller import State, ACTION_INFO

RULES_SUMMARY = """\
COUP RULES:
- Each player starts with 2 coins and 2 hidden influence cards.
- Card types: Duke, Assassin, Captain, Contessa, Ambassador (3 of each in the game).
- On your turn, choose one action. Some actions claim a card — anyone may challenge.
- If challenged and you HAVE the card: challenger loses 1 influence; your card is swapped.
- If challenged and you DON'T have the card: you lose 1 influence; action is cancelled.
- Some actions can be blocked by specific cards. Blocks can also be challenged.
- Lose both influence cards and you are eliminated. Last player standing wins.

ACTIONS:
- Income: Take 1 coin. (No card claim, cannot be blocked)
- Foreign Aid: Take 2 coins. (No card claim, can be blocked by Duke)
- Tax: Take 3 coins. (Claims Duke, cannot be blocked)
- Steal: Take 2 coins from a target. (Claims Captain, blocked by Ambassador or Captain)
- Exchange: Draw 2 cards, return 2. (Claims Ambassador, cannot be blocked)
- Assassinate: Pay 3 coins, target loses 1 influence. (Claims Assassin, blocked by Contessa)
- Coup: Pay 7 coins, target loses 1 influence. (No card claim, cannot be blocked, MANDATORY at 10+ coins)
"""


def build_prompt(controller, player, agent, event_log):
    """Build a prompt string for an AI agent given the current game state.

    Uses the full response format (speech + action + private_thought) for
    CHOOSE_ACTION, and a slim action-only format for all other states.

    Args:
        controller: GameController instance
        player: Player object for this agent
        agent: Agent instance (for private thoughts)
        event_log: list of {"type": "event"/"speech", ...} dicts
    """
    is_turn = controller.state == State.CHOOSE_ACTION
    sections = [
        RULES_SUMMARY,
        _game_state_section(controller, player),
        _private_info_section(player, agent),
        _public_log_section(event_log),
        _decision_section(controller, player),
        _response_format_full() if is_turn else _response_format_slim(),
    ]
    return "\n".join(sections)


def _game_state_section(controller, player):
    """Current game state visible to all players."""
    game = controller.game
    lines = ["CURRENT GAME STATE:"]

    if controller.current_player:
        lines.append(f"Current turn: {controller.current_player.name}")

    for p in game.players:
        alive = "ALIVE" if p.is_alive() else "ELIMINATED"
        cards_count = len(p.influence)
        marker = " (you)" if p == player else ""
        lines.append(
            f"  {p.name}{marker}: {p.coins} coins, "
            f"{cards_count} influence card(s) [{alive}]"
        )

    if game.revealed_cards:
        lines.append(f"Revealed cards: {', '.join(game.revealed_cards)}")
    else:
        lines.append("Revealed cards: None yet")

    return "\n".join(lines)


def _private_info_section(player, agent):
    """Private information only this player can see."""
    lines = ["YOUR PRIVATE INFO:"]
    lines.append(f"Your cards: {', '.join(player.influence)}")
    lines.append(f"Your coins: {player.coins}")
    lines.append(f"Your previous private thoughts:\n{agent.get_thoughts_text()}")
    return "\n".join(lines)


def _public_log_section(event_log):
    """Recent public history of events and speech."""
    lines = ["PUBLIC GAME LOG:"]
    if not event_log:
        lines.append("  (Game just started — no events yet)")
    else:
        # Show last 30 entries to keep prompt manageable
        recent = event_log[-30:]
        for entry in recent:
            if entry["type"] == "event":
                lines.append(f"  [Event] {entry['text']}")
            elif entry["type"] == "speech":
                lines.append(f"  [Speech] {entry['player']}: \"{entry['text']}\"")
    return "\n".join(lines)


def _decision_section(controller, player):
    """State-specific instructions telling the agent what decision to make."""
    message, options = controller.get_prompt(player)

    lines = ["DECISION REQUIRED:", message]

    state = controller.state

    if state == State.CHOOSE_ACTION:
        lines.append("\nAvailable actions and what they do:")
        for opt in options:
            if opt in ACTION_INFO:
                claimed, blockable, needs_target, cost = ACTION_INFO[opt]
                desc_parts = []
                if cost > 0:
                    desc_parts.append(f"costs {cost} coins")
                if claimed:
                    desc_parts.append(f"claims {claimed}")
                if blockable:
                    desc_parts.append(f"can be blocked by {'/'.join(blockable)}")
                if needs_target:
                    desc_parts.append("requires a target")
                desc = "; ".join(desc_parts) if desc_parts else "no special requirements"
                lines.append(f"  - {opt}: {desc}")

    if options:
        lines.append(f"\nYour valid choices: {options}")
        lines.append("You MUST pick one of the above options exactly as written.")

    return "\n".join(lines)


def _response_format_full():
    """Full response format for turn actions — includes speech and private thought."""
    return (
        '\nRESPOND WITH EXACTLY THIS JSON FORMAT (no other text):\n'
        '{\n'
        '  "speech": "your public statement to other players. use this strategically or however you see fit.",\n'
        '  "action": "your chosen option from the valid choices above",\n'
        '  "private_thought": "your private strategic reasoning (optional, not shown to others). Keep it concise and focused."\n'
        '}'
    )


def _response_format_slim():
    """Slim response format for reactive decisions ."""
    return (
        '\nRESPOND WITH EXACTLY THIS JSON FORMAT (no other text):\n'
        '{\n'
        '  "speech": "your public statement to other players",\n'
        '  "action": "your chosen option from the valid choices above"\n'
        '}'
    )
