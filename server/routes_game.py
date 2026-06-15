"""Game API routes: setup, start, status."""

import asyncio
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from AI_game.config import load_config, get_available_agents
from AI_game.agent_factory import create_agents_from_names, build_agent_names
from AI_game.agents import create_agent
from server.game_session import SessionManager, SessionMode

router = APIRouter(prefix="/api")

# Global session manager
session_manager = SessionManager()


class BotMatchRequest(BaseModel):
    """Request body for starting a bot-vs-bot match."""
    agents: list[str] = Field(
        ..., min_length=2, max_length=6,
        description="List of agent provider names (e.g. ['Claude', 'Gemini'])"
    )
    game_count: int = Field(default=1, ge=1, le=99)
    seed: Optional[int] = None
    shuffle_order: bool = False
    survey_interval: int = Field(default=0, ge=0, le=99)
    history_depths: Optional[list[int]] = None
    rules_summaries: Optional[list[bool]] = None
    strategy_guides: Optional[list[bool]] = None


class HumanMatchRequest(BaseModel):
    """Request body for starting a human-vs-bots match."""
    opponents: list[str] = Field(
        ..., min_length=1, max_length=5,
        description="List of opponent provider names"
    )
    player_position: int = Field(
        default=0, ge=0,
        description="Human player's seat position (0-indexed)"
    )
    history_depths: Optional[list[int]] = None
    rules_summaries: Optional[list[bool]] = None
    strategy_guides: Optional[list[bool]] = None
    seed: Optional[int] = None


def _load_config_with_env():
    """Load config with environment variable fallbacks for API keys."""
    try:
        config = load_config()
    except FileNotFoundError:
        config = {
            "agents": {},
            "prompt_mode": "heavy",
        }

    # Environment variable fallbacks
    if not config.get("api_key"):
        config["api_key"] = os.environ.get("OPENROUTER_API_KEY", "")
    if not config.get("anthropic_api_key"):
        config["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")

    return config


@router.get("/config")
async def get_config():
    """Return available models/agents without exposing API keys."""
    try:
        config = _load_config_with_env()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    agents = config.get("agents", {})
    available = []
    for name, model in agents.items():
        available.append({
            "name": name,
            "model": model,
        })

    return {
        "agents": available,
        "prompt_mode": config.get("prompt_mode", "heavy"),
    }


@router.post("/game/bot-match")
async def start_bot_match(req: BotMatchRequest):
    """Start a bot-vs-bot game and return the game_id."""
    try:
        config = _load_config_with_env()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config error: {str(e)}")

    try:
        # Build display names with numbering
        display_names = build_agent_names(req.agents)

        agents = create_agents_from_names(
            display_names, config,
            history_depths=req.history_depths,
            rules_summaries=req.rules_summaries,
            strategy_guides=req.strategy_guides,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent creation error: {str(e)}")

    game_id = session_manager.create_session(
        agents=agents,
        mode=SessionMode.BOT_VS_BOT,
        seed=req.seed,
        survey_interval=req.survey_interval,
    )

    # Start the game in the background
    session = session_manager.get_session(game_id)
    asyncio.create_task(session.run_game())

    return {
        "game_id": game_id,
        "players": [
            {"name": a.name, "model": a.model}
            for a in agents
        ],
    }


@router.post("/game/human-match")
async def start_human_match(req: HumanMatchRequest):
    """Start a human-vs-bots game and return the game_id."""
    try:
        config = _load_config_with_env()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config error: {str(e)}")

    try:
        # Build opponent agent names
        opponent_names = build_agent_names(req.opponents)

        # Create opponent agents
        bot_agents = create_agents_from_names(
            opponent_names, config,
            history_depths=req.history_depths,
            rules_summaries=req.rules_summaries,
            strategy_guides=req.strategy_guides,
        )

        # Create a "human" agent placeholder -- uses a dummy agent that
        # won't actually query any API (game_session handles human input)
        human_name = "You"
        human_agent = create_agent(
            name=human_name,
            model="human",
            history_depth=0,
            rules_summary=False,
            strategy_guide=False,
            openrouter_api_key="dummy",
            anthropic_api_key="dummy",
        )

        # Insert human at the requested position
        all_agents = list(bot_agents)
        pos = min(req.player_position, len(all_agents))
        all_agents.insert(pos, human_agent)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent creation error: {str(e)}")

    game_id = session_manager.create_session(
        agents=all_agents,
        mode=SessionMode.HUMAN_VS_BOT,
        seed=req.seed,
    )

    session = session_manager.get_session(game_id)
    session.human_player_name = human_name

    # Start the game in the background
    asyncio.create_task(session.run_game())

    return {
        "game_id": game_id,
        "players": [
            {"name": a.name, "model": a.model}
            for a in all_agents
        ],
        "human_player": human_name,
    }


@router.get("/game/{game_id}/status")
async def get_game_status(game_id: str):
    """Get current game status (fallback if WebSocket drops)."""
    session = session_manager.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")
    return session.get_status()
