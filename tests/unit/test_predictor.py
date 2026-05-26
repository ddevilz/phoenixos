# tests/unit/test_predictor.py
from unittest.mock import AsyncMock


async def test_predict_returns_direct_matches() -> None:
    from core.agents.predictor import predict_failures

    direct_result = AsyncMock()
    direct_result.data = AsyncMock(return_value=[
        {"id": "sig-1", "summary": "ImportError in auth", "category": "build_error",
         "affected_component": "src/auth.py", "fragility_score": 0.8, "direct": True},
    ])
    similar_result = AsyncMock()
    similar_result.data = AsyncMock(return_value=[])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[direct_result, similar_result])

    results = await predict_failures(["src/auth.py"], mock_session)

    assert len(results) == 1
    assert results[0]["id"] == "sig-1"
    assert results[0]["match_type"] == "direct"
    assert results[0]["confidence"] == 0.8


async def test_predict_expands_similar_to() -> None:
    from core.agents.predictor import predict_failures

    direct_result = AsyncMock()
    direct_result.data = AsyncMock(return_value=[
        {"id": "sig-1", "summary": "auth error", "category": "build_error",
         "affected_component": "src/auth.py", "fragility_score": 0.8, "direct": True},
    ])
    similar_result = AsyncMock()
    similar_result.data = AsyncMock(return_value=[
        {"id": "sig-2", "summary": "related login error", "category": "test_failure",
         "affected_component": "src/login.py", "fragility_score": 0.6, "direct": False},
    ])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[direct_result, similar_result])

    results = await predict_failures(["src/auth.py"], mock_session)

    ids = [r["id"] for r in results]
    assert "sig-1" in ids
    assert "sig-2" in ids
    sig2 = next(r for r in results if r["id"] == "sig-2")
    assert sig2["match_type"] == "similar"
    assert abs(sig2["confidence"] - 0.42) < 0.001


async def test_predict_empty_changed_files_returns_empty() -> None:
    from core.agents.predictor import predict_failures

    mock_session = AsyncMock()

    results = await predict_failures([], mock_session)

    assert results == []
    mock_session.run.assert_not_called()


async def test_predict_caps_at_ten() -> None:
    from core.agents.predictor import predict_failures

    # 15 direct matches — only top 10 by confidence should be returned
    direct_records = [
        {"id": f"sig-{i}", "summary": f"error {i}", "category": "build_error",
         "affected_component": "src/auth.py", "fragility_score": i / 15.0, "direct": True}
        for i in range(1, 16)
    ]
    direct_result = AsyncMock()
    direct_result.data = AsyncMock(return_value=direct_records)
    similar_result = AsyncMock()
    similar_result.data = AsyncMock(return_value=[])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[direct_result, similar_result])

    results = await predict_failures(["src/auth.py"], mock_session)

    assert len(results) == 10
    assert results[0]["id"] == "sig-15"  # highest fragility_score = 15/15 = 1.0
