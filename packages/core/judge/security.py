import logging
from typing import Any, Literal

from core.judge.base import BaseJudge, _extract_json
from core.models.failure import JudgeResult

logger = logging.getLogger(__name__)

_SSRF_FLAGS = {"ssrf", "server-side request forgery"}
_INJECTION_FLAGS = {
    "injection", "sql injection", "shell injection",
    "template injection", "command injection",
}

_SYSTEM_PROMPT = """\
You are a security code reviewer.

Review the PR diff for security issues. Check for:
1. SSRF risk — user-controlled URLs passed to HTTP clients
2. Injection vectors — SQL, shell, template, or command injection
3. Hardcoded secrets, API keys, tokens, or passwords
4. Unsafe deserialization or pickle usage
5. New dependencies that may introduce vulnerabilities

CRITICAL RULE: If you find SSRF or injection, set score=0.2 and verdict="block".

Respond with a JSON object only:
{
  "score": <0.0-1.0>,
  "verdict": "<pass|warn|block>",
  "reasoning": "<1-3 sentence explanation>",
  "flags": ["<specific security issue>", ...]
}

Scoring: score > 0.7 = pass, 0.4-0.7 = warn, < 0.4 = block.
If no issues found, return score=1.0, verdict="pass", flags=[]."""


def _has_critical_flag(flags: list[str]) -> bool:
    """Return True if any flag mentions SSRF or injection."""
    lowered = [f.lower() for f in flags]
    return any(kw in flag for flag in lowered for kw in _SSRF_FLAGS | _INJECTION_FLAGS)


class SecurityJudge(BaseJudge):
    name = "security"
    timeout_result = JudgeResult(
        judge="security",
        score=0.3,
        verdict="block",
        reasoning="Security judge timed out — defaulting to block on uncertainty.",
        flags=["judge_timeout"],
    )

    def _build_messages(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        diff = context.get("diff", "(no diff provided)")
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Diff:\n```diff\n{diff}\n```"},
        ]

    def _parse_response(self, raw: str) -> JudgeResult:
        data = _extract_json(raw)
        flags: list[str] = data.get("flags", [])
        score = float(data["score"])
        verdict: Literal["pass", "warn", "block"] = data["verdict"]

        # Enforce critical flag override regardless of what the LLM scored
        if _has_critical_flag(flags):
            score = 0.2
            verdict = "block"

        return JudgeResult(
            judge="security",
            score=score,
            verdict=verdict,
            reasoning=data.get("reasoning", ""),
            flags=flags,
        )
