import logging
from typing import Any

logger = logging.getLogger(__name__)


async def predict_failures(changed_files: list[str], session: Any) -> list[dict[str, Any]]:
    if not changed_files:
        return []
    try:
        direct_result = await session.run(
            """
            MATCH (s:FailureSignature)
            WHERE s.affected_component IN $changed_files
            RETURN s.id AS id, s.summary AS summary, s.category AS category,
                   s.affected_component AS affected_component,
                   coalesce(s.fragility_score, 0.0) AS fragility_score,
                   true AS direct
            """,
            changed_files=changed_files,
        )
        direct_records = await direct_result.data()

        similar_result = await session.run(
            """
            MATCH (s:FailureSignature)-[:SIMILAR_TO]->(related:FailureSignature)
            WHERE s.affected_component IN $changed_files
              AND NOT related.affected_component IN $changed_files
            RETURN related.id AS id, related.summary AS summary,
                   related.category AS category,
                   related.affected_component AS affected_component,
                   coalesce(related.fragility_score, 0.0) AS fragility_score,
                   false AS direct
            """,
            changed_files=changed_files,
        )
        similar_records = await similar_result.data()

        seen: dict[str, dict[str, Any]] = {}
        for record in direct_records:
            entry = dict(record)
            entry["match_type"] = "direct"
            entry["confidence"] = entry["fragility_score"] * 1.0
            seen[entry["id"]] = entry

        for record in similar_records:
            entry = dict(record)
            if entry["id"] not in seen:
                entry["match_type"] = "similar"
                entry["confidence"] = entry["fragility_score"] * 0.7
                seen[entry["id"]] = entry

        ranked = sorted(seen.values(), key=lambda x: x["confidence"], reverse=True)
        return [
            {
                "id": r["id"],
                "summary": r["summary"],
                "category": r["category"],
                "affected_component": r["affected_component"],
                "fragility_score": r["fragility_score"],
                "confidence": r["confidence"],
                "match_type": r["match_type"],
            }
            for r in ranked[:10]
        ]
    except Exception as exc:
        logger.error("Failure prediction failed: %s", exc)
        return []
