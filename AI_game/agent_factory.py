"""Shared helper for creating Agent instances from configuration.

Used by both the Tkinter setup UI and the headless bulk runner so that
agent-creation logic lives in one place without requiring Tkinter.
"""

from AI_game.config import load_config, get_available_agents, get_prompt_mode
from AI_game.agents import create_agent


def create_agents_from_names(agent_names, config):
    """Create a list of Agent instances from display names and config.

    Args:
        agent_names: list of display names, e.g. ["Claude", "Claude 2", "Gemini"].
            Number suffixes (e.g. "Claude 2") are stripped to find the provider key
            in the config.
        config: parsed ai_config.json dict with "api_key" and "agents" keys.

    Returns:
        list of Agent instances in the same order as agent_names.

    Raises:
        ValueError: if an agent name does not match any configured provider.
    """
    api_key = config["api_key"]
    agents_cfg = config["agents"]
    available = get_available_agents(config)
    agents = []

    for name in agent_names:
        matched = False
        for provider in available:
            if name == provider or name.startswith(provider + " "):
                model = agents_cfg[provider]
                agent = create_agent(name, api_key, model)
                agents.append(agent)
                matched = True
                break
        if not matched:
            raise ValueError(
                f"Unknown agent '{name}'. "
                f"Available providers: {', '.join(available)}"
            )

    return agents


def build_agent_names(provider_names):
    """Convert a list of provider names into display names with numbering.

    Duplicate providers get a numeric suffix starting from the second
    occurrence, e.g. ["Claude", "Claude", "Gemini"] -> ["Claude", "Claude 2", "Gemini"].

    Args:
        provider_names: list of provider names (must match keys in ai_config.json "agents").

    Returns:
        list of display names with numbering applied.
    """
    counts = {}
    display_names = []

    for provider in provider_names:
        counts[provider] = counts.get(provider, 0) + 1
        n = counts[provider]
        if n > 1:
            display_names.append(f"{provider} {n}")
        else:
            display_names.append(provider)

    # Second pass: if a provider appeared more than once, the first occurrence
    # should also be numbered (but the existing convention in setup_ui keeps the
    # first as bare name, second as "Name 2", etc.)  We follow that convention.
    return display_names
