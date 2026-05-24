import asyncio
import logging

from openai import AsyncOpenAI

from core.models.failure import FailureSignature

logger = logging.getLogger(__name__)

_TIMEOUT: float = 10.0
_MODEL = "text-embedding-3-small"

_openai_client: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI()
    return _openai_client


async def embed_text(text: str) -> list[float]:
    """Call OpenAI embeddings API and return 1536-dim vector. Raises on error."""
    response = await asyncio.wait_for(
        _get_openai().embeddings.create(
            model=_MODEL,
            input=text,
        ),
        timeout=_TIMEOUT,
    )
    return response.data[0].embedding


async def embed(signature: FailureSignature) -> FailureSignature:
    """Fill FailureSignature.embedding via OpenAI text-embedding-3-small.

    Returns model_copy with embedding filled on success.
    Returns signature unchanged (embedding stays []) on any error — logs error.
    """
    text = f"{signature.category} {signature.summary} {signature.affected_component}"
    try:
        vector = await embed_text(text)
    except Exception as exc:
        logger.error("Embedding failed for signature %s: %s", signature.id, exc)
        return signature
    return signature.model_copy(update={"embedding": vector})
