import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from core.models.failure import FailureEvent, FailureSignature

logger = logging.getLogger(__name__)


class PhoenixState(TypedDict):
    event: FailureEvent
    signature: FailureSignature | None
    predictions: list[dict]
    at_risk: list[str]
    fragility_scores: dict[str, float]


async def _extract_node(state: PhoenixState) -> dict[str, Any]:
    from core.ingestor.signature import extract

    signature = await extract(state["event"])
    if signature is not None:
        from core.api.ws import broadcast_event

        await broadcast_event(
            "signature_extracted",
            state["event"].run_id,
            {
                "signature_id": signature.id,
                "category": signature.category,
                "affected_component": signature.affected_component,
            },
        )
    return {"signature": signature}


async def _embed_node(state: PhoenixState) -> dict[str, Any]:
    from core.embeddings.pipeline import embed

    signature = state["signature"]
    if signature is None:
        return {}
    embedded = await embed(signature)
    return {"signature": embedded}


async def _write_node(state: PhoenixState) -> dict[str, Any]:
    from core.db.neo4j import neo4j_session
    from core.embeddings.dedup import dedup
    from core.graph.scoring import recompute_fragility
    from core.graph.writer import write

    signature = state["signature"]
    if signature is None:
        return {}
    async with neo4j_session() as session:
        result = await dedup(signature, session)
        await write(signature, result, session)
        await recompute_fragility(session)
    from core.api.ws import broadcast_event

    await broadcast_event(
        "graph_updated",
        state["event"].run_id,
        {
            "node_type": "FailureSignature",
            "node_id": signature.id,
        },
    )
    logger.info(
        "signature=%s category=%s dedup=%s run=%s",
        signature.id,
        signature.category,
        result.kind,
        state["event"].run_id,
    )
    return {}


async def _predict_node(state: PhoenixState) -> dict[str, Any]:
    from core.agents.predictor import predict_failures
    from core.db.neo4j import neo4j_session
    from core.graph.blast_radius import get_blast_radius

    changed_files = state["event"].changed_files
    try:
        async with neo4j_session() as session:
            predictions = await predict_failures(changed_files, session)
            radius = await get_blast_radius(changed_files, session)
        return {
            "predictions": predictions,
            "at_risk": radius["at_risk"],
            "fragility_scores": radius["fragility_scores"],
        }
    except Exception as exc:
        logger.error("Predict node failed: %s", exc)
        return {"predictions": [], "at_risk": [], "fragility_scores": {}}


def _route_after_extract(state: PhoenixState) -> str:
    return "embed" if state["signature"] is not None else END


_graph = StateGraph(PhoenixState)
_graph.add_node("extract", _extract_node)
_graph.add_node("embed", _embed_node)
_graph.add_node("write", _write_node)
_graph.add_node("predict", _predict_node)
_graph.add_edge(START, "extract")
_graph.add_conditional_edges("extract", _route_after_extract)
_graph.add_edge("embed", "write")
_graph.add_edge("write", "predict")
_graph.add_edge("predict", END)
pipeline = _graph.compile()
