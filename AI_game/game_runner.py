"""Core orchestration loop: drives GameController with AI agents."""

from src.controller import GameController, State
from AI_game.prompt_builder import build_prompt
from AI_game.response_parser import parse_response, ParseError
from AI_game.console_output import ConsoleOutput

MAX_RETRIES = 3


class GameRunner:
    """Runs a complete Coup game with AI agents."""

    def __init__(self, agents):
        """Initialize with a list of Agent instances in turn order.

        Args:
            agents: list of Agent instances (2-6 agents)
        """
        self.agents = agents
        self.controller = GameController()
        self.output = ConsoleOutput()
        self.event_log = []       # list of {"type": "event"/"speech", ...}
        self._log_cursor = 0      # tracks how far we've consumed controller.log
        self._turn_number = 0

    def run(self):
        """Run the full game from setup to game over."""
        self._setup_game()
        self.output.game_started(self.controller)
        self._game_loop()

    def _setup_game(self):
        """Programmatically feed setup inputs to bypass the UI setup states."""
        # Step 1: Set player count
        self.controller.handle_input(str(len(self.agents)))

        # Step 2: Set each player name
        for agent in self.agents:
            self.controller.handle_input(agent.name)

        self._consume_log()

    def _build_agent_map(self):
        """Map player names to Agent instances."""
        return {agent.name: agent for agent in self.agents}

    def _game_loop(self):
        """Main game loop — query agents until game over."""
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
                self.output.turn_start(player.name, self._turn_number)
                last_turn_player = player

            agent = agent_map.get(player.name)
            if agent is None:
                break

            message, options = self.controller.get_prompt(player)

            if options is None:
                # Text entry state — shouldn't happen after setup
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
            else:
                self.output.agent_response(player.name, "(silent)", action)

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

    def _query_agent(self, agent, player, options):
        """Build prompt, query agent, parse response. Retry on failure.

        Returns (action, speech) tuple.
        """
        prompt = build_prompt(self.controller, player, agent, self.event_log)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self.output.agent_thinking(agent.name)
                raw = agent.query(prompt)
                self.output.agent_done()

                result = parse_response(raw, options)

                # Store private thought if provided
                private = result.get("private_thought", "")
                if private:
                    agent.add_thought(private)

                return result["action"], result["speech"]

            except ParseError as e:
                self.output.agent_done()
                self.output.agent_error(agent.name, attempt, str(e))
            except Exception as e:
                self.output.agent_done()
                self.output.agent_error(agent.name, attempt, f"API error: {e}")

        # All retries exhausted — fall back to first valid option
        fallback = options[0]
        self.output.agent_fallback(agent.name, fallback)
        return fallback, ""

    def _consume_log(self):
        """Transfer new controller log entries into event_log and print them."""
        while self._log_cursor < len(self.controller.log):
            text = self.controller.log[self._log_cursor]
            self.event_log.append({"type": "event", "text": text})
            self.output.game_event(text)
            self._log_cursor += 1
