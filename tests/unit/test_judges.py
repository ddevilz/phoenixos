import json
from unittest.mock import AsyncMock, patch

_DIFF = "- old line\n+ new line"


def _raw(score: float, verdict: str, reasoning: str, flags: list[str]) -> str:
    return json.dumps({"score": score, "verdict": verdict, "reasoning": reasoning, "flags": flags})


# ── Behavior Judge ────────────────────────────────────────────────────────────


async def test_behavior_judge_pass() -> None:
    from core.judge.behavior import BehaviorJudge

    raw = _raw(0.9, "pass", "No contract breaks found.", [])
    with patch("core.judge.base._stream_text", new_callable=AsyncMock, return_value=raw):
        result = await BehaviorJudge().judge({"diff": _DIFF, "test_contents": {}})

    assert result.judge == "behavior"
    assert result.score == 0.9
    assert result.verdict == "pass"
    assert result.flags == []


async def test_behavior_judge_includes_test_contents_in_prompt() -> None:
    from core.judge.behavior import BehaviorJudge

    captured: list[list[dict]] = []

    async def capture(messages):
        captured.append(messages)
        return _raw(0.8, "pass", "ok", [])

    with patch("core.judge.base._stream_text", side_effect=capture):
        await BehaviorJudge().judge(
            {
                "diff": _DIFF,
                "test_contents": {"tests/unit/test_auth.py": "def test_login(): pass"},
            }
        )

    user_msg = captured[0][1]["content"]
    assert "test_auth.py" in user_msg
    assert "test_login" in user_msg


async def test_behavior_judge_timeout_returns_warn() -> None:
    import asyncio

    from core.judge.behavior import BehaviorJudge

    async def slow(_):
        await asyncio.sleep(100)

    with (
        patch("core.judge.base._stream_text", side_effect=slow),
        patch("core.judge.base._JUDGE_TIMEOUT", 0.01),
    ):
        result = await BehaviorJudge().judge({"diff": _DIFF})

    assert result.verdict == "warn"
    assert result.score == 0.5
    assert "judge_timeout" in result.flags


# ── Security Judge ────────────────────────────────────────────────────────────


async def test_security_judge_pass_clean_diff() -> None:
    from core.judge.security import SecurityJudge

    raw = _raw(1.0, "pass", "No security issues.", [])
    with patch("core.judge.base._stream_text", new_callable=AsyncMock, return_value=raw):
        result = await SecurityJudge().judge({"diff": _DIFF})

    assert result.verdict == "pass"
    assert result.score == 1.0


async def test_security_judge_forces_block_on_ssrf_flag() -> None:
    from core.judge.security import SecurityJudge

    # LLM returns warn but flags SSRF — must be overridden to block
    raw = _raw(0.6, "warn", "Possible SSRF.", ["SSRF: user URL passed to httpx"])
    with patch("core.judge.base._stream_text", new_callable=AsyncMock, return_value=raw):
        result = await SecurityJudge().judge({"diff": _DIFF})

    assert result.verdict == "block"
    assert result.score == 0.2


async def test_security_judge_forces_block_on_injection_flag() -> None:
    from core.judge.security import SecurityJudge

    raw = _raw(0.5, "warn", "Injection risk.", ["SQL injection in query builder"])
    with patch("core.judge.base._stream_text", new_callable=AsyncMock, return_value=raw):
        result = await SecurityJudge().judge({"diff": _DIFF})

    assert result.verdict == "block"
    assert result.score == 0.2


async def test_security_judge_timeout_returns_block() -> None:
    import asyncio

    from core.judge.security import SecurityJudge

    async def slow(_):
        await asyncio.sleep(100)

    with (
        patch("core.judge.base._stream_text", side_effect=slow),
        patch("core.judge.base._JUDGE_TIMEOUT", 0.01),
    ):
        result = await SecurityJudge().judge({"diff": _DIFF})

    assert result.verdict == "block"
    assert result.score == 0.3
    assert "judge_timeout" in result.flags


# ── Regression Judge ─────────────────────────────────────────────────────────


async def test_regression_judge_no_signatures_returns_pass() -> None:
    from core.judge.regression import RegressionJudge

    raw = _raw(1.0, "pass", "No prior failures for this component.", [])
    with patch("core.judge.base._stream_text", new_callable=AsyncMock, return_value=raw):
        result = await RegressionJudge().judge({"diff": _DIFF, "similar_signatures": []})

    assert result.verdict == "pass"
    assert result.score == 1.0


async def test_regression_judge_flags_matching_signature() -> None:
    from core.judge.regression import RegressionJudge

    sigs = [
        {
            "id": "abc123def456",
            "summary": "JWT failure",
            "category": "test_failure",
            "affected_component": "src/auth.py",
            "fragility_score": 0.8,
        }
    ]
    raw = _raw(0.3, "block", "Diff resembles past JWT failures.", ["abc123de"])
    with patch("core.judge.base._stream_text", new_callable=AsyncMock, return_value=raw):
        result = await RegressionJudge().judge({"diff": _DIFF, "similar_signatures": sigs})

    assert result.verdict == "block"
    assert "abc123de" in result.flags


async def test_regression_judge_includes_signatures_in_prompt() -> None:
    from core.judge.regression import RegressionJudge

    sigs = [
        {
            "id": "sig-xyz",
            "summary": "DB timeout",
            "category": "flaky",
            "affected_component": "src/db.py",
            "fragility_score": 0.6,
        }
    ]
    captured: list[list[dict]] = []

    async def capture(messages):
        captured.append(messages)
        return _raw(0.8, "pass", "ok", [])

    with patch("core.judge.base._stream_text", side_effect=capture):
        await RegressionJudge().judge({"diff": _DIFF, "similar_signatures": sigs})

    user_msg = captured[0][1]["content"]
    assert "DB timeout" in user_msg
    assert "src/db.py" in user_msg


async def test_fetch_similar_signatures_returns_empty_on_no_files() -> None:
    from core.judge.regression import fetch_similar_signatures

    mock_session = AsyncMock()
    result = await fetch_similar_signatures([], mock_session)

    assert result == []
    mock_session.run.assert_not_called()
