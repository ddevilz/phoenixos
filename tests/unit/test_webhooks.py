import aiosqlite
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(tmp_path, monkeypatch):
    # monkeypatch.setenv is sufficient — _get_db_path() reads os.getenv at call time
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    from core.main import app

    return app, str(tmp_path / "test.db")


def test_webhook_accepted_for_synthetic_payload(app_with_db):
    app, _ = app_with_db
    with TestClient(app) as client:
        payload = {
            "repo": "owner/repo",
            "run_id": "999",
            "workflow": "CI",
            "job": "test",
            "step": "Run pytest",
            "exit_code": 1,
            "log_tail": "FAILED test_foo",
            "changed_files": ["src/main.py"],
        }
        response = client.post(
            "/api/webhooks/github",
            json=payload,
            headers={"x-github-event": "push"},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert "event_id" in response.json()


def test_webhook_ignored_for_non_failure_workflow_run(app_with_db):
    app, _ = app_with_db
    with TestClient(app) as client:
        payload = {
            "workflow_run": {
                "id": 1,
                "name": "CI",
                "conclusion": "success",
            },
            "repository": {"full_name": "owner/repo"},
        }
        response = client.post(
            "/api/webhooks/github",
            json=payload,
            headers={"x-github-event": "workflow_run"},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


async def test_webhook_stores_event_in_sqlite(app_with_db):
    app, db_path = app_with_db
    with TestClient(app) as client:
        payload = {
            "repo": "owner/repo",
            "run_id": "777",
            "workflow": "CI",
            "job": "build",
            "step": "compile",
            "exit_code": 2,
            "log_tail": "error: undefined symbol",
            "changed_files": [],
        }
        response = client.post(
            "/api/webhooks/github",
            json=payload,
            headers={"x-github-event": "push"},
        )
    event_id = response.json()["event_id"]

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT id, run_id, job FROM failure_events WHERE id = ?", (event_id,)
        ) as cursor:
            row = await cursor.fetchone()

    assert row is not None
    assert row[1] == "777"
    assert row[2] == "build"
