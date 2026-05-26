# tests/unit/test_blast_radius.py
from unittest.mock import AsyncMock


async def test_blast_radius_returns_direct_components() -> None:
    from core.graph.blast_radius import get_blast_radius

    direct_result = AsyncMock()
    direct_result.data = AsyncMock(return_value=[
        {"component": "src/auth.py", "fragility_score": 0.8},
    ])
    similar_result = AsyncMock()
    similar_result.data = AsyncMock(return_value=[])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[direct_result, similar_result])

    result = await get_blast_radius(["src/auth.py"], mock_session)

    assert "src/auth.py" in result["at_risk"]
    assert result["fragility_scores"]["src/auth.py"] == 0.8


async def test_blast_radius_expands_similar_to() -> None:
    from core.graph.blast_radius import get_blast_radius

    direct_result = AsyncMock()
    direct_result.data = AsyncMock(return_value=[
        {"component": "src/auth.py", "fragility_score": 0.8},
    ])
    similar_result = AsyncMock()
    similar_result.data = AsyncMock(return_value=[
        {"component": "src/login.py", "fragility_score": 0.6},
    ])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[direct_result, similar_result])

    result = await get_blast_radius(["src/auth.py"], mock_session)

    assert "src/auth.py" in result["at_risk"]
    assert "src/login.py" in result["at_risk"]
    assert result["fragility_scores"]["src/login.py"] == 0.6


async def test_blast_radius_empty_changed_files_returns_empty() -> None:
    from core.graph.blast_radius import get_blast_radius

    mock_session = AsyncMock()

    result = await get_blast_radius([], mock_session)

    assert result == {"at_risk": [], "fragility_scores": {}}
    mock_session.run.assert_not_called()


async def test_blast_radius_caps_at_ten_sorted_desc() -> None:
    from core.graph.blast_radius import get_blast_radius

    # 15 direct components with varying scores
    records = [
        {"component": f"src/mod_{i}.py", "fragility_score": i / 15.0}
        for i in range(1, 16)
    ]
    direct_result = AsyncMock()
    direct_result.data = AsyncMock(return_value=records)
    similar_result = AsyncMock()
    similar_result.data = AsyncMock(return_value=[])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[direct_result, similar_result])

    result = await get_blast_radius(["src/any.py"], mock_session)

    assert len(result["at_risk"]) == 10
    assert result["at_risk"][0] == "src/mod_15.py"  # highest score first
    assert len(result["fragility_scores"]) == 10
