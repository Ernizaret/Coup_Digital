"""Multi-window Tkinter UI for Coup, driven by GameController.

Each player gets their own window showing only their private information.
"""

import tkinter as tk
from tkinter import scrolledtext
from src.controller import GameController, State


class SetupWindow:
    """Manages the root tk.Tk() window for pre-game setup."""

    def __init__(self, root, controller):
        self.root = root
        self.root.title("Coup - Setup")
        self.root.minsize(400, 300)
        self.controller = controller
        self.player_windows = []

        self._build_layout()
        self.refresh()

    def _build_layout(self):
        self.prompt_label = tk.Label(
            self.root, text="", font=("Helvetica", 14),
            wraplength=350, justify=tk.LEFT)
        self.prompt_label.pack(padx=10, pady=(20, 10), anchor=tk.W)

        self.button_frame = tk.Frame(self.root)
        self.button_frame.pack(fill=tk.X, padx=10)

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
        # If the game has started, transition to player windows
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
                    command=lambda v=opt: self._on_button_click(v))
                btn.pack(side=tk.LEFT, padx=3, pady=2)

    def _refresh_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        for line in self.controller.log:
            self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _on_button_click(self, value):
        self.controller.handle_input(value)
        self.refresh()

    def _on_entry_submit(self):
        value = self.entry_var.get().strip()
        if value:
            self.controller.handle_input(value)
            self.entry_var.set("")
            self.refresh()

    def _open_player_windows(self):
        for i, player in enumerate(self.controller.game.players):
            pw = PlayerWindow(self, player, i)
            self.player_windows.append(pw)
        self.root.withdraw()

    def refresh_all_player_windows(self):
        """Called after any input to refresh every player window."""
        # Check if the game was reset (New Game)
        if self.controller.state == State.SETUP_PLAYER_COUNT:
            self._close_all_player_windows()
            self.root.deiconify()
            self.refresh()
            return

        for pw in self.player_windows:
            pw.refresh()

    def _close_all_player_windows(self):
        for pw in self.player_windows:
            pw.window.destroy()
        self.player_windows = []

    def quit_all(self):
        self.root.destroy()


class PlayerWindow:
    """One Toplevel window per player, showing private info only for its owner."""

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

        # Text entry (for edge cases, though setup uses SetupWindow)
        self.entry_frame = tk.Frame(self.prompt_frame)
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(self.entry_frame, textvariable=self.entry_var,
                              font=("Helvetica", 12), width=30)
        self.entry.pack(side=tk.LEFT, padx=(0, 5))
        self.entry_btn = tk.Button(self.entry_frame, text="Submit",
                                   command=self._on_entry_submit)
        self.entry_btn.pack(side=tk.LEFT)
        self.entry.bind("<Return>", lambda e: self._on_entry_submit())

        # Bottom: scrollable game log
        self.log_text = scrolledtext.ScrolledText(
            self.window, height=12, state=tk.DISABLED,
            font=("Courier", 10), wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    def refresh(self):
        self._refresh_players()
        self._refresh_prompt()
        self._refresh_log()

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

            # Name label
            name_text = p.name
            if is_current and alive:
                name_text = f"> {p.name} <"
            name_lbl = tk.Label(frame, text=name_text,
                                font=("Helvetica", 11, "bold"))
            if not alive:
                name_lbl.config(fg="gray")
            elif is_current:
                name_lbl.config(fg="blue")
            name_lbl.pack()

            # Info label — privacy-aware
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
            # This player needs to respond — show personalized prompt
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
            # Another player (or multiple) are active — show waiting message
            if active_players:
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

    def _on_button_click(self, value):
        self.controller.handle_input(value, self.player)
        self.app.refresh_all_player_windows()

    def _on_entry_submit(self):
        value = self.entry_var.get().strip()
        if value:
            self.controller.handle_input(value, self.player)
            self.entry_var.set("")
            self.app.refresh_all_player_windows()

    def _on_close(self):
        self.app.quit_all()


def main():
    root = tk.Tk()
    controller = GameController()
    app = SetupWindow(root, controller)
    root.mainloop()


if __name__ == "__main__":
    main()
