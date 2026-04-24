"""Load OpenRouter API key and agent model configuration from ai_config.json."""

import json
import os

CONFIG_FILENAME = "ai_config.json"


def _find_config_path():
    """Look for ai_config.json in the project root (parent of AI_game/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    return os.path.join(project_root, CONFIG_FILENAME)


def load_config():
    """Read ai_config.json and return the parsed dict.

    Returns dict with "api_key" (str) and "agents" (dict of name -> model).
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
    if not config.get("api_key", "").strip():
        raise ValueError(
            "No OpenRouter API key found in ai_config.json.\n"
            "Set the \"api_key\" field to your OpenRouter key."
        )
    return config


def get_available_agents(config):
    """Return list of agent names from the config."""
    return list(config.get("agents", {}).keys())
