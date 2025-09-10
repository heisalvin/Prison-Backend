# app/routes/activity.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import asyncio

router = APIRouter()

_connections: List[WebSocket] = []

@router.websocket("/ws/activity")
async def websocket_activity(ws: WebSocket):
    """
    Clients connect here to receive live activity events.
    This keeps the connection alive without requiring clients to send messages.
    Broadcasts are pushed from other code via broadcast_activity().
    """
    await ws.accept()
    _connections.append(ws)
    try:
        while True:
            # Keep the connection open without blocking on client messages
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        if ws in _connections:
            _connections.remove(ws)
    except Exception:
        if ws in _connections:
            _connections.remove(ws)

async def broadcast_activity(payload: dict):
    """
    Send payload to all connected websocket clients.
    Non-blocking tolerant: removes failed connections.
    """
    for conn in list(_connections):
        try:
            await conn.send_json(payload)
        except Exception:
            try:
                _connections.remove(conn)
            except Exception:
                pass
