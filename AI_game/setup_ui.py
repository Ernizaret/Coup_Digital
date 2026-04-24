"""Tkinter setup window: select AI agents and turn order, then start the game."""

import tkinter as tk
from tkinter import messagebox

from AI_game.config import load_config, get_available_agents
from AI_game.agents import create_agent
from AI_game.game_runner import GameRunner


class AgentSetupWindow:
    """Setup window for selecting AI agents and configuring turn order."""

    def __init__(self, root):
        self.root = root
        self.root.title("Coup — AI Agent Setup")
        self.root.minsize(500, 400)

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

        self._build_layout()

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
        add_frame = tk.LabelFrame(self.root, text="Add Agent", padx=10, pady=5)
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

        # Start button
        self.start_btn = tk.Button(
            self.root, text="Start Game",
            font=("Helvetica", 13, "bold"), padx=20, pady=8,
            state=tk.DISABLED, command=self._start_game)
        self.start_btn.pack(pady=15)

    def _add_agent(self, provider_name):
        count = self.listbox.size()
        if count >= 6:
            messagebox.showwarning("Limit", "Maximum 6 agents.")
            return

        self._agent_counts[provider_name] += 1
        n = self._agent_counts[provider_name]
        # Append number if this is the 2nd+ of same provider
        if n > 1:
            display_name = f"{provider_name} {n}"
        else:
            display_name = provider_name

        self.listbox.insert(tk.END, display_name)
        self._update_start_btn()

    def _remove(self):
        sel = self.listbox.curselection()
        if sel:
            self.listbox.delete(sel[0])
            self._update_start_btn()

    def _move_up(self):
        sel = self.listbox.curselection()
        if sel and sel[0] > 0:
            idx = sel[0]
            text = self.listbox.get(idx)
            self.listbox.delete(idx)
            self.listbox.insert(idx - 1, text)
            self.listbox.selection_set(idx - 1)

    def _move_down(self):
        sel = self.listbox.curselection()
        if sel and sel[0] < self.listbox.size() - 1:
            idx = sel[0]
            text = self.listbox.get(idx)
            self.listbox.delete(idx)
            self.listbox.insert(idx + 1, text)
            self.listbox.selection_set(idx + 1)

    def _update_start_btn(self):
        count = self.listbox.size()
        if 2 <= count <= 6:
            self.start_btn.config(state=tk.NORMAL)
        else:
            self.start_btn.config(state=tk.DISABLED)

    def _start_game(self):
        """Create Agent instances and launch the game runner."""
        agent_names = [self.listbox.get(i) for i in range(self.listbox.size())]

        api_key = self.config["api_key"]
        agents_cfg = self.config["agents"]
        agents = []
        for name in agent_names:
            # Find the provider config — strip number suffix
            for provider in self.available:
                if name == provider or name.startswith(provider + " "):
                    model = agents_cfg[provider]
                    agent = create_agent(name, api_key, model)
                    agents.append(agent)
                    break

        self.root.destroy()

        # Run the game (blocks until game over)
        runner = GameRunner(agents)
        runner.run()


def main():
    root = tk.Tk()
    AgentSetupWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
