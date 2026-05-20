"""Tests for bluff/challenge tracking and timeout logic in AI_game.game_runner."""

import unittest
from unittest.mock import patch, MagicMock

from src.controller import GameController, State
from AI_game.game_runner import GameRunner, smart_default, QUERY_TIMEOUT


class FakeAgent:
    """Minimal agent stub with bluff/challenge counters."""

    def __init__(self, name, model="test-model", history_depth=2):
        self.name = name
        self.model = model
        self.history_depth = history_depth
        self.rules_summary = False
        self.strategy_guide = False
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0
        self.query_count = 0
        self.bluffs = 0
        self.bluffs_caught = 0
        self.challenges_issued = 0
        self.challenges_correct = 0

    def query_structured(self, prompt_sections):
        return '{"action": "Income", "speech": ""}'


def _make_runner(agent_names=("Alice", "Bob")):
    """Create a GameRunner with fake agents, set up the game, return it."""
    agents = [FakeAgent(name) for name in agent_names]
    runner = GameRunner(agents, quiet=True, log=False)
    runner._setup_game()
    return runner, agents


def _get_player_agents(runner):
    """Build player -> agent map for the runner."""
    return runner._build_player_agent_map()


class TestCounterReset(unittest.TestCase):
    """Verify bluff/challenge counters are reset at game start."""

    def test_counters_reset_on_setup(self):
        agents = [FakeAgent("Alice"), FakeAgent("Bob")]
        # Set non-zero values before setup
        agents[0].bluffs = 5
        agents[0].bluffs_caught = 2
        agents[0].challenges_issued = 3
        agents[0].challenges_correct = 1
        agents[1].bluffs = 10

        runner = GameRunner(agents, quiet=True, log=False)
        runner._setup_game()

        for agent in agents:
            self.assertEqual(agent.bluffs, 0)
            self.assertEqual(agent.bluffs_caught, 0)
            self.assertEqual(agent.challenges_issued, 0)
            self.assertEqual(agent.challenges_correct, 0)


class TestActionBluffDetection(unittest.TestCase):
    """Test that action bluffs are correctly detected."""

    def test_bluff_detected_when_claiming_card_not_held(self):
        """Claiming Tax (Duke) without having Duke should count as a bluff."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        # Give Alice cards that are NOT Duke
        alice = ctrl.game.players[0]
        alice.influence = ["Captain", "Assassin"]

        agent_alice = player_agents[alice]

        # Simulate: Alice chooses Tax (claims Duke)
        state_before = State.CHOOSE_ACTION
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Tax")  # This sets pending_claimed_card = "Duke"

        runner._track_bluff_challenge_events(
            state_before, "Tax", alice, agent_alice,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_alice.bluffs, 1)

    def test_no_bluff_when_player_has_claimed_card(self):
        """Claiming Tax (Duke) while holding Duke should NOT be a bluff."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        alice.influence = ["Duke", "Assassin"]

        agent_alice = player_agents[alice]

        state_before = State.CHOOSE_ACTION
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Tax")

        runner._track_bluff_challenge_events(
            state_before, "Tax", alice, agent_alice,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_alice.bluffs, 0)

    def test_no_bluff_for_income(self):
        """Income has no claimed card and should never be a bluff."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        agent_alice = player_agents[alice]

        state_before = State.CHOOSE_ACTION
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Income")

        runner._track_bluff_challenge_events(
            state_before, "Income", alice, agent_alice,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_alice.bluffs, 0)

    def test_no_bluff_for_foreign_aid(self):
        """Foreign Aid has no claimed card and should never be a bluff."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        agent_alice = player_agents[alice]

        state_before = State.CHOOSE_ACTION
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Foreign Aid")

        runner._track_bluff_challenge_events(
            state_before, "Foreign Aid", alice, agent_alice,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_alice.bluffs, 0)

    def test_bluff_steal_without_captain(self):
        """Stealing (Captain) without Captain should be a bluff."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]
        alice.influence = ["Duke", "Assassin"]
        bob.coins = 5  # Needs coins to be stolen

        agent_alice = player_agents[alice]

        # Choose Steal action
        state_before = State.CHOOSE_ACTION
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Steal")

        runner._track_bluff_challenge_events(
            state_before, "Steal", alice, agent_alice,
            log_cursor_before, player_agents,
        )

        # Bluff is detected when action is chosen (pending_claimed_card set)
        self.assertEqual(agent_alice.bluffs, 1)

    def test_exchange_bluff_without_ambassador(self):
        """Exchange (Ambassador) without Ambassador should be a bluff."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        alice.influence = ["Duke", "Captain"]

        agent_alice = player_agents[alice]

        state_before = State.CHOOSE_ACTION
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Exchange")

        runner._track_bluff_challenge_events(
            state_before, "Exchange", alice, agent_alice,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_alice.bluffs, 1)


class TestBlockBluffDetection(unittest.TestCase):
    """Test that block bluffs are correctly detected."""

    def test_block_bluff_detected(self):
        """Blocking with a card not held should count as a bluff."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        # Alice chooses Foreign Aid -- Bob can block with Duke
        alice.influence = ["Captain", "Assassin"]
        bob.influence = ["Captain", "Assassin"]  # No Duke

        # Set up state: Alice chose Foreign Aid, now at BLOCK_QUERY
        ctrl.handle_input("Foreign Aid")
        # Controller should be at BLOCK_QUERY now
        self.assertEqual(ctrl.state, State.BLOCK_QUERY)

        agent_bob = player_agents[bob]
        state_before = State.BLOCK_QUERY
        log_cursor_before = len(ctrl.log)

        # Bob blocks with Duke (a bluff -- he doesn't have Duke)
        ctrl.handle_input("Block with Duke", bob)

        runner._track_bluff_challenge_events(
            state_before, "Block with Duke", bob, agent_bob,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_bob.bluffs, 1)

    def test_honest_block_not_counted(self):
        """Blocking with a card that IS held should NOT be a bluff."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        alice.influence = ["Captain", "Assassin"]
        bob.influence = ["Duke", "Assassin"]  # Has Duke

        ctrl.handle_input("Foreign Aid")
        self.assertEqual(ctrl.state, State.BLOCK_QUERY)

        agent_bob = player_agents[bob]
        state_before = State.BLOCK_QUERY
        log_cursor_before = len(ctrl.log)

        ctrl.handle_input("Block with Duke", bob)

        runner._track_bluff_challenge_events(
            state_before, "Block with Duke", bob, agent_bob,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_bob.bluffs, 0)

    def test_dont_block_not_counted(self):
        """Choosing 'Don't block' should not trigger any bluff."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        ctrl.handle_input("Foreign Aid")
        self.assertEqual(ctrl.state, State.BLOCK_QUERY)

        agent_bob = player_agents[bob]
        state_before = State.BLOCK_QUERY
        log_cursor_before = len(ctrl.log)

        ctrl.handle_input("Don't block", bob)

        runner._track_bluff_challenge_events(
            state_before, "Don't block", bob, agent_bob,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_bob.bluffs, 0)


class TestChallengeIssuedDetection(unittest.TestCase):
    """Test that challenges_issued increments correctly."""

    def test_challenge_issued_on_yes(self):
        """Responding 'Yes' to a challenge query should increment challenges_issued."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        # Alice claims Tax (Duke)
        ctrl.handle_input("Tax")
        self.assertEqual(ctrl.state, State.CHALLENGE_QUERY)

        agent_bob = player_agents[bob]
        state_before = State.CHALLENGE_QUERY
        log_cursor_before = len(ctrl.log)

        ctrl.handle_input("Yes", bob)

        runner._track_bluff_challenge_events(
            state_before, "Yes", bob, agent_bob,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_bob.challenges_issued, 1)

    def test_no_challenge_on_decline(self):
        """Responding 'No' should NOT increment challenges_issued."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        ctrl.handle_input("Tax")
        self.assertEqual(ctrl.state, State.CHALLENGE_QUERY)

        agent_bob = player_agents[bob]
        state_before = State.CHALLENGE_QUERY
        log_cursor_before = len(ctrl.log)

        ctrl.handle_input("No", bob)

        runner._track_bluff_challenge_events(
            state_before, "No", bob, agent_bob,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_bob.challenges_issued, 0)

    def test_challenge_issued_on_block_challenge(self):
        """Responding 'Yes' to a CHALLENGE_BLOCK_QUERY should increment challenges_issued."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        # Alice does Foreign Aid, Bob blocks with Duke
        ctrl.handle_input("Foreign Aid")
        ctrl.handle_input("Block with Duke", bob)
        self.assertEqual(ctrl.state, State.CHALLENGE_BLOCK_QUERY)

        agent_alice = player_agents[alice]
        state_before = State.CHALLENGE_BLOCK_QUERY
        log_cursor_before = len(ctrl.log)

        ctrl.handle_input("Yes", alice)

        runner._track_bluff_challenge_events(
            state_before, "Yes", alice, agent_alice,
            log_cursor_before, player_agents,
        )

        self.assertEqual(agent_alice.challenges_issued, 1)


class TestChallengeOutcomes(unittest.TestCase):
    """Test bluffs_caught and challenges_correct on challenge resolution."""

    def test_successful_action_challenge(self):
        """When a challenge succeeds, bluffs_caught and challenges_correct increment."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        # Alice doesn't have Duke -- Tax is a bluff
        alice.influence = ["Captain", "Assassin"]

        agent_alice = player_agents[alice]
        agent_bob = player_agents[bob]

        # Alice chooses Tax -- track the bluff
        state_before = State.CHOOSE_ACTION
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Tax")
        runner._track_bluff_challenge_events(
            state_before, "Tax", alice, agent_alice,
            log_cursor_before, player_agents,
        )
        self.assertEqual(agent_alice.bluffs, 1)

        # Now Bob challenges
        self.assertEqual(ctrl.state, State.CHALLENGE_QUERY)
        state_before = State.CHALLENGE_QUERY
        log_cursor_before = len(ctrl.log)

        ctrl.handle_input("Yes", bob)

        runner._track_bluff_challenge_events(
            state_before, "Yes", bob, agent_bob,
            log_cursor_before, player_agents,
        )

        # Bob's challenge was correct
        self.assertEqual(agent_bob.challenges_issued, 1)
        self.assertEqual(agent_bob.challenges_correct, 1)
        # Alice was caught bluffing
        self.assertEqual(agent_alice.bluffs_caught, 1)

    def test_failed_action_challenge(self):
        """When a challenge fails, no bluffs_caught or challenges_correct increment."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        # Alice HAS Duke -- Tax is honest
        alice.influence = ["Duke", "Assassin"]

        agent_alice = player_agents[alice]
        agent_bob = player_agents[bob]

        # Alice chooses Tax
        state_before = State.CHOOSE_ACTION
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Tax")
        runner._track_bluff_challenge_events(
            state_before, "Tax", alice, agent_alice,
            log_cursor_before, player_agents,
        )
        self.assertEqual(agent_alice.bluffs, 0)

        # Bob challenges (incorrectly)
        self.assertEqual(ctrl.state, State.CHALLENGE_QUERY)
        state_before = State.CHALLENGE_QUERY
        log_cursor_before = len(ctrl.log)

        ctrl.handle_input("Yes", bob)

        runner._track_bluff_challenge_events(
            state_before, "Yes", bob, agent_bob,
            log_cursor_before, player_agents,
        )

        # Bob's challenge was wrong
        self.assertEqual(agent_bob.challenges_issued, 1)
        self.assertEqual(agent_bob.challenges_correct, 0)
        # Alice was NOT caught bluffing
        self.assertEqual(agent_alice.bluffs_caught, 0)

    def test_successful_block_challenge(self):
        """When a block challenge succeeds, blocker's bluffs_caught increments."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        # Bob doesn't have Duke (block bluff)
        bob.influence = ["Captain", "Assassin"]

        agent_alice = player_agents[alice]
        agent_bob = player_agents[bob]

        # Alice does Foreign Aid
        ctrl.handle_input("Foreign Aid")

        # Bob blocks with Duke (bluff)
        state_before = State.BLOCK_QUERY
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Block with Duke", bob)
        runner._track_bluff_challenge_events(
            state_before, "Block with Duke", bob, agent_bob,
            log_cursor_before, player_agents,
        )
        self.assertEqual(agent_bob.bluffs, 1)

        # Alice challenges the block
        self.assertEqual(ctrl.state, State.CHALLENGE_BLOCK_QUERY)
        state_before = State.CHALLENGE_BLOCK_QUERY
        log_cursor_before = len(ctrl.log)

        ctrl.handle_input("Yes", alice)

        runner._track_bluff_challenge_events(
            state_before, "Yes", alice, agent_alice,
            log_cursor_before, player_agents,
        )

        # Alice's challenge was correct
        self.assertEqual(agent_alice.challenges_issued, 1)
        self.assertEqual(agent_alice.challenges_correct, 1)
        # Bob's bluff was caught
        self.assertEqual(agent_bob.bluffs_caught, 1)

    def test_failed_block_challenge(self):
        """When a block challenge fails, no bluffs_caught increment."""
        runner, agents = _make_runner()
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        # Bob HAS Duke (honest block)
        bob.influence = ["Duke", "Assassin"]

        agent_alice = player_agents[alice]
        agent_bob = player_agents[bob]

        # Alice does Foreign Aid
        ctrl.handle_input("Foreign Aid")

        # Bob blocks with Duke (honest)
        state_before = State.BLOCK_QUERY
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Block with Duke", bob)
        runner._track_bluff_challenge_events(
            state_before, "Block with Duke", bob, agent_bob,
            log_cursor_before, player_agents,
        )
        self.assertEqual(agent_bob.bluffs, 0)

        # Alice challenges the block (incorrectly)
        self.assertEqual(ctrl.state, State.CHALLENGE_BLOCK_QUERY)
        state_before = State.CHALLENGE_BLOCK_QUERY
        log_cursor_before = len(ctrl.log)

        ctrl.handle_input("Yes", alice)

        runner._track_bluff_challenge_events(
            state_before, "Yes", alice, agent_alice,
            log_cursor_before, player_agents,
        )

        # Alice's challenge was wrong
        self.assertEqual(agent_alice.challenges_issued, 1)
        self.assertEqual(agent_alice.challenges_correct, 0)
        # Bob was NOT caught
        self.assertEqual(agent_bob.bluffs_caught, 0)


class TestChallengeAutoLoseAttribution(unittest.TestCase):
    """Verify bluffs_caught is attributed correctly when the challenged player
    has only 1 card left and auto-loses, causing _advance_turn() to change
    current_player within the same handle_input() call (issue #45)."""

    def test_bluffs_caught_attributed_after_auto_lose(self):
        """When a 1-card player bluffs and is challenged, bluffs_caught goes
        to the correct player even though current_player changes."""
        runner, agents = _make_runner(("Alice", "Bob", "Charlie"))
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]
        charlie = ctrl.game.players[2]

        # Alice has only 1 card and it's NOT Duke -- Tax is a bluff
        alice.influence = ["Captain"]

        agent_alice = player_agents[alice]
        agent_bob = player_agents[bob]

        # Alice chooses Tax (bluff) -- snapshot state before
        state_before = State.CHOOSE_ACTION
        log_cursor_before = len(ctrl.log)
        acting_player_before = ctrl.current_player
        ctrl.handle_input("Tax")
        runner._track_bluff_challenge_events(
            state_before, "Tax", alice, agent_alice,
            log_cursor_before, player_agents,
            acting_player_before=acting_player_before,
        )
        self.assertEqual(agent_alice.bluffs, 1)

        # Bob challenges -- Alice has 1 card so she auto-loses,
        # _advance_turn() fires, changing current_player away from Alice
        self.assertEqual(ctrl.state, State.CHALLENGE_QUERY)
        state_before = State.CHALLENGE_QUERY
        log_cursor_before = len(ctrl.log)
        acting_player_before = ctrl.current_player
        blocker_before = ctrl.blocker

        ctrl.handle_input("Yes", bob)

        # current_player should have changed (advanced past eliminated Alice)
        self.assertNotEqual(ctrl.current_player, alice)

        runner._track_bluff_challenge_events(
            state_before, "Yes", bob, agent_bob,
            log_cursor_before, player_agents,
            acting_player_before=acting_player_before,
            blocker_before=blocker_before,
        )

        # Alice was caught bluffing (attributed correctly despite turn advance)
        self.assertEqual(agent_alice.bluffs_caught, 1)
        self.assertEqual(agent_bob.challenges_issued, 1)
        self.assertEqual(agent_bob.challenges_correct, 1)

    def test_block_bluffs_caught_attributed_after_auto_lose(self):
        """When a 1-card blocker bluffs a block and is challenged,
        bluffs_caught goes to the blocker even if ctrl.blocker changes."""
        runner, agents = _make_runner(("Alice", "Bob", "Charlie"))
        ctrl = runner.controller
        player_agents = _get_player_agents(runner)

        alice = ctrl.game.players[0]
        bob = ctrl.game.players[1]

        # Bob has only 1 card and it's NOT Duke -- block is a bluff
        bob.influence = ["Captain"]

        agent_alice = player_agents[alice]
        agent_bob = player_agents[bob]

        # Alice does Foreign Aid
        ctrl.handle_input("Foreign Aid")

        # Bob blocks with Duke (bluff, he only has Captain)
        state_before = State.BLOCK_QUERY
        log_cursor_before = len(ctrl.log)
        ctrl.handle_input("Block with Duke", bob)
        runner._track_bluff_challenge_events(
            state_before, "Block with Duke", bob, agent_bob,
            log_cursor_before, player_agents,
        )
        self.assertEqual(agent_bob.bluffs, 1)

        # Alice challenges the block -- Bob auto-loses his last card
        self.assertEqual(ctrl.state, State.CHALLENGE_BLOCK_QUERY)
        state_before = State.CHALLENGE_BLOCK_QUERY
        log_cursor_before = len(ctrl.log)
        acting_player_before = ctrl.current_player
        blocker_before = ctrl.blocker

        ctrl.handle_input("Yes", alice)

        runner._track_bluff_challenge_events(
            state_before, "Yes", alice, agent_alice,
            log_cursor_before, player_agents,
            acting_player_before=acting_player_before,
            blocker_before=blocker_before,
        )

        # Bob's bluff was caught (attributed correctly despite auto-lose)
        self.assertEqual(agent_bob.bluffs_caught, 1)
        self.assertEqual(agent_alice.challenges_issued, 1)
        self.assertEqual(agent_alice.challenges_correct, 1)


class TestSmartDefault(unittest.TestCase):
    """Unit tests for the smart_default() fallback picker."""

    def _make_controller(self):
        """Create a 2-player controller past setup."""
        ctrl = GameController()
        ctrl.handle_input("2")
        ctrl.handle_input("Alice")
        ctrl.handle_input("Bob")
        return ctrl

    def test_income_default_for_choose_action(self):
        ctrl = self._make_controller()
        options = ["Income", "Foreign Aid", "Tax", "Steal", "Exchange"]
        result = smart_default(State.CHOOSE_ACTION, options, ctrl)
        self.assertEqual(result, "Income")

    def test_forced_coup_when_10_coins(self):
        ctrl = self._make_controller()
        ctrl.current_player.coins = 10
        options = ["Coup"]
        result = smart_default(State.CHOOSE_ACTION, options, ctrl)
        self.assertEqual(result, "Coup")

    def test_challenge_query_defaults_no(self):
        ctrl = self._make_controller()
        result = smart_default(State.CHALLENGE_QUERY, ["Yes", "No"], ctrl)
        self.assertEqual(result, "No")

    def test_challenge_block_query_defaults_no(self):
        ctrl = self._make_controller()
        result = smart_default(
            State.CHALLENGE_BLOCK_QUERY, ["Yes", "No"], ctrl,
        )
        self.assertEqual(result, "No")

    def test_block_query_defaults_dont_block(self):
        ctrl = self._make_controller()
        options = ["Block with Duke", "Don't block"]
        result = smart_default(State.BLOCK_QUERY, options, ctrl)
        self.assertEqual(result, "Don't block")

    def test_choose_target_returns_valid_option(self):
        ctrl = self._make_controller()
        options = ["Alice", "Bob"]
        result = smart_default(State.CHOOSE_TARGET, options, ctrl)
        self.assertIn(result, options)

    def test_lose_influence_returns_valid_option(self):
        ctrl = self._make_controller()
        options = ["Duke", "Captain"]
        result = smart_default(State.LOSE_INFLUENCE, options, ctrl)
        self.assertIn(result, options)

    def test_exchange_return_first_returns_valid_option(self):
        ctrl = self._make_controller()
        options = ["Duke", "Captain", "Assassin"]
        result = smart_default(State.EXCHANGE_RETURN_FIRST, options, ctrl)
        self.assertIn(result, options)

    def test_exchange_return_second_returns_valid_option(self):
        ctrl = self._make_controller()
        options = ["Duke", "Captain"]
        result = smart_default(State.EXCHANGE_RETURN_SECOND, options, ctrl)
        self.assertIn(result, options)


class SlowFakeAgent:
    """Agent stub that simulates slow responses via mocked time."""

    def __init__(self, name, delay_per_call=0):
        self.name = name
        self.model = "test-model"
        self.history_depth = 2
        self.rules_summary = False
        self.strategy_guide = False
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0
        self.query_count = 0
        self.bluffs = 0
        self.bluffs_caught = 0
        self.challenges_issued = 0
        self.challenges_correct = 0
        self.card_guesses_total = 0
        self.card_guesses_correct = 0
        self.call_count = 0

    def query_structured(self, prompt_sections):
        self.call_count += 1
        raise Exception("Simulated slow failure")


class TestQueryAgentTimeout(unittest.TestCase):
    """Integration tests for the timeout logic in _query_agent."""

    def _make_runner_with_slow_agent(self):
        agents = [SlowFakeAgent("Alice"), SlowFakeAgent("Bob")]
        runner = GameRunner(agents, quiet=True, log=False)
        runner._setup_game()
        return runner, agents

    @patch("AI_game.game_runner.time")
    def test_timeout_triggers_smart_default(self, mock_time):
        """When the deadline is exceeded, smart_default is used."""
        runner, agents = self._make_runner_with_slow_agent()
        ctrl = runner.controller

        # Simulate: first monotonic() call returns 0 (deadline set),
        # second call (pre-attempt check) returns 0 (within budget),
        # third call (post-attempt check) returns deadline+1 (expired)
        mock_time.monotonic = MagicMock(
            side_effect=[0, 0, QUERY_TIMEOUT + 1],
        )

        player = ctrl.game.players[0]
        options = ["Income", "Foreign Aid", "Tax"]

        action, speech = runner._query_agent(agents[0], player, options)
        self.assertEqual(action, "Income")
        self.assertEqual(speech, "")
        # Only one attempt should have been made
        self.assertEqual(agents[0].call_count, 1)

    @patch("AI_game.game_runner.time")
    def test_no_retry_after_budget_exceeded(self, mock_time):
        """After a failed attempt, if budget is exceeded, no further retry."""
        runner, agents = self._make_runner_with_slow_agent()
        ctrl = runner.controller

        # First call: deadline set at 0+120=120
        # Second call: pre-attempt 1 check -> 0 (within budget)
        # Third call: post-attempt 1 check -> 121 (expired, no retry)
        mock_time.monotonic = MagicMock(
            side_effect=[0, 0, QUERY_TIMEOUT + 1],
        )

        player = ctrl.game.players[0]
        options = ["Yes", "No"]
        # Simulate a CHALLENGE_QUERY state
        ctrl.state = State.CHALLENGE_QUERY

        action, speech = runner._query_agent(agents[0], player, options)
        self.assertEqual(action, "No")  # smart_default for challenge
        self.assertEqual(agents[0].call_count, 1)

    @patch("AI_game.game_runner.time")
    def test_retries_work_within_budget(self, mock_time):
        """Normal retry behavior when within the time budget."""
        runner, agents = self._make_runner_with_slow_agent()
        ctrl = runner.controller

        # All monotonic() calls return 0 (always within budget)
        mock_time.monotonic = MagicMock(return_value=0)

        player = ctrl.game.players[0]
        options = ["Income", "Foreign Aid"]

        action, speech = runner._query_agent(agents[0], player, options)
        # All 3 retries should have been attempted
        self.assertEqual(agents[0].call_count, 3)
        # Falls back via smart_default (not timeout)
        self.assertEqual(action, "Income")

    @patch("AI_game.game_runner.time")
    def test_pre_attempt_budget_check(self, mock_time):
        """If budget is already exceeded before attempt, skip immediately."""
        runner, agents = self._make_runner_with_slow_agent()
        ctrl = runner.controller

        # First call: deadline set at 0+120=120
        # Second call: pre-attempt check -> already expired
        mock_time.monotonic = MagicMock(
            side_effect=[0, QUERY_TIMEOUT + 1],
        )

        player = ctrl.game.players[0]
        options = ["Income", "Foreign Aid"]

        action, speech = runner._query_agent(agents[0], player, options)
        # No attempt should have been made
        self.assertEqual(agents[0].call_count, 0)
        self.assertEqual(action, "Income")


if __name__ == "__main__":
    unittest.main()
