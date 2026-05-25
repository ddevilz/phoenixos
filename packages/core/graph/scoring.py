import logging
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

import networkx as nx
from neo4j import AsyncSession

logger = logging.getLogger(__name__)

_PAGERANK_ALPHA = 0.85

_CYPHER_FETCH_GRAPH = (
    "MATCH (a:FailureSignature) "
    "OPTIONAL MATCH (a)-[r:SIMILAR_TO]->(b:FailureSignature) "
    "RETURN a.id AS src, b.id AS dst, r.similarity AS weight"
)

_CYPHER_WRITE_SCORES = (
    "UNWIND $scores AS row "
    "MATCH (s:FailureSignature {id: row.id}) "
    "SET s.fragility_score = row.score"
)

_CYPHER_FETCH_COMPONENT = (
    "MATCH (s:FailureSignature {affected_component: $component}) "
    "WHERE s.last_seen >= $since AND s.last_seen <= $now "
    "RETURN s.last_seen AS last_seen, s.occurrence_count AS count"
)


async def recompute_fragility(session: AsyncSession) -> dict[str, float]:
    try:
        result = await session.run(_CYPHER_FETCH_GRAPH)
        records = await result.data()

        G: nx.DiGraph = nx.DiGraph()
        for row in records:
            G.add_node(row["src"])
            if row["dst"] is not None:
                weight = row["weight"] if row["weight"] is not None else 1.0
                G.add_edge(row["src"], row["dst"], weight=weight)

        if len(G) == 0:
            return {}

        scores: dict[str, float] = nx.pagerank(G, weight="weight", alpha=_PAGERANK_ALPHA)

        await session.run(
            _CYPHER_WRITE_SCORES,
            scores=[{"id": k, "score": v} for k, v in scores.items()],
        )

        return scores
    except Exception as exc:
        logger.error("FragilityScore recompute failed: %s", exc)
        return {}


class _Bucket(TypedDict):
    start: datetime
    end: datetime
    count: int


async def get_flakiness_trajectory(
    component: str,
    session: AsyncSession,
    window_days: int = 28,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=window_days)
    bucket_size = timedelta(days=window_days / 4)

    buckets: list[_Bucket] = [
        {
            "start": since + i * bucket_size,
            "end": since + (i + 1) * bucket_size,
            "count": 0,
        }
        for i in range(4)
    ]

    result = await session.run(
        _CYPHER_FETCH_COMPONENT,
        component=component,
        since=since.isoformat(),
        now=now.isoformat(),
    )
    records = await result.data()

    for record in records:
        last_seen = datetime.fromisoformat(str(record["last_seen"]))
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        idx = int((last_seen - since) / bucket_size)
        idx = max(0, min(3, idx))
        buckets[idx]["count"] += record["count"] or 0

    first = buckets[0]["count"]
    last = buckets[3]["count"]

    if first == 0 and last == 0:
        trajectory = "stable"
    elif first == 0 or last > first * 1.5:
        trajectory = "rising"
    elif last < first * 0.67:
        trajectory = "falling"
    else:
        trajectory = "stable"

    return {
        "component": component,
        "trajectory": trajectory,
        "window_days": window_days,
        "buckets": [
            {
                "start": b["start"].date().isoformat(),
                "end": b["end"].date().isoformat(),
                "count": b["count"],
            }
            for b in buckets
        ],
    }
