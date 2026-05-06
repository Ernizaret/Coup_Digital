"""Tkinter setup window: select AI agents, configure custom start conditions,
and run one or more games back-to-back."""

import json
import os
import tkinter as tk
from tkinter import messagebox

from AI_game.config import load_config, get_available_agents
from AI_game.agents import create_agent
from AI_game.game_runner import GameRunner
from AI_game.console_output import ConsoleOutput
from AI_game.presets import (
    VALID_CARDS, _find_presets_path, load_presets_file,
)

CARD_OPTIONS = ["Random"] + VALID_CARDS
CARD_ABBREV = {
    "Duke": "D",
    "Assassin": "A",
    "Captain": "C",
    "Contessa": "Co",
    "Ambassador": "Am",
}
DEFAULT_COINS = 2


class AgentSetupWindow:
    """Setup window for selecting AI agents and configuring turn order."""

    def __init__(self, root):
        self.root = root
        self.root.title("Coup — AI Agent Setup")
        self.root.minsize(500, 520)

        # Load config
        try:
            self.config = load_config()
        except FileNotFoundError as e:
            messagebox.showerror("Config Error", str(e))
            self.root.destroy()
            return

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

        # Custom start conditions state
        self._custom_expanded = False
        self._player_rows = []  # list of dicts with StringVars/IntVars

        self._build_layout()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self):
        # Title
        title = tk.Label(
            self.root, text="Select AI Agents for Coup",
            font=("Helvetica", 16, "bold"))
        title.pack(pady=(15, 5))

        subtitle = tk.Label(
            self.root, text="Add 2-6 agents, arrange turn order, then start.",
            font=("Helvetica", 10))
        subtitle.pack(pady=(0, 10))

        # Add-agent buttons
        add_frame = tk.LabelFrame(self.root, text="Add Agent", padx=10,
                                  pady=5)
        add_frame.pack(fill=tk.X, padx=15, pady=5)

        for name in self.available:
            btn = tk.Button(
                add_frame, text=f"+ {name}",
                font=("Helvetica", 11), padx=8, pady=3,
                command=lambda n=name: self._add_agent(n))
            btn.pack(side=tk.LEFT, padx=4, pady=3)

        # Turn order list
        list_frame = tk.LabelFrame(
            self.root, text="Turn Order", padx=10, pady=5)
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

        # Game count selector
        game_count_frame = tk.Frame(self.root)
        game_count_frame.pack(fill=tk.X, padx=15, pady=(5, 0))

        tk.Label(game_count_frame, text="Number of games:",
                 font=("Helvetica", 11)).pack(side=tk.LEFT)
        self.game_count_var = tk.IntVar(value=1)
        self.game_count_spin = tk.Spinbox(
            game_count_frame, from_=1, to=999, width=5,
            textvariable=self.game_count_var, font=("Helvetica", 11))
        self.game_count_spin.pack(side=tk.LEFT, padx=(8, 0))

        # Custom start conditions toggle
        self.toggle_btn = tk.Button(
            self.root, text="▶ Custom Start Conditions",
            font=("Helvetica", 11), relief=tk.FLAT,
            command=self._toggle_custom)
        self.toggle_btn.pack(fill=tk.X, padx=15, pady=(8, 0))

        # Custom start conditions frame (initially hidden)
        self.custom_frame = tk.Frame(self.root)
        # Inner frame for player rows
        self.custom_rows_frame = tk.Frame(self.custom_frame)
        self.custom_rows_frame.pack(fill=tk.X, padx=5, pady=5)

        # Deck label
        self.deck_label = tk.Label(
            self.custom_frame, text="Remaining deck: —",
            font=("Helvetica", 10))
        self.deck_label.pack(anchor=tk.W, padx=10, pady=(2, 5))

        # Preset save / load row
        preset_frame = tk.Frame(self.custom_frame)
        preset_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        tk.Button(preset_frame, text="Save Preset",
                  command=self._save_preset).pack(side=tk.LEFT, padx=4)

        tk.Label(preset_frame, text="Load:").pack(side=tk.LEFT, padx=(8, 2))
        self._preset_var = tk.StringVar(value="")
        self._preset_menu = tk.OptionMenu(
            preset_frame, self._preset_var, "")
        self._preset_menu.config(width=18)
        self._preset_menu.pack(side=tk.LEFT, padx=4)
        self._refresh_preset_menu()

        # Start button
        self.start_btn = tk.Button(
            self.root, text="Start Game",
            font=("Helvetica", 13, "bold"), padx=20, pady=8,
            state=tk.DISABLED, command=self._start_game)
        self.start_btn.pack(pady=15)

    # ------------------------------------------------------------------
    # Agent list management
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Custom start conditions
    # ------------------------------------------------------------------

    def _toggle_custom(self):
        """Show or hide the custom start conditions frame."""
        if self._custom_expanded:
            self.custom_frame.pack_forget()
            self.toggle_btn.config(text="▶ Custom Start Conditions")
            self._custom_expanded = False
        else:
            # Insert custom_frame right after the toggle button
            self.custom_frame.pack(fill=tk.X, padx=15, pady=(0, 0),
                                   after=self.toggle_btn)
            self.toggle_btn.config(text="▼ Custom Start Conditions")
            self._custom_expanded = True
            self._rebuild_custom_rows()

    def _rebuild_custom_rows(self):
        """Clear and rebuild the per-player configuration rows."""
        # Destroy old row widgets
        for child in self.custom_rows_frame.winfo_children():
            child.destroy()
        self._player_rows = []

        agent_names = [self.listbox.get(i)
                       for i in range(self.listbox.size())]

        if not agent_names:
            return

        # Header row
        hdr = tk.Frame(self.custom_rows_frame)
        hdr.pack(fill=tk.X, pady=(0, 2))
        tk.Label(hdr, text="Player", width=14, anchor=tk.W,
                 font=("Helvetica", 9, "bold")).pack(side=tk.LEFT)
        tk.Label(hdr, text="Card 1", width=12,
                 font=("Helvetica", 9, "bold")).pack(side=tk.LEFT)
        tk.Label(hdr, text="Card 2", width=12,
                 font=("Helvetica", 9, "bold")).pack(side=tk.LEFT)
        tk.Label(hdr, text="Coins", width=6,
                 font=("Helvetica", 9, "bold")).pack(side=tk.LEFT)

        for name in agent_names:
            row_frame = tk.Frame(self.custom_rows_frame)
            row_frame.pack(fill=tk.X, pady=1)

            tk.Label(row_frame, text=name, width=14, anchor=tk.W,
                     font=("Helvetica", 10)).pack(side=tk.LEFT)

            card1_var = tk.StringVar(value="Random")
            card1_var.trace_add("write", self._on_card_change)
            card1_menu = tk.OptionMenu(row_frame, card1_var, *CARD_OPTIONS)
            card1_menu.config(width=10)
            card1_menu.pack(side=tk.LEFT, padx=2)

            card2_var = tk.StringVar(value="Random")
            card2_var.trace_add("write", self._on_card_change)
            card2_menu = tk.OptionMenu(row_frame, card2_var, *CARD_OPTIONS)
            card2_menu.config(width=10)
            card2_menu.pack(side=tk.LEFT, padx=2)

            coins_var = tk.IntVar(value=DEFAULT_COINS)
            coins_spin = tk.Spinbox(
                row_frame, from_=0, to=12, width=4,
                textvariable=coins_var, font=("Helvetica", 10))
            coins_spin.pack(side=tk.LEFT, padx=2)

            self._player_rows.append({
                "name": name,
                "card1_var": card1_var,
                "card2_var": card2_var,
                "coins_var": coins_var,
            })

        self._update_deck_label()

    def _on_card_change(self, *args):
        """Callback fired when any card dropdown changes."""
        self._update_deck_label()

    def _update_deck_label(self, *args):
        """Recompute remaining deck counts and update the label."""
        counts = {c: 3 for c in VALID_CARDS}

        for row in self._player_rows:
            for var_key in ("card1_var", "card2_var"):
                card = row[var_key].get()
                if card != "Random":
                    counts[card] -= 1

        invalid = any(v < 0 for v in counts.values())

        parts = []
        for card in VALID_CARDS:
            abbrev = CARD_ABBREV[card]
            parts.append(f"{counts[card]}{abbrev}")

        text = "Remaining deck: " + " ".join(parts)
        self.deck_label.config(text=text, fg="red" if invalid else "black")

    # ------------------------------------------------------------------
    # Preset save / load
    # ------------------------------------------------------------------

    def _refresh_preset_menu(self):
        """Reload the preset dropdown from presets.json."""
        menu = self._preset_menu["menu"]
        menu.delete(0, tk.END)

        names = self._get_preset_names()
        if not names:
            menu.add_command(label="(no presets)", state=tk.DISABLED)
            return

        for name in names:
            menu.add_command(
                label=name,
                command=lambda n=name: self._load_preset(n))

    def _get_preset_names(self):
        """Return list of preset names from presets.json (empty list if missing)."""
        path = _find_presets_path()
        if not os.path.exists(path):
            return []
        try:
            data = load_presets_file(path)
            return list(data.get("presets", {}).keys())
        except Exception:
            return []

    def _save_preset(self):
        """Save current UI configuration as a named preset to presets.json."""
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "Save Preset", "Preset name:", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()

        preset = self._build_preset_from_ui()
        if preset is None:
            # Build a minimal preset with just the player names
            agent_names = [self.listbox.get(i)
                           for i in range(self.listbox.size())]
            preset = {
                "players": {n: {} for n in agent_names},
                "deck": "auto",
            }

        # Add turn order
        agent_names = [self.listbox.get(i)
                       for i in range(self.listbox.size())]
        preset["turn_order"] = agent_names

        # Load existing file or create new
        path = _find_presets_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {"presets": {}}
        else:
            data = {"presets": {}}

        data.setdefault("presets", {})[name] = preset

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self._refresh_preset_menu()
        messagebox.showinfo("Saved", f"Preset '{name}' saved.")

    def _load_preset(self, name):
        """Populate the UI from a saved preset."""
        try:
            data = load_presets_file()
        except Exception as e:
            messagebox.showerror("Load Error", str(e))
            return

        presets = data.get("presets", {})
        if name not in presets:
            messagebox.showerror("Load Error", f"Preset '{name}' not found.")
            return

        preset = presets[name]
        self._preset_var.set(name)

        players_cfg = preset.get("players", {})
        turn_order = preset.get("turn_order")
        if turn_order is not None:
            player_names = turn_order
        else:
            player_names = list(players_cfg.keys())

        # Clear listbox and agent counts
        self.listbox.delete(0, tk.END)
        self._agent_counts = {n: 0 for n in self.available}

        agents_cfg = self.config["agents"]
        for pname in player_names:
            # Figure out the provider and update counts
            for provider in self.available:
                if pname == provider or pname.startswith(provider + " "):
                    self._agent_counts[provider] += 1
                    break
            self.listbox.insert(tk.END, pname)

        self._update_start_btn()

        # Expand custom section if not already
        if not self._custom_expanded:
            self._toggle_custom()
        else:
            self._rebuild_custom_rows()

        # Populate card/coin values
        for row in self._player_rows:
            pname = row["name"]
            cfg = players_cfg.get(pname, {})
            hand = cfg.get("hand", [])

            if len(hand) >= 1:
                row["card1_var"].set(hand[0])
            else:
                row["card1_var"].set("Random")

            if len(hand) >= 2:
                row["card2_var"].set(hand[1])
            else:
                row["card2_var"].set("Random")

            coins = cfg.get("coins", DEFAULT_COINS)
            row["coins_var"].set(coins)

        self._update_deck_label()

    # ------------------------------------------------------------------
    # Build preset dict from UI
    # ------------------------------------------------------------------

    def _build_preset_from_ui(self):
        """Construct a preset dict from the current UI state.

        Returns None if the custom section is collapsed or all values are
        at their defaults (all Random cards, 2 coins each).
        """
        if not self._custom_expanded:
            return None

        has_custom = False
        players = {}

        for row in self._player_rows:
            name = row["name"]
            card1 = row["card1_var"].get()
            card2 = row["card2_var"].get()
            try:
                coins = row["coins_var"].get()
            except tk.TclError:
                coins = DEFAULT_COINS

            hand = []
            if card1 != "Random":
                hand.append(card1)
                has_custom = True
            if card2 != "Random":
                hand.append(card2)
                has_custom = True

            player_cfg = {}
            if hand:
                player_cfg["hand"] = hand
            if coins != DEFAULT_COINS:
                player_cfg["coins"] = coins
                has_custom = True

            if player_cfg:
                players[name] = player_cfg

        if not has_custom:
            return None

        return {"players": players, "deck": "auto"}

    # ------------------------------------------------------------------
    # Start game
    # ------------------------------------------------------------------

    def _start_game(self):
        """Create Agent instances and launch the game runner."""
        try:
            game_count = self.game_count_var.get()
        except tk.TclError:
            game_count = 1
        if game_count < 1:
            game_count = 1

        preset = self._build_preset_from_ui()

        # Validate deck if custom conditions are set
        if preset is not None:
            counts = {c: 3 for c in VALID_CARDS}
            for row in self._player_rows:
                for var_key in ("card1_var", "card2_var"):
                    card = row[var_key].get()
                    if card != "Random":
                        counts[card] -= 1
            if any(v < 0 for v in counts.values()):
                messagebox.showerror(
                    "Invalid Configuration",
                    "Too many of one card type assigned. "
                    "Each card type has at most 3 copies in the deck."
                )
                return

        agent_names = [self.listbox.get(i)
                       for i in range(self.listbox.size())]
        api_key = self.config["api_key"]
        agents_cfg = self.config["agents"]

        self.root.destroy()

        if game_count == 1:
            # Single game
            agents = self._create_agents(agent_names, api_key, agents_cfg)
            runner = GameRunner(agents, preset=preset)
            runner.run()
        else:
            # Batch run
            output = ConsoleOutput()
            results = []
            all_agents = []

            for game_num in range(1, game_count + 1):
                agents = self._create_agents(agent_names, api_key, agents_cfg)
                runner = GameRunner(agents, preset=preset)
                runner.run()

                winner = runner.controller.game.get_living_players()[0]
                results.append(winner.name)
                all_agents.extend(agents)
                output.batch_progress(game_num, game_count, winner.name)

            output.batch_summary(results, all_agents)

    def _create_agents(self, agent_names, api_key, agents_cfg):
        """Create a fresh set of Agent instances for the given names."""
        agents = []
        for name in agent_names:
            for provider in self.available:
                if name == provider or name.startswith(provider + " "):
                    model = agents_cfg[provider]
                    agent = create_agent(name, api_key, model)
                    agents.append(agent)
                    break
        return agents


def main():
    root = tk.Tk()
    AgentSetupWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
