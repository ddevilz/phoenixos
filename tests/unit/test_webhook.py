# tests/unit/test_webhook.py
import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Import core.main at module level so core.api.webhooks is cached before fixtures patch it
import core.api.webhooks  # noqa: F401
import core.main  # noqa: F401
import pytest
from core.api.webhooks import _run_pipeline
from core.embeddings.dedup import DedupKind, DedupResult
from core.models.failure import FailureEvent, FailureSignature
from httpx import ASGITransport, AsyncClient


def _sign(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


FAILURE_PAYLOAD = {
    "action": "completed",
    "workflow_run": {
        "id": 99999,
        "name": "CI",
        "conclusion": "failure",
        "head_sha": "abc123",
        "updated_at": "2026-05-24T12:00:00Z",
    },
    "repository": {"full_name": "owner/repo"},
}

SUCCESS_PAYLOAD = {
    "action": "completed",
    "workflow_run": {
        "id": 88888,
        "name": "CI",
        "conclusion": "success",
        "head_sha": "def456",
        "updated_at": "2026-05-24T12:00:00Z",
    },
    "repository": {"full_name": "owner/repo"},
}


@pytest.fixture
async def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    changed_files_mock = AsyncMock(return_value=["src/auth.py"])
    with (
        patch("core.db.sqlite._DB_PATH", db_path),
        patch("core.db.neo4j.init_driver", new_callable=AsyncMock),
        patch("core.db.neo4j.close_driver", new_callable=AsyncMock),
        patch("core.api.webhooks._get_changed_files", changed_files_mock),
        patch("core.api.webhooks._run_pipeline", new_callable=AsyncMock),
    ):
        from core.db.sqlite import init_db
        await init_db()  # ASGITransport skips lifespan; create tables explicitly
        from core.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


async def test_webhook_rejects_invalid_signature(client):
    body = json.dumps(FAILURE_PAYLOAD).encode()
    with patch.dict("os.environ", {"GITHUB_WEBHOOK_SECRET": "real-secret"}):
        r = await client.post(
            "/api/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=badhash",
            },
        )
    assert r.status_code == 401


async def test_webhook_skips_verification_with_no_secret(client):
    body = json.dumps(FAILURE_PAYLOAD).encode()
    with patch.dict("os.environ", {"GITHUB_WEBHOOK_SECRET": ""}):
        r = await client.post(
            "/api/webhooks/github",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 202


async def test_webhook_ignores_success_runs(client):
    body = json.dumps(SUCCESS_PAYLOAD).encode()
    with patch.dict("os.environ", {"GITHUB_WEBHOOK_SECRET": ""}):
        r = await client.post(
            "/api/webhooks/github",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


async def test_webhook_accepts_failure_and_returns_run_id(client):
    body = json.dumps(FAILURE_PAYLOAD).encode()
    with patch.dict("os.environ", {"GITHUB_WEBHOOK_SECRET": ""}):
        r = await client.post(
            "/api/webhooks/github",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 202
    assert r.json()["run_id"] == "99999"


async def test_webhook_response_includes_event_id(client):
    body = json.dumps(FAILURE_PAYLOAD).encode()
    with patch.dict("os.environ", {"GITHUB_WEBHOOK_SECRET": ""}):
        r = await client.post(
            "/api/webhooks/github",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 202
    data = r.json()
    assert "event_id" in data, f"response missing event_id: {data}"
    # event_id is the SQLite PK — must be a UUID4 string
    assert len(data["event_id"]) == 36
    assert data["event_id"].count("-") == 4


async def test_webhook_writes_to_sqlite(client, tmp_path):
    import aiosqlite

    # tmp_path is shared with the client fixture — both use tmp_path / "test.db"
    db_path = str(tmp_path / "test.db")
    body = json.dumps(FAILURE_PAYLOAD).encode()

    with patch.dict("os.environ", {"GITHUB_WEBHOOK_SECRET": ""}):
        r = await client.post(
            "/api/webhooks/github",
            content=body,
            headers={"Content-Type": "application/json"},
        )

    assert r.status_code == 202

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT id, repo, workflow FROM pipeline_runs")
        rows = await cursor.fetchall()

    assert len(rows) == 1
    assert rows[0][1] == "owner/repo"
    assert rows[0][2] == "CI"


async def test_run_pipeline_calls_embed_after_extract() -> None:
    event = FailureEvent(
        id="evt-1",
        repo="owner/repo",
        run_id="99",
        workflow="CI",
        job="CI",
        step="unknown",
        exit_code=1,
        log_tail="error",
        changed_files=[],
        timestamp=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    mock_sig = FailureSignature(
        id="sig-1",
        summary="test failure",
        category="test_failure",
        affected_component="src/foo.py",
        embedding=[],
        first_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        occurrence_count=1,
    )
    embedded_sig = mock_sig.model_copy(update={"embedding": [0.1] * 1536})
    dedup_result = DedupResult(kind=DedupKind.NEW, matched_id=None, similarity=None)

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "core.ingestor.signature.extract", new_callable=AsyncMock, return_value=mock_sig
        ) as mock_extract,
        patch(
            "core.embeddings.pipeline.embed", new_callable=AsyncMock, return_value=embedded_sig
        ) as mock_embed,
        patch("core.embeddings.dedup.dedup", new_callable=AsyncMock, return_value=dedup_result),
        patch("core.db.neo4j.neo4j_session", return_value=mock_ctx),
        patch("core.graph.writer.write", new_callable=AsyncMock),
        patch("core.graph.scoring.recompute_fragility", new_callable=AsyncMock),
    ):
        await _run_pipeline(event)

    mock_extract.assert_called_once_with(event)
    mock_embed.assert_called_once_with(mock_sig)


async def test_run_pipeline_calls_dedup_after_embed() -> None:
    event = FailureEvent(
        id="evt-1",
        repo="owner/repo",
        run_id="99",
        workflow="CI",
        job="CI",
        step="unknown",
        exit_code=1,
        log_tail="error",
        changed_files=[],
        timestamp=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    mock_sig = FailureSignature(
        id="sig-1",
        summary="test failure",
        category="test_failure",
        affected_component="src/foo.py",
        embedding=[],
        first_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        occurrence_count=1,
    )
    embedded_sig = mock_sig.model_copy(update={"embedding": [0.1] * 1536})
    dedup_result = DedupResult(kind=DedupKind.NEW, matched_id=None, similarity=None)

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.ingestor.signature.extract", new_callable=AsyncMock, return_value=mock_sig),
        patch("core.embeddings.pipeline.embed", new_callable=AsyncMock, return_value=embedded_sig),
        patch(
            "core.embeddings.dedup.dedup", new_callable=AsyncMock, return_value=dedup_result
        ) as mock_dedup,
        patch("core.db.neo4j.neo4j_session", return_value=mock_ctx),
        patch("core.graph.writer.write", new_callable=AsyncMock),
        patch("core.graph.scoring.recompute_fragility", new_callable=AsyncMock),
    ):
        await _run_pipeline(event)

    mock_dedup.assert_called_once_with(embedded_sig, mock_session)


async def test_run_pipeline_calls_write_after_dedup() -> None:
    event = FailureEvent(
        id="evt-1",
        repo="owner/repo",
        run_id="99",
        workflow="CI",
        job="CI",
        step="unknown",
        exit_code=1,
        log_tail="error",
        changed_files=[],
        timestamp=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    mock_sig = FailureSignature(
        id="sig-1",
        summary="test failure",
        category="test_failure",
        affected_component="src/foo.py",
        embedding=[],
        first_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        occurrence_count=1,
    )
    embedded_sig = mock_sig.model_copy(update={"embedding": [0.1] * 1536})
    dedup_result = DedupResult(kind=DedupKind.NEW, matched_id=None, similarity=None)

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.ingestor.signature.extract", new_callable=AsyncMock, return_value=mock_sig),
        patch("core.embeddings.pipeline.embed", new_callable=AsyncMock, return_value=embedded_sig),
        patch("core.embeddings.dedup.dedup", new_callable=AsyncMock, return_value=dedup_result),
        patch("core.db.neo4j.neo4j_session", return_value=mock_ctx),
        patch(
            "core.graph.writer.write", new_callable=AsyncMock
        ) as mock_write,
        patch("core.graph.scoring.recompute_fragility", new_callable=AsyncMock),
    ):
        await _run_pipeline(event)

    mock_write.assert_called_once_with(embedded_sig, dedup_result, mock_session)


async def test_run_pipeline_returns_early_when_extract_returns_none() -> None:
    event = FailureEvent(
        id="evt-1",
        repo="owner/repo",
        run_id="99",
        workflow="CI",
        job="CI",
        step="unknown",
        exit_code=1,
        log_tail="",
        changed_files=[],
        timestamp=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
    )

    with (
        patch("core.ingestor.signature.extract", new_callable=AsyncMock, return_value=None),
        patch("core.embeddings.pipeline.embed", new_callable=AsyncMock) as mock_embed,
        patch("core.embeddings.dedup.dedup", new_callable=AsyncMock) as mock_dedup,
        patch("core.graph.writer.write", new_callable=AsyncMock) as mock_write,
        patch(
            "core.graph.scoring.recompute_fragility", new_callable=AsyncMock
        ) as mock_recompute,
    ):
        await _run_pipeline(event)

    mock_embed.assert_not_called()
    mock_dedup.assert_not_called()
    mock_write.assert_not_called()
    mock_recompute.assert_not_called()


async def test_run_pipeline_calls_recompute_after_write() -> None:
    event = FailureEvent(
        id="evt-1",
        repo="owner/repo",
        run_id="99",
        workflow="CI",
        job="CI",
        step="unknown",
        exit_code=1,
        log_tail="",
        changed_files=[],
        timestamp=datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
    )
    mock_sig = FailureSignature(
        id="sig-1",
        summary="test failure",
        category="test_failure",
        affected_component="src/foo.py",
        embedding=[],
        first_seen=datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
        occurrence_count=1,
    )
    embedded_sig = mock_sig.model_copy(update={"embedding": [0.1] * 1536})
    dedup_result = DedupResult(kind=DedupKind.NEW, matched_id=None, similarity=None)

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.ingestor.signature.extract", new_callable=AsyncMock, return_value=mock_sig),
        patch("core.embeddings.pipeline.embed", new_callable=AsyncMock, return_value=embedded_sig),
        patch("core.embeddings.dedup.dedup", new_callable=AsyncMock, return_value=dedup_result),
        patch("core.db.neo4j.neo4j_session", return_value=mock_ctx),
        patch("core.graph.writer.write", new_callable=AsyncMock),
        patch(
            "core.graph.scoring.recompute_fragility", new_callable=AsyncMock
        ) as mock_recompute,
    ):
        await _run_pipeline(event)

    mock_recompute.assert_called_once_with(mock_session)
