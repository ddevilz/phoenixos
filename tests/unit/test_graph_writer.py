from datetime import datetime, timezone
from unittest.mock import AsyncMock

from core.embeddings.dedup import DedupKind, DedupResult
from core.models.failure import FailureSignature


def _make_signature() -> FailureSignature:
    return FailureSignature(
        id="sig-new",
        summary="ImportError in auth module",
        category="build_error",
        affected_component="src/auth.py",
        embedding=[0.1] * 1536,
        first_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        occurrence_count=1,
    )


async def test_write_exact_updates_existing_node() -> None:
    from core.graph.writer import write

    sig = _make_signature()
    dedup_result = DedupResult(kind=DedupKind.EXACT, matched_id="existing-1", similarity=0.95)
    mock_session = AsyncMock()

    await write(sig, dedup_result, mock_session)

    mock_session.run.assert_called_once()
    cypher = mock_session.run.call_args[0][0]
    kwargs = mock_session.run.call_args[1]
    assert "MATCH" in cypher
    assert "SET" in cypher
    assert "occurrence_count" in cypher
    assert kwargs["matched_id"] == "existing-1"
    assert "last_seen" in kwargs


async def test_write_new_creates_node() -> None:
    from core.graph.writer import write

    sig = _make_signature()
    dedup_result = DedupResult(kind=DedupKind.NEW, matched_id=None, similarity=None)
    mock_session = AsyncMock()

    await write(sig, dedup_result, mock_session)

    mock_session.run.assert_called_once()
    cypher = mock_session.run.call_args[0][0]
    kwargs = mock_session.run.call_args[1]
    assert "MERGE" in cypher
    assert "ON CREATE SET" in cypher
    assert kwargs["id"] == sig.id
    assert kwargs["summary"] == sig.summary
    assert kwargs["embedding"] == sig.embedding


async def test_write_similar_creates_node_and_edge() -> None:
    from core.graph.writer import write

    sig = _make_signature()
    dedup_result = DedupResult(kind=DedupKind.SIMILAR, matched_id="existing-1", similarity=0.87)
    mock_session = AsyncMock()

    await write(sig, dedup_result, mock_session)

    mock_session.run.assert_called_once()
    cypher = mock_session.run.call_args[0][0]
    kwargs = mock_session.run.call_args[1]
    assert "SIMILAR_TO" in cypher
    assert kwargs["similarity"] == 0.87
    assert "created_at" in kwargs
    assert kwargs["matched_id"] == "existing-1"
    assert kwargs["embedding"] == sig.embedding


async def test_write_similar_with_no_matched_id_falls_back_to_new() -> None:
    from core.graph.writer import write

    sig = _make_signature()
    # matched_id=None should trigger fallback to NEW, not silently drop edge
    dedup_result = DedupResult(kind=DedupKind.SIMILAR, matched_id=None, similarity=0.87)
    mock_session = AsyncMock()

    await write(sig, dedup_result, mock_session)

    mock_session.run.assert_called_once()
    cypher = mock_session.run.call_args[0][0]
    kwargs = mock_session.run.call_args[1]
    assert "MERGE" in cypher
    assert "SIMILAR_TO" not in cypher
    assert kwargs["id"] == sig.id


async def test_write_swallows_exception() -> None:
    from core.graph.writer import write

    sig = _make_signature()
    dedup_result = DedupResult(kind=DedupKind.NEW, matched_id=None, similarity=None)
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=Exception("Neo4j down"))

    await write(sig, dedup_result, mock_session)  # must not raise
