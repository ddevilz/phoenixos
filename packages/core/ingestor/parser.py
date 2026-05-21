import uuid
from datetime import datetime, timezone
from typing import Any

from core.models.failure import FailureEvent


def parse_github_webhook(payload: dict[str, Any], event_type: str) -> FailureEvent | None:
    """
    Convert a GitHub Actions webhook payload to a FailureEvent.
    Returns None if the event is not a failure we handle.

    Accepts two payload shapes:
    1. Synthetic / test payloads — flat dict with run_id, job, step fields.
    2. Real GitHub workflow_run events with conclusion=failure.
    """
    # Synthetic payload: has run_id + job + step at top level
    if "run_id" in payload and "job" in payload and "step" in payload:
        ts_raw = payload.get("timestamp")
        timestamp = datetime.fromisoformat(ts_raw) if ts_raw else datetime.now(timezone.utc)
        return FailureEvent(
            id=payload.get("id", str(uuid.uuid4())),
            repo=payload["repo"],
            run_id=str(payload["run_id"]),
            workflow=payload["workflow"],
            job=payload["job"],
            step=payload["step"],
            exit_code=int(payload.get("exit_code", 1)),
            log_tail=payload.get("log_tail", ""),
            changed_files=list(payload.get("changed_files", [])),
            timestamp=timestamp,
        )

    # Real GitHub workflow_run event
    if event_type == "workflow_run":
        run = payload.get("workflow_run", {})
        if run.get("conclusion") != "failure":
            return None
        repo = payload.get("repository", {}).get("full_name", "unknown/unknown")
        raw_ts = run.get("updated_at", "")
        timestamp = (
            datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            if raw_ts
            else datetime.now(timezone.utc)
        )
        return FailureEvent(
            id=str(uuid.uuid4()),
            repo=repo,
            run_id=str(run["id"]),
            workflow=run.get("name", "unknown"),
            job="unknown",
            step="unknown",
            exit_code=1,
            log_tail="",
            changed_files=[],
            timestamp=timestamp,
        )

    return None
