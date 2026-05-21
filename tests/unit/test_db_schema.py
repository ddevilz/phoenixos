import aiosqlite
import pytest


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


async def test_init_db_creates_pipeline_runs(db_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", db_path)
    from core.db.sqlite import init_db

    await init_db()

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_runs'"
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None, "pipeline_runs table not created"


async def test_init_db_creates_failure_events(db_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", db_path)
    from core.db.sqlite import init_db

    await init_db()

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='failure_events'"
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None, "failure_events table not created"


async def test_init_db_idempotent(db_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", db_path)
    from core.db.sqlite import init_db

    await init_db()
    await init_db()  # second call must not raise
