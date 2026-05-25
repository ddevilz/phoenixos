import logging

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph")


@router.get("/fragility")
async def get_fragility_scores():
    from core.db.neo4j import neo4j_session

    try:
        async with neo4j_session() as session:
            result = await session.run(
                "MATCH (s:FailureSignature) "
                "RETURN s.id AS id, s.fragility_score AS fragility_score"
            )
            return await result.data()
    except Exception as exc:
        logger.error("Fragility scores query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Graph database unavailable")


@router.post("/fragility/recompute")
async def force_recompute_fragility():
    from core.db.neo4j import neo4j_session
    from core.graph.scoring import recompute_fragility

    try:
        async with neo4j_session() as session:
            scores = await recompute_fragility(session)
        return {"recomputed": len(scores)}
    except Exception as exc:
        logger.error("Fragility recompute failed: %s", exc)
        raise HTTPException(status_code=503, detail="Graph database unavailable")


@router.get("/flakiness/{component:path}")
async def get_flakiness(
    component: str,
    window_days: int = Query(default=28, ge=1, le=365),
):
    from core.db.neo4j import neo4j_session
    from core.graph.scoring import get_flakiness_trajectory

    try:
        async with neo4j_session() as session:
            return await get_flakiness_trajectory(component, session, window_days)
    except Exception as exc:
        logger.error("Flakiness trajectory query failed for %s: %s", component, exc)
        raise HTTPException(status_code=503, detail="Graph database unavailable")
