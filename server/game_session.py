"""Game session manager: wraps GameRunner with WebSocket event streaming."""

import asyncio
import json
import time
import uuid
from enum import Enum

from src.controller import GameController, State
from AI_game.prompt_builder import build_prompt_sections
from AI_game.response_parser import parse_response, ParseError
from AI_game.log_writer import LogWriter
from AI_game.stats import record_game
from AI_game.game_runner import smart_default, MAX_RETRIES, QUERY_TIMEOUT
from scripts.build_site_data import build_all


class SessionMode(str, Enum):
    BOT_VS_BOT = "bot_vs_bot"
    HUMAN_VS_BOT = "human_vs_bot"


class SessionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


class GameSession:
    """Manages a single game session with WebSocket event broadcasting."""

    def __init__(self, game_id, agents, mode, seed=None,
                 survey_interval=0, preset_name=None):
        self.game_id = game_id
        self.agents = agents
        self.mode = mode
        self.seed = seed
        self.survey_interval = survey_interval
        self.preset_name = preset_name
        self.status = SessionStatus.PENDING
        self.result = None
        self.error_message = None

        # WebSocket connections
        self.websockets = set()

        # Human player input queue (for human mode)
        self.human_input_queue = asyncio.Queue()
        self.human_player_name = None  # set during setup for human mode

        # Game state for streaming
        self.controller = None
        self.event_log = []
        self._log_cursor = 0
        self._turn_number = 0
        self._round_number = 0
        self._round_turn_count = 0
        self._points_data = {}

        # Track which cards each player has lost (for revealed card display)
        # We reconstruct this from the controller's log entries.
        self._revealed_per_player = {}  # player_name -> list of card strings

    async def add_websocket(self, ws):
        """Register a WebSocket connection for this session."""
        self.websockets.add(ws)

    async def remove_websocket(self, ws):
        """Unregister a WebSocket connection."""
        self.websockets.discard(ws)

    async def broadcast(self, message):
        """Send a JSON message to all connected WebSocket clients."""
        if not self.websockets:
            return
        data = json.dumps(message)
        disconnected = set()
        for ws in self.websockets:
            try:
                await ws.send_text(data)
            except Exception:
                disconnected.add(ws)
        self.websockets -= disconnected

    async def run_game(self):
        """Run the full game asynchronously, streaming events via WebSocket."""
        try:
            self.status = SessionStatus.RUNNING
            await self.broadcast({
                "type": "game_started",
                "game_id": self.game_id,
                "mode": self.mode,
            })

            self.controller = GameController(seed=self.seed)
            log_writer = LogWriter()

            # Setup game
            self.controller.handle_input(str(len(self.agents)))
            for agent in self.agents:
                self.controller.handle_input(agent.name)
            self._consume_log_sync()

            # Reset per-game counters
            for agent in self.agents:
                agent.bluffs = 0
                agent.bluffs_caught = 0
                agent.challenges_issued = 0
                agent.challenges_correct = 0
                agent.card_guesses_total = 0
                agent.card_guesses_correct = 0
                agent.cards_guessed = 0
                agent.cards_guessed_correct = 0
                agent.turn_eliminated = 0

            # Capture the actual seed
            self.seed = self.controller.game.seed

            # Setup log writer
            log_writer.game_started(self.controller, "heavy", seed=self.seed)
            log_writer.set_agents(self.agents)

            # Broadcast initial game state
            await self._broadcast_game_state()

            # Run the game loop
            result = await self._game_loop(log_writer)

            if result:
                self.result = result
                self.status = SessionStatus.FINISHED

                # Record stats
                record_game(self.agents, result["winner_agent_obj"],
                            seed=self.seed, points_data=self._points_data)

                # Write log
                log_writer.game_over(result["winner_name"],
                                     winner_agent=result["winner_agent_obj"])

                # Regenerate website data JSON files
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None, build_all, True  # quiet=True
                    )
                except Exception:
                    pass  # Non-critical: site data will be stale until next rebuild

                await self.broadcast({
                    "type": "game_over",
                    "winner_name": result["winner_name"],
                    "winner_model": result["winner_model"],
                    "seed": self.seed,
                })
            else:
                self.status = SessionStatus.ERROR
                self.error_message = "Game ended abnormally"
                await self.broadcast({
                    "type": "error",
                    "message": "Game ended abnormally",
                })

        except Exception as e:
            self.status = SessionStatus.ERROR
            self.error_message = str(e)
            await self.broadcast({
                "type": "error",
                "message": f"Game error: {str(e)}",
            })

    async def _game_loop(self, log_writer):
        """Main game loop -- query agents until game over."""
        agent_map = {agent.name: agent for agent in self.agents}
        player_agents = {}
        for p in self.controller.game.players:
            if p.name in agent_map:
                player_agents[p] = agent_map[p.name]

        last_turn_player = None

        while self.controller.state != State.GAME_OVER:
            player = self.controller.get_active_player()
            if player is None:
                break

            # Track turn transitions
            if (self.controller.state == State.CHOOSE_ACTION
                    and player != last_turn_player):
                self._turn_number += 1
                self._round_turn_count += 1

                living_count = len(
                    self.controller.game.get_living_players()
                )
                if (self._round_turn_count >= living_count
                        and self._turn_number > living_count):
                    self._round_number += 1
                    self._round_turn_count = 0

                self.event_log.append({
                    "type": "event",
                    "text": "",
                    "turn_boundary": True,
                    "turn_player": player.name,
                    "turn_number": self._turn_number,
                })

                log_writer.turn_start(player.name, self._turn_number)

                await self.broadcast({
                    "type": "turn_start",
                    "player": player.name,
                    "turn_number": self._turn_number,
                })

                last_turn_player = player

            agent = agent_map.get(player.name)
            if agent is None:
                break

            message, options = self.controller.get_prompt(player)
            if options is None:
                break

            # Check if this is a human player's turn
            is_human = (self.mode == SessionMode.HUMAN_VS_BOT
                        and player.name == self.human_player_name)

            if is_human:
                action, speech = await self._get_human_input(
                    player, message, options
                )
            else:
                action, speech = await self._query_agent_async(
                    agent, player, options
                )

            # Broadcast the agent/human response
            await self.broadcast({
                "type": "agent_response",
                "player": player.name,
                "model": agent.model if agent else "human",
                "action": action,
                "speech": speech or "(silent)",
                "state": self.controller.state.name,
            })

            if speech:
                self.event_log.append({
                    "type": "speech",
                    "player": player.name,
                    "text": speech,
                })
                self.controller.send_chat(player.name, speech)
                log_writer.agent_response(player.name, speech, action)
            else:
                log_writer.agent_response(player.name, "(silent)", action)

            # Execute the action
            state_before = self.controller.state
            log_cursor_before = len(self.controller.log)
            acting_player_before = self.controller.current_player
            blocker_before = self.controller.blocker

            self.controller.handle_input(action, player)

            # Track bluff/challenge events (simplified)
            self._track_bluff_challenge(
                state_before, action, player, agent,
                log_cursor_before, player_agents,
                acting_player_before, blocker_before,
            )

            # Detect eliminated players
            for p, ag in player_agents.items():
                if len(p.influence) == 0 and ag.turn_eliminated == 0:
                    ag.turn_eliminated = self._turn_number

            # Consume new log entries and broadcast
            await self._consume_and_broadcast_log(log_writer)

            # Broadcast state after each action
            await self._broadcast_game_state()

            # Snapshot points after each full turn
            if self.controller.state == State.CHOOSE_ACTION:
                self._snapshot_points()

            # Small yield to allow WebSocket messages to be sent
            await asyncio.sleep(0.05)

        # Game over
        if self.controller.state == State.GAME_OVER:
            self._snapshot_points()
            await self._consume_and_broadcast_log(log_writer)
            winner = self.controller.game.get_living_players()[0]
            winner_agent = agent_map[winner.name]
            return {
                "winner_name": winner.name,
                "winner_model": winner_agent.model,
                "winner_agent_obj": winner_agent,
                "agents": self.agents,
                "seed": self.seed,
            }
        return None

    async def _query_agent_async(self, agent, player, options):
        """Query an AI agent asynchronously (runs blocking call in executor)."""
        loop = asyncio.get_event_loop()

        prompt_sections = build_prompt_sections(
            self.controller, player, self.event_log,
            history_depth=agent.history_depth,
            rules_summary=agent.rules_summary,
            strategy_guide=agent.strategy_guide,
        )

        deadline = time.monotonic() + QUERY_TIMEOUT
        timed_out = False

        for attempt in range(1, MAX_RETRIES + 1):
            if time.monotonic() >= deadline:
                timed_out = True
                break

            try:
                raw = await loop.run_in_executor(
                    None, agent.query_structured, prompt_sections
                )
                result = parse_response(raw, options)
                return result["action"], result["speech"]
            except ParseError:
                pass
            except Exception:
                pass

            if time.monotonic() >= deadline:
                timed_out = True
                break

        # Fall back to a safe default
        fallback = smart_default(
            self.controller.state, options, self.controller,
        )
        return fallback, ""

    async def _get_human_input(self, player, message, options):
        """Wait for human input via WebSocket."""
        # Send prompt to human player
        await self.broadcast({
            "type": "awaiting_human_input",
            "player": player.name,
            "message": message,
            "options": options,
            "state": self.controller.state.name,
        })

        # Wait for input from human (with timeout)
        try:
            input_data = await asyncio.wait_for(
                self.human_input_queue.get(), timeout=300
            )
            action = input_data.get("action", options[0])
            speech = input_data.get("speech", "")

            # Validate the action
            if action not in options:
                action = options[0]

            return action, speech
        except asyncio.TimeoutError:
            fallback = smart_default(
                self.controller.state, options, self.controller,
            )
            return fallback, ""

    def _consume_log_sync(self):
        """Consume controller log entries into event_log (synchronous)."""
        while self._log_cursor < len(self.controller.log):
            text = self.controller.log[self._log_cursor]
            self.event_log.append({"type": "event", "text": text})
            self._log_cursor += 1

    async def _consume_and_broadcast_log(self, log_writer):
        """Consume new controller log entries and broadcast them."""
        while self._log_cursor < len(self.controller.log):
            text = self.controller.log[self._log_cursor]
            self.event_log.append({"type": "event", "text": text})
            log_writer.game_event(text)

            await self.broadcast({
                "type": "event",
                "text": text,
            })
            self._log_cursor += 1

    def _compute_revealed_per_player(self):
        """Compute which cards each player has revealed.

        Scans controller log entries for "<name> loses <Card>." patterns
        and rebuilds the per-player revealed cards mapping.
        """
        import re
        revealed = {}
        # Build a set of known player names for reliable matching
        player_names = set()
        if self.controller and self.controller.game:
            player_names = {p.name for p in self.controller.game.players}

        for entry in self.controller.log:
            # Match pattern: "<player> loses <card>."
            for name in player_names:
                prefix = f"{name} loses "
                if entry.startswith(prefix) and entry.endswith("."):
                    card = entry[len(prefix):-1]  # strip trailing period
                    if card:
                        if name not in revealed:
                            revealed[name] = []
                        revealed[name].append(card)
                    break

        self._revealed_per_player = revealed

    async def _broadcast_game_state(self):
        """Broadcast current game state to all WebSocket clients."""
        if not self.controller or not self.controller.game:
            return

        # Compute per-player revealed cards from log
        self._compute_revealed_per_player()

        players = []
        for p in self.controller.game.players:
            revealed = self._revealed_per_player.get(p.name, [])

            player_data = {
                "name": p.name,
                "coins": p.coins,
                "influence_count": len(p.influence),
                "alive": p.is_alive(),
                "revealed": revealed,
            }

            # For human player in human mode, include their hand
            if (self.mode == SessionMode.HUMAN_VS_BOT
                    and p.name == self.human_player_name):
                player_data["hand"] = [str(c) for c in p.influence]

            players.append(player_data)

        await self.broadcast({
            "type": "game_state",
            "players": players,
            "state": self.controller.state.name,
            "turn_number": self._turn_number,
            "seed": self.seed,
        })

    def _snapshot_points(self):
        """Record current points for all players after a turn resolves."""
        for player in self.controller.game.players:
            influence_count = len(player.influence)
            if influence_count == 0:
                points = 0
            else:
                points = player.coins + 7 * influence_count
            if player.name not in self._points_data:
                self._points_data[player.name] = []
            self._points_data[player.name].append(points)

    def _track_bluff_challenge(self, state_before, action, player, agent,
                               log_cursor_before, player_agents,
                               acting_player_before, blocker_before):
        """Track bluff and challenge events (mirrors GameRunner logic)."""
        ctrl = self.controller
        if acting_player_before is None:
            acting_player_before = ctrl.current_player
        if blocker_before is None:
            blocker_before = ctrl.blocker

        # Action bluff detection
        if state_before == State.CHOOSE_ACTION and ctrl.pending_claimed_card:
            acting = acting_player_before
            if not acting.has_influence(ctrl.pending_claimed_card):
                acting_agent = player_agents.get(acting)
                if acting_agent:
                    acting_agent.bluffs += 1

        # Block bluff detection
        if (state_before == State.BLOCK_QUERY
                and action != "Don't block"
                and ctrl.blocker is not None
                and ctrl.block_claimed_card is not None):
            blocker = ctrl.blocker
            if not blocker.has_influence(ctrl.block_claimed_card):
                blocker_agent = player_agents.get(blocker)
                if blocker_agent:
                    blocker_agent.bluffs += 1

        # Challenge issued detection
        if (state_before in (State.CHALLENGE_QUERY,
                             State.CHALLENGE_BLOCK_QUERY)
                and action == "Yes"):
            if agent:
                agent.challenges_issued += 1

        # Challenge outcome detection
        new_logs = ctrl.log[log_cursor_before:]
        for entry in new_logs:
            if "Challenge succeeds!" in entry:
                acting_agent = player_agents.get(acting_player_before)
                if acting_agent:
                    acting_agent.bluffs_caught += 1
                if (state_before in (State.CHALLENGE_QUERY,
                                     State.CHALLENGE_BLOCK_QUERY)
                        and action == "Yes" and agent):
                    agent.challenges_correct += 1

            if "Block fails!" in entry:
                blocker_agent = (player_agents.get(blocker_before)
                                 if blocker_before else None)
                if blocker_agent:
                    blocker_agent.bluffs_caught += 1
                if (state_before == State.CHALLENGE_BLOCK_QUERY
                        and action == "Yes" and agent):
                    agent.challenges_correct += 1

    def get_status(self):
        """Return current session status as a dict."""
        result = {
            "game_id": self.game_id,
            "mode": self.mode,
            "status": self.status,
            "turn_number": self._turn_number,
            "seed": self.seed,
        }
        if self.result:
            result["winner_name"] = self.result["winner_name"]
            result["winner_model"] = self.result["winner_model"]
        if self.error_message:
            result["error"] = self.error_message

        if self.controller and self.controller.game:
            result["players"] = [
                {
                    "name": p.name,
                    "coins": p.coins,
                    "influence_count": len(p.influence),
                    "alive": p.is_alive(),
                }
                for p in self.controller.game.players
            ]
        return result


class SessionManager:
    """Manages all active game sessions."""

    def __init__(self):
        self.sessions = {}

    def create_session(self, agents, mode, seed=None,
                       survey_interval=0, preset_name=None):
        """Create a new game session and return its ID."""
        game_id = str(uuid.uuid4())[:8]
        session = GameSession(
            game_id=game_id,
            agents=agents,
            mode=mode,
            seed=seed,
            survey_interval=survey_interval,
            preset_name=preset_name,
        )
        self.sessions[game_id] = session
        return game_id

    def get_session(self, game_id):
        """Get a session by ID, or None if not found."""
        return self.sessions.get(game_id)

    def remove_session(self, game_id):
        """Remove a completed session."""
        self.sessions.pop(game_id, None)
