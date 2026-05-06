"""Load, validate, and apply game preset configurations for AI games."""

import json
import os

PRESETS_FILENAME = "presets.json"
VALID_CARDS = ["Duke", "Assassin", "Captain", "Contessa", "Ambassador"]
STANDARD_DECK = VALID_CARDS * 3  # 15 cards total
MAX_CARD_COUNT = 3


class PresetError(Exception):
    """Raised when a preset configuration is invalid."""
    pass


def _find_presets_path():
    """Look for presets.json in the project root (parent of AI_game/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    return os.path.join(project_root, PRESETS_FILENAME)


def load_presets_file(path=None):
    """Load and parse the presets JSON file.

    Args:
        path: Optional path to the presets file. If None, uses default location.

    Returns:
        Dict with "presets" key containing named preset configurations.

    Raises:
        FileNotFoundError: If the presets file doesn't exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    if path is None:
        path = _find_presets_path()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Presets file not found: {path}\n"
            f"Create a presets.json file in the project root."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_preset(presets_data, preset_name):
    """Retrieve a named preset from the presets data.

    Args:
        presets_data: Parsed presets JSON dict.
        preset_name: Name of the preset to retrieve.

    Returns:
        The preset configuration dict.

    Raises:
        PresetError: If the preset name doesn't exist.
    """
    presets = presets_data.get("presets", {})
    if preset_name not in presets:
        available = list(presets.keys())
        raise PresetError(
            f"Preset '{preset_name}' not found. "
            f"Available presets: {available}"
        )
    return presets[preset_name]


def validate_preset(preset):
    """Validate a preset configuration.

    Checks:
    - Each player has exactly 1 or 2 influence cards
    - All card names are valid
    - No card type exceeds its maximum count of 3 across all hands + deck
    - Total cards across all hands + remaining deck <= 15
    - Coin counts are non-negative integers

    Args:
        preset: A preset configuration dict.

    Raises:
        PresetError: If validation fails.
    """
    players = preset.get("players", {})

    if not players:
        raise PresetError("Preset must define at least one player.")

    # Collect all cards assigned to player hands
    all_hand_cards = []

    for player_name, player_cfg in players.items():
        # Validate hand
        hand = player_cfg.get("hand")
        if hand is not None:
            if not isinstance(hand, list):
                raise PresetError(
                    f"Player '{player_name}': hand must be a list of card names."
                )
            if len(hand) < 1 or len(hand) > 2:
                raise PresetError(
                    f"Player '{player_name}': hand must have exactly 1 or 2 cards, "
                    f"got {len(hand)}."
                )
            for card in hand:
                if card not in VALID_CARDS:
                    raise PresetError(
                        f"Player '{player_name}': invalid card '{card}'. "
                        f"Valid cards: {VALID_CARDS}"
                    )
            all_hand_cards.extend(hand)

        # Validate coins
        coins = player_cfg.get("coins")
        if coins is not None:
            if not isinstance(coins, int) or coins < 0:
                raise PresetError(
                    f"Player '{player_name}': coins must be a non-negative integer, "
                    f"got {coins!r}."
                )

    # Validate deck if explicitly provided
    deck_cfg = preset.get("deck")
    deck_cards = []
    if deck_cfg is not None and deck_cfg != "auto":
        if not isinstance(deck_cfg, list):
            raise PresetError("Deck must be 'auto', null, or a list of card names.")
        for card in deck_cfg:
            if card not in VALID_CARDS:
                raise PresetError(
                    f"Invalid card in deck: '{card}'. Valid cards: {VALID_CARDS}"
                )
        deck_cards = deck_cfg

    # Check card count constraints
    all_cards = all_hand_cards + deck_cards
    if len(all_cards) > 15:
        raise PresetError(
            f"Total cards across all hands + deck ({len(all_cards)}) exceeds 15."
        )

    # Check no card type exceeds max count
    for card_type in VALID_CARDS:
        count = all_cards.count(card_type)
        if count > MAX_CARD_COUNT:
            raise PresetError(
                f"Card '{card_type}' appears {count} times across hands and deck, "
                f"but maximum is {MAX_CARD_COUNT}."
            )


def compute_remaining_deck(preset):
    """Compute the remaining deck after dealing preset hands.

    If deck is explicitly specified (as a list), returns that list.
    If deck is "auto" or None, computes by removing dealt cards from the standard deck.

    Args:
        preset: A validated preset configuration dict.

    Returns:
        List of card names for the remaining deck.
    """
    deck_cfg = preset.get("deck")

    # Explicit deck
    if isinstance(deck_cfg, list):
        return list(deck_cfg)

    # Auto-calculate: start with standard 15 and remove dealt cards
    remaining = list(STANDARD_DECK)
    players = preset.get("players", {})
    for player_name, player_cfg in players.items():
        hand = player_cfg.get("hand")
        if hand is not None:
            for card in hand:
                if card in remaining:
                    remaining.remove(card)
                else:
                    raise PresetError(
                        f"Cannot auto-compute deck: card '{card}' for player "
                        f"'{player_name}' not available in remaining standard deck."
                    )
    return remaining


def apply_preset(preset, agents):
    """Apply a preset configuration to create game objects with custom state.

    This creates Player objects with pre-assigned hands and coins, and a Deck
    with the appropriate remaining cards. Returns the objects needed to
    construct a Game with skip_deal=True.

    Args:
        preset: A validated preset configuration dict.
        agents: List of Agent instances in turn order.

    Returns:
        Tuple of (players, deck_cards) where:
        - players: list of Player objects with hands and coins set
        - deck_cards: list of card names for the Deck

    Raises:
        PresetError: If agent names don't match preset player names.
    """
    from src.player import Player

    players_cfg = preset.get("players", {})

    # Determine turn order: use preset's turn_order if specified,
    # otherwise use the order agents are provided
    turn_order = preset.get("turn_order")
    if turn_order is not None:
        # Reorder agents to match turn_order
        agent_map = {a.name: a for a in agents}
        ordered_names = turn_order
    else:
        ordered_names = [a.name for a in agents]

    # Validate that all preset players have a matching agent
    for player_name in players_cfg:
        agent_names = [a.name for a in agents]
        if player_name not in agent_names:
            raise PresetError(
                f"Preset references player '{player_name}' but no agent with that "
                f"name exists. Available agents: {agent_names}"
            )

    # Create players in turn order
    players = []
    for name in ordered_names:
        p = Player(name)
        cfg = players_cfg.get(name, {})

        # Set coins (default: 2, already set by Player.__init__)
        coins = cfg.get("coins")
        if coins is not None:
            p.coins = coins

        # Set hand
        hand = cfg.get("hand")
        if hand is not None:
            for card in hand:
                p.add_influence(card)

        players.append(p)

    # Compute remaining deck
    deck_cards = compute_remaining_deck(preset)

    return players, deck_cards
