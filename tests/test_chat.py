"""Tests for the chat functionality."""

import unittest
from src.controller import GameController, State


def setup_two_player_game(gc):
    """Run through setup to get a 2-player game ready for actions."""
    gc.handle_input("2")
    gc.handle_input("Alice")
    gc.handle_input("Bob")


class TestChat(unittest.TestCase):
    def test_chat_messages_initially_empty(self):
        gc = GameController()
        self.assertEqual(gc.chat_messages, [])

    def test_send_chat_appends_message(self):
        gc = GameController()
        setup_two_player_game(gc)
        gc.send_chat("Alice", "Hello!")
        self.assertEqual(gc.chat_messages, [("Alice", "Hello!")])

    def test_multiple_messages_preserve_order(self):
        gc = GameController()
        setup_two_player_game(gc)
        gc.send_chat("Alice", "Hi")
        gc.send_chat("Bob", "Hey")
        gc.send_chat("Alice", "How are you?")
        self.assertEqual(len(gc.chat_messages), 3)
        self.assertEqual(gc.chat_messages[0], ("Alice", "Hi"))
        self.assertEqual(gc.chat_messages[1], ("Bob", "Hey"))
        self.assertEqual(gc.chat_messages[2], ("Alice", "How are you?"))

    def test_chat_cleared_on_reset(self):
        gc = GameController()
        setup_two_player_game(gc)
        gc.send_chat("Alice", "Hello!")
        self.assertEqual(len(gc.chat_messages), 1)
        gc.reset()
        self.assertEqual(gc.chat_messages, [])

    def test_chat_cleared_on_new_game(self):
        gc = GameController()
        setup_two_player_game(gc)
        gc.send_chat("Alice", "GG")
        # Force game over and start new game
        gc.state = State.GAME_OVER
        gc.handle_input("New Game")
        self.assertEqual(gc.chat_messages, [])

    def test_chat_does_not_affect_game_state(self):
        gc = GameController()
        setup_two_player_game(gc)
        state_before = gc.state
        current_before = gc.current_player
        gc.send_chat("Alice", "I have a Duke")
        self.assertEqual(gc.state, state_before)
        self.assertEqual(gc.current_player, current_before)


if __name__ == "__main__":
    unittest.main()
