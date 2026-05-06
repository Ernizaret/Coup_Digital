"""Tests for AI_game.config — configuration loading and validation."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from AI_game.config import (
    load_config, get_prompt_mode, get_available_agents,
    VALID_PROMPT_MODES, DEFAULT_PROMPT_MODE,
)


class TestLoadConfig(unittest.TestCase):
    """Test load_config() with temp config files."""

    def _write_config(self, data, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_valid_config_loads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({
                "api_key": "test-key-123",
                "agents": {"Alice": "model-a"},
                "prompt_mode": "heavy",
            }, path)
            with patch("AI_game.config._find_config_path", return_value=path):
                config = load_config()
            self.assertEqual(config["api_key"], "test-key-123")
            self.assertEqual(config["prompt_mode"], "heavy")

    def test_missing_config_raises(self):
        with patch("AI_game.config._find_config_path",
                    return_value="/nonexistent/path/ai_config.json"):
            with self.assertRaises(FileNotFoundError):
                load_config()

    def test_empty_api_key_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({"api_key": "", "agents": {}}, path)
            with patch("AI_game.config._find_config_path", return_value=path):
                with self.assertRaises(ValueError):
                    load_config()

    def test_whitespace_api_key_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({"api_key": "   ", "agents": {}}, path)
            with patch("AI_game.config._find_config_path", return_value=path):
                with self.assertRaises(ValueError):
                    load_config()

    def test_prompt_mode_defaults_to_heavy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({"api_key": "key123", "agents": {}}, path)
            with patch("AI_game.config._find_config_path", return_value=path):
                config = load_config()
            self.assertEqual(config["prompt_mode"], "heavy")

    def test_invalid_prompt_mode_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({
                "api_key": "key123",
                "prompt_mode": "turbo",
            }, path)
            with patch("AI_game.config._find_config_path", return_value=path):
                with self.assertRaises(ValueError):
                    load_config()

    def test_light_prompt_mode_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({
                "api_key": "key123",
                "prompt_mode": "light",
            }, path)
            with patch("AI_game.config._find_config_path", return_value=path):
                config = load_config()
            self.assertEqual(config["prompt_mode"], "light")


class TestGetPromptMode(unittest.TestCase):
    def test_returns_mode_from_config(self):
        self.assertEqual(get_prompt_mode({"prompt_mode": "light"}), "light")

    def test_defaults_to_heavy(self):
        self.assertEqual(get_prompt_mode({}), DEFAULT_PROMPT_MODE)


class TestGetAvailableAgents(unittest.TestCase):
    def test_returns_agent_names(self):
        config = {"agents": {"Alice": "model-a", "Bob": "model-b"}}
        self.assertEqual(get_available_agents(config), ["Alice", "Bob"])

    def test_empty_agents(self):
        self.assertEqual(get_available_agents({"agents": {}}), [])

    def test_missing_agents_key(self):
        self.assertEqual(get_available_agents({}), [])


if __name__ == "__main__":
    unittest.main()
