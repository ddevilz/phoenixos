import math
from enum import Enum

from neo4j import AsyncSession
from pydantic import BaseModel

from core.models.failure import FailureSignature

EXACT_THRESHOLD: float = 0.92
SIMILAR_THRESHOLD: float = 0.80


class DedupKind(str, Enum):
    EXACT = "exact"
    SIMILAR = "similar"
    NEW = "new"


class DedupResult(BaseModel):
    kind: DedupKind
    matched_id: str | None
    similarity: float | None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure Python cosine similarity. Returns 0.0 for zero vectors or mismatched lengths."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def dedup(signature: FailureSignature, session: AsyncSession) -> DedupResult:
    """Compare signature embedding against existing Neo4j nodes.

    Returns decision only — no writes.
    """
    if not signature.embedding:
        return DedupResult(kind=DedupKind.NEW, matched_id=None, similarity=None)

    result = await session.run(
        "MATCH (s:FailureSignature) WHERE s.embedding IS NOT NULL "
        "RETURN s.id AS id, s.embedding AS embedding"
    )
    records = await result.data()

    if not records:
        return DedupResult(kind=DedupKind.NEW, matched_id=None, similarity=None)

    best_id: str | None = None
    best_score: float = 0.0
    for record in records:
        score = cosine_similarity(signature.embedding, record["embedding"])
        if score > best_score:
            best_score = score
            best_id = record["id"]

    if best_score >= EXACT_THRESHOLD:
        return DedupResult(kind=DedupKind.EXACT, matched_id=best_id, similarity=best_score)
    if best_score >= SIMILAR_THRESHOLD:
        return DedupResult(kind=DedupKind.SIMILAR, matched_id=best_id, similarity=best_score)
    return DedupResult(kind=DedupKind.NEW, matched_id=None, similarity=best_score)
