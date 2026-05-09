"""Build minimal, token-efficient prompts for AI agents based on current game state."""

from src.controller import State, ACTION_INFO

# Rules summary text covering all actions, challenge/block mechanics,
# losing influence, and the win condition.  Included in the prompt only
# when the agent has rules_summary=True.
RULES_SUMMARY = """\
RULES REFERENCE:
Actions:
  - Income: Take 1 coin. No card claim. Cannot be blocked or challenged.
  - Foreign Aid: Take 2 coins. No card claim. Can be blocked by Duke.
  - Coup: Pay 7 coins to force a player to lose influence. Cannot be blocked or challenged. You MUST coup if you have 10+ coins.
  - Tax: Claim Duke. Take 3 coins from the treasury.
  - Assassinate: Claim Assassin. Pay 3 coins to force a target to lose influence. Can be blocked by Contessa.
  - Steal: Claim Captain. Take 2 coins from a target player. Can be blocked by Captain or Ambassador.
  - Exchange: Claim Ambassador. Draw 2 cards from the deck, choose which to keep, return 2.

Challenge rules:
  - Any player can challenge another player's claimed card.
  - If the challenge succeeds (player did NOT have the claimed card), the challenged player loses influence.
  - If the challenge fails (player DID have the claimed card), the challenger loses influence and the challenged player reshuffles their revealed card into the deck and draws a replacement.

Block rules:
  - Specific cards can block specific actions (Duke blocks Foreign Aid, Contessa blocks Assassinate, Captain/Ambassador block Steal).
  - A block is itself a card claim and can be challenged by any player.
  - If a block is not challenged, or the challenge of the block fails, the block stands and the original action is cancelled.

Losing influence:
  - When you lose influence, you choose one of your cards to reveal (eliminate). That card is permanently out of play.

Win condition:
  - The last player with at least one unrevealed card (influence) wins the game."""

STRATEGY_GUIDE = """\
STRATEGY GUIDE:
- In the early game, you want to be the Duke so you can gain the coin advantage. 
The Assassin can be nice to knock opponents down in influence early and the Contessa can help to block early assassination attempts as well. 
If you are none of these, you may want to take the Ambassador action and exchange your cards with the Court Deck.
- Do not take foreign aid in the early game. There will likely be many others claiming to be the Duke and taking 3 coins so it will not be much of a risk to also claim to be the Duke to block your foreign aid.
In your first few turns, pretend to be the Duke, even if you are not. Getting 3 coins per turn will be extremely helpful later in the game. 
It will not be worth it for your opponents to challenge you unless you do it every single time. 
It does make you a bit of a target if you have more coins than anyone else, so do not be afraid to use them early to assassinate someone.
- The best late game character is the Captain to steal and block others’ stealing and control the cash flow. 
The Contessa can also be nice if someone attempts to assassinate you and the Assassin can be good for a final assassination for 3 coins instead of 7. 
If you are not one of these after the first player is exiled, you may want to take the Ambassador action to exchange cards with the Court Deck.
- Once you get into the late game when there are 1-2 opponents remaining, taking foreign aid can force others to give you information or allow you to get 2 coins each turn. 
2 coins and information may be more valuable late game than getting 3 coins with the Duke.
- Stealing with the Captain gets to be far more valuable in the late game as your number of opponents decreases. 
If you have a single opponent, taking 2 coins from them means +2 for you and -2 for them, resulting in a 4 coin swing in your favor, and likely securing an uncontested Coup in a matter of turns.
- If you and an opponent each have 1 influence, it comes down to who will be able to get up to 7 coins first. 
You usually have three options here: steal with the Captain, tax with the Duke, or assassinate with the Assassin. 
If you do not have any of these characters, you better start faking it as the Captain or the Duke until you have the coin advantage or you will lose.
- There are only 15 cards in the whole Court Deck, so you can do some quick probability calculations every time someone takes a character action to get a feel for the likelihood that they are telling the truth. 
Use that, along with past character actions and any tells they may have to help make your final decision about when to challenge.
"""


def build_prompt_sections(controller, player, event_log, history_depth=2,
                          rules_summary=False, strategy_guide=False):
    """Build structured prompt sections for an AI agent given the current game state.

    Returns a dict with keys:
        - "identity": str -- identity line (cacheable, never changes)
        - "rules_summary": str -- rules reference (cacheable, static; empty when disabled)
        - "strategy_guide": str -- strategy tips (cacheable, static; empty when disabled)
        - "game_log": str -- turn history based on history_depth (grows only)
        - "decision_prompt": str -- game state + decision + response format (changes each query)

    Args:
        controller: GameController instance
        player: Player object for this agent
        event_log: list of {"type": "event"/"speech", ..., "turn": int} dicts
        history_depth: int -- how many turns of history to include (0 = none)
        rules_summary: bool -- whether to include the rules reference section
        strategy_guide: bool -- whether to include the strategy guide section
    """
    identity = _identity_section(controller, player)
    rules = RULES_SUMMARY if rules_summary else ""
    strategy = STRATEGY_GUIDE if strategy_guide else ""
    game_log = _turn_history_section(event_log, player, history_depth)

    decision_parts = [
        _game_state_section(controller, player),
        _decision_section(controller, player),
        _response_format(),
    ]
    decision_prompt = "\n".join(decision_parts)

    return {
        "identity": identity,
        "rules_summary": rules,
        "strategy_guide": strategy,
        "game_log": game_log,
        "decision_prompt": decision_prompt,
    }


def build_prompt(controller, player, event_log, history_depth=2,
                 rules_summary=False, strategy_guide=False):
    """Build a flat prompt string for an AI agent given the current game state.

    This is a convenience wrapper around build_prompt_sections() that returns
    a single concatenated string.

    Args:
        controller: GameController instance
        player: Player object for this agent
        event_log: list of {"type": "event"/"speech", ..., "turn": int} dicts
        history_depth: int -- how many turns of history to include (0 = none)
        rules_summary: bool -- whether to include the rules reference section
        strategy_guide: bool -- whether to include the strategy guide section
    """
    sections = build_prompt_sections(controller, player, event_log,
                                     history_depth,
                                     rules_summary=rules_summary,
                                     strategy_guide=strategy_guide)
    parts = [sections["identity"]]
    if sections["rules_summary"]:
        parts.append(sections["rules_summary"])
    if sections["strategy_guide"]:
        parts.append(sections["strategy_guide"])
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
        numbered = " | ".join(options)
        lines.append(f"Valid choices: [{numbered}]")
        lines.append(
            "You MUST pick exactly one of the above choices. "
            "Put your chosen option in the \"action\" field verbatim."
        )

    return "\n".join(lines)


def _response_format():
    """Response format instructions -- JSON with action and speech only."""
    return (
        '\nRESPOND IN JSON:\n'
        '{"speech": "your public statement to go with your action. please be concise and keep it short.", '
        '"action": "one of the valid choices listed above, copied exactly"}'
    )


VALID_CARD_TYPES = ["Duke", "Assassin", "Captain", "Ambassador", "Contessa"]


def build_survey_prompt_sections(controller, player, event_log,
                                  history_depth=2, rules_summary=False,
                                  strategy_guide=False):
    """Build structured prompt sections for a card-guess survey.

    Returns a dict with the same keys as build_prompt_sections():
        - "identity": str
        - "rules_summary": str (empty when disabled)
        - "strategy_guide": str (empty when disabled)
        - "game_log": str
        - "decision_prompt": str -- game state + survey question + response format

    The decision_prompt replaces the normal DECIDE section with a SURVEY section
    asking the player to guess hidden cards of each remaining opponent.
    """
    identity = _identity_section(controller, player)
    rules = RULES_SUMMARY if rules_summary else ""
    strategy = STRATEGY_GUIDE if strategy_guide else ""
    game_log = _turn_history_section(event_log, player, history_depth)

    survey_parts = [
        _game_state_section(controller, player),
        _survey_section(controller, player),
        _survey_response_format(),
    ]
    decision_prompt = "\n".join(survey_parts)

    return {
        "identity": identity,
        "rules_summary": rules,
        "strategy_guide": strategy,
        "game_log": game_log,
        "decision_prompt": decision_prompt,
    }


def _survey_section(controller, player):
    """Build the SURVEY section listing each opponent's hidden card count."""
    game = controller.game
    lines = [
        "SURVEY: Guess the hidden cards of each remaining player.",
    ]

    for p in game.players:
        if p == player or not p.is_alive():
            continue
        hidden_count = len(p.influence)
        if hidden_count == 1:
            lines.append(f"- {p.name} (1 hidden card): guess 1 card")
        else:
            lines.append(
                f"- {p.name} ({hidden_count} hidden cards): "
                f"guess {hidden_count} cards"
            )

    card_list = " | ".join(VALID_CARD_TYPES)
    lines.append(f"\nValid card types: [{card_list}]")

    return "\n".join(lines)


def _survey_response_format():
    """Response format for the card-guess survey -- JSON with guesses dict."""
    return (
        '\nRESPOND IN JSON:\n'
        '{"guesses": {"PlayerName": ["Card1", "Card2"], ...}}\n'
        'Provide your best guess for each opponent\'s hidden cards. '
        'Use exact card names from the valid card types list.'
    )
