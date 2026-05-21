from typing import Annotated, Any

import aiosqlite
from fastapi import APIRouter, Depends, Header, Request

from core.db.sqlite import get_db
from core.ingestor.parser import parse_github_webhook
from core.models.failure import FailureEvent

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/github")
async def github_webhook(
    request: Request,
    db: Annotated[aiosqlite.Connection, Depends(get_db)],
    x_github_event: str = Header(default="push"),
) -> dict[str, Any]:
    payload = await request.json()
    event = parse_github_webhook(payload, x_github_event)

    if event is None:
        return {"status": "ignored"}

    await _store_event(db, event)
    return {"status": "accepted", "event_id": event.id}


async def _store_event(db: aiosqlite.Connection, event: FailureEvent) -> None:
    await db.execute(
        """
        INSERT OR IGNORE INTO pipeline_runs (id, repo, workflow, status, triggered_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (event.run_id, event.repo, event.workflow, "failure", event.timestamp.isoformat()),
    )
    await db.execute(
        """
        INSERT OR IGNORE INTO failure_events
            (id, run_id, job, step, exit_code, log_tail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            event.run_id,
            event.job,
            event.step,
            event.exit_code,
            event.log_tail,
            event.timestamp.isoformat(),
        ),
    )
    await db.commit()
