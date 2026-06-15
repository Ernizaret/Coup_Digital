"""FastAPI application: serves website static files and game API.

Run from the project root:
    uvicorn server.app:app --reload
    # or
    python -m server.app
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path BEFORE other imports so that
# AI_game.*, src.*, and scripts.* can be resolved.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from server.routes_game import router as game_router
from server.ws_handler import router as ws_router

WEBSITE_DIR = PROJECT_ROOT / "website"

app = FastAPI(
    title="AI Coup Arena",
    description="Play Coup against AI models or watch bot-vs-bot matches",
    version="1.0.0",
)

# CORS -- allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes and WebSocket handler
app.include_router(game_router)
app.include_router(ws_router)

# Serve AI_game/logs and AI_game/review directories for game log viewer
AI_GAME_DIR = PROJECT_ROOT / "AI_game"
if (AI_GAME_DIR / "logs").exists():
    app.mount(
        "/AI_game/logs",
        StaticFiles(directory=str(AI_GAME_DIR / "logs")),
        name="game_logs",
    )
if (AI_GAME_DIR / "review").exists():
    app.mount(
        "/AI_game/review",
        StaticFiles(directory=str(AI_GAME_DIR / "review")),
        name="game_reviews",
    )

# Serve CSV downloads
@app.get("/AI_game/winrates.csv")
async def serve_winrates_csv():
    return FileResponse(str(AI_GAME_DIR / "winrates.csv"))


@app.get("/AI_game/game_log_3.csv")
async def serve_game_log_csv():
    return FileResponse(str(AI_GAME_DIR / "game_log_3.csv"))


@app.get("/AI_game/points.csv")
async def serve_points_csv():
    return FileResponse(str(AI_GAME_DIR / "points.csv"))

# Serve website static files (CSS, JS, data)
app.mount(
    "/css",
    StaticFiles(directory=str(WEBSITE_DIR / "css")),
    name="css",
)
app.mount(
    "/js",
    StaticFiles(directory=str(WEBSITE_DIR / "js")),
    name="js",
)
app.mount(
    "/data",
    StaticFiles(directory=str(WEBSITE_DIR / "data")),
    name="data",
)


# HTML page routes
@app.get("/")
async def index():
    return FileResponse(str(WEBSITE_DIR / "index.html"))


@app.get("/index.html")
async def index_html():
    return FileResponse(str(WEBSITE_DIR / "index.html"))


@app.get("/stats.html")
async def stats_html():
    return FileResponse(str(WEBSITE_DIR / "stats.html"))


@app.get("/logs.html")
async def logs_html():
    return FileResponse(str(WEBSITE_DIR / "logs.html"))


@app.get("/play.html")
async def play_html():
    return FileResponse(str(WEBSITE_DIR / "play.html"))


@app.on_event("startup")
async def startup_event():
    """Run on server startup."""
    print(f"AI Coup Arena server starting...")
    print(f"Website directory: {WEBSITE_DIR}")
    print(f"AI game directory: {AI_GAME_DIR}")
    print(f"Open http://localhost:8000 in your browser")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=True,
    )
