from datetime import datetime

from pydantic import BaseModel


class FailureEvent(BaseModel):
    id: str
    repo: str
    run_id: str
    workflow: str
    job: str
    step: str
    exit_code: int
    log_tail: str
    changed_files: list[str]
    timestamp: datetime


class FailureSignature(BaseModel):
    id: str
    summary: str
    category: str  # "test_failure" | "build_error" | "contract_violation" | "flaky"
    affected_component: str
    embedding: list[float]  # 1536-dim, text-embedding-3-small
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int
