"""Load, validate, and apply custom game presets for AI games.

A preset defines starting conditions: per-player hands and coins, and
optionally the remaining deck composition. This enables controlled
experiments where the only variable is AI decision-making.
"""

import json
import os

from src.player import Player
from src.coup import Game

PRESETS_FILENAME = "presets.json"
VALID_CARDS = ["Duke", "Assassin", "Captain", "Contessa", "Ambassador"]
CARDS_PER_TYPE = 3
TOTAL_CARDS = len(VALID_CARDS) * CARDS_PER_TYPE  # 15


def _find_presets_path():
    """Look for presets.json in the project root (parent of AI_game/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    return os.path.join(project_root, PRESETS_FILENAME)


def load_presets():
    """Read presets.json and return the parsed dict of presets.

    Returns:
        dict mapping preset names to preset config dicts.

    Raises:
        FileNotFoundError: if presets.json does not exist.
        ValueError: if the file is malformed.
    """
    path = _find_presets_path()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Presets file not found: {path}\n"
            f"Create a presets.json file in the project root."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    presets = data.get("presets", {})
    if not isinstance(presets, dict):
        raise ValueError("'presets' key in presets.json must be a dict.")
    return presets


def get_preset(preset_name):
    """Load presets.json and return a single preset by name.

    Args:
        preset_name: key in the presets dict.

    Returns:
        The preset config dict.

    Raises:
        FileNotFoundError: if presets.json is missing.
        ValueError: if the preset name is not found.
    """
    presets = load_presets()
    if preset_name not in presets:
        available = ", ".join(sorted(presets.keys())) or "(none)"
        raise ValueError(
            f"Preset '{preset_name}' not found. Available: {available}"
        )
    return presets[preset_name]


def validate_preset(preset, player_names):
    """Validate a preset configuration against the game rules.

    Args:
        preset: dict with "players" (and optionally "deck", "description").
        player_names: list of player display names that will play.

    Returns:
        list of error strings. Empty list means valid.
    """
    errors = []
    players_cfg = preset.get("players", {})

    # Check that preset defines players that match the provided names
    preset_player_names = set(players_cfg.keys())
    provided_names = set(player_names)

    # Players in preset but not in game
    extra = preset_player_names - provided_names
    if extra:
        errors.append(
            f"Preset defines players not in the game: {sorted(extra)}"
        )

    # Count all cards assigned to players
    all_hand_cards = []
    for pname, pcfg in players_cfg.items():
        hand = pcfg.get("hand", [])
        coins = pcfg.get("coins", 2)

        # Hand size: must be 1 or 2
        if not isinstance(hand, list):
            errors.append(f"{pname}: 'hand' must be a list, got {type(hand).__name__}.")
            continue
        if len(hand) < 1 or len(hand) > 2:
            errors.append(
                f"{pname}: hand must have 1 or 2 cards, got {len(hand)}."
            )

        # Card validity
        for card in hand:
            if card not in VALID_CARDS:
                errors.append(
                    f"{pname}: invalid card '{card}'. "
                    f"Valid: {VALID_CARDS}"
                )

        all_hand_cards.extend(hand)

        # Coins: non-negative integer
        if not isinstance(coins, int) or coins < 0:
            errors.append(
                f"{pname}: coins must be a non-negative integer, got {coins}."
            )

    # Deck configuration
    deck_cfg = preset.get("deck", "auto")
    deck_cards = []
    if isinstance(deck_cfg, list):
        deck_cards = deck_cfg
        for card in deck_cards:
            if card not in VALID_CARDS:
                errors.append(
                    f"Deck contains invalid card '{card}'. "
                    f"Valid: {VALID_CARDS}"
                )
    elif deck_cfg != "auto":
        errors.append(
            f"'deck' must be 'auto' or a list of cards, got: {deck_cfg}"
        )

    # If deck is auto, compute what the deck would be for card-count checks.
    # Only attempt this if all hand cards are valid (otherwise we can't
    # remove invalid cards from the standard deck).
    all_hand_cards_valid = all(c in VALID_CARDS for c in all_hand_cards)
    if deck_cfg == "auto" and all_hand_cards_valid:
        try:
            deck_cards = _compute_auto_deck(all_hand_cards)
        except ValueError as e:
            errors.append(str(e))

    # Total cards across hands + deck <= 15
    total = len(all_hand_cards) + len(deck_cards)
    if total > TOTAL_CARDS:
        errors.append(
            f"Total cards ({total}) exceeds maximum ({TOTAL_CARDS}). "
            f"Hands: {len(all_hand_cards)}, Deck: {len(deck_cards)}."
        )

    # No card type exceeds 3 across hands + deck
    combined = all_hand_cards + deck_cards
    for card_type in VALID_CARDS:
        count = combined.count(card_type)
        if count > CARDS_PER_TYPE:
            errors.append(
                f"Card '{card_type}' appears {count} times across hands and "
                f"deck (maximum {CARDS_PER_TYPE})."
            )

    return errors


def _compute_auto_deck(hand_cards):
    """Compute the remaining deck given cards already dealt to hands.

    Starts from the standard 15-card deck and removes each card in
    hand_cards. Returns the remaining cards list.

    Args:
        hand_cards: list of card name strings assigned to player hands.

    Returns:
        list of remaining card strings.

    Raises:
        ValueError: if hand_cards contains more of a card type than available.
    """
    remaining = VALID_CARDS * CARDS_PER_TYPE  # copy of full deck list
    remaining = list(remaining)
    for card in hand_cards:
        if card in remaining:
            remaining.remove(card)
        else:
            raise ValueError(
                f"Cannot remove '{card}' from deck — not enough copies. "
                f"Check that no card type exceeds {CARDS_PER_TYPE} total."
            )
    return remaining


def apply_preset(preset, game, player_names):
    """Apply a validated preset to a Game object.

    This should be called after the Game has been created with skip_deal=True.
    It assigns hands, coins, and configures the deck according to the preset.

    Args:
        preset: validated preset dict.
        game: Game instance (created with skip_deal=True so hands are empty).
        player_names: list of player names in turn order (matching game.players).

    Raises:
        ValueError: if the preset is invalid for the given players.
    """
    errors = validate_preset(preset, player_names)
    if errors:
        raise ValueError(
            "Invalid preset:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    players_cfg = preset.get("players", {})
    all_hand_cards = []

    # Build a name-to-player map
    player_map = {p.name: p for p in game.players}

    # Assign hands and coins
    for pname, pcfg in players_cfg.items():
        if pname not in player_map:
            continue  # already validated above
        player = player_map[pname]
        hand = pcfg.get("hand", [])
        coins = pcfg.get("coins", 2)

        # Set coins
        player.coins = coins

        # Assign hand cards
        for card in hand:
            player.add_influence(card)

        all_hand_cards.extend(hand)

    # Configure deck
    deck_cfg = preset.get("deck", "auto")
    if isinstance(deck_cfg, list):
        game.deck.cards = list(deck_cfg)
    else:
        # Auto-compute: start from full deck, remove dealt cards
        game.deck.cards = _compute_auto_deck(all_hand_cards)


def build_preset_game(preset, player_names):
    """Create a fully configured Game from a preset and player names.

    This is a convenience function that creates Player objects, builds the
    Game with skip_deal=True, and applies the preset.

    Args:
        preset: validated preset dict.
        player_names: list of player name strings in turn order.

    Returns:
        Game instance with hands, coins, and deck configured per the preset.

    Raises:
        ValueError: if the preset is invalid.
    """
    players = [Player(name) for name in player_names]
    game = Game(players, skip_deal=True)
    apply_preset(preset, game, player_names)
    return game
