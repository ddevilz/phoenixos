import os
from collections.abc import AsyncGenerator

import aiosqlite

_DB_PATH = os.getenv("SQLITE_PATH", "./data/phoenix.db")

_CREATE_PIPELINE_RUNS = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id           TEXT PRIMARY KEY,
    repo         TEXT NOT NULL,
    workflow     TEXT NOT NULL,
    status       TEXT NOT NULL,
    triggered_at DATETIME NOT NULL,
    completed_at DATETIME,
    commit_sha   TEXT
);
"""

_CREATE_FAILURE_EVENTS = """
CREATE TABLE IF NOT EXISTS failure_events (
    id           TEXT PRIMARY KEY,
    run_id       TEXT REFERENCES pipeline_runs(id),
    signature_id TEXT,
    job          TEXT NOT NULL,
    step         TEXT NOT NULL,
    exit_code    INTEGER,
    log_tail     TEXT,
    created_at   DATETIME NOT NULL
);
"""


async def init_db() -> None:
    """Create tables on startup. Idempotent — safe to call multiple times."""
    db_dir = os.path.dirname(_DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(_CREATE_PIPELINE_RUNS)
        await db.execute(_CREATE_FAILURE_EVENTS)
        await db.commit()


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async generator for FastAPI Depends() injection."""
    async with aiosqlite.connect(_DB_PATH) as db:
        yield db
