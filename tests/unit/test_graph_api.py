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
    mock_result.data = AsyncMock(
        return_value=[
            {"id": "sig-1", "fragility_score": 0.6},
            {"id": "sig-2", "fragility_score": 0.4},
        ]
    )
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("core.api.graph.neo4j_session", return_value=mock_ctx):
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
        patch("core.api.graph.neo4j_session", return_value=mock_ctx),
        patch(
            "core.api.graph.recompute_fragility",
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
        patch("core.api.graph.neo4j_session", return_value=mock_ctx),
        patch(
            "core.api.graph.get_flakiness_trajectory",
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
    with patch("core.api.graph.neo4j_session", side_effect=Exception("driver not ready")):
        r = await client.get("/api/graph/fragility")

    assert r.status_code == 503


async def test_get_genealogy_returns_chain(client) -> None:
    expected = {
        "fix_id": "fix-1",
        "depth": 2,
        "chain": [
            {
                "id": "fix-1",
                "description": "latest patch",
                "author_type": "human",
                "commit_sha": "abc1",
                "timestamp": "2026-01-01T00:00:00",
            },
            {
                "id": "fix-2",
                "description": "earlier patch",
                "author_type": "ai",
                "commit_sha": "abc2",
                "timestamp": "2025-12-01T00:00:00",
            },
            {
                "id": "fix-3",
                "description": "root fix",
                "author_type": "human",
                "commit_sha": "abc3",
                "timestamp": "2025-11-01T00:00:00",
            },
        ],
        "warning": None,
    }
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.api.graph.neo4j_session", return_value=mock_ctx),
        patch(
            "core.api.graph.get_fix_genealogy",
            new_callable=AsyncMock,
            return_value=expected,
        ),
    ):
        r = await client.get("/api/graph/genealogy/fix-1")

    assert r.status_code == 200
    body = r.json()
    assert body["fix_id"] == "fix-1"
    assert body["depth"] == 2
    assert len(body["chain"]) == 3
    assert body["warning"] is None


async def test_post_predict_returns_predictions(client) -> None:
    predictions = [
        {
            "id": "sig-1",
            "summary": "ImportError in auth",
            "category": "build_error",
            "affected_component": "src/auth.py",
            "fragility_score": 0.8,
            "confidence": 0.8,
            "match_type": "direct",
        }
    ]
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.api.graph.neo4j_session", return_value=mock_ctx),
        patch(
            "core.api.graph.predict_failures",
            new_callable=AsyncMock,
            return_value=predictions,
        ),
    ):
        r = await client.post("/api/graph/predict", json={"changed_files": ["src/auth.py"]})

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == "sig-1"
    assert body[0]["match_type"] == "direct"


async def test_post_blast_radius_returns_at_risk(client) -> None:
    expected = {
        "at_risk": ["src/auth.py", "src/login.py"],
        "fragility_scores": {"src/auth.py": 0.8, "src/login.py": 0.56},
    }
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.api.graph.neo4j_session", return_value=mock_ctx),
        patch(
            "core.api.graph.get_blast_radius",
            new_callable=AsyncMock,
            return_value=expected,
        ),
    ):
        r = await client.post(
            "/api/graph/blast-radius",
            json={"changed_files": ["src/auth.py"]},
        )

    assert r.status_code == 200
    body = r.json()
    assert "at_risk" in body
    assert "fragility_scores" in body
    assert "src/auth.py" in body["at_risk"]


async def test_get_network_returns_nodes_and_edges(client) -> None:
    nodes = [
        {
            "id": "sig-1",
            "fragility_score": 0.81,
            "summary": "timeout regression",
            "category": "test_failure",
            "affected_component": "lib/transfer.c",
            "occurrence_count": 7,
            "first_seen": "2026-03-02T00:00:00",
            "last_seen": "2026-06-05T00:00:00",
        }
    ]
    edges = [{"source": "sig-1", "target": "sig-2", "similarity": 0.87}]

    nodes_result = AsyncMock()
    nodes_result.data = AsyncMock(return_value=nodes)
    edges_result = AsyncMock()
    edges_result.data = AsyncMock(return_value=edges)

    mock_session = AsyncMock()
    # two queries: nodes first, edges second
    mock_session.run = AsyncMock(side_effect=[nodes_result, edges_result])
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("core.api.graph.neo4j_session", return_value=mock_ctx):
        r = await client.get("/api/graph/network")

    assert r.status_code == 200
    body = r.json()
    assert body["nodes"][0]["id"] == "sig-1"
    assert body["nodes"][0]["affected_component"] == "lib/transfer.c"
    assert body["edges"][0]["source"] == "sig-1"
    assert body["edges"][0]["similarity"] == 0.87


async def test_get_network_returns_503_when_neo4j_unavailable(client) -> None:
    with patch("core.api.graph.neo4j_session", side_effect=Exception("driver not ready")):
        r = await client.get("/api/graph/network")
    assert r.status_code == 503


async def test_get_network_returns_empty_when_no_data(client) -> None:
    empty = AsyncMock()
    empty.data = AsyncMock(return_value=[])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[empty, empty])
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("core.api.graph.neo4j_session", return_value=mock_ctx):
        r = await client.get("/api/graph/network")
    assert r.status_code == 200
    assert r.json() == {"nodes": [], "edges": []}
