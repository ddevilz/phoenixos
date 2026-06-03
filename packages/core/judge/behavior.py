import logging
from typing import Any

from core.judge.base import BaseJudge, _extract_json
from core.models.failure import JudgeResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a code reviewer focused on behavioral contracts.

Review the PR diff and associated test files. Check for:
1. Silent behavioral changes (return type shifts, default value changes, interface narrowing)
2. Tests not updated to reflect changed logic
3. Observable behavior contract breaks (changed function signatures used by callers)

Respond with a JSON object only:
{
  "score": <0.0-1.0>,
  "verdict": "<pass|warn|block>",
  "reasoning": "<1-3 sentence explanation>",
  "flags": ["<specific contract break>", ...]
}

Scoring: score > 0.7 = pass, 0.4-0.7 = warn, < 0.4 = block.
If no issues found, return score=1.0, verdict="pass", flags=[]."""


class BehaviorJudge(BaseJudge):
    name = "behavior"
    timeout_result = JudgeResult(
        judge="behavior",
        score=0.5,
        verdict="warn",
        reasoning="Judge timed out — could not complete behavioral analysis.",
        flags=["judge_timeout"],
    )

    def _build_messages(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        diff = context.get("diff", "(no diff provided)")
        test_contents: dict[str, str] = context.get("test_contents", {})

        test_section = ""
        if test_contents:
            parts = [f"### {path}\n```python\n{src}\n```" for path, src in test_contents.items()]
            test_section = "\n\nTest files:\n" + "\n\n".join(parts)
        else:
            test_section = "\n\nTest files: (none found)"

        user_content = f"Diff:\n```diff\n{diff}\n```{test_section}"
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _parse_response(self, raw: str) -> JudgeResult:
        data = _extract_json(raw)
        return JudgeResult(
            judge="behavior",
            score=float(data["score"]),
            verdict=data["verdict"],
            reasoning=data.get("reasoning", ""),
            flags=data.get("flags", []),
        )
