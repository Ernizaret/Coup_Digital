"""Multi-window Tkinter UI for Coup, driven by GameController.

Each human player gets their own window showing only their private information.
AI players respond automatically via the API using the same agent infrastructure
as AI_game.
"""

import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

from src.controller import GameController, State


# Card dropdown options for custom start conditions (lazy-imported from presets)
_CARD_OPTIONS = None
_VALID_CARDS = None


def _get_card_options():
    """Lazy-load card options to avoid requiring AI_game at import time."""
    global _CARD_OPTIONS, _VALID_CARDS
    if _CARD_OPTIONS is None:
        try:
            from AI_game.presets import VALID_CARDS
            _VALID_CARDS = VALID_CARDS
            _CARD_OPTIONS = ["Random"] + VALID_CARDS
        except ImportError:
            _VALID_CARDS = ["Duke", "Assassin", "Captain", "Contessa",
                            "Ambassador"]
            _CARD_OPTIONS = ["Random"] + _VALID_CARDS
    return _CARD_OPTIONS


class SetupWindow:
    """Manages the root tk.Tk() window for pre-game setup.

    Supports two phases:
      Phase 1: Player count selection (buttons 2-6), same as the original.
      Phase 2: Rich player configuration panel where each slot can be
               designated Human or AI, with advanced settings for AI games.
    """

    def __init__(self, root, controller):
        self.root = root
        self.root.title("Coup - Setup")
        self.root.minsize(500, 400)
        self.controller = controller
        self.player_windows = []

        # AI-related state (initialized lazily when AI players are configured)
        self.ai_agents = {}       # Player -> Agent mapping
        self.event_log = []       # list of {"type": "event"/"speech", ...}
        self._log_cursor = 0
        self._turn_number = 0
        self._last_turn_player = None

        # Phase 2 state
        self.num_players = 0
        self.player_rows = []
        self.config = None            # ai_config.json parsed dict
        self.available_agents = []    # list of provider names from config
        self._ai_config_loaded = False
        self._custom_expanded = False
        self._advanced_rows = []      # per-AI-player advanced setting rows
        self._ai_processing = False   # guard against re-entrant AI processing

        self._build_layout()
        self.refresh()

    # ------------------------------------------------------------------
    # Layout: Phase 1 (reused for count selection)
    # ------------------------------------------------------------------

    def _build_layout(self):
        self.prompt_label = tk.Label(
            self.root, text="", font=("Helvetica", 14),
            wraplength=450, justify=tk.LEFT)
        self.prompt_label.pack(padx=10, pady=(20, 10), anchor=tk.W)

        self.button_frame = tk.Frame(self.root)
        self.button_frame.pack(fill=tk.X, padx=10)

        # Entry frame (used during original SETUP_PLAYER_NAME state,
        # kept for backward compat but Phase 2 bypasses it)
        self.entry_frame = tk.Frame(self.root)
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(self.entry_frame, textvariable=self.entry_var,
                              font=("Helvetica", 12), width=30)
        self.entry.pack(side=tk.LEFT, padx=(0, 5))
        self.entry_btn = tk.Button(self.entry_frame, text="Submit",
                                   command=self._on_entry_submit)
        self.entry_btn.pack(side=tk.LEFT)
        self.entry.bind("<Return>", lambda e: self._on_entry_submit())

        self.log_text = scrolledtext.ScrolledText(
            self.root, height=6, state=tk.DISABLED,
            font=("Courier", 10), wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 10))

    def refresh(self):
        # If the game has started (through the original flow, not Phase 2),
        # transition to player windows.
        if (self.controller.state not in (State.SETUP_PLAYER_COUNT,
                                          State.SETUP_PLAYER_NAME)
                and self.controller.game is not None
                and not self.player_windows):
            self._open_player_windows()
            return

        self._refresh_prompt()
        self._refresh_log()

    def _refresh_prompt(self):
        for widget in self.button_frame.winfo_children():
            widget.destroy()
        self.entry_frame.pack_forget()

        message, options = self.controller.get_prompt()
        self.prompt_label.config(text=message)

        if self.controller.state == State.SETUP_PLAYER_NAME:
            self.entry_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
            self.entry_var.set("")
            self.entry.focus_set()
        elif options:
            for opt in options:
                btn = tk.Button(
                    self.button_frame, text=opt,
                    font=("Helvetica", 11), padx=10, pady=4,
                    command=lambda v=opt: self._on_count_selected(v))
                btn.pack(side=tk.LEFT, padx=3, pady=2)

    def _refresh_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        for line in self.controller.log:
            self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _on_count_selected(self, value):
        """Handle player count button click -- transition to Phase 2."""
        try:
            n = int(value)
            if 2 <= n <= 6:
                self.num_players = n
                self._show_player_config()
                return
        except ValueError:
            pass

    def _on_entry_submit(self):
        """Handle text entry submit (legacy, for original SETUP_PLAYER_NAME)."""
        value = self.entry_var.get().strip()
        if value:
            self.controller.handle_input(value)
            self.entry_var.set("")
            self.refresh()

    # ------------------------------------------------------------------
    # Phase 2: Player Configuration Panel
    # ------------------------------------------------------------------

    def _load_ai_config(self):
        """Try to load ai_config.json. Non-fatal if missing."""
        if self._ai_config_loaded:
            return
        self._ai_config_loaded = True
        try:
            from AI_game.config import load_config, get_available_agents
            self.config = load_config()
            self.available_agents = get_available_agents(self.config)
        except Exception:
            self.config = None
            self.available_agents = []

    def _show_player_config(self):
        """Show the player configuration panel after count selection."""
        # Hide Phase 1 widgets
        for widget in self.button_frame.winfo_children():
            widget.destroy()
        self.entry_frame.pack_forget()
        self.log_text.pack_forget()
        self.prompt_label.config(text="Configure Players:")

        # Try loading AI config
        self._load_ai_config()

        # Scrollable content frame
        self._config_canvas = tk.Canvas(self.root)
        self._config_scrollbar = tk.Scrollbar(
            self.root, orient=tk.VERTICAL, command=self._config_canvas.yview)
        self._config_canvas.configure(yscrollcommand=self._config_scrollbar.set)

        self._config_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._config_canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self._config_inner = tk.Frame(self._config_canvas)
        self._config_canvas.create_window(
            (0, 0), window=self._config_inner, anchor=tk.NW)
        self._config_inner.bind(
            "<Configure>",
            lambda e: self._config_canvas.configure(
                scrollregion=self._config_canvas.bbox("all")))

        # Build player configuration rows
        self.player_rows = []
        players_frame = tk.LabelFrame(
            self._config_inner, text="Players", padx=10, pady=5)
        players_frame.pack(fill=tk.X, padx=5, pady=5)

        for i in range(self.num_players):
            row = self._build_player_row(players_frame, i)
            self.player_rows.append(row)

        # Advanced settings (collapsible)
        self._advanced_toggle_btn = tk.Button(
            self._config_inner,
            text="\u25b6 Advanced Settings (click to expand)",
            font=("Helvetica", 10), relief=tk.FLAT, cursor="hand2",
            command=self._toggle_advanced_section)
        self._advanced_toggle_btn.pack(fill=tk.X, padx=5, pady=(10, 0))

        self._advanced_frame = tk.LabelFrame(
            self._config_inner, text="Advanced Settings", padx=10, pady=5)
        # Not packed yet -- toggled by button

        self._build_advanced_settings()

        # Start button
        self.start_btn = tk.Button(
            self._config_inner, text="Start Game",
            font=("Helvetica", 13, "bold"), padx=20, pady=8,
            command=self._start_game)
        self.start_btn.pack(pady=15)

    def _build_player_row(self, parent, index):
        """Build a single player configuration row."""
        row_frame = tk.Frame(parent)
        row_frame.pack(fill=tk.X, pady=3)

        tk.Label(row_frame, text=f"Player {index + 1}:",
                 font=("Helvetica", 11), width=10, anchor=tk.W).pack(
                     side=tk.LEFT)

        # Type variable (Human/AI)
        type_var = tk.StringVar(value="Human")

        # Radio buttons
        tk.Radiobutton(row_frame, text="Human", variable=type_var,
                       value="Human",
                       command=lambda: self._on_type_change(index)).pack(
                           side=tk.LEFT)

        ai_radio = None
        if self.available_agents:
            ai_radio = tk.Radiobutton(
                row_frame, text="AI", variable=type_var, value="AI",
                command=lambda: self._on_type_change(index))
            ai_radio.pack(side=tk.LEFT)

        # Name entry (for Human)
        name_var = tk.StringVar(value=f"Player {index + 1}")
        name_entry = tk.Entry(row_frame, textvariable=name_var,
                              font=("Helvetica", 11), width=15)
        name_entry.pack(side=tk.LEFT, padx=5)

        # Model dropdown (for AI, hidden initially)
        model_var = tk.StringVar(
            value=self.available_agents[0] if self.available_agents else "")

        # Create the model dropdown in a sub-frame for easy show/hide
        model_frame = tk.Frame(row_frame)
        if self.available_agents:
            model_menu = tk.OptionMenu(
                model_frame, model_var, *self.available_agents)
            model_menu.config(width=15)
            model_menu.pack(side=tk.LEFT)
        else:
            model_menu = None
        # model_frame is NOT packed initially (hidden)

        return {
            "frame": row_frame,
            "type_var": type_var,
            "name_var": name_var,
            "name_entry": name_entry,
            "model_var": model_var,
            "model_frame": model_frame,
            "model_menu": model_menu,
            "ai_radio": ai_radio,
        }

    def _on_type_change(self, index):
        """Handle switching between Human and AI for a player slot."""
        row = self.player_rows[index]
        if row["type_var"].get() == "AI":
            row["name_entry"].pack_forget()
            row["model_frame"].pack(side=tk.LEFT, padx=5)
        else:
            row["model_frame"].pack_forget()
            row["name_entry"].pack(side=tk.LEFT, padx=5)

        # Rebuild advanced AI rows when player types change
        if self._custom_expanded:
            self._rebuild_advanced_ai_rows()

    # ------------------------------------------------------------------
    # Advanced Settings Section
    # ------------------------------------------------------------------

    def _build_advanced_settings(self):
        """Build the advanced settings section (seed, prompt mode,
        per-player AI settings, presets)."""
        # Seed
        seed_frame = tk.Frame(self._advanced_frame)
        seed_frame.pack(fill=tk.X, pady=3)

        tk.Label(seed_frame, text="Seed:",
                 font=("Helvetica", 11)).pack(side=tk.LEFT)
        self._seed_var = tk.StringVar(value="")
        self._seed_entry = tk.Entry(
            seed_frame, textvariable=self._seed_var,
            font=("Helvetica", 11), width=15)
        self._seed_entry.pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(seed_frame, text="(empty = random)",
                 font=("Helvetica", 9)).pack(side=tk.LEFT, padx=(5, 0))

        # Prompt mode
        prompt_frame = tk.Frame(self._advanced_frame)
        prompt_frame.pack(fill=tk.X, pady=3)

        tk.Label(prompt_frame, text="Prompt Mode:",
                 font=("Helvetica", 11)).pack(side=tk.LEFT)
        self._prompt_mode_var = tk.StringVar(value="heavy")
        tk.Radiobutton(prompt_frame, text="Heavy",
                       variable=self._prompt_mode_var,
                       value="heavy").pack(side=tk.LEFT, padx=(8, 0))
        tk.Radiobutton(prompt_frame, text="Light",
                       variable=self._prompt_mode_var,
                       value="light").pack(side=tk.LEFT)

        # Per-AI-player settings container
        self._ai_settings_label = tk.Label(
            self._advanced_frame,
            text="Per-AI-Player Settings:",
            font=("Helvetica", 11, "bold"))
        self._ai_settings_label.pack(fill=tk.X, pady=(8, 2), anchor=tk.W)

        self._ai_settings_container = tk.Frame(self._advanced_frame)
        self._ai_settings_container.pack(fill=tk.X)

        # Custom start conditions section
        self._custom_start_label = tk.Label(
            self._advanced_frame,
            text="Custom Start Conditions:",
            font=("Helvetica", 11, "bold"))
        self._custom_start_label.pack(fill=tk.X, pady=(8, 2), anchor=tk.W)

        self._custom_rows_container = tk.Frame(self._advanced_frame)
        self._custom_rows_container.pack(fill=tk.X)
        self._custom_player_rows = []

        # Deck indicator
        self._deck_indicator_var = tk.StringVar(value="")
        self._deck_indicator_label = tk.Label(
            self._advanced_frame,
            textvariable=self._deck_indicator_var,
            font=("Helvetica", 10))
        self._deck_indicator_label.pack(fill=tk.X, pady=(5, 0))

        # Preset save/load
        preset_frame = tk.Frame(self._advanced_frame)
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

    def _toggle_advanced_section(self):
        """Toggle the advanced settings section visibility."""
        if self._custom_expanded:
            self._advanced_frame.pack_forget()
            self._advanced_toggle_btn.config(
                text="\u25b6 Advanced Settings (click to expand)")
            # Re-pack start button
            self.start_btn.pack_forget()
            self.start_btn.pack(pady=15)
            self._custom_expanded = False
        else:
            self._advanced_frame.pack(
                fill=tk.X, padx=5, pady=(0, 5),
                after=self._advanced_toggle_btn)
            self._advanced_toggle_btn.config(
                text="\u25bc Advanced Settings (click to collapse)")
            # Re-pack start button
            self.start_btn.pack_forget()
            self.start_btn.pack(pady=15)
            self._custom_expanded = True
            self._rebuild_advanced_ai_rows()
            self._rebuild_custom_start_rows()

    def _rebuild_advanced_ai_rows(self):
        """Rebuild per-AI-player settings rows (history depth, rules,
        strategy)."""
        # Destroy old rows
        for row in self._advanced_rows:
            row["frame"].destroy()
        self._advanced_rows = []

        # Build rows for AI players only
        for i, prow in enumerate(self.player_rows):
            if prow["type_var"].get() != "AI":
                continue

            model_name = prow["model_var"].get()
            display = model_name or f"AI Player {i + 1}"

            row_frame = tk.Frame(self._ai_settings_container)
            row_frame.pack(fill=tk.X, pady=1)

            tk.Label(row_frame, text=f"{display}:",
                     font=("Helvetica", 10), width=14,
                     anchor=tk.W).pack(side=tk.LEFT)

            history_depth_var = tk.StringVar(value="2")
            tk.Spinbox(
                row_frame, from_=0, to=99, width=3,
                textvariable=history_depth_var,
                font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(2, 0))
            tk.Label(row_frame, text="history",
                     font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(2, 0))

            rules_summary_var = tk.BooleanVar(value=False)
            tk.Checkbutton(
                row_frame, text="rules",
                variable=rules_summary_var,
                font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(8, 0))

            strategy_guide_var = tk.BooleanVar(value=False)
            tk.Checkbutton(
                row_frame, text="strategy",
                variable=strategy_guide_var,
                font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(8, 0))

            self._advanced_rows.append({
                "frame": row_frame,
                "player_index": i,
                "history_depth_var": history_depth_var,
                "rules_summary_var": rules_summary_var,
                "strategy_guide_var": strategy_guide_var,
            })

    def _rebuild_custom_start_rows(self):
        """Rebuild per-player custom start condition rows (card selections,
        coins)."""
        card_options = _get_card_options()

        # Save old values
        old_values = {}
        for row in self._custom_player_rows:
            old_values[row["index"]] = {
                "card1": row["card1_var"].get(),
                "card2": row["card2_var"].get(),
                "coins": row["coins_var"].get(),
            }

        # Destroy old
        for row in self._custom_player_rows:
            row["frame"].destroy()
        self._custom_player_rows = []

        # Build for all players
        for i, prow in enumerate(self.player_rows):
            is_ai = prow["type_var"].get() == "AI"
            if is_ai:
                name = prow["model_var"].get() or f"AI {i + 1}"
            else:
                name = prow["name_var"].get() or f"Player {i + 1}"

            row_frame = tk.Frame(self._custom_rows_container)
            row_frame.pack(fill=tk.X, pady=1)

            tk.Label(row_frame, text=f"{name}:",
                     font=("Helvetica", 10), width=14,
                     anchor=tk.W).pack(side=tk.LEFT)

            card1_var = tk.StringVar(value="Random")
            card2_var = tk.StringVar(value="Random")
            coins_var = tk.StringVar(value="2")

            # Restore previous values
            if i in old_values:
                prev = old_values[i]
                if prev["card1"] in card_options:
                    card1_var.set(prev["card1"])
                if prev["card2"] in card_options:
                    card2_var.set(prev["card2"])
                try:
                    c = int(prev["coins"])
                    if 0 <= c <= 12:
                        coins_var.set(str(c))
                except (ValueError, TypeError):
                    pass

            card1_menu = tk.OptionMenu(
                row_frame, card1_var, *card_options,
                command=lambda *a: self._update_deck_indicator())
            card1_menu.config(width=10)
            card1_menu.pack(side=tk.LEFT, padx=2)

            card2_menu = tk.OptionMenu(
                row_frame, card2_var, *card_options,
                command=lambda *a: self._update_deck_indicator())
            card2_menu.config(width=10)
            card2_menu.pack(side=tk.LEFT, padx=2)

            coins_spin = tk.Spinbox(
                row_frame, from_=0, to=12, width=3,
                textvariable=coins_var, font=("Helvetica", 10))
            coins_spin.pack(side=tk.LEFT, padx=(5, 0))

            tk.Label(row_frame, text="coins",
                     font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(2, 0))

            self._custom_player_rows.append({
                "frame": row_frame,
                "index": i,
                "card1_var": card1_var,
                "card2_var": card2_var,
                "coins_var": coins_var,
            })

        self._update_deck_indicator()

    def _update_deck_indicator(self):
        """Recalculate and display remaining deck composition."""
        if not self._custom_player_rows:
            self._deck_indicator_var.set("")
            return

        try:
            from AI_game.setup_ui import (
                compute_remaining_deck, validate_deck_config,
                format_deck_indicator, count_random_cards,
                validate_enough_cards_for_random,
            )
        except ImportError:
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

    # ------------------------------------------------------------------
    # Preset save/load
    # ------------------------------------------------------------------

    def _refresh_preset_list(self):
        """Reload preset names into the dropdown."""
        try:
            from AI_game.setup_ui import load_preset_names
        except ImportError:
            return

        menu = self._preset_dropdown["menu"]
        menu.delete(0, tk.END)
        names = load_preset_names()
        if not names:
            menu.add_command(
                label="(no presets)",
                command=lambda: self._preset_var.set(""))
        else:
            for name in names:
                menu.add_command(
                    label=name,
                    command=lambda n=name: self._preset_var.set(n))
            if (not self._preset_var.get()
                    or self._preset_var.get() not in names):
                self._preset_var.set(names[0])

    def _load_preset(self):
        """Load selected preset into the custom conditions UI."""
        try:
            from AI_game.setup_ui import load_preset_data
            from AI_game.presets import VALID_CARDS
        except ImportError:
            messagebox.showerror("Load Preset", "AI_game module not available.")
            return

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

        # Build the current player names for matching
        player_names = self._get_player_names()

        for row in self._custom_player_rows:
            idx = row["index"]
            name = player_names[idx] if idx < len(player_names) else ""
            if name in players_cfg:
                pcfg = players_cfg[name]
                hand = pcfg.get("hand", [])
                coins = pcfg.get("coins", 2)

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
                row["card1_var"].set("Random")
                row["card2_var"].set("Random")
                row["coins_var"].set("2")

        self._update_deck_indicator()

    def _save_preset(self):
        """Save current custom conditions as a preset."""
        try:
            from AI_game.setup_ui import (
                build_preset_from_selections, save_preset_to_file,
            )
        except ImportError:
            messagebox.showerror("Save Preset", "AI_game module not available.")
            return

        player_names = self._get_player_names()
        if not player_names:
            messagebox.showwarning("Save Preset",
                                   "Configure players before saving a preset.")
            return

        card_selections = self._get_card_selections()
        coin_values = self._get_coin_values()
        preset = build_preset_from_selections(
            player_names, card_selections, coin_values)

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
            desc = f"Custom setup: {', '.join(player_names)}"
            preset["description"] = desc
            save_preset_to_file(pname, preset)
            self._refresh_preset_list()
            self._preset_var.set(pname)
            name_dialog.destroy()
            messagebox.showinfo("Save Preset",
                                f"Preset '{pname}' saved successfully.")

        tk.Button(name_dialog, text="Save", command=do_save,
                  font=("Helvetica", 11)).pack(pady=5)

    # ------------------------------------------------------------------
    # Data extraction helpers
    # ------------------------------------------------------------------

    def _get_player_names(self):
        """Return the list of resolved player names."""
        names = []
        # First pass: collect raw names
        raw_names = []
        for i, row in enumerate(self.player_rows):
            is_ai = row["type_var"].get() == "AI"
            if is_ai:
                raw_names.append(row["model_var"].get())
            else:
                name = row["name_var"].get().strip()
                raw_names.append(name if name else f"Player {i + 1}")

        # Build unique AI names using agent_factory
        ai_indices = [i for i, row in enumerate(self.player_rows)
                      if row["type_var"].get() == "AI"]
        if ai_indices:
            try:
                from AI_game.agent_factory import build_agent_names
                ai_provider_names = [raw_names[i] for i in ai_indices]
                ai_display_names = build_agent_names(ai_provider_names)
                for j, idx in enumerate(ai_indices):
                    raw_names[idx] = ai_display_names[j]
            except ImportError:
                pass

        return raw_names

    def _get_card_selections(self):
        """Return list of (card1, card2) tuples from custom rows."""
        selections = []
        for row in self._custom_player_rows:
            c1 = row["card1_var"].get()
            c2 = row["card2_var"].get()
            selections.append((c1, c2))
        return selections

    def _get_coin_values(self):
        """Return list of int coin values from custom rows."""
        values = []
        for row in self._custom_player_rows:
            try:
                v = int(row["coins_var"].get())
                values.append(max(0, min(12, v)))
            except (ValueError, TypeError):
                values.append(2)
        return values

    def _get_seed(self):
        """Return the seed as an integer, or None if empty/invalid."""
        if not hasattr(self, '_seed_var'):
            return None
        raw = self._seed_var.get().strip()
        if not raw:
            return None
        try:
            return int(raw)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Start Game
    # ------------------------------------------------------------------

    def _start_game(self):
        """Validate config, feed to controller, create agents, start game."""
        # Collect player configs
        player_configs = []
        for i, row in enumerate(self.player_rows):
            is_ai = row["type_var"].get() == "AI"
            if is_ai:
                model_name = row["model_var"].get()
                if not model_name:
                    messagebox.showerror(
                        "Configuration Error",
                        f"Player {i + 1}: No AI model selected.")
                    return
                player_configs.append({
                    "name": model_name,
                    "is_ai": True,
                    "model": model_name,
                })
            else:
                name = row["name_var"].get().strip()
                if not name:
                    name = f"Player {i + 1}"
                player_configs.append({
                    "name": name,
                    "is_ai": False,
                })

        # Build unique AI names
        ai_indices = [i for i, c in enumerate(player_configs) if c["is_ai"]]
        if ai_indices:
            if not self.config:
                messagebox.showerror(
                    "Configuration Error",
                    "Cannot use AI players: ai_config.json not found or "
                    "invalid.\n\nPlease create ai_config.json with your API "
                    "keys and agent definitions.")
                return
            try:
                from AI_game.agent_factory import build_agent_names
                ai_provider_names = [player_configs[i]["model"]
                                     for i in ai_indices]
                ai_display_names = build_agent_names(ai_provider_names)
                for j, idx in enumerate(ai_indices):
                    player_configs[idx]["name"] = ai_display_names[j]
            except ImportError:
                messagebox.showerror(
                    "Configuration Error",
                    "AI_game module not available.")
                return

        # Check for duplicate names
        names = [c["name"] for c in player_configs]
        if len(set(names)) != len(names):
            # Disambiguate by appending numbers
            seen = {}
            for i, name in enumerate(names):
                if name in seen:
                    seen[name] += 1
                    names[i] = f"{name} ({seen[name]})"
                    player_configs[i]["name"] = names[i]
                else:
                    seen[name] = 1

        # Validate custom start conditions if expanded
        inline_preset = None
        if self._custom_expanded and self._custom_player_rows:
            try:
                from AI_game.setup_ui import (
                    build_preset_from_selections, compute_remaining_deck,
                    validate_deck_config, count_random_cards,
                    validate_enough_cards_for_random,
                )

                card_selections = self._get_card_selections()
                coin_values = self._get_coin_values()
                inline_preset = build_preset_from_selections(
                    names, card_selections, coin_values)

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
            except ImportError:
                pass

        # Get seed
        seed = self._get_seed()

        # Feed to controller: count then names
        self.controller = GameController(seed=seed)
        self.controller.handle_input(str(len(player_configs)))
        for cfg in player_configs:
            self.controller.handle_input(cfg["name"])

        # Mark AI players
        for i, cfg in enumerate(player_configs):
            if cfg["is_ai"]:
                self.controller.game.players[i].is_ai = True

        # Apply inline preset if configured
        if inline_preset is not None:
            self._apply_inline_preset(inline_preset)

        # Create Agent objects for AI players
        if any(c["is_ai"] for c in player_configs):
            try:
                self._create_ai_agents(player_configs)
            except Exception as e:
                messagebox.showerror(
                    "Agent Creation Error",
                    f"Failed to create AI agents:\n\n{e}")
                return

        # Initialize event log
        self.event_log = []
        self._log_cursor = len(self.controller.log)
        self._turn_number = 0
        self._last_turn_player = None

        # Open player windows (humans only)
        self._open_player_windows()

        # Start AI orchestration
        self.root.after(200, self._check_and_process_ai)

    def _apply_inline_preset(self, inline_preset):
        """Apply an inline preset dict to the game after it has been created."""
        try:
            from AI_game.presets import apply_preset
        except ImportError:
            return

        game = self.controller.game
        player_names = [p.name for p in game.players]

        # Clear dealt hands and return cards to deck
        all_dealt_cards = []
        for player in game.players:
            all_dealt_cards.extend(player.influence)
            player.influence = []
            player.coins = 2
        for card in all_dealt_cards:
            game.deck.return_card(card)

        # Apply the preset
        apply_preset(inline_preset, game, player_names)
        self.controller._log("Custom start conditions applied.")

    def _create_ai_agents(self, player_configs):
        """Create Agent objects for AI players."""
        from AI_game.agent_factory import create_agents_from_names

        ai_configs = [(i, c) for i, c in enumerate(player_configs)
                      if c["is_ai"]]
        ai_names = [c["name"] for _, c in ai_configs]

        # Get per-agent settings from advanced section
        history_depths = None
        rules_summaries = None
        strategy_guides = None

        if self._custom_expanded and self._advanced_rows:
            # Build maps from player_index to settings
            ai_settings_map = {}
            for arow in self._advanced_rows:
                pidx = arow["player_index"]
                try:
                    hd = int(arow["history_depth_var"].get())
                    hd = max(0, hd)
                except (ValueError, TypeError):
                    hd = 2
                ai_settings_map[pidx] = {
                    "history_depth": hd,
                    "rules_summary": arow["rules_summary_var"].get(),
                    "strategy_guide": arow["strategy_guide_var"].get(),
                }

            history_depths = []
            rules_summaries = []
            strategy_guides = []
            for idx, _ in ai_configs:
                settings = ai_settings_map.get(idx, {})
                history_depths.append(settings.get("history_depth", 2))
                rules_summaries.append(settings.get("rules_summary", False))
                strategy_guides.append(settings.get("strategy_guide", False))

        agents = create_agents_from_names(
            ai_names, self.config,
            history_depths=history_depths,
            rules_summaries=rules_summaries,
            strategy_guides=strategy_guides,
        )

        # Map Player objects to Agent objects
        self.ai_agents = {}
        agent_idx = 0
        for i, cfg in enumerate(player_configs):
            if cfg["is_ai"]:
                player = self.controller.game.players[i]
                self.ai_agents[player] = agents[agent_idx]
                agent_idx += 1

    # ------------------------------------------------------------------
    # Player Windows
    # ------------------------------------------------------------------

    def _open_player_windows(self):
        """Create PlayerWindows for human players only."""
        human_index = 0
        for i, player in enumerate(self.controller.game.players):
            if not player.is_ai:
                pw = PlayerWindow(self, player, human_index)
                self.player_windows.append(pw)
                human_index += 1
        self.root.withdraw()

    def refresh_all_player_windows(self):
        """Called after any input to refresh every player window."""
        # Check if the game was reset (New Game)
        if self.controller.state == State.SETUP_PLAYER_COUNT:
            self._close_all_player_windows()
            self._reset_ai_state()
            self.root.deiconify()
            # Rebuild setup from scratch
            self._rebuild_setup_window()
            return

        for pw in self.player_windows:
            pw.refresh()

    def _close_all_player_windows(self):
        for pw in self.player_windows:
            pw.window.destroy()
        self.player_windows = []

    def _reset_ai_state(self):
        """Reset all AI-related state for a new game."""
        self.ai_agents = {}
        self.event_log = []
        self._log_cursor = 0
        self._turn_number = 0
        self._last_turn_player = None
        self._ai_processing = False

    def _rebuild_setup_window(self):
        """Rebuild the setup window for a new game after Game Over."""
        # Destroy all existing widgets
        for widget in self.root.winfo_children():
            widget.destroy()

        # Reset Phase 2 state
        self.num_players = 0
        self.player_rows = []
        self._ai_config_loaded = False
        self._custom_expanded = False
        self._advanced_rows = []
        self._custom_player_rows = []

        # Rebuild Phase 1 layout
        self._build_layout()
        self.refresh()

    def quit_all(self):
        self.root.destroy()

    # ------------------------------------------------------------------
    # AI Orchestration
    # ------------------------------------------------------------------

    def _check_and_process_ai(self):
        """After any state change, check if active player is AI and process."""
        if self._ai_processing:
            return  # Already processing an AI turn

        if self.controller.state in (State.SETUP_PLAYER_COUNT,
                                     State.SETUP_PLAYER_NAME):
            return

        if self.controller.state == State.GAME_OVER:
            self.refresh_all_player_windows()
            return

        active = self.controller.get_active_players()
        if not active:
            return

        # Find AI players among active players
        ai_player = next((p for p in active if p.is_ai), None)
        if ai_player is None:
            return  # Only humans active, wait for input

        # Process AI turn in background thread
        self._ai_processing = True
        self._process_ai_turn(ai_player)

    def _process_ai_turn(self, player):
        """Query AI player in background thread."""
        agent = self.ai_agents.get(player)
        if agent is None:
            self._ai_processing = False
            return

        # Insert turn boundary if needed
        if (self.controller.state == State.CHOOSE_ACTION
                and self.controller.current_player != self._last_turn_player):
            self._turn_number += 1
            self.event_log.append({
                "type": "event",
                "text": "",
                "turn_boundary": True,
                "turn_player": self.controller.current_player.name,
                "turn_number": self._turn_number,
            })
            self._last_turn_player = self.controller.current_player

        # Update windows to show "thinking"
        for pw in self.player_windows:
            pw.refresh()

        def worker():
            message, options = self.controller.get_prompt(player)
            if options is None:
                self.root.after(0, self._on_ai_done_no_action)
                return

            action, speech = self._query_ai(agent, player, options)
            self.root.after(0, lambda: self._on_ai_response(
                player, action, speech))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _query_ai(self, agent, player, options):
        """Build prompt, query agent, parse response. Retry on failure."""
        try:
            from AI_game.prompt_builder import build_prompt_sections
            from AI_game.response_parser import parse_response, ParseError
            from AI_game.game_runner import smart_default
        except ImportError:
            # If imports fail, use a basic fallback
            return options[0] if options else "Income", ""

        prompt_sections = build_prompt_sections(
            self.controller, player, self.event_log,
            history_depth=agent.history_depth,
            rules_summary=agent.rules_summary,
            strategy_guide=agent.strategy_guide,
        )

        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                raw = agent.query_structured(prompt_sections)
                result = parse_response(raw, options)
                return result["action"], result["speech"]
            except Exception:
                pass

        # Fallback
        fallback = smart_default(
            self.controller.state, options, self.controller)
        return fallback, ""

    def _on_ai_done_no_action(self):
        """Handle case where AI had no action to take."""
        self._ai_processing = False

    def _on_ai_response(self, player, action, speech):
        """Handle AI response on main thread."""
        # Record speech
        if speech:
            self.controller.send_chat(player.name, speech)
            self.event_log.append({
                "type": "speech",
                "player": player.name,
                "text": speech,
            })

        # Execute the action
        self.controller.handle_input(action, player)
        self._consume_log()

        self._ai_processing = False
        self.refresh_all_player_windows()

        # Check for more AI to process (with small delay for UI
        # responsiveness)
        self.root.after(100, self._check_and_process_ai)

    def _consume_log(self):
        """Transfer new controller log entries into event_log."""
        while self._log_cursor < len(self.controller.log):
            text = self.controller.log[self._log_cursor]
            self.event_log.append({"type": "event", "text": text})
            self._log_cursor += 1


class PlayerWindow:
    """One Toplevel window per human player, showing private info only."""

    def __init__(self, app, player, player_index):
        self.app = app
        self.controller = app.controller
        self.player = player
        self.player_index = player_index

        self.window = tk.Toplevel(app.root)
        self.window.title(f"Coup - {player.name}")
        self.window.minsize(800, 600)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # Offset windows so they don't stack
        offset_x = 100 + (player_index * 40)
        offset_y = 80 + (player_index * 40)
        self.window.geometry(f"+{offset_x}+{offset_y}")

        self._build_layout()
        self.refresh()

    def _build_layout(self):
        # Top: player info panels
        self.player_frame = tk.Frame(self.window)
        self.player_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        self.player_panels = []

        # Middle: prompt + buttons
        self.prompt_frame = tk.Frame(self.window)
        self.prompt_frame.pack(fill=tk.X, padx=10, pady=10)

        self.prompt_label = tk.Label(
            self.prompt_frame, text="", font=("Helvetica", 14),
            wraplength=700, justify=tk.LEFT)
        self.prompt_label.pack(anchor=tk.W)

        self.button_frame = tk.Frame(self.prompt_frame)
        self.button_frame.pack(fill=tk.X, pady=(5, 0))

        # Text entry (for edge cases)
        self.entry_frame = tk.Frame(self.prompt_frame)
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(self.entry_frame, textvariable=self.entry_var,
                              font=("Helvetica", 12), width=30)
        self.entry.pack(side=tk.LEFT, padx=(0, 5))
        self.entry_btn = tk.Button(self.entry_frame, text="Submit",
                                   command=self._on_entry_submit)
        self.entry_btn.pack(side=tk.LEFT)
        self.entry.bind("<Return>", lambda e: self._on_entry_submit())

        # Bottom half: game log (left) and chat (right) side by side
        self.bottom_frame = tk.Frame(self.window)
        self.bottom_frame.pack(fill=tk.BOTH, expand=True, padx=10,
                               pady=(0, 10))

        # Game log (left)
        log_frame = tk.LabelFrame(self.bottom_frame, text="Game Log")
        log_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, state=tk.DISABLED,
            font=("Courier", 10), wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Chat (right)
        chat_frame = tk.LabelFrame(self.bottom_frame, text="Chat")
        chat_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        self.chat_text = scrolledtext.ScrolledText(
            chat_frame, height=12, state=tk.DISABLED,
            font=("Courier", 10), wrap=tk.WORD)
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        chat_input_frame = tk.Frame(chat_frame)
        chat_input_frame.pack(fill=tk.X, pady=(4, 0))

        self.chat_var = tk.StringVar()
        self.chat_entry = tk.Entry(chat_input_frame,
                                   textvariable=self.chat_var,
                                   font=("Helvetica", 10))
        self.chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                             padx=(0, 4))
        self.chat_entry.bind("<Return>", lambda e: self._on_chat_send())

        self.chat_send_btn = tk.Button(chat_input_frame, text="Send",
                                       command=self._on_chat_send)
        self.chat_send_btn.pack(side=tk.LEFT)

    def refresh(self):
        self._refresh_players()
        self._refresh_prompt()
        self._refresh_log()
        self._refresh_chat()

    def _refresh_players(self):
        for frame, _, _ in self.player_panels:
            frame.destroy()
        self.player_panels = []

        if self.controller.game is None:
            return

        for p in self.controller.game.players:
            frame = tk.Frame(self.player_frame, bd=2, relief=tk.GROOVE,
                             padx=8, pady=4)
            frame.pack(side=tk.LEFT, padx=4, fill=tk.Y)

            is_current = (p == self.controller.current_player)
            alive = p.is_alive()

            # Name label (include AI indicator)
            name_text = p.name
            if p.is_ai and alive:
                name_text += " [AI]"
            if is_current and alive:
                name_text = f"> {name_text} <"
            name_lbl = tk.Label(frame, text=name_text,
                                font=("Helvetica", 11, "bold"))
            if not alive:
                name_lbl.config(fg="gray")
            elif is_current:
                name_lbl.config(fg="blue")
            name_lbl.pack()

            # Info label -- privacy-aware
            if alive:
                if p is self.player:
                    # Own cards: show face-up
                    cards = ", ".join(p.influence)
                    info_text = f"Coins: {p.coins}\nCards: {cards}"
                else:
                    # Other players: show card count only
                    count = len(p.influence)
                    card_word = "card" if count == 1 else "cards"
                    info_text = f"Coins: {p.coins}\n{count} {card_word}"
            else:
                info_text = "ELIMINATED"

            info_lbl = tk.Label(frame, text=info_text,
                                font=("Helvetica", 9), justify=tk.LEFT)
            if not alive:
                info_lbl.config(fg="gray")
            info_lbl.pack()

            self.player_panels.append((frame, name_lbl, info_lbl))

        # Show revealed cards
        if self.controller.game.revealed_cards:
            frame = tk.Frame(self.player_frame, bd=2, relief=tk.RIDGE,
                             padx=8, pady=4)
            frame.pack(side=tk.LEFT, padx=4, fill=tk.Y)
            lbl = tk.Label(frame, text="Revealed",
                           font=("Helvetica", 11, "bold"), fg="red")
            lbl.pack()
            cards_text = "\n".join(self.controller.game.revealed_cards)
            cards_lbl = tk.Label(frame, text=cards_text,
                                 font=("Helvetica", 9), justify=tk.LEFT)
            cards_lbl.pack()
            self.player_panels.append((frame, lbl, cards_lbl))

    def _refresh_prompt(self):
        for widget in self.button_frame.winfo_children():
            widget.destroy()
        self.entry_frame.pack_forget()

        active_players = self.controller.get_active_players()

        if self.controller.state == State.GAME_OVER:
            # All windows show game-over message and New Game button
            message, options = self.controller.get_prompt()
            self.prompt_label.config(text=message)
            if options:
                for opt in options:
                    btn = tk.Button(
                        self.button_frame, text=opt,
                        font=("Helvetica", 11), padx=10, pady=4,
                        command=lambda v=opt: self._on_button_click(v))
                    btn.pack(side=tk.LEFT, padx=3, pady=2)
        elif self.player in active_players:
            # This player needs to respond -- show personalized prompt
            message, options = self.controller.get_prompt(self.player)
            self.prompt_label.config(text=message)
            if options:
                for opt in options:
                    btn = tk.Button(
                        self.button_frame, text=opt,
                        font=("Helvetica", 11), padx=10, pady=4,
                        command=lambda v=opt: self._on_button_click(v))
                    btn.pack(side=tk.LEFT, padx=3, pady=2)
        else:
            # Another player (or multiple) are active -- show waiting message
            if active_players:
                # Check if all active players are AI
                ai_active = [p for p in active_players if p.is_ai]
                human_active = [p for p in active_players if not p.is_ai]

                if ai_active and not human_active:
                    names = ", ".join(p.name for p in ai_active)
                    self.prompt_label.config(
                        text=f"AI is thinking... ({names})")
                else:
                    names = ", ".join(p.name for p in active_players)
                    self.prompt_label.config(
                        text=f"Waiting for {names} to respond...")
            else:
                self.prompt_label.config(text="")

    def _refresh_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        for line in self.controller.log:
            self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _refresh_chat(self):
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        for name, text in self.controller.chat_messages:
            self.chat_text.insert(tk.END, f"{name}: {text}\n")
        self.chat_text.see(tk.END)
        self.chat_text.config(state=tk.DISABLED)

    def _on_chat_send(self):
        text = self.chat_var.get().strip()
        if text:
            self.controller.send_chat(self.player.name, text)
            self.chat_var.set("")
            self.app.refresh_all_player_windows()

    def _on_button_click(self, value):
        self.controller.handle_input(value, self.player)
        self.app._consume_log()
        self.app.refresh_all_player_windows()
        # Trigger AI processing for any AI turns that follow
        self.app.root.after(100, self.app._check_and_process_ai)

    def _on_entry_submit(self):
        value = self.entry_var.get().strip()
        if value:
            self.controller.handle_input(value, self.player)
            self.entry_var.set("")
            self.app._consume_log()
            self.app.refresh_all_player_windows()
            self.app.root.after(100, self.app._check_and_process_ai)

    def _on_close(self):
        self.app.quit_all()


def main():
    root = tk.Tk()
    controller = GameController()
    app = SetupWindow(root, controller)
    root.mainloop()


if __name__ == "__main__":
    main()
