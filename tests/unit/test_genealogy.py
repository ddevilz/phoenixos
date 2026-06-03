# tests/unit/test_genealogy.py
from unittest.mock import AsyncMock


async def test_genealogy_returns_chain_with_depth() -> None:
    from core.graph.genealogy import get_fix_genealogy

    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(
        return_value=[
            {
                "chain": [
                    {
                        "id": "fix-1",
                        "description": "patch 1",
                        "author_type": "human",
                        "commit_sha": "abc1",
                        "timestamp": "2026-01-01T00:00:00",
                    },
                    {
                        "id": "fix-2",
                        "description": "patch 2",
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
                "depth": 2,
            }
        ]
    )
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await get_fix_genealogy("fix-1", mock_session)

    assert result["fix_id"] == "fix-1"
    assert result["depth"] == 2
    assert len(result["chain"]) == 3
    assert result["warning"] is None


async def test_genealogy_depth_zero_no_edges() -> None:
    from core.graph.genealogy import get_fix_genealogy

    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(
        return_value=[
            {
                "chain": [
                    {
                        "id": "fix-1",
                        "description": "only fix",
                        "author_type": "human",
                        "commit_sha": "abc1",
                        "timestamp": "2026-01-01T00:00:00",
                    }
                ],
                "depth": 0,
            }
        ]
    )
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await get_fix_genealogy("fix-1", mock_session)

    assert result["depth"] == 0
    assert len(result["chain"]) == 1
    assert result["warning"] is None


async def test_genealogy_warning_when_depth_exceeds_two() -> None:
    from core.graph.genealogy import get_fix_genealogy

    chain = [
        {
            "id": f"fix-{i}",
            "description": f"patch {i}",
            "author_type": "human",
            "commit_sha": f"abc{i}",
            "timestamp": "2026-01-01T00:00:00",
        }
        for i in range(1, 5)
    ]
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(return_value=[{"chain": chain, "depth": 3}])
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await get_fix_genealogy("fix-1", mock_session)

    assert result["depth"] == 3
    assert result["warning"] == "symptom suppression chain detected"


async def test_genealogy_fix_not_found_returns_empty() -> None:
    from core.graph.genealogy import get_fix_genealogy

    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(return_value=[])
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await get_fix_genealogy("unknown-fix", mock_session)

    assert result["fix_id"] == "unknown-fix"
    assert result["depth"] == 0
    assert result["chain"] == []
    assert result["warning"] is None
