import logging
from typing import Any

from core.judge.base import BaseJudge, _extract_json
from core.models.failure import JudgeResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a regression detection specialist with access to a failure history graph.

Review the PR diff against the past failure signatures provided. Check if this diff:
1. Resembles patterns that caused past failures
2. Touches components with high fragility scores (> 0.7)
3. Re-introduces previously fixed issues

Respond with a JSON object only:
{
  "score": <0.0-1.0>,
  "verdict": "<pass|warn|block>",
  "reasoning": "<1-3 sentence explanation>",
  "flags": ["<past signature ID or pattern that matches>", ...]
}

Scoring: score > 0.7 = pass, 0.4-0.7 = warn, < 0.4 = block.
If no regression risk found, return score=1.0, verdict="pass", flags=[]."""


async def fetch_similar_signatures(
    changed_files: list[str], session: Any, limit: int = 5
) -> list[dict[str, Any]]:
    """Query Neo4j for top-N FailureSignatures affecting changed_files."""
    if not changed_files:
        return []
    try:
        result = await session.run(
            """
            MATCH (s:FailureSignature)
            WHERE s.affected_component IN $files
            RETURN s.id AS id, s.summary AS summary, s.category AS category,
                   s.affected_component AS affected_component,
                   coalesce(s.fragility_score, 0.0) AS fragility_score
            ORDER BY s.fragility_score DESC
            LIMIT $limit
            """,
            files=changed_files,
            limit=limit,
        )
        return await result.data()
    except Exception as exc:
        logger.error("Failed to fetch similar signatures: %s", exc)
        return []


class RegressionJudge(BaseJudge):
    name = "regression"
    timeout_result = JudgeResult(
        judge="regression",
        score=0.5,
        verdict="warn",
        reasoning="Regression judge timed out — could not complete historical analysis.",
        flags=["judge_timeout"],
    )

    def _build_messages(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        diff = context.get("diff", "(no diff provided)")
        signatures: list[dict[str, Any]] = context.get("similar_signatures", [])

        if signatures:
            sig_lines = []
            for s in signatures:
                sig_lines.append(
                    f"- [{s['id'][:8]}] {s['category']} in {s['affected_component']} "
                    f"(fragility={s.get('fragility_score', 0):.2f}): {s['summary']}"
                )
            sig_section = "Past failure signatures:\n" + "\n".join(sig_lines)
        else:
            sig_section = "Past failure signatures: (none found — first-time component)"

        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"{sig_section}\n\nDiff:\n```diff\n{diff}\n```"},
        ]

    def _parse_response(self, raw: str) -> JudgeResult:
        data = _extract_json(raw)
        return JudgeResult(
            judge="regression",
            score=float(data["score"]),
            verdict=data["verdict"],
            reasoning=data.get("reasoning", ""),
            flags=data.get("flags", []),
        )
