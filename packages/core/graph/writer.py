import logging
from datetime import datetime, timezone

from neo4j import AsyncSession

from core.embeddings.dedup import DedupKind, DedupResult
from core.models.failure import FailureSignature

logger = logging.getLogger(__name__)

_CYPHER_EXACT = (
    "MATCH (s:FailureSignature {id: $matched_id}) "
    "SET s.last_seen = $last_seen, "
    "s.occurrence_count = s.occurrence_count + 1"
)

_CYPHER_NEW = (
    "MERGE (s:FailureSignature {id: $id}) "
    "ON CREATE SET "
    "s.summary = $summary, "
    "s.category = $category, "
    "s.affected_component = $affected_component, "
    "s.embedding = $embedding, "
    "s.first_seen = $first_seen, "
    "s.last_seen = $last_seen, "
    "s.occurrence_count = $occurrence_count "
    "ON MATCH SET "
    "s.last_seen = $last_seen, "
    "s.occurrence_count = s.occurrence_count + 1"
)

_CYPHER_SIMILAR = (
    "MERGE (s:FailureSignature {id: $id}) "
    "ON CREATE SET "
    "s.summary = $summary, "
    "s.category = $category, "
    "s.affected_component = $affected_component, "
    "s.embedding = $embedding, "
    "s.first_seen = $first_seen, "
    "s.last_seen = $last_seen, "
    "s.occurrence_count = $occurrence_count "
    "WITH s "
    "MATCH (existing:FailureSignature {id: $matched_id}) "
    "MERGE (s)-[r:SIMILAR_TO]->(existing) "
    "ON CREATE SET r.similarity = $similarity, "
    "r.created_at = $created_at"
)


async def write(
    signature: FailureSignature,
    dedup_result: DedupResult,
    session: AsyncSession,
) -> None:
    """Write FailureSignature to Neo4j based on dedup decision. Logs errors, never raises."""
    try:
        if dedup_result.kind == DedupKind.SIMILAR and not dedup_result.matched_id:
            logger.warning(
                "SIMILAR result has no matched_id for signature %s — writing as NEW",
                signature.id,
            )
            await session.run(
                _CYPHER_NEW,
                id=signature.id,
                summary=signature.summary,
                category=signature.category,
                affected_component=signature.affected_component,
                embedding=signature.embedding,
                first_seen=signature.first_seen.isoformat(),
                last_seen=signature.last_seen.isoformat(),
                occurrence_count=signature.occurrence_count,
            )
        elif dedup_result.kind == DedupKind.EXACT:
            await session.run(
                _CYPHER_EXACT,
                matched_id=dedup_result.matched_id,
                last_seen=signature.last_seen.isoformat(),
            )
        elif dedup_result.kind == DedupKind.NEW:
            await session.run(
                _CYPHER_NEW,
                id=signature.id,
                summary=signature.summary,
                category=signature.category,
                affected_component=signature.affected_component,
                embedding=signature.embedding,
                first_seen=signature.first_seen.isoformat(),
                last_seen=signature.last_seen.isoformat(),
                occurrence_count=signature.occurrence_count,
            )
        else:
            await session.run(
                _CYPHER_SIMILAR,
                id=signature.id,
                summary=signature.summary,
                category=signature.category,
                affected_component=signature.affected_component,
                embedding=signature.embedding,
                first_seen=signature.first_seen.isoformat(),
                last_seen=signature.last_seen.isoformat(),
                occurrence_count=signature.occurrence_count,
                matched_id=dedup_result.matched_id,
                similarity=dedup_result.similarity,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
    except Exception as exc:
        logger.error("Graph write failed for signature %s: %s", signature.id, exc)
