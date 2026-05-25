# packages/core/api/webhooks.py
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import aiosqlite
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from core.db.sqlite import get_db
from core.models.failure import FailureEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks")


def _verify_signature(body: bytes, signature: str) -> bool:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return True
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _get_changed_files(repo: str, sha: str) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"https://api.github.com/repos/{repo}/commits/{sha}",
                headers={"Accept": "application/vnd.github+json"},
            )
            r.raise_for_status()
            return [f["filename"] for f in r.json().get("files", [])]
    except Exception:
        return []


async def _run_pipeline(event: FailureEvent) -> None:
    from core.db.neo4j import neo4j_session
    from core.embeddings.dedup import dedup
    from core.embeddings.pipeline import embed
    from core.graph.scoring import recompute_fragility
    from core.graph.writer import write
    from core.ingestor.signature import extract

    signature = await extract(event)
    if signature is None:
        return

    signature = await embed(signature)

    async with neo4j_session() as session:
        result = await dedup(signature, session)
        await write(signature, result, session)
        await recompute_fragility(session)

    logger.info(
        "signature=%s category=%s embedding_dim=%d dedup=%s matched=%s run=%s",
        signature.id,
        signature.category,
        len(signature.embedding),
        result.kind,
        result.matched_id,
        event.run_id,
    )


@router.post("/github", status_code=202)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db),
    x_hub_signature_256: str | None = Header(default=None),
):
    body = await request.body()

    if not _verify_signature(body, x_hub_signature_256 or ""):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)

    if payload.get("action") != "completed":
        return JSONResponse(status_code=200, content={"status": "ignored"})

    run = payload.get("workflow_run", {})
    if run.get("conclusion") != "failure":
        return JSONResponse(status_code=200, content={"status": "ignored"})

    repo = payload.get("repository", {}).get("full_name", "")
    sha = run.get("head_sha", "")
    changed_files = await _get_changed_files(repo, sha)

    ts_raw = (
        run.get("updated_at") or run.get("created_at") or datetime.now(timezone.utc).isoformat()
    )
    timestamp = datetime.fromisoformat(ts_raw)

    event = FailureEvent(
        id=str(uuid.uuid4()),
        repo=repo,
        run_id=str(run.get("id", "")),
        workflow=run.get("name", ""),
        job=run.get("name", ""),
        step="unknown",
        exit_code=1,
        log_tail="",
        changed_files=changed_files,
        timestamp=timestamp,
    )

    await db.execute(
        """
        INSERT OR IGNORE INTO pipeline_runs (id, repo, workflow, status, triggered_at, commit_sha)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event.run_id, event.repo, event.workflow, "failure", event.timestamp.isoformat(), sha),
    )
    await db.execute(
        """
        INSERT INTO failure_events
            (id, run_id, signature_id, job, step, exit_code, log_tail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            event.run_id,
            None,
            event.job,
            event.step,
            event.exit_code,
            event.log_tail,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await db.commit()

    background_tasks.add_task(_run_pipeline, event)
    return {"status": "accepted", "run_id": event.run_id}
