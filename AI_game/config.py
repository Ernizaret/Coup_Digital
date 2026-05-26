"""Load API keys and agent model configuration from ai_config.json."""

import json
import os

CONFIG_FILENAME = "ai_config.json"
VALID_PROMPT_MODES = ("heavy", "light")
DEFAULT_PROMPT_MODE = "heavy"


def _find_config_path():
    """Look for ai_config.json in the project root (parent of AI_game/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    return os.path.join(project_root, CONFIG_FILENAME)


def _has_claude_agent(config):
    """Return True if any configured agent uses a Claude model."""
    for model in config.get("agents", {}).values():
        if model.startswith("claude"):
            return True
    return False


def load_config():
    """Read ai_config.json and return the parsed dict.

    Returns dict with "api_key" (str), "anthropic_api_key" (str, optional),
    "agents" (dict of name -> model), and "prompt_mode" (str, defaults to
    "heavy").

    The "api_key" (OpenRouter) is required when any non-Claude agent is
    configured.  The "anthropic_api_key" is required when any Claude agent
    is configured (model name starts with "claude").

    Raises FileNotFoundError with a helpful message if the file is missing.
    """
    path = _find_config_path()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Copy ai_config.json.example to ai_config.json and fill in your API key."
        )
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    has_claude = _has_claude_agent(config)
    has_non_claude = any(
        not model.startswith("claude")
        for model in config.get("agents", {}).values()
    )

    # OpenRouter key is required when non-Claude agents are configured
    if has_non_claude and not config.get("api_key", "").strip():
        raise ValueError(
            "No OpenRouter API key found in ai_config.json.\n"
            "Set the \"api_key\" field to your OpenRouter key."
        )

    # Anthropic key is required when Claude agents are configured
    if has_claude and not config.get("anthropic_api_key", "").strip():
        raise ValueError(
            "No Anthropic API key found in ai_config.json.\n"
            "Set the \"anthropic_api_key\" field to your Anthropic key.\n"
            "Claude models are called directly via the Anthropic API."
        )

    # Validate / default prompt_mode
    config.setdefault("prompt_mode", DEFAULT_PROMPT_MODE)
    if config["prompt_mode"] not in VALID_PROMPT_MODES:
        raise ValueError(
            f"Invalid prompt_mode '{config['prompt_mode']}' in ai_config.json.\n"
            f"Valid values: {', '.join(VALID_PROMPT_MODES)}"
        )
    return config


def get_prompt_mode(config):
    """Return the prompt mode from config (defaults to 'heavy')."""
    return config.get("prompt_mode", DEFAULT_PROMPT_MODE)


def get_available_agents(config):
    """Return list of agent names from the config."""
    return list(config.get("agents", {}).keys())
