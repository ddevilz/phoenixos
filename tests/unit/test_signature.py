import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from core.models.failure import FailureEvent, FailureSignature, FailureSignatureExtract


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


def _mock_openai_response(summary: str, category: str, component: str):
    """Build a mock that mimics client.chat.completions.create() response."""
    payload = json.dumps({
        "summary": summary,
        "category": category,
        "affected_component": component,
    })
    choice = MagicMock()
    choice.message.content = payload
    response = MagicMock()
    response.choices = [choice]
    return response


async def test_extract_returns_failure_signature():
    from core.ingestor.signature import extract

    mock_response = _mock_openai_response(
        summary="ImportError in auth module prevents startup",
        category="build_error",
        component="src/auth.py",
    )

    with patch("core.ingestor.signature._get_openai") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

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

    with patch("core.ingestor.signature._get_openai") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )
        mock_get_client.return_value = mock_client

        result = await extract(_make_event())

    assert result is None


async def test_extract_returns_none_on_timeout():
    import asyncio

    from core.ingestor.signature import extract

    async def slow_create(*args, **kwargs):
        await asyncio.sleep(100)

    with patch("core.ingestor.signature._get_openai") as mock_get_client, patch(
        "core.ingestor.signature._TIMEOUT", 0.01
    ):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = slow_create
        mock_get_client.return_value = mock_client

        result = await extract(_make_event())

    assert result is None


async def test_extract_uses_log_tail_in_prompt():
    """Verify log_tail content is included in the LLM call."""
    from core.ingestor.signature import extract

    mock_response = _mock_openai_response("desc", "test_failure", "src/test.py")
    captured_messages = []

    async def capture_create(*args, **kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return mock_response

    with patch("core.ingestor.signature._get_openai") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = capture_create
        mock_get_client.return_value = mock_client

        await extract(_make_event(log_tail="FATAL: connection refused on port 5432"))

    full_text = " ".join(m["content"] for m in captured_messages)
    assert "connection refused on port 5432" in full_text
