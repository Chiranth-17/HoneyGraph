"""Authenticated real-time alert change stream."""

from __future__ import annotations

import asyncio
import os

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.serializers import json_value

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/alerts")
async def alert_socket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[os.getenv("JWT_ALGORITHM", "HS256")])
        user = websocket.app.state.db.users.find_one({"username": payload["sub"], "active": True})
        if not user: raise ValueError("unknown user")
    except Exception:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        with websocket.app.state.db.alerts.watch([{"$match": {"operationType": "insert"}}], max_await_time_ms=100) as stream:
            while True:
                change = await asyncio.to_thread(stream.try_next)
                if change:
                    await websocket.send_json(json_value(change["fullDocument"]))
                else:
                    await asyncio.sleep(0.01)
    except WebSocketDisconnect:
        return
