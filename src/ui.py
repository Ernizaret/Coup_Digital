"""Tkinter UI for Coup, driven by GameController."""

import tkinter as tk
from tkinter import scrolledtext
from src.controller import GameController, State


class CoupApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Coup")
        self.root.minsize(800, 600)
        self.controller = GameController()

        self._build_layout()
        self.refresh()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self):
        # Top: player info panels
        self.player_frame = tk.Frame(self.root)
        self.player_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        self.player_panels = []  # list of (frame, name_lbl, info_lbl)

        # Middle: prompt + buttons
        self.prompt_frame = tk.Frame(self.root)
        self.prompt_frame.pack(fill=tk.X, padx=10, pady=10)

        self.prompt_label = tk.Label(
            self.prompt_frame, text="", font=("Helvetica", 14),
            wraplength=700, justify=tk.LEFT)
        self.prompt_label.pack(anchor=tk.W)

        self.button_frame = tk.Frame(self.prompt_frame)
        self.button_frame.pack(fill=tk.X, pady=(5, 0))

        # Text entry (for player names)
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
            self.root, height=12, state=tk.DISABLED,
            font=("Courier", 10), wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    # ------------------------------------------------------------------
    # Refresh — re-render everything from controller state
    # ------------------------------------------------------------------
    def refresh(self):
        self._refresh_players()
        self._refresh_prompt()
        self._refresh_log()

    def _refresh_players(self):
        # Clear old panels
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

            # Info label
            if alive:
                cards = ", ".join(p.influence)
                info_text = f"Coins: {p.coins}\nCards: {cards}"
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
        # Clear old buttons
        for widget in self.button_frame.winfo_children():
            widget.destroy()
        self.entry_frame.pack_forget()

        message, options = self.controller.get_prompt()
        self.prompt_label.config(text=message)

        if self.controller.state == State.SETUP_PLAYER_NAME:
            # Show text entry for names
            self.entry_frame.pack(fill=tk.X, pady=(5, 0))
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

    # ------------------------------------------------------------------
    # Input handlers
    # ------------------------------------------------------------------
    def _on_button_click(self, value):
        self.controller.handle_input(value)
        self.refresh()

    def _on_entry_submit(self):
        value = self.entry_var.get().strip()
        if value:
            self.controller.handle_input(value)
            self.entry_var.set("")
            self.refresh()


def main():
    root = tk.Tk()
    app = CoupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
