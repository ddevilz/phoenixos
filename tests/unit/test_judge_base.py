import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

from core.models.failure import JudgeResult
from core.judge.base import BaseJudge, _extract_json


# ── Concrete stub for testing ─────────────────────────────────────────────────

class _StubJudge(BaseJudge):
    name = "behavior"
    timeout_result = JudgeResult(
        judge="behavior", score=0.5, verdict="warn",
        reasoning="timeout", flags=["judge_timeout"],
    )

    def _build_messages(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"role": "user", "content": context.get("diff", "")}]

    def _parse_response(self, raw: str) -> JudgeResult:
        data = _extract_json(raw)
        return JudgeResult(
            judge="behavior",
            score=data["score"],
            verdict=data["verdict"],
            reasoning=data["reasoning"],
            flags=data.get("flags", []),
        )


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_judge_returns_parsed_result_on_success() -> None:
    import json

    raw = json.dumps({"score": 0.9, "verdict": "pass", "reasoning": "looks good", "flags": []})

    with patch("core.judge.base._stream_text", new_callable=AsyncMock, return_value=raw):
        result = await _StubJudge().judge({"diff": "some diff"})

    assert result.score == 0.9
    assert result.verdict == "pass"
    assert result.flags == []
    assert result.judge == "behavior"


async def test_judge_returns_timeout_result_on_timeout() -> None:
    async def slow(*args, **kwargs):
        await asyncio.sleep(100)

    with patch("core.judge.base._stream_text", side_effect=slow), \
         patch("core.judge.base._JUDGE_TIMEOUT", 0.01):
        result = await _StubJudge().judge({"diff": "some diff"})

    assert result.verdict == "warn"
    assert "judge_timeout" in result.flags


async def test_judge_returns_timeout_result_on_llm_error() -> None:
    with patch("core.judge.base._stream_text", new_callable=AsyncMock,
               side_effect=Exception("API error")):
        result = await _StubJudge().judge({"diff": "some diff"})

    assert result.verdict == "warn"
    assert result.score == 0.5


async def test_extract_json_strips_markdown_fences() -> None:
    raw = "Here is the result:\n```json\n{\"score\": 0.8}\n```"
    data = _extract_json(raw)
    assert data["score"] == 0.8


async def test_extract_json_plain_json() -> None:
    raw = '{"score": 0.5, "verdict": "warn"}'
    data = _extract_json(raw)
    assert data["verdict"] == "warn"
