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
            self._write_config({
                "api_key": "",
                "agents": {"Gemini": "google/gemini-pro"},
            }, path)
            with patch("AI_game.config._find_config_path", return_value=path):
                with self.assertRaises(ValueError):
                    load_config()

    def test_whitespace_api_key_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({
                "api_key": "   ",
                "agents": {"Gemini": "google/gemini-pro"},
            }, path)
            with patch("AI_game.config._find_config_path", return_value=path):
                with self.assertRaises(ValueError):
                    load_config()

    def test_missing_anthropic_key_with_claude_agent_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({
                "api_key": "or-key",
                "agents": {"Claude": "claude-sonnet-4-20250514"},
            }, path)
            with patch("AI_game.config._find_config_path", return_value=path):
                with self.assertRaises(ValueError):
                    load_config()

    def test_no_agents_allows_empty_keys(self):
        """When no agents are configured, neither API key is required."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({"api_key": "", "agents": {}}, path)
            with patch("AI_game.config._find_config_path", return_value=path):
                config = load_config()
            self.assertEqual(config["agents"], {})

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

    def test_env_var_fallback_openrouter(self):
        """OPENROUTER_API_KEY env var fills in empty api_key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({
                "api_key": "",
                "agents": {"Gemini": "google/gemini-pro"},
            }, path)
            env = {"OPENROUTER_API_KEY": "env-or-key", "ANTHROPIC_API_KEY": ""}
            with patch("AI_game.config._find_config_path", return_value=path), \
                 patch.dict(os.environ, env, clear=False):
                config = load_config()
            self.assertEqual(config["api_key"], "env-or-key")

    def test_env_var_fallback_anthropic(self):
        """ANTHROPIC_API_KEY env var fills in empty anthropic_api_key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({
                "api_key": "or-key",
                "anthropic_api_key": "",
                "agents": {"Claude": "claude-sonnet-4-20250514"},
            }, path)
            env = {"ANTHROPIC_API_KEY": "env-ant-key", "OPENROUTER_API_KEY": ""}
            with patch("AI_game.config._find_config_path", return_value=path), \
                 patch.dict(os.environ, env, clear=False):
                config = load_config()
            self.assertEqual(config["anthropic_api_key"], "env-ant-key")

    def test_env_var_does_not_override_existing_key(self):
        """Env var should NOT replace a key that already has a value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({
                "api_key": "file-key",
                "agents": {"Gemini": "google/gemini-pro"},
            }, path)
            env = {"OPENROUTER_API_KEY": "env-or-key"}
            with patch("AI_game.config._find_config_path", return_value=path), \
                 patch.dict(os.environ, env, clear=False):
                config = load_config()
            self.assertEqual(config["api_key"], "file-key")

    def test_env_var_missing_still_raises(self):
        """If env var is also empty, validation still raises."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ai_config.json")
            self._write_config({
                "api_key": "",
                "agents": {"Gemini": "google/gemini-pro"},
            }, path)
            env = {"OPENROUTER_API_KEY": "", "ANTHROPIC_API_KEY": ""}
            with patch("AI_game.config._find_config_path", return_value=path), \
                 patch.dict(os.environ, env, clear=False):
                with self.assertRaises(ValueError):
                    load_config()


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
