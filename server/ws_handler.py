"""WebSocket connection handler for game streaming."""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.routes_game import session_manager

router = APIRouter()


@router.websocket("/ws/game/{game_id}")
async def game_websocket(websocket: WebSocket, game_id: str):
    """WebSocket endpoint for real-time game streaming.

    Clients connect to receive game events (turn_start, agent_response,
    event, game_state, game_over).

    For human-vs-bot mode, the client sends JSON messages with:
        {"type": "human_action", "action": "...", "speech": "..."}
    """
    session = session_manager.get_session(game_id)
    if not session:
        await websocket.close(code=4004, reason="Game not found")
        return

    await websocket.accept()
    await session.add_websocket(websocket)

    # Send current game status on connect
    try:
        status = session.get_status()
        await websocket.send_text(json.dumps({
            "type": "connected",
            "game_id": game_id,
            **status,
        }))
    except Exception:
        pass

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON",
                }))
                continue

            msg_type = msg.get("type")

            if msg_type == "human_action":
                # Human player sending their action choice
                if session.human_player_name:
                    await session.human_input_queue.put({
                        "action": msg.get("action", ""),
                        "speech": msg.get("speech", ""),
                    })
                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "This is not a human-player game",
                    }))

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "get_status":
                status = session.get_status()
                await websocket.send_text(json.dumps({
                    "type": "status",
                    **status,
                }))

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await session.remove_websocket(websocket)
