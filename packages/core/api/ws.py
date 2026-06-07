import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from core.db.sqlite import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


class _ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def broadcast(self, data: dict[str, Any]) -> None:
        if not self._connections:
            return
        message = json.dumps(data)
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


manager = _ConnectionManager()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        await manager.disconnect(websocket)


@router.get("/events/recent")
async def recent_events(
    limit: int = 50,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Return the most recent pipeline_run events from SQLite for Live Feed history."""
    db.row_factory = aiosqlite.Row
    cur = await db.execute(
        """
        SELECT pr.id AS run_id, pr.repo, pr.workflow, pr.status, pr.triggered_at,
               fe.id AS event_id, fe.job, fe.step
        FROM pipeline_runs pr
        LEFT JOIN failure_events fe ON fe.run_id = pr.id
        ORDER BY pr.triggered_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = await cur.fetchall()
    events = []
    for r in rows:
        events.append(
            {
                "type": "pipeline_started" if r["status"] == "running" else "signature_extracted",
                "timestamp": r["triggered_at"],
                "run_id": r["run_id"],
                "payload": {
                    "repo": r["repo"],
                    "workflow": r["workflow"],
                    "status": r["status"],
                    "job": r["job"],
                },
            }
        )
    return events


async def broadcast_event(
    event_type: str,
    run_id: str,
    payload: dict[str, Any],
) -> None:
    try:
        await manager.broadcast(
            {
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "payload": payload,
            }
        )
    except Exception as exc:
        logger.error("Broadcast failed: %s", exc)
