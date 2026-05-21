import os
from collections.abc import AsyncGenerator

import aiosqlite

_SQL_CREATE_PIPELINE_RUNS = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id           TEXT PRIMARY KEY,
    repo         TEXT NOT NULL,
    workflow     TEXT NOT NULL,
    status       TEXT NOT NULL,
    triggered_at TEXT NOT NULL,
    completed_at TEXT,
    commit_sha   TEXT
)
"""

_SQL_CREATE_FAILURE_EVENTS = """
CREATE TABLE IF NOT EXISTS failure_events (
    id           TEXT PRIMARY KEY,
    run_id       TEXT REFERENCES pipeline_runs(id),
    signature_id TEXT,
    job          TEXT NOT NULL,
    step         TEXT NOT NULL,
    exit_code    INTEGER,
    log_tail     TEXT,
    created_at   TEXT NOT NULL
)
"""


def _get_db_path() -> str:
    return os.getenv("SQLITE_PATH", "./data/phoenix.db")


async def init_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(_SQL_CREATE_PIPELINE_RUNS)
        await db.execute(_SQL_CREATE_FAILURE_EVENTS)
        await db.commit()


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async generator for FastAPI Depends() injection."""
    async with aiosqlite.connect(_get_db_path()) as db:
        yield db
