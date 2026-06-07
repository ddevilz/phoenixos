import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.ws import broadcast_event
from core.db.neo4j import neo4j_session
from core.ingestor.diff_parser import fetch_and_parse, parse_from_raw
from core.judge.behavior import BehaviorJudge
from core.judge.graph_writer import write_eval_result
from core.judge.regression import RegressionJudge, fetch_similar_signatures
from core.judge.scorer import aggregate
from core.judge.security import SecurityJudge
from core.models.failure import AggregateScore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/evals")


@router.get("/history")
async def eval_history(limit: int = 20):
    """Return recent EvalResult nodes from Neo4j, newest first."""
    try:
        async with neo4j_session() as session:
            result = await session.run(
                """
                MATCH (e:EvalResult)
                OPTIONAL MATCH (e)-[:FLAGGED]->(v:ContractViolation)
                RETURN e.id AS id,
                       e.pr_url AS pr_url,
                       e.trust_score AS trust_score,
                       e.verdict AS verdict,
                       e.evaluated_at AS evaluated_at,
                       e.changed_files AS changed_files,
                       collect(v.description) AS flags
                ORDER BY e.evaluated_at DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            rows = await result.data()
        return rows
    except Exception as exc:
        logger.error("Eval history query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Graph database unavailable")


class EvalRequest(BaseModel):
    pr_url: str | None = None
    diff: str | None = None


@router.post("/run", response_model=AggregateScore)
async def run_eval(body: EvalRequest) -> AggregateScore:
    if not body.pr_url and not body.diff:
        raise HTTPException(status_code=422, detail="Provide either pr_url or diff")

    token = os.environ.get("GITHUB_TOKEN")

    # ── 1. Parse the diff ────────────────────────────────────────────────────
    if body.pr_url:
        try:
            pr_diff = await fetch_and_parse(body.pr_url, token=token)
        except Exception as exc:
            logger.error("PR diff fetch failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"GitHub fetch failed: {exc}")
    else:
        pr_diff = parse_from_raw(body.diff or "")

    # ── 2. Fetch similar signatures for the regression judge ─────────────────
    similar_signatures: list[dict] = []
    try:
        async with neo4j_session() as session:
            similar_signatures = await fetch_similar_signatures(pr_diff.changed_files, session)
    except Exception as exc:
        logger.warning("Could not fetch similar signatures: %s", exc)

    # ── 3. Fan out all 3 judges in parallel ──────────────────────────────────
    behavior_ctx = {"diff": pr_diff.diff, "test_contents": pr_diff.test_contents}
    security_ctx = {"diff": pr_diff.diff}
    regression_ctx = {"diff": pr_diff.diff, "similar_signatures": similar_signatures}

    behavior_result, security_result, regression_result = await asyncio.gather(
        BehaviorJudge().judge(behavior_ctx),
        SecurityJudge().judge(security_ctx),
        RegressionJudge().judge(regression_ctx),
    )

    # ── 4. Aggregate into a trust score ──────────────────────────────────────
    result = aggregate([behavior_result, security_result, regression_result])

    # ── 5. Write eval result to Neo4j (best-effort) ──────────────────────────
    try:
        async with neo4j_session() as session:
            await write_eval_result(
                pr_url=body.pr_url or "(raw diff)",
                changed_files=pr_diff.changed_files,
                aggregate=result,
                session=session,
            )
    except Exception as exc:
        logger.warning("Graph write for eval failed (non-fatal): %s", exc)

    # ── 6. Broadcast over WebSocket ──────────────────────────────────────────
    try:
        await broadcast_event(
            "eval_complete",
            "eval",
            {
                "trust_score": result.trust_score,
                "verdict": result.verdict,
                "pr_url": body.pr_url,
            },
        )
    except Exception as exc:
        logger.warning("WS broadcast failed (non-fatal): %s", exc)

    return result
