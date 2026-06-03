# tests/unit/test_pipeline.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from core.embeddings.dedup import DedupKind, DedupResult
from core.models.failure import FailureEvent, FailureSignature


def _make_event(changed_files: list[str] | None = None) -> FailureEvent:
    return FailureEvent(
        id="evt-1",
        repo="owner/repo",
        run_id="99",
        workflow="CI",
        job="CI",
        step="unknown",
        exit_code=1,
        log_tail="error",
        changed_files=changed_files or [],
        timestamp=datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc),
    )


def _make_sig(embedding: list[float] | None = None) -> FailureSignature:
    return FailureSignature(
        id="sig-1",
        summary="test failure",
        category="test_failure",
        affected_component="src/auth.py",
        embedding=embedding or [0.1] * 1536,
        first_seen=datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc),
        occurrence_count=1,
    )


async def test_pipeline_full_run_calls_write_and_embed() -> None:
    from core.orchestrator.pipeline import pipeline

    event = _make_event()
    mock_sig = _make_sig(embedding=[])
    embedded_sig = _make_sig()
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
        patch("core.db.neo4j.neo4j_session", return_value=mock_ctx),
        patch("core.embeddings.dedup.dedup", new_callable=AsyncMock, return_value=dedup_result),
        patch("core.graph.writer.write", new_callable=AsyncMock) as mock_write,
        patch("core.graph.scoring.recompute_fragility", new_callable=AsyncMock),
    ):
        state = await pipeline.ainvoke(
            {
                "event": event,
                "signature": None,
                "predictions": [],
                "at_risk": [],
                "fragility_scores": {},
            }
        )

    mock_extract.assert_called_once_with(event)
    mock_embed.assert_called_once_with(mock_sig)
    mock_write.assert_called_once()
    assert state["signature"] == embedded_sig


async def test_pipeline_skips_write_when_extract_returns_none() -> None:
    from core.orchestrator.pipeline import pipeline

    event = _make_event()

    with (
        patch("core.ingestor.signature.extract", new_callable=AsyncMock, return_value=None),
        patch("core.embeddings.pipeline.embed", new_callable=AsyncMock) as mock_embed,
        patch("core.graph.writer.write", new_callable=AsyncMock) as mock_write,
        patch("core.graph.scoring.recompute_fragility", new_callable=AsyncMock) as mock_recompute,
    ):
        state = await pipeline.ainvoke(
            {
                "event": event,
                "signature": None,
                "predictions": [],
                "at_risk": [],
                "fragility_scores": {},
            }
        )

    assert state["signature"] is None
    mock_embed.assert_not_called()
    mock_write.assert_not_called()
    mock_recompute.assert_not_called()


async def test_pipeline_state_has_predictions() -> None:
    from core.orchestrator.pipeline import pipeline

    event = _make_event(changed_files=["src/auth.py"])
    mock_sig = _make_sig()
    dedup_result = DedupResult(kind=DedupKind.NEW, matched_id=None, similarity=None)

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    expected_predictions = [
        {
            "id": "sig-1",
            "match_type": "direct",
            "confidence": 0.8,
            "summary": "auth error",
            "category": "build_error",
            "affected_component": "src/auth.py",
            "fragility_score": 0.8,
        }
    ]
    expected_radius = {"at_risk": ["src/auth.py"], "fragility_scores": {"src/auth.py": 0.8}}

    with (
        patch("core.ingestor.signature.extract", new_callable=AsyncMock, return_value=mock_sig),
        patch("core.embeddings.pipeline.embed", new_callable=AsyncMock, return_value=mock_sig),
        patch("core.db.neo4j.neo4j_session", return_value=mock_ctx),
        patch("core.embeddings.dedup.dedup", new_callable=AsyncMock, return_value=dedup_result),
        patch("core.graph.writer.write", new_callable=AsyncMock),
        patch("core.graph.scoring.recompute_fragility", new_callable=AsyncMock),
        patch(
            "core.agents.predictor.predict_failures",
            new_callable=AsyncMock,
            return_value=expected_predictions,
        ),
        patch(
            "core.graph.blast_radius.get_blast_radius",
            new_callable=AsyncMock,
            return_value=expected_radius,
        ),
    ):
        state = await pipeline.ainvoke(
            {
                "event": event,
                "signature": None,
                "predictions": [],
                "at_risk": [],
                "fragility_scores": {},
            }
        )

    assert state["predictions"] == expected_predictions
    assert state["at_risk"] == ["src/auth.py"]
    assert state["fragility_scores"]["src/auth.py"] == 0.8


async def test_phoenix_state_fields() -> None:
    from core.orchestrator.pipeline import PhoenixState

    event = _make_event()
    state: PhoenixState = {
        "event": event,
        "signature": None,
        "predictions": [],
        "at_risk": [],
        "fragility_scores": {},
    }
    assert state["event"] is event
    assert state["signature"] is None
    assert state["predictions"] == []
    assert state["at_risk"] == []
    assert state["fragility_scores"] == {}
