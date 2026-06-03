# tests/unit/test_scoring.py
from unittest.mock import AsyncMock


async def test_recompute_fragility_single_node_no_edges() -> None:
    from core.graph.scoring import recompute_fragility

    fetch_result = AsyncMock()
    fetch_result.data = AsyncMock(return_value=[{"src": "sig-1", "dst": None, "weight": None}])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[fetch_result, AsyncMock()])

    scores = await recompute_fragility(mock_session)

    assert "sig-1" in scores
    assert scores["sig-1"] > 0
    assert mock_session.run.call_count == 2


async def test_recompute_fragility_two_nodes_with_edge() -> None:
    from core.graph.scoring import recompute_fragility

    # sig-1 → sig-2 via SIMILAR_TO; sig-2 has incoming edge → higher PageRank
    fetch_result = AsyncMock()
    fetch_result.data = AsyncMock(
        return_value=[
            {"src": "sig-1", "dst": "sig-2", "weight": 0.9},
            {"src": "sig-2", "dst": None, "weight": None},
        ]
    )
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[fetch_result, AsyncMock()])

    scores = await recompute_fragility(mock_session)

    assert scores["sig-2"] > scores["sig-1"]


async def test_recompute_fragility_writes_scores_back() -> None:
    from core.graph.scoring import recompute_fragility

    fetch_result = AsyncMock()
    fetch_result.data = AsyncMock(return_value=[{"src": "sig-1", "dst": None, "weight": None}])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[fetch_result, AsyncMock()])

    await recompute_fragility(mock_session)

    assert mock_session.run.call_count == 2
    write_cypher = mock_session.run.call_args_list[1][0][0]
    assert "UNWIND" in write_cypher
    assert "fragility_score" in write_cypher
    write_kwargs = mock_session.run.call_args_list[1][1]
    payload = write_kwargs["scores"]
    assert len(payload) == 1
    assert payload[0]["id"] == "sig-1"
    assert isinstance(payload[0]["score"], float)


async def test_recompute_fragility_swallows_exception() -> None:
    from core.graph.scoring import recompute_fragility

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=Exception("Neo4j down"))

    result = await recompute_fragility(mock_session)

    assert result == {}


async def test_recompute_fragility_swallows_write_exception() -> None:
    from core.graph.scoring import recompute_fragility

    fetch_result = AsyncMock()
    fetch_result.data = AsyncMock(return_value=[{"src": "sig-1", "dst": None, "weight": None}])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[fetch_result, Exception("write failed")])

    result = await recompute_fragility(mock_session)

    assert result == {}


async def test_trajectory_empty_graph_returns_stable() -> None:
    from core.graph.scoring import get_flakiness_trajectory

    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(return_value=[])
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await get_flakiness_trajectory("src/auth.py", mock_session)

    assert result["trajectory"] == "stable"
    assert result["component"] == "src/auth.py"
    assert result["window_days"] == 28
    assert len(result["buckets"]) == 4
    assert all(b["count"] == 0 for b in result["buckets"])


async def test_trajectory_rising() -> None:
    from datetime import datetime, timedelta, timezone

    from core.graph.scoring import get_flakiness_trajectory

    now = datetime.now(timezone.utc)
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    # Bucket boundaries with window=28, 4 buckets: [28-21], [21-14], [14-7], [7-0] days ago
    mock_result.data = AsyncMock(
        return_value=[
            {"last_seen": (now - timedelta(days=25)).isoformat(), "count": 1},
            {"last_seen": (now - timedelta(days=18)).isoformat(), "count": 2},
            {"last_seen": (now - timedelta(days=11)).isoformat(), "count": 4},
            {"last_seen": (now - timedelta(days=3)).isoformat(), "count": 8},
        ]
    )
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await get_flakiness_trajectory("src/auth.py", mock_session)

    assert result["trajectory"] == "rising"


async def test_trajectory_falling() -> None:
    from datetime import datetime, timedelta, timezone

    from core.graph.scoring import get_flakiness_trajectory

    now = datetime.now(timezone.utc)
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(
        return_value=[
            {"last_seen": (now - timedelta(days=25)).isoformat(), "count": 8},
            {"last_seen": (now - timedelta(days=18)).isoformat(), "count": 4},
            {"last_seen": (now - timedelta(days=11)).isoformat(), "count": 2},
            {"last_seen": (now - timedelta(days=3)).isoformat(), "count": 1},
        ]
    )
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await get_flakiness_trajectory("src/auth.py", mock_session)

    assert result["trajectory"] == "falling"


async def test_trajectory_stable() -> None:
    from datetime import datetime, timedelta, timezone

    from core.graph.scoring import get_flakiness_trajectory

    now = datetime.now(timezone.utc)
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(
        return_value=[
            {"last_seen": (now - timedelta(days=25)).isoformat(), "count": 3},
            {"last_seen": (now - timedelta(days=18)).isoformat(), "count": 3},
            {"last_seen": (now - timedelta(days=11)).isoformat(), "count": 4},
            {"last_seen": (now - timedelta(days=3)).isoformat(), "count": 4},
        ]
    )
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await get_flakiness_trajectory("src/auth.py", mock_session)

    assert result["trajectory"] == "stable"
