import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from core.models.failure import AggregateScore

logger = logging.getLogger(__name__)


async def write_eval_result(
    pr_url: str,
    changed_files: list[str],
    aggregate: AggregateScore,
    session: Any,
) -> str:
    """
    Write the eval result to Neo4j.

    Creates an EvalResult node and ContractViolation nodes for any
    flagged behavioral issues, linked to matching FailureSignature nodes.
    Returns the EvalResult node ID.
    """
    eval_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Write EvalResult node
    await session.run(
        """
        MERGE (e:EvalResult {id: $id})
        SET e.pr_url = $pr_url,
            e.trust_score = $trust_score,
            e.verdict = $verdict,
            e.evaluated_at = $evaluated_at,
            e.changed_files = $changed_files
        """,
        id=eval_id,
        pr_url=pr_url,
        trust_score=aggregate.trust_score,
        verdict=aggregate.verdict,
        evaluated_at=now,
        changed_files=changed_files,
    )

    # Write ContractViolation nodes for behavior flags
    behavior_results = [r for r in aggregate.judge_results if r.judge == "behavior" and r.flags]
    for result in behavior_results:
        for flag in result.flags:
            if flag == "judge_timeout":
                continue
            violation_id = str(uuid.uuid4())
            await session.run(
                """
                MERGE (v:ContractViolation {id: $id})
                SET v.description = $description,
                    v.eval_id = $eval_id,
                    v.detected_at = $detected_at
                WITH v
                MATCH (e:EvalResult {id: $eval_id})
                MERGE (e)-[:FLAGGED]->(v)
                """,
                id=violation_id,
                description=flag,
                eval_id=eval_id,
                detected_at=now,
            )

    # Link EvalResult to FailureSignatures for components in changed_files
    if changed_files:
        await session.run(
            """
            MATCH (s:FailureSignature)
            WHERE s.affected_component IN $changed_files
            MATCH (e:EvalResult {id: $eval_id})
            MERGE (e)-[:COVERS]->(s)
            """,
            changed_files=changed_files,
            eval_id=eval_id,
        )

    logger.info(
        "eval_id=%s verdict=%s trust_score=%.3f files=%d",
        eval_id, aggregate.verdict, aggregate.trust_score, len(changed_files),
    )
    return eval_id
