import logging
from typing import Any

logger = logging.getLogger(__name__)


async def get_blast_radius(changed_files: list[str], session: Any) -> dict[str, Any]:
    if not changed_files:
        return {"at_risk": [], "fragility_scores": {}}
    try:
        direct_result = await session.run(
            """
            MATCH (s:FailureSignature)
            WHERE s.affected_component IN $changed_files
            RETURN s.affected_component AS component,
                   coalesce(s.fragility_score, 0.0) AS fragility_score
            """,
            changed_files=changed_files,
        )
        direct_records = await direct_result.data()

        similar_result = await session.run(
            """
            MATCH (s:FailureSignature)-[:SIMILAR_TO]->(related:FailureSignature)
            WHERE s.affected_component IN $changed_files
              AND NOT related.affected_component IN $changed_files
            RETURN related.affected_component AS component,
                   coalesce(related.fragility_score, 0.0) AS fragility_score
            """,
            changed_files=changed_files,
        )
        similar_records = await similar_result.data()

        scores: dict[str, float] = {}
        for record in direct_records + similar_records:
            comp: str = record["component"]
            score: float = record["fragility_score"]
            if comp not in scores or score > scores[comp]:
                scores[comp] = score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
        at_risk = [comp for comp, _ in ranked]
        fragility_scores = {comp: score for comp, score in ranked}
        return {"at_risk": at_risk, "fragility_scores": fragility_scores}
    except Exception as exc:
        logger.error("Blast radius query failed: %s", exc)
        return {"at_risk": [], "fragility_scores": {}}
