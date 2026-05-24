from unittest.mock import patch

import aiosqlite
import pytest
from core.db.sqlite import init_db


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")


async def test_init_db_creates_tables(db_path: str) -> None:
    with patch("core.db.sqlite._DB_PATH", db_path):
        await init_db()

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] async for row in cursor]

    assert "failure_events" in tables
    assert "pipeline_runs" in tables


async def test_init_db_is_idempotent(db_path: str) -> None:
    with patch("core.db.sqlite._DB_PATH", db_path):
        await init_db()
        await init_db()  # second call must not raise


async def test_pipeline_runs_columns(db_path: str) -> None:
    with patch("core.db.sqlite._DB_PATH", db_path):
        await init_db()

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("PRAGMA table_info(pipeline_runs)")
        cols = {row[1] async for row in cursor}

    assert cols == {
        "id", "repo", "workflow", "status", "triggered_at", "completed_at", "commit_sha"
    }


async def test_failure_events_columns(db_path: str) -> None:
    with patch("core.db.sqlite._DB_PATH", db_path):
        await init_db()

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("PRAGMA table_info(failure_events)")
        cols = {row[1] async for row in cursor}

    assert cols == {
        "id", "run_id", "signature_id", "job", "step", "exit_code", "log_tail", "created_at"
    }
