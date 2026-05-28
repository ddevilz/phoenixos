import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from core.models.failure import FailureEvent, FailureSignature


def _make_event(**overrides) -> FailureEvent:
    defaults = dict(
        id="evt-1",
        repo="owner/repo",
        run_id="99",
        workflow="CI",
        job="CI",
        step="unknown",
        exit_code=1,
        log_tail="ImportError: cannot import name 'validate' from 'core.auth'",
        changed_files=["src/auth.py"],
        timestamp=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return FailureEvent(**defaults)


def _json_response(summary: str, category: str, component: str) -> str:
    return json.dumps({
        "summary": summary,
        "category": category,
        "affected_component": component,
    })


async def test_extract_returns_failure_signature():
    from core.ingestor.signature import extract

    with patch(
        "core.ingestor.signature._stream_completion",
        new_callable=AsyncMock,
        return_value=_json_response(
            "ImportError in auth module prevents startup", "build_error", "src/auth.py"
        ),
    ):
        result = await extract(_make_event())

    assert result is not None
    assert isinstance(result, FailureSignature)
    assert result.summary == "ImportError in auth module prevents startup"
    assert result.category == "build_error"
    assert result.affected_component == "src/auth.py"
    assert result.embedding == []
    assert result.occurrence_count == 1
    assert result.first_seen == result.last_seen


async def test_extract_returns_none_on_llm_error():
    from core.ingestor.signature import extract

    with patch(
        "core.ingestor.signature._stream_completion",
        new_callable=AsyncMock,
        side_effect=Exception("API error"),
    ):
        result = await extract(_make_event())

    assert result is None


async def test_extract_returns_none_on_timeout():
    import asyncio

    from core.ingestor.signature import extract

    async def slow(*args, **kwargs):
        await asyncio.sleep(100)

    with patch("core.ingestor.signature._stream_completion", side_effect=slow), patch(
        "core.ingestor.signature._TIMEOUT", 0.01
    ):
        result = await extract(_make_event())

    assert result is None


async def test_extract_uses_log_tail_in_prompt():
    from core.ingestor.signature import extract

    captured: list[list[dict]] = []

    async def capture(messages):
        captured.append(messages)
        return _json_response("desc", "test_failure", "src/test.py")

    with patch("core.ingestor.signature._stream_completion", side_effect=capture):
        await extract(_make_event(log_tail="FATAL: connection refused on port 5432"))

    full_text = " ".join(m["content"] for m in captured[0])
    assert "connection refused on port 5432" in full_text
