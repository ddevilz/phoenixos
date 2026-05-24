from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from core.models.failure import FailureSignature


def _make_signature(embedding: list[float]) -> FailureSignature:
    return FailureSignature(
        id="sig-new",
        summary="ImportError in auth module",
        category="build_error",
        affected_component="src/auth.py",
        embedding=embedding,
        first_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        occurrence_count=1,
    )


def _mock_session(records: list[dict]) -> AsyncMock:
    """Build a mock AsyncSession whose run().data() returns records."""
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(return_value=records)
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    return mock_session


async def test_cosine_similarity_identical() -> None:
    from core.embeddings.dedup import cosine_similarity

    assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)


async def test_cosine_similarity_orthogonal() -> None:
    from core.embeddings.dedup import cosine_similarity

    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


async def test_cosine_similarity_zero_vector() -> None:
    from core.embeddings.dedup import cosine_similarity

    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == pytest.approx(0.0)


async def test_dedup_new_when_no_existing() -> None:
    from core.embeddings.dedup import DedupKind, dedup

    sig = _make_signature([1.0, 0.0, 0.0])
    session = _mock_session([])

    result = await dedup(sig, session)

    assert result.kind == DedupKind.NEW
    assert result.matched_id is None
    assert result.similarity is None


async def test_dedup_exact_match() -> None:
    from core.embeddings.dedup import DedupKind, dedup

    sig = _make_signature([1.0, 0.0, 0.0])
    # Same vector → cosine similarity = 1.0 (>= 0.92)
    session = _mock_session([{"id": "existing-1", "embedding": [1.0, 0.0, 0.0]}])

    result = await dedup(sig, session)

    assert result.kind == DedupKind.EXACT
    assert result.matched_id == "existing-1"
    assert result.similarity == pytest.approx(1.0)


async def test_dedup_similar_match() -> None:
    from core.embeddings.dedup import DedupKind, dedup

    sig = _make_signature([1.0, 0.0, 0.0])
    # [0.87, 0.493, 0.0] has norm ≈ 1.0, dot with [1,0,0] = 0.87 → similarity ≈ 0.87
    # 0.87 is >= 0.80 and < 0.92 → SIMILAR
    session = _mock_session([{"id": "existing-1", "embedding": [0.87, 0.493, 0.0]}])

    result = await dedup(sig, session)

    assert result.kind == DedupKind.SIMILAR
    assert result.matched_id == "existing-1"
    assert result.similarity == pytest.approx(0.87, abs=0.01)


async def test_dedup_new_below_threshold() -> None:
    from core.embeddings.dedup import DedupKind, dedup

    sig = _make_signature([1.0, 0.0, 0.0])
    # [0.0, 1.0, 0.0] → cosine similarity = 0.0 (< 0.80) → NEW
    session = _mock_session([{"id": "existing-1", "embedding": [0.0, 1.0, 0.0]}])

    result = await dedup(sig, session)

    assert result.kind == DedupKind.NEW
    assert result.matched_id is None
    assert result.similarity == pytest.approx(0.0)


async def test_cosine_similarity_mismatched_lengths() -> None:
    from core.embeddings.dedup import cosine_similarity

    assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


async def test_dedup_skips_query_for_empty_embedding() -> None:
    from core.embeddings.dedup import DedupKind, dedup

    sig = _make_signature([])
    session = _mock_session([])

    result = await dedup(sig, session)

    assert result.kind == DedupKind.NEW
    assert result.matched_id is None
    assert result.similarity is None
    session.run.assert_not_called()


async def test_dedup_returns_best_match_across_multiple_records() -> None:
    from core.embeddings.dedup import DedupKind, dedup

    sig = _make_signature([1.0, 0.0, 0.0])
    # First record has low similarity, second has exact match — dedup must pick the best
    session = _mock_session([
        {"id": "worse-sig", "embedding": [0.0, 1.0, 0.0]},
        {"id": "best-sig", "embedding": [1.0, 0.0, 0.0]},
    ])

    result = await dedup(sig, session)

    assert result.kind == DedupKind.EXACT
    assert result.matched_id == "best-sig"
    assert result.similarity == pytest.approx(1.0)
