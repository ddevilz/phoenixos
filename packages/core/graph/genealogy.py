import logging
from typing import Any

logger = logging.getLogger(__name__)


async def get_fix_genealogy(fix_id: str, session: Any) -> dict[str, Any]:
    _empty: dict[str, Any] = {"fix_id": fix_id, "depth": 0, "chain": [], "warning": None}
    try:
        result = await session.run(
            """
            MATCH path = (f:Fix {id: $fix_id})-[:SUPPRESSED_BY*0..]->(root:Fix)
            WHERE NOT (root)-[:SUPPRESSED_BY]->()
            RETURN [n IN nodes(path) | {
                id: n.id,
                description: n.description,
                author_type: n.author_type,
                commit_sha: n.commit_sha,
                timestamp: n.timestamp
            }] AS chain,
            length(path) AS depth
            """,
            fix_id=fix_id,
        )
        records = await result.data()
        if not records:
            return _empty
        record = records[0]
        depth: int = record["depth"]
        chain: list[dict[str, Any]] = record["chain"]
        warning = "symptom suppression chain detected" if depth > 2 else None
        return {"fix_id": fix_id, "depth": depth, "chain": chain, "warning": warning}
    except Exception as exc:
        logger.error("Fix genealogy query failed for %s: %s", fix_id, exc)
        return _empty
