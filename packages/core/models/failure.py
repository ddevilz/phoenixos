from __future__ import annotations

from datetime import datetime
from typing import Literal

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


class FailureSignatureExtract(BaseModel):
    """Trimmed model for gpt-4o-mini structured output — only fields the LLM fills."""
    summary: str
    category: Literal["test_failure", "build_error", "contract_violation", "flaky"]
    affected_component: str


class FailureSignature(BaseModel):
    id: str
    summary: str
    category: Literal["test_failure", "build_error", "contract_violation", "flaky"]
    affected_component: str
    embedding: list[float]   # 1536-dim — empty [] until T06 fills it
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int


class Fix(BaseModel):
    id: str
    commit_sha: str
    author_type: str  # "human" | "ai"
    description: str
    timestamp: datetime
    suppressed_by: str | None = None  # ID of the Fix this suppresses
