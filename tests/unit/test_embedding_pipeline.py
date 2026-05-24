from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from core.models.failure import FailureSignature


def _make_signature(**overrides) -> FailureSignature:
    defaults = dict(
        id="sig-1",
        summary="ImportError in auth module prevents startup",
        category="build_error",
        affected_component="src/auth.py",
        embedding=[],
        first_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
        occurrence_count=1,
    )
    defaults.update(overrides)
    return FailureSignature(**defaults)


def _mock_client(vector: list[float] | None = None) -> MagicMock:
    """Build a mock AsyncOpenAI client whose embeddings.create returns vector."""
    v = vector if vector is not None else [0.1] * 1536
    embedding_obj = MagicMock()
    embedding_obj.embedding = v
    response = MagicMock()
    response.data = [embedding_obj]
    client = MagicMock()
    client.embeddings.create = AsyncMock(return_value=response)
    return client


async def test_embed_text_calls_correct_model() -> None:
    from core.embeddings.pipeline import embed_text

    mock_client = _mock_client()
    with patch("core.embeddings.pipeline._get_openai", return_value=mock_client):
        result = await embed_text("some failure text")

    mock_client.embeddings.create.assert_called_once()
    call_kwargs = mock_client.embeddings.create.call_args.kwargs
    assert call_kwargs["model"] == "text-embedding-3-small"
    assert result == [0.1] * 1536


async def test_embed_text_passes_correct_input_text() -> None:
    from core.embeddings.pipeline import embed_text

    captured: list[dict] = []

    async def capture(**kwargs):
        captured.append(kwargs)
        embedding_obj = MagicMock()
        embedding_obj.embedding = [0.2] * 1536
        resp = MagicMock()
        resp.data = [embedding_obj]
        return resp

    mock_client = MagicMock()
    mock_client.embeddings.create = capture

    with patch("core.embeddings.pipeline._get_openai", return_value=mock_client):
        await embed_text("connection refused on port 5432")

    assert len(captured) == 1
    assert captured[0]["input"] == "connection refused on port 5432"


async def test_embed_assembles_correct_text_format() -> None:
    from core.embeddings.pipeline import embed

    captured: list[str] = []

    async def capture(**kwargs):
        captured.append(kwargs["input"])
        embedding_obj = MagicMock()
        embedding_obj.embedding = [0.1] * 1536
        resp = MagicMock()
        resp.data = [embedding_obj]
        return resp

    mock_client = MagicMock()
    mock_client.embeddings.create = capture

    # category="build_error", summary="ImportError...", affected_component="src/auth.py"
    sig = _make_signature()
    with patch("core.embeddings.pipeline._get_openai", return_value=mock_client):
        await embed(sig)

    assert len(captured) == 1
    assert captured[0] == "build_error ImportError in auth module prevents startup src/auth.py"


async def test_embed_returns_signature_with_filled_embedding() -> None:
    from core.embeddings.pipeline import embed

    vector = [0.1] * 1536
    mock_client = _mock_client(vector)
    sig = _make_signature()

    with patch("core.embeddings.pipeline._get_openai", return_value=mock_client):
        result = await embed(sig)

    assert result.embedding == vector
    # All other fields unchanged
    assert result.id == sig.id
    assert result.summary == sig.summary
    assert result.category == sig.category
    assert result.affected_component == sig.affected_component
    assert result.occurrence_count == sig.occurrence_count
    assert result.first_seen == sig.first_seen


async def test_embed_returns_signature_unchanged_on_api_error() -> None:
    from core.embeddings.pipeline import embed

    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock(side_effect=Exception("API unavailable"))
    sig = _make_signature()

    with patch("core.embeddings.pipeline._get_openai", return_value=mock_client):
        result = await embed(sig)

    assert result.embedding == []
    assert result.id == sig.id
