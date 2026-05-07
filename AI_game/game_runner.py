"""Core orchestration loop: drives GameController with AI agents."""

from src.controller import GameController, State
from AI_game.prompt_builder import build_prompt_sections
from AI_game.response_parser import parse_response, ParseError
from AI_game.console_output import ConsoleOutput
from AI_game.log_writer import LogWriter
from AI_game.stats import record_game
from AI_game.presets import get_preset, apply_preset

MAX_RETRIES = 3


class GameRunner:
    """Runs a complete Coup game with AI agents."""

    def __init__(self, agents, prompt_mode="heavy", quiet=False, log=True,
                 preset_name=None, seed=None):
        """Initialize with a list of Agent instances in turn order.

        Args:
            agents: list of Agent instances (2-6 agents)
            prompt_mode: "heavy" or "light" -- kept for backward compat (unused now)
            quiet: if True, suppress play-by-play console output
            log: if True, write a markdown transcript to AI_game/logs/
            preset_name: optional preset name from presets.json to configure
                custom starting conditions (hands, coins, deck).
            seed: optional integer seed for deterministic randomness.
                If None, a random seed is generated automatically.
        """
        self.agents = agents
        self.prompt_mode = prompt_mode
        self.preset_name = preset_name
        self.seed = seed
        self.controller = GameController(seed=seed)
        self.output = ConsoleOutput(quiet=quiet)
        self.log_writer = LogWriter() if log else None
        self.event_log = []       # list of {"type": "event"/"speech", ...}
        self._log_cursor = 0      # tracks how far we've consumed controller.log
        self._turn_number = 0

    def run(self):
        """Run the full game from setup to game over.

        Returns:
            dict with game result info, or None if the game ended abnormally.
            Keys: "winner_name", "winner_model", "agents", "seed".
        """
        self._setup_game()
        if self.preset_name:
            self._apply_preset()
        # Capture the actual seed from the Game object (auto-generated if none provided)
        self.seed = self.controller.game.seed
        self.output.game_started(self.controller, self.prompt_mode,
                                 seed=self.seed)
        if self.log_writer:
            self.log_writer.game_started(self.controller, self.prompt_mode,
                                         seed=self.seed)
            self.log_writer.set_agents(self.agents)
        return self._game_loop()

    def _setup_game(self):
        """Programmatically feed setup inputs to bypass the UI setup states."""
        # Step 1: Set player count
        self.controller.handle_input(str(len(self.agents)))

        # Step 2: Set each player name
        for agent in self.agents:
            self.controller.handle_input(agent.name)

        self._consume_log()

    def _apply_preset(self):
        """Override game state with a preset's custom starting conditions.

        Loads the named preset, validates it against the current player names,
        then replaces player hands, coins, and deck composition.
        """
        preset = get_preset(self.preset_name)
        game = self.controller.game
        player_names = [p.name for p in game.players]

        # Clear the randomly-dealt hands (deal_initial_cards already ran)
        all_dealt_cards = []
        for player in game.players:
            all_dealt_cards.extend(player.influence)
            player.influence = []
            player.coins = 2  # reset to default before preset applies

        # Return dealt cards to deck so we have a full deck again
        for card in all_dealt_cards:
            game.deck.return_card(card)

        # Now apply the preset (which assigns hands, coins, and configures deck)
        apply_preset(preset, game, player_names)

        self.controller._log(f"Preset '{self.preset_name}' applied.")

    def _build_agent_map(self):
        """Map player names to Agent instances."""
        return {agent.name: agent for agent in self.agents}

    def _game_loop(self):
        """Main game loop -- query agents until game over."""
        agent_map = self._build_agent_map()
        last_turn_player = None

        while self.controller.state != State.GAME_OVER:
            player = self.controller.get_active_player()
            if player is None:
                break

            # Track turn transitions
            if (self.controller.state == State.CHOOSE_ACTION
                    and player != last_turn_player):
                self._turn_number += 1
                # Insert a turn boundary marker into event_log
                self.event_log.append({
                    "type": "event",
                    "text": "",
                    "turn_boundary": True,
                    "turn_player": player.name,
                    "turn_number": self._turn_number,
                })
                self.output.turn_start(player.name, self._turn_number)
                if self.log_writer:
                    self.log_writer.turn_start(player.name, self._turn_number)
                last_turn_player = player

            agent = agent_map.get(player.name)
            if agent is None:
                break

            message, options = self.controller.get_prompt(player)

            if options is None:
                # Text entry state -- shouldn't happen after setup
                break

            action, speech = self._query_agent(agent, player, options)

            # Record speech and send to controller chat
            if speech:
                self.event_log.append({
                    "type": "speech",
                    "player": player.name,
                    "text": speech,
                })
                self.controller.send_chat(player.name, speech)
                self.output.agent_response(player.name, speech, action)
                if self.log_writer:
                    self.log_writer.agent_response(player.name, speech, action)
            else:
                self.output.agent_response(player.name, "(silent)", action)
                if self.log_writer:
                    self.log_writer.agent_response(
                        player.name, "(silent)", action)

            # Execute the action
            self.controller.handle_input(action, player)
            self._consume_log()

            # Print game state after each full turn
            if self.controller.state == State.CHOOSE_ACTION:
                self.output.game_state_summary(self.controller)

        # Game over
        if self.controller.state == State.GAME_OVER:
            self._consume_log()
            winner = self.controller.game.get_living_players()[0]
            self.output.game_over(winner.name)
            self.output.token_usage(self.agents)
            # Record stats -- find the winning agent's model
            agent_map = self._build_agent_map()
            winner_agent = agent_map[winner.name]
            if self.log_writer:
                self.log_writer.game_over(winner.name,
                                          winner_agent=winner_agent)
            record_game(self.agents, winner_agent.model,
                        history_depth=winner_agent.history_depth,
                        seed=self.seed)
            return {
                "winner_name": winner.name,
                "winner_model": winner_agent.model,
                "agents": self.agents,
                "seed": self.seed,
            }
        return None

    def _query_agent(self, agent, player, options):
        """Build prompt, query agent, parse response. Retry on failure.

        Returns (action, speech) tuple.
        """
        prompt_sections = build_prompt_sections(
            self.controller, player, self.event_log,
            history_depth=agent.history_depth,
        )

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self.output.agent_thinking(agent.name)
                raw = agent.query_structured(prompt_sections)
                self.output.agent_done()

                result = parse_response(raw, options)

                return result["action"], result["speech"]

            except ParseError as e:
                self.output.agent_done()
                self.output.agent_error(agent.name, attempt, str(e))
            except Exception as e:
                self.output.agent_done()
                self.output.agent_error(agent.name, attempt, f"API error: {e}")

        # All retries exhausted -- fall back to first valid option
        fallback = options[0]
        self.output.agent_fallback(agent.name, fallback)
        return fallback, ""

    def _consume_log(self):
        """Transfer new controller log entries into event_log and print them."""
        while self._log_cursor < len(self.controller.log):
            text = self.controller.log[self._log_cursor]
            self.event_log.append({"type": "event", "text": text})
            self.output.game_event(text)
            if self.log_writer:
                self.log_writer.game_event(text)
            self._log_cursor += 1
