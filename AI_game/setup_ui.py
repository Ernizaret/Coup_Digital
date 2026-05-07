"""Tkinter setup window: select AI agents and turn order, then start the game.

Supports game count selection (1-999), collapsible custom start conditions
(per-player hand/coin overrides), deck validation, and preset save/load.
"""

import json
import os
import random
import time
import tkinter as tk
from tkinter import messagebox

from AI_game.config import load_config, get_available_agents, get_prompt_mode
from AI_game.agent_factory import create_agents_from_names
from AI_game.game_runner import GameRunner
from AI_game.presets import (
    VALID_CARDS, CARDS_PER_TYPE, TOTAL_CARDS,
    validate_preset, _find_presets_path,
)

# Card dropdown options: "Random" plus the five Coup card types
CARD_OPTIONS = ["Random"] + VALID_CARDS

# Short labels for the deck indicator (e.g. "D" for Duke)
_CARD_SHORT = {
    "Duke": "D",
    "Assassin": "A",
    "Captain": "C",
    "Contessa": "Co",
    "Ambassador": "Am",
}

# ANSI codes for console progress output
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Pure helper functions (no Tkinter dependency — testable without a display)
# ---------------------------------------------------------------------------

def build_preset_from_selections(agent_names, card_selections, coin_values):
    """Build a preset dict from UI selections.

    Args:
        agent_names: list of player display names.
        card_selections: list of (card1, card2) tuples per player where each
            value is a card name string or "Random".
        coin_values: list of int coin values per player.

    Returns:
        A preset dict suitable for validate_preset / apply_preset, or None
        if all settings are at their defaults (both cards Random, 2 coins).
    """
    players_cfg = {}
    has_custom = False

    for i, name in enumerate(agent_names):
        card1, card2 = card_selections[i]
        coins = coin_values[i]

        hand = [c for c in (card1, card2) if c != "Random"]
        is_default = (card1 == "Random" and card2 == "Random" and coins == 2)

        if not is_default:
            has_custom = True

        # Always include every player so validate_preset sees them all
        entry = {"coins": coins}
        if hand:
            entry["hand"] = hand
        else:
            entry["hand"] = []
        players_cfg[name] = entry

    if not has_custom:
        return None

    return {"players": players_cfg, "deck": "auto"}


def compute_remaining_deck(card_selections):
    """Compute the remaining deck composition after assigned cards.

    Args:
        card_selections: list of (card1, card2) tuples; "Random" entries are
            skipped since they will be drawn from the deck at game time.

    Returns:
        dict mapping card name -> remaining count (3 minus assigned count).
    """
    assigned = {}
    for card1, card2 in card_selections:
        for card in (card1, card2):
            if card != "Random":
                assigned[card] = assigned.get(card, 0) + 1

    remaining = {}
    for card_type in VALID_CARDS:
        remaining[card_type] = CARDS_PER_TYPE - assigned.get(card_type, 0)
    return remaining


def format_deck_indicator(remaining):
    """Format the remaining deck dict as a compact string.

    Args:
        remaining: dict from compute_remaining_deck().

    Returns:
        String like "3D 3A 2C 3Co 3Am".
    """
    parts = []
    for card_type in VALID_CARDS:
        count = remaining.get(card_type, 0)
        parts.append(f"{count}{_CARD_SHORT[card_type]}")
    return " ".join(parts)


def validate_deck_config(remaining):
    """Check if the remaining deck composition is valid.

    Args:
        remaining: dict from compute_remaining_deck().

    Returns:
        list of error strings. Empty list means valid.
    """
    errors = []
    for card_type in VALID_CARDS:
        count = remaining.get(card_type, 0)
        if count < 0:
            over = -count
            errors.append(
                f"{card_type}: {CARDS_PER_TYPE + over} assigned "
                f"(max {CARDS_PER_TYPE})"
            )
    return errors


def count_random_cards(card_selections):
    """Count how many 'Random' cards are in the selections.

    Args:
        card_selections: list of (card1, card2) tuples.

    Returns:
        int count of Random entries.
    """
    count = 0
    for card1, card2 in card_selections:
        if card1 == "Random":
            count += 1
        if card2 == "Random":
            count += 1
    return count


def validate_enough_cards_for_random(remaining, num_random):
    """Check that there are enough cards in the deck for random draws.

    Args:
        remaining: dict from compute_remaining_deck().
        num_random: number of Random card slots that need to draw.

    Returns:
        list of error strings. Empty list means valid.
    """
    total_remaining = sum(max(0, v) for v in remaining.values())
    if num_random > total_remaining:
        return [
            f"Need {num_random} random draws but only "
            f"{total_remaining} cards remain in deck"
        ]
    return []


# ---------------------------------------------------------------------------
# Preset file I/O helpers
# ---------------------------------------------------------------------------

def load_preset_names():
    """Load the list of preset names from presets.json.

    Returns:
        list of preset name strings, or empty list if file not found.
    """
    path = _find_presets_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        presets = data.get("presets", {})
        if isinstance(presets, dict):
            return sorted(presets.keys())
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def load_preset_data(preset_name):
    """Load a single preset's data dict from presets.json.

    Returns:
        The preset dict, or None if not found.
    """
    path = _find_presets_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("presets", {}).get(preset_name)
    except (json.JSONDecodeError, TypeError):
        return None


def save_preset_to_file(preset_name, preset_data):
    """Save a preset to presets.json, creating the file if needed.

    Args:
        preset_name: key name for the preset.
        preset_data: the preset dict (players, deck, description).
    """
    path = _find_presets_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"presets": {}}

    if "presets" not in data or not isinstance(data["presets"], dict):
        data["presets"] = {}

    data["presets"][preset_name] = preset_data

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# ---------------------------------------------------------------------------
# Tkinter UI
# ---------------------------------------------------------------------------

class AgentSetupWindow:
    """Setup window for selecting AI agents and configuring turn order."""

    def __init__(self, root, prompt_mode_override=None, preset_name=None,
                 seed=None):
        self.root = root
        self.root.title("Coup \u2014 AI Agent Setup")
        self.root.minsize(520, 500)
        self.preset_name = preset_name
        self._cli_seed = seed  # seed from CLI argument (None = auto-generate)

        # Load config
        try:
            self.config = load_config()
        except FileNotFoundError as e:
            messagebox.showerror("Config Error", str(e))
            self.root.destroy()
            return

        # Resolve prompt mode: CLI override > config file
        if prompt_mode_override is not None:
            self.prompt_mode = prompt_mode_override
        else:
            self.prompt_mode = get_prompt_mode(self.config)

        self.available = get_available_agents(self.config)
        if len(self.available) < 2:
            messagebox.showerror(
                "Config Error",
                "Need at least 2 agents configured in ai_config.json.\n"
                "Add agent entries under the \"agents\" key."
            )
            self.root.destroy()
            return

        # Track how many of each agent type have been added (for numbering)
        self._agent_counts = {name: 0 for name in self.available}

        # Per-player custom condition widgets (rebuilt on agent list change)
        self._player_rows = []  # list of dicts with widget references
        self._custom_expanded = False

        self._build_layout()

    def _build_layout(self):
        # Use a canvas with scrollbar for the entire window content
        self._main_frame = tk.Frame(self.root)
        self._main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title = tk.Label(
            self._main_frame, text="Select AI Agents for Coup",
            font=("Helvetica", 16, "bold"))
        title.pack(pady=(15, 5))

        subtitle = tk.Label(
            self._main_frame,
            text="Add 2-6 agents, arrange turn order, then start.",
            font=("Helvetica", 10))
        subtitle.pack(pady=(0, 10))

        # Add-agent buttons
        add_frame = tk.LabelFrame(
            self._main_frame, text="Add Agent", padx=10, pady=5)
        add_frame.pack(fill=tk.X, padx=15, pady=5)

        for name in self.available:
            btn = tk.Button(
                add_frame, text=f"+ {name}",
                font=("Helvetica", 11), padx=8, pady=3,
                command=lambda n=name: self._add_agent(n))
            btn.pack(side=tk.LEFT, padx=4, pady=3)

        # Turn order list
        list_frame = tk.LabelFrame(
            self._main_frame, text="Turn Order", padx=10, pady=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        self.listbox = tk.Listbox(
            list_frame, font=("Helvetica", 12), height=6)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btn_side = tk.Frame(list_frame)
        btn_side.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))

        tk.Button(btn_side, text="Move Up", width=10,
                  command=self._move_up).pack(pady=2)
        tk.Button(btn_side, text="Move Down", width=10,
                  command=self._move_down).pack(pady=2)
        tk.Button(btn_side, text="Remove", width=10,
                  command=self._remove).pack(pady=2)

        # ---- Game count selector ----
        game_count_frame = tk.Frame(self._main_frame)
        game_count_frame.pack(fill=tk.X, padx=15, pady=(10, 5))

        tk.Label(game_count_frame, text="Number of games:",
                 font=("Helvetica", 11)).pack(side=tk.LEFT)

        self._game_count_var = tk.StringVar(value="1")
        self._game_count_spin = tk.Spinbox(
            game_count_frame, from_=1, to=999, width=5,
            textvariable=self._game_count_var,
            font=("Helvetica", 11))
        self._game_count_spin.pack(side=tk.LEFT, padx=(8, 0))

        # ---- Seed entry ----
        seed_frame = tk.Frame(self._main_frame)
        seed_frame.pack(fill=tk.X, padx=15, pady=(5, 5))

        tk.Label(seed_frame, text="Seed (optional):",
                 font=("Helvetica", 11)).pack(side=tk.LEFT)

        self._seed_var = tk.StringVar(
            value=str(self._cli_seed) if self._cli_seed is not None else "")
        self._seed_entry = tk.Entry(
            seed_frame, textvariable=self._seed_var,
            font=("Helvetica", 11), width=15)
        self._seed_entry.pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(seed_frame, text="(empty = random)",
                 font=("Helvetica", 9)).pack(side=tk.LEFT, padx=(5, 0))

        # ---- Shuffle checkbox ----
        shuffle_frame = tk.Frame(self._main_frame)
        shuffle_frame.pack(fill=tk.X, padx=15, pady=(5, 5))

        self._shuffle_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            shuffle_frame, text="Randomize turn order each game",
            variable=self._shuffle_var, font=("Helvetica", 11),
        ).pack(side=tk.LEFT)

        # ---- Collapsible custom start conditions ----
        self._custom_toggle_btn = tk.Button(
            self._main_frame,
            text="\u25b6 Custom Start Conditions (click to expand)",
            font=("Helvetica", 10), relief=tk.FLAT, cursor="hand2",
            command=self._toggle_custom_section)
        self._custom_toggle_btn.pack(fill=tk.X, padx=15, pady=(5, 0))

        # The collapsible frame (hidden by default)
        self._custom_frame = tk.LabelFrame(
            self._main_frame, text="Custom Start Conditions",
            padx=10, pady=5)
        # Will be packed/unpacked by _toggle_custom_section

        # Inside custom frame: player rows container
        self._players_container = tk.Frame(self._custom_frame)
        self._players_container.pack(fill=tk.X)

        # Deck indicator
        self._deck_indicator_var = tk.StringVar(value="")
        self._deck_indicator_label = tk.Label(
            self._custom_frame, textvariable=self._deck_indicator_var,
            font=("Helvetica", 10))
        self._deck_indicator_label.pack(fill=tk.X, pady=(5, 0))

        # ---- Preset save/load ----
        preset_frame = tk.Frame(self._custom_frame)
        preset_frame.pack(fill=tk.X, pady=(8, 0))

        tk.Label(preset_frame, text="Presets:",
                 font=("Helvetica", 10)).pack(side=tk.LEFT)

        self._preset_var = tk.StringVar(value="")
        self._preset_dropdown = tk.OptionMenu(
            preset_frame, self._preset_var, "")
        self._preset_dropdown.config(width=18)
        self._preset_dropdown.pack(side=tk.LEFT, padx=(5, 5))

        tk.Button(preset_frame, text="Load", width=6,
                  command=self._load_preset).pack(side=tk.LEFT, padx=2)
        tk.Button(preset_frame, text="Save", width=6,
                  command=self._save_preset).pack(side=tk.LEFT, padx=2)
        tk.Button(preset_frame, text="Refresh", width=7,
                  command=self._refresh_preset_list).pack(side=tk.LEFT, padx=2)

        self._refresh_preset_list()

        # ---- Start button ----
        self.start_btn = tk.Button(
            self._main_frame, text="Start Game",
            font=("Helvetica", 13, "bold"), padx=20, pady=8,
            state=tk.DISABLED, command=self._start_game)
        self.start_btn.pack(pady=15)

    # ----- Agent list management -----

    def _add_agent(self, provider_name):
        count = self.listbox.size()
        if count >= 6:
            messagebox.showwarning("Limit", "Maximum 6 agents.")
            return

        self._agent_counts[provider_name] += 1
        n = self._agent_counts[provider_name]
        if n > 1:
            display_name = f"{provider_name} {n}"
        else:
            display_name = provider_name

        self.listbox.insert(tk.END, display_name)
        self._update_start_btn()
        self._rebuild_custom_rows()

    def _remove(self):
        sel = self.listbox.curselection()
        if sel:
            self.listbox.delete(sel[0])
            self._update_start_btn()
            self._rebuild_custom_rows()

    def _move_up(self):
        sel = self.listbox.curselection()
        if sel and sel[0] > 0:
            idx = sel[0]
            text = self.listbox.get(idx)
            self.listbox.delete(idx)
            self.listbox.insert(idx - 1, text)
            self.listbox.selection_set(idx - 1)
            self._rebuild_custom_rows()

    def _move_down(self):
        sel = self.listbox.curselection()
        if sel and sel[0] < self.listbox.size() - 1:
            idx = sel[0]
            text = self.listbox.get(idx)
            self.listbox.delete(idx)
            self.listbox.insert(idx + 1, text)
            self.listbox.selection_set(idx + 1)
            self._rebuild_custom_rows()

    def _update_start_btn(self):
        count = self.listbox.size()
        if 2 <= count <= 6:
            self.start_btn.config(state=tk.NORMAL)
        else:
            self.start_btn.config(state=tk.DISABLED)

    # ----- Collapsible custom section -----

    def _toggle_custom_section(self):
        if self._custom_expanded:
            self._custom_frame.pack_forget()
            self._custom_toggle_btn.config(
                text="\u25b6 Custom Start Conditions (click to expand)")
            # Re-pack start button after the toggle button
            self.start_btn.pack_forget()
            self.start_btn.pack(pady=15)
            self._custom_expanded = False
        else:
            self._custom_frame.pack(fill=tk.X, padx=15, pady=(0, 5),
                                    after=self._custom_toggle_btn)
            self._custom_toggle_btn.config(
                text="\u25bc Custom Start Conditions (click to collapse)")
            # Re-pack start button at the bottom
            self.start_btn.pack_forget()
            self.start_btn.pack(pady=15)
            self._custom_expanded = True
            self._rebuild_custom_rows()

    # ----- Per-player custom rows -----

    def _rebuild_custom_rows(self):
        """Destroy and recreate per-player card/coin/history-depth rows."""
        # Save current values before destroying
        old_values = {}
        for row in self._player_rows:
            name = row["name"]
            old_values[name] = {
                "card1": row["card1_var"].get(),
                "card2": row["card2_var"].get(),
                "coins": row["coins_var"].get(),
                "history_depth": row["history_depth_var"].get(),
            }

        # Destroy old widgets
        for row in self._player_rows:
            row["frame"].destroy()
        self._player_rows = []

        # Build new rows for current agent list
        agent_names = self._get_agent_names()
        for name in agent_names:
            row_frame = tk.Frame(self._players_container)
            row_frame.pack(fill=tk.X, pady=1)

            tk.Label(row_frame, text=f"{name}:",
                     font=("Helvetica", 10), width=14,
                     anchor=tk.W).pack(side=tk.LEFT)

            card1_var = tk.StringVar(value="Random")
            card2_var = tk.StringVar(value="Random")
            coins_var = tk.StringVar(value="2")
            history_depth_var = tk.StringVar(value="2")

            # Restore previous values if this player existed before
            if name in old_values:
                prev = old_values[name]
                if prev["card1"] in CARD_OPTIONS:
                    card1_var.set(prev["card1"])
                if prev["card2"] in CARD_OPTIONS:
                    card2_var.set(prev["card2"])
                try:
                    c = int(prev["coins"])
                    if 0 <= c <= 12:
                        coins_var.set(str(c))
                except (ValueError, TypeError):
                    pass
                try:
                    hd = int(prev["history_depth"])
                    if hd >= 0:
                        history_depth_var.set(str(hd))
                except (ValueError, TypeError):
                    pass

            card1_menu = tk.OptionMenu(row_frame, card1_var, *CARD_OPTIONS,
                                       command=lambda *a: self._update_deck_indicator())
            card1_menu.config(width=10)
            card1_menu.pack(side=tk.LEFT, padx=2)

            card2_menu = tk.OptionMenu(row_frame, card2_var, *CARD_OPTIONS,
                                       command=lambda *a: self._update_deck_indicator())
            card2_menu.config(width=10)
            card2_menu.pack(side=tk.LEFT, padx=2)

            coins_spin = tk.Spinbox(
                row_frame, from_=0, to=12, width=3,
                textvariable=coins_var, font=("Helvetica", 10))
            coins_spin.pack(side=tk.LEFT, padx=(5, 0))

            tk.Label(row_frame, text="coins",
                     font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(2, 0))

            history_depth_spin = tk.Spinbox(
                row_frame, from_=0, to=99, width=3,
                textvariable=history_depth_var, font=("Helvetica", 10))
            history_depth_spin.pack(side=tk.LEFT, padx=(8, 0))

            tk.Label(row_frame, text="history",
                     font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(2, 0))

            self._player_rows.append({
                "name": name,
                "frame": row_frame,
                "card1_var": card1_var,
                "card2_var": card2_var,
                "coins_var": coins_var,
                "history_depth_var": history_depth_var,
            })

        self._update_deck_indicator()

    def _update_deck_indicator(self):
        """Recalculate and display the remaining deck composition."""
        if not self._player_rows:
            self._deck_indicator_var.set("")
            return

        card_selections = self._get_card_selections()
        remaining = compute_remaining_deck(card_selections)
        errors = validate_deck_config(remaining)

        num_random = count_random_cards(card_selections)
        errors.extend(validate_enough_cards_for_random(remaining, num_random))

        indicator = f"Remaining deck: {format_deck_indicator(remaining)}"
        if errors:
            indicator += f"  \u26a0 {'; '.join(errors)}"
            self._deck_indicator_label.config(fg="red")
        else:
            self._deck_indicator_label.config(fg="black")

        self._deck_indicator_var.set(indicator)

    # ----- Preset save/load -----

    def _refresh_preset_list(self):
        """Reload preset names into the dropdown."""
        menu = self._preset_dropdown["menu"]
        menu.delete(0, tk.END)
        names = load_preset_names()
        if not names:
            menu.add_command(label="(no presets)",
                             command=lambda: self._preset_var.set(""))
        else:
            for name in names:
                menu.add_command(
                    label=name,
                    command=lambda n=name: self._preset_var.set(n))
            if not self._preset_var.get() or self._preset_var.get() not in names:
                self._preset_var.set(names[0])

    def _load_preset(self):
        """Load selected preset into the custom conditions UI."""
        preset_name = self._preset_var.get()
        if not preset_name:
            messagebox.showinfo("Load Preset", "No preset selected.")
            return

        data = load_preset_data(preset_name)
        if data is None:
            messagebox.showerror("Load Preset",
                                 f"Preset '{preset_name}' not found.")
            return

        players_cfg = data.get("players", {})

        # Apply to current player rows
        for row in self._player_rows:
            name = row["name"]
            if name in players_cfg:
                pcfg = players_cfg[name]
                hand = pcfg.get("hand", [])
                coins = pcfg.get("coins", 2)

                # Set card dropdowns
                if len(hand) >= 1 and hand[0] in VALID_CARDS:
                    row["card1_var"].set(hand[0])
                else:
                    row["card1_var"].set("Random")

                if len(hand) >= 2 and hand[1] in VALID_CARDS:
                    row["card2_var"].set(hand[1])
                else:
                    row["card2_var"].set("Random")

                row["coins_var"].set(str(coins))
            else:
                # Reset to defaults for players not in preset
                row["card1_var"].set("Random")
                row["card2_var"].set("Random")
                row["coins_var"].set("2")

        self._update_deck_indicator()

    def _save_preset(self):
        """Save current custom conditions as a preset."""
        agent_names = self._get_agent_names()
        if not agent_names:
            messagebox.showwarning("Save Preset",
                                   "Add agents before saving a preset.")
            return

        card_selections = self._get_card_selections()
        coin_values = self._get_coin_values()
        preset = build_preset_from_selections(
            agent_names, card_selections, coin_values)

        if preset is None:
            messagebox.showinfo(
                "Save Preset",
                "All settings are at defaults. Nothing custom to save.")
            return

        # Ask for preset name
        name_dialog = tk.Toplevel(self.root)
        name_dialog.title("Save Preset")
        name_dialog.geometry("300x120")
        name_dialog.transient(self.root)
        name_dialog.grab_set()

        tk.Label(name_dialog, text="Preset name:",
                 font=("Helvetica", 11)).pack(pady=(15, 5))

        name_entry = tk.Entry(name_dialog, font=("Helvetica", 11), width=25)
        name_entry.pack(pady=5)
        name_entry.focus_set()

        def do_save():
            pname = name_entry.get().strip()
            if not pname:
                messagebox.showwarning("Save Preset", "Name cannot be empty.",
                                       parent=name_dialog)
                return
            # Add description
            desc = f"Custom setup: {', '.join(agent_names)}"
            preset["description"] = desc
            save_preset_to_file(pname, preset)
            self._refresh_preset_list()
            self._preset_var.set(pname)
            name_dialog.destroy()
            messagebox.showinfo("Save Preset",
                                f"Preset '{pname}' saved successfully.")

        tk.Button(name_dialog, text="Save", command=do_save,
                  font=("Helvetica", 11)).pack(pady=5)

    # ----- Data extraction helpers -----

    def _get_agent_names(self):
        """Return list of agent names from the listbox."""
        return [self.listbox.get(i) for i in range(self.listbox.size())]

    def _get_card_selections(self):
        """Return list of (card1, card2) tuples from custom rows."""
        selections = []
        for row in self._player_rows:
            c1 = row["card1_var"].get()
            c2 = row["card2_var"].get()
            selections.append((c1, c2))
        return selections

    def _get_coin_values(self):
        """Return list of int coin values from custom rows."""
        values = []
        for row in self._player_rows:
            try:
                v = int(row["coins_var"].get())
                values.append(max(0, min(12, v)))
            except (ValueError, TypeError):
                values.append(2)
        return values

    def _get_history_depths(self):
        """Return list of int history_depth values from custom rows."""
        values = []
        for row in self._player_rows:
            try:
                v = int(row["history_depth_var"].get())
                values.append(max(0, v))
            except (ValueError, TypeError):
                values.append(2)
        return values

    def _get_game_count(self):
        """Return the game count from the spinbox (clamped to 1-999)."""
        try:
            n = int(self._game_count_var.get())
            return max(1, min(999, n))
        except (ValueError, TypeError):
            return 1

    def _get_seed(self):
        """Return the seed as an integer, or None if empty/invalid."""
        raw = self._seed_var.get().strip()
        if not raw:
            return None
        try:
            return int(raw)
        except (ValueError, TypeError):
            return None

    # ----- Start game -----

    def _start_game(self):
        """Create Agent instances and launch the game runner."""
        agent_names = self._get_agent_names()
        game_count = self._get_game_count()
        seed = self._get_seed()

        # Collect history depths (uses custom section values or defaults)
        if self._custom_expanded and self._player_rows:
            history_depths = self._get_history_depths()
        else:
            history_depths = None  # use default (2) for all agents

        # Build preset from custom conditions (if any are non-default)
        preset_name = None
        inline_preset = None

        if self._custom_expanded and self._player_rows:
            card_selections = self._get_card_selections()
            coin_values = self._get_coin_values()
            inline_preset = build_preset_from_selections(
                agent_names, card_selections, coin_values)

            # Validate if custom conditions are set
            if inline_preset is not None:
                remaining = compute_remaining_deck(card_selections)
                errors = validate_deck_config(remaining)
                num_random = count_random_cards(card_selections)
                errors.extend(
                    validate_enough_cards_for_random(remaining, num_random))
                if errors:
                    messagebox.showerror(
                        "Invalid Configuration",
                        "Cannot start with invalid card configuration:\n\n"
                        + "\n".join(f"  - {e}" for e in errors))
                    return

        # Fall back to CLI preset if no inline custom conditions
        if inline_preset is None:
            preset_name = self.preset_name

        self.root.destroy()

        shuffle = self._shuffle_var.get()

        if game_count == 1:
            # Single game
            agents = create_agents_from_names(
                agent_names, self.config, history_depths=history_depths)
            if shuffle:
                random.shuffle(agents)
            runner = GameRunner(agents, prompt_mode=self.prompt_mode,
                                preset_name=preset_name, seed=seed)
            if inline_preset is not None:
                self._apply_inline_preset(runner, inline_preset)
            runner.run()
        else:
            # Multi-game run
            self._run_multi_game(
                agent_names, game_count, preset_name, inline_preset,
                seed=seed, history_depths=history_depths,
                shuffle=shuffle)

    def _apply_inline_preset(self, runner, inline_preset):
        """Monkey-patch a GameRunner so it applies an inline preset dict
        instead of looking up a named preset from presets.json.

        This works by replacing the runner's _apply_preset method with one
        that uses the inline dict directly.
        """
        from AI_game.presets import apply_preset

        def patched_apply():
            game = runner.controller.game
            player_names = [p.name for p in game.players]
            all_dealt_cards = []
            for player in game.players:
                all_dealt_cards.extend(player.influence)
                player.influence = []
                player.coins = 2
            for card in all_dealt_cards:
                game.deck.return_card(card)
            apply_preset(inline_preset, game, player_names)
            runner.controller._log("Custom start conditions applied.")

        # Store the original preset_name and patch
        runner.preset_name = "__inline__"
        runner._apply_preset = patched_apply

    def _run_multi_game(self, agent_names, game_count, preset_name,
                        inline_preset, seed=None, history_depths=None,
                        shuffle=False):
        """Execute multiple games and print progress and summary."""
        results = []
        errors = []

        print(f"\n{BOLD}{'=' * 60}")
        print("          COUP \u2014 MULTI-GAME RUN (UI)")
        print(f"{'=' * 60}{RESET}")
        print(f"  Games to run:  {game_count}")
        print(f"  Agents:        {', '.join(agent_names)}")
        print(f"  Prompt mode:   {self.prompt_mode}")
        if inline_preset:
            print(f"  Custom setup:  yes")
        elif preset_name:
            print(f"  Preset:        {preset_name}")
        if seed is not None:
            print(f"  Starting seed: {seed}")
        print(f"  Shuffle order: {'on' if shuffle else 'off'}")
        print()

        start_time = time.time()

        for game_num in range(1, game_count + 1):
            try:
                agents = create_agents_from_names(
                    agent_names, self.config, history_depths=history_depths)

                if shuffle:
                    random.shuffle(agents)

                # Compute per-game seed: if a base seed was given, increment it
                game_seed = (seed + game_num - 1) if seed is not None else None

                runner = GameRunner(
                    agents, prompt_mode=self.prompt_mode,
                    quiet=(game_count > 5),
                    preset_name=preset_name, seed=game_seed)

                if inline_preset is not None:
                    self._apply_inline_preset(runner, inline_preset)

                result = runner.run()

                if result is not None:
                    results.append(result)
                    winner = result["winner_name"]
                    game_seed_display = result.get("seed", "?")
                    print(
                        f"  Game {game_num}/{game_count} complete "
                        f"\u2014 winner: {BOLD}{winner}{RESET} "
                        f"(seed: {game_seed_display})"
                    )
                else:
                    errors.append(
                        (game_num, "Game ended abnormally (no winner)"))
                    print(
                        f"  Game {game_num}/{game_count} "
                        f"{DIM}ABORTED (no winner){RESET}"
                    )

            except KeyboardInterrupt:
                print(f"\n\n  Interrupted after {game_num - 1} games.")
                break

            except Exception as e:
                errors.append((game_num, str(e)))
                print(
                    f"  Game {game_num}/{game_count} "
                    f"{DIM}ERROR: {e}{RESET}"
                )

        elapsed = time.time() - start_time
        self._print_summary(results, errors, elapsed)

    def _print_summary(self, results, errors, elapsed):
        """Print end-of-run summary report."""
        total_games = len(results) + len(errors)
        successful = len(results)
        failed = len(errors)

        print(f"\n{BOLD}{'=' * 60}")
        print("                  MULTI-GAME SUMMARY")
        print(f"{'=' * 60}{RESET}")

        print(f"  Total games:     {total_games}")
        print(f"  Successful:      {successful}")
        if failed > 0:
            print(f"  Failed/aborted:  {failed}")
        print(f"  Elapsed time:    {elapsed:.1f}s", end="")
        if successful > 0:
            print(f" ({elapsed / successful:.1f}s avg per game)")
        else:
            print()
        print(f"  Prompt mode:     {self.prompt_mode}")

        if not results:
            print(f"\n  No successful games to summarize.\n")
            return

        # Win rates by model
        model_stats = {}
        for result in results:
            for agent in result["agents"]:
                model = agent.model
                if model not in model_stats:
                    model_stats[model] = {
                        "games": 0, "wins": 0,
                        "total_tokens": 0, "cached_tokens": 0, "queries": 0,
                    }
                model_stats[model]["games"] += 1
                model_stats[model]["total_tokens"] += (
                    agent.prompt_tokens + agent.completion_tokens
                )
                model_stats[model]["cached_tokens"] += agent.cached_tokens
                model_stats[model]["queries"] += agent.query_count

            winner_model = result["winner_model"]
            if winner_model in model_stats:
                model_stats[winner_model]["wins"] += 1

        print(f"\n  {BOLD}Win Rates:{RESET}")
        for model in sorted(model_stats.keys()):
            s = model_stats[model]
            rate = s["wins"] / s["games"] * 100 if s["games"] > 0 else 0
            print(f"    {model}: {s['wins']}/{s['games']} wins ({rate:.1f}%)")

        # Token usage
        total_tokens = sum(s["total_tokens"] for s in model_stats.values())
        total_cached = sum(s["cached_tokens"] for s in model_stats.values())
        total_queries = sum(s["queries"] for s in model_stats.values())
        avg_tokens = total_tokens / successful if successful > 0 else 0

        print(f"\n  {BOLD}Token Usage:{RESET}")
        print(f"    Total tokens:       {total_tokens:,}")
        print(f"    Cached tokens:      {total_cached:,}", end="")
        if total_tokens > 0:
            print(f" ({total_cached / total_tokens * 100:.1f}% of total)")
        else:
            print()
        print(f"    Total queries:      {total_queries:,}")
        print(f"    Avg tokens/game:    {avg_tokens:,.0f}")

        # Per-model breakdown
        print(f"\n  {BOLD}Per-Model Token Breakdown:{RESET}")
        for model in sorted(model_stats.keys()):
            s = model_stats[model]
            avg_per_q = (
                s["total_tokens"] / s["queries"] if s["queries"] > 0 else 0
            )
            cache_pct = (
                f"{s['cached_tokens'] / s['total_tokens'] * 100:.1f}%"
                if s["total_tokens"] > 0 else "0%"
            )
            print(
                f"    {model}: {s['total_tokens']:,} tokens "
                f"(cached: {s['cached_tokens']:,}, {cache_pct}) "
                f"| {avg_per_q:,.0f} tokens/query over {s['queries']} queries"
            )

        # Errors
        if errors:
            print(f"\n  {BOLD}Errors:{RESET}")
            for game_num, error_msg in errors:
                print(f"    Game {game_num}: {error_msg}")

        print()


def main(prompt_mode_override=None, preset_name=None, seed=None):
    root = tk.Tk()
    AgentSetupWindow(root, prompt_mode_override=prompt_mode_override,
                     preset_name=preset_name, seed=seed)
    root.mainloop()


if __name__ == "__main__":
    main()
