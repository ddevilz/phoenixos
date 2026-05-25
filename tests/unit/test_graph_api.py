# tests/unit/test_graph_api.py
from unittest.mock import AsyncMock, MagicMock, patch

import core.main  # noqa: F401 — must import before fixture patches
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    with (
        patch("core.db.sqlite._DB_PATH", db_path),
        patch("core.db.neo4j.init_driver", new_callable=AsyncMock),
        patch("core.db.neo4j.close_driver", new_callable=AsyncMock),
    ):
        from core.db.sqlite import init_db
        await init_db()
        from core.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


async def test_get_fragility_returns_scores(client) -> None:
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(return_value=[
        {"id": "sig-1", "fragility_score": 0.6},
        {"id": "sig-2", "fragility_score": 0.4},
    ])
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("core.db.neo4j.neo4j_session", return_value=mock_ctx):
        r = await client.get("/api/graph/fragility")

    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["id"] == "sig-1"
    assert data[0]["fragility_score"] == 0.6
    assert data[1]["id"] == "sig-2"
    assert data[1]["fragility_score"] == 0.4


async def test_post_recompute_returns_count(client) -> None:
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.db.neo4j.neo4j_session", return_value=mock_ctx),
        patch(
            "core.graph.scoring.recompute_fragility",
            new_callable=AsyncMock,
            return_value={"sig-1": 0.6, "sig-2": 0.4},
        ),
    ):
        r = await client.post("/api/graph/fragility/recompute")

    assert r.status_code == 200
    assert r.json() == {"recomputed": 2}


async def test_get_flakiness_returns_trajectory(client) -> None:
    expected = {
        "component": "src/auth.py",
        "trajectory": "rising",
        "window_days": 28,
        "buckets": [
            {"start": "2026-04-27", "end": "2026-05-04", "count": 1},
            {"start": "2026-05-04", "end": "2026-05-11", "count": 2},
            {"start": "2026-05-11", "end": "2026-05-18", "count": 4},
            {"start": "2026-05-18", "end": "2026-05-25", "count": 8},
        ],
    }
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.db.neo4j.neo4j_session", return_value=mock_ctx),
        patch(
            "core.graph.scoring.get_flakiness_trajectory",
            new_callable=AsyncMock,
            return_value=expected,
        ),
    ):
        r = await client.get("/api/graph/flakiness/src%2Fauth.py")

    assert r.status_code == 200
    body = r.json()
    assert body["trajectory"] == "rising"
    assert body["component"] == "src/auth.py"
    assert len(body["buckets"]) == 4


async def test_get_fragility_returns_503_when_neo4j_unavailable(client) -> None:
    with patch("core.db.neo4j.neo4j_session", side_effect=Exception("driver not ready")):
        r = await client.get("/api/graph/fragility")

    assert r.status_code == 503
