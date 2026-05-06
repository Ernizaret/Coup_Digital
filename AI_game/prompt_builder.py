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

RULES_SUMMARY_LIGHT = """\
COUP: 2 coins, 2 hidden cards each. Cards: Duke, Assassin, Captain, Contessa, Ambassador (3 each).
Actions: Income(+1), Foreign Aid(+2, blocked by Duke), Tax(+3, Duke), Steal(+2 from target, Captain, blocked by Ambassador/Captain), Exchange(draw 2 return 2, Ambassador), Assassinate(pay 3, target -1 influence, Assassin, blocked by Contessa), Coup(pay 7, target -1 influence, mandatory at 10+).
Challenge: have card = challenger loses influence; don't have = you lose, action cancelled. Blocks can be challenged too.
"""

# Number of log entries to include in each mode
_LOG_WINDOW_HEAVY = 30
_LOG_WINDOW_LIGHT = 10


def build_prompt_sections(controller, player, agent, event_log, prompt_mode="heavy"):
    """Build structured prompt sections for an AI agent given the current game state.

    Returns a dict with keys:
        - "rules_summary": str — static rules text (cacheable, never changes)
        - "private_thoughts": str — agent's accumulated private thoughts (grows only)
        - "game_log": str — recent public game events (grows only)
        - "decision_prompt": str — game state + decision + response format (changes each query)

    In heavy mode (default): uses full response format (with private_thought)
    for CHOOSE_ACTION, slim format for other states. Includes full rules
    summary and larger game log window.

    In light mode: always uses slim response format (no private_thought),
    uses shorter rules summary, smaller game log window, and omits private
    thoughts from the private info section.

    Args:
        controller: GameController instance
        player: Player object for this agent
        agent: Agent instance (for private thoughts)
        event_log: list of {"type": "event"/"speech", ...} dicts
        prompt_mode: "heavy" or "light"
    """
    is_light = prompt_mode == "light"
    is_turn = controller.state == State.CHOOSE_ACTION
    use_full_format = is_turn and not is_light
    log_window = _LOG_WINDOW_LIGHT if is_light else _LOG_WINDOW_HEAVY

    rules_summary = RULES_SUMMARY_LIGHT if is_light else RULES_SUMMARY

    if is_light:
        private_thoughts = ""
    else:
        private_thoughts = (
            "YOUR PREVIOUS PRIVATE THOUGHTS:\n" + agent.get_thoughts_text()
        )

    game_log = _public_log_section(event_log, log_window=log_window)

    decision_parts = [
        _game_state_section(controller, player),
        _private_info_section(player, agent, include_thoughts=False),
        _decision_section(controller, player),
        _response_format_full() if use_full_format else _response_format_slim(),
    ]
    decision_prompt = "\n".join(decision_parts)

    return {
        "rules_summary": rules_summary,
        "private_thoughts": private_thoughts,
        "game_log": game_log,
        "decision_prompt": decision_prompt,
    }


def build_prompt(controller, player, agent, event_log, prompt_mode="heavy"):
    """Build a flat prompt string for an AI agent given the current game state.

    This is a convenience wrapper around build_prompt_sections() that returns
    a single concatenated string. Used for backward compatibility.

    Args:
        controller: GameController instance
        player: Player object for this agent
        agent: Agent instance (for private thoughts)
        event_log: list of {"type": "event"/"speech", ...} dicts
        prompt_mode: "heavy" or "light"
    """
    sections = build_prompt_sections(controller, player, agent, event_log, prompt_mode)
    parts = [sections["rules_summary"]]
    if sections["private_thoughts"]:
        parts.append(sections["private_thoughts"])
    parts.append(sections["game_log"])
    parts.append(sections["decision_prompt"])
    return "\n".join(parts)


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


def _private_info_section(player, agent, include_thoughts=True):
    """Private information only this player can see."""
    lines = ["YOUR PRIVATE INFO:"]
    lines.append(f"Your cards: {', '.join(player.influence)}")
    lines.append(f"Your coins: {player.coins}")
    if include_thoughts:
        lines.append(f"Your previous private thoughts:\n{agent.get_thoughts_text()}")
    return "\n".join(lines)


def _public_log_section(event_log, log_window=_LOG_WINDOW_HEAVY):
    """Recent public history of events and speech."""
    lines = ["PUBLIC GAME LOG:"]
    if not event_log:
        lines.append("  (Game just started — no events yet)")
    else:
        recent = event_log[-log_window:]
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
