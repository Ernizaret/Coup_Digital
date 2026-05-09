"""Tests for bluff/challenge tracking in AI_game.game_runner.GameRunner."""

import unittest

from src.controller import GameController, State
from AI_game.game_runner import GameRunner


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


if __name__ == "__main__":
    unittest.main()
