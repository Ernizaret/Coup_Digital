"""Load OpenRouter API key and agent model configuration from ai_config.json."""

import json
import os

from AI_game.agents import create_agent

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


def create_agents_from_config(config, agent_names):
    """Create Agent instances from a list of agent names, handling numbered suffixes.

    When the same provider name appears multiple times, the second and subsequent
    instances get numbered suffixes (e.g. "Claude", "Claude 2", "Claude 3").

    Args:
        config: dict from load_config() with "api_key" and "agents" keys.
        agent_names: list of provider names (e.g. ["Claude", "Claude", "Gemini"]).

    Returns:
        list of Agent instances in the same order.
    """
    api_key = config["api_key"]
    agents_cfg = config["agents"]
    available = list(agents_cfg.keys())

    # Count occurrences of each provider to assign numbered suffixes
    counts = {}
    agents = []
    for name in agent_names:
        # Find the matching provider
        provider = None
        for p in available:
            if name == p or name.startswith(p + " "):
                provider = p
                break
        if provider is None:
            raise ValueError(
                f"Unknown agent '{name}'. Available: {available}"
            )

        counts[provider] = counts.get(provider, 0) + 1
        n = counts[provider]
        display_name = provider if n == 1 else f"{provider} {n}"
        model = agents_cfg[provider]
        agents.append(create_agent(display_name, api_key, model))

    return agents
