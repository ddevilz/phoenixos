from unittest.mock import AsyncMock, MagicMock, patch

from core.models.failure import AggregateScore, JudgeResult


def _make_aggregate(verdict: str = "pass", trust_score: float = 0.9) -> AggregateScore:
    return AggregateScore(
        trust_score=trust_score,
        verdict=verdict,
        judge_results=[
            JudgeResult(judge="behavior", score=trust_score, verdict=verdict,
                        reasoning="ok", flags=[]),
            JudgeResult(judge="security", score=trust_score, verdict=verdict,
                        reasoning="ok", flags=[]),
            JudgeResult(judge="regression", score=trust_score, verdict=verdict,
                        reasoning="ok", flags=[]),
        ],
    )


async def test_write_eval_result_creates_eval_node() -> None:
    from core.judge.graph_writer import write_eval_result

    session = AsyncMock()
    session.run = AsyncMock()

    eval_id = await write_eval_result(
        pr_url="https://github.com/owner/repo/pull/1",
        changed_files=["src/auth.py"],
        aggregate=_make_aggregate(),
        session=session,
    )

    assert eval_id  # returns a non-empty UUID
    assert session.run.call_count >= 1
    # First call is the MERGE EvalResult
    first_call_query = session.run.call_args_list[0][0][0]
    assert "EvalResult" in first_call_query


async def test_write_eval_result_creates_violation_for_behavior_flags() -> None:
    from core.judge.graph_writer import write_eval_result

    aggregate = AggregateScore(
        trust_score=0.3,
        verdict="block",
        judge_results=[
            JudgeResult(judge="behavior", score=0.3, verdict="block",
                        reasoning="broke contract", flags=["return type changed in login()"]),
            JudgeResult(judge="security", score=0.9, verdict="pass", reasoning="ok", flags=[]),
            JudgeResult(judge="regression", score=0.9, verdict="pass", reasoning="ok", flags=[]),
        ],
    )

    session = AsyncMock()
    session.run = AsyncMock()

    await write_eval_result("pr_url", ["src/auth.py"], aggregate, session)

    queries = [call[0][0] for call in session.run.call_args_list]
    assert any("ContractViolation" in q for q in queries)


async def test_write_eval_result_links_to_failure_signatures() -> None:
    from core.judge.graph_writer import write_eval_result

    session = AsyncMock()
    session.run = AsyncMock()

    await write_eval_result("pr_url", ["src/auth.py", "src/db.py"], _make_aggregate(), session)

    queries = [call[0][0] for call in session.run.call_args_list]
    assert any("COVERS" in q for q in queries)


async def test_write_eval_result_skips_timeout_flags() -> None:
    """judge_timeout flags should not create ContractViolation nodes."""
    from core.judge.graph_writer import write_eval_result

    aggregate = AggregateScore(
        trust_score=0.5,
        verdict="warn",
        judge_results=[
            JudgeResult(judge="behavior", score=0.5, verdict="warn",
                        reasoning="timeout", flags=["judge_timeout"]),
            JudgeResult(judge="security", score=0.9, verdict="pass", reasoning="", flags=[]),
            JudgeResult(judge="regression", score=0.9, verdict="pass", reasoning="", flags=[]),
        ],
    )

    session = AsyncMock()
    session.run = AsyncMock()

    await write_eval_result("pr_url", [], aggregate, session)

    queries = [call[0][0] for call in session.run.call_args_list]
    assert not any("ContractViolation" in q for q in queries)


async def test_evals_run_endpoint_returns_aggregate_score() -> None:
    from httpx import ASGITransport, AsyncClient
    from unittest.mock import AsyncMock, patch

    from core.main import app

    mock_result = JudgeResult(
        judge="behavior", score=0.9, verdict="pass", reasoning="ok", flags=[]
    )

    with (
        patch("core.judge.behavior.BehaviorJudge.judge", new_callable=AsyncMock,
              return_value=mock_result),
        patch("core.judge.security.SecurityJudge.judge", new_callable=AsyncMock,
              return_value=JudgeResult(judge="security", score=0.9, verdict="pass",
                                       reasoning="ok", flags=[])),
        patch("core.judge.regression.RegressionJudge.judge", new_callable=AsyncMock,
              return_value=JudgeResult(judge="regression", score=0.9, verdict="pass",
                                       reasoning="ok", flags=[])),
        patch("core.judge.regression.fetch_similar_signatures",
              new_callable=AsyncMock, return_value=[]),
        patch("core.db.neo4j.neo4j_session"),
        patch("core.judge.graph_writer.write_eval_result",
              new_callable=AsyncMock, return_value="eval-id-1"),
        patch("core.api.ws.broadcast_event", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/api/evals/run", json={"diff": "- old\n+ new"})

    assert r.status_code == 200
    body = r.json()
    assert "trust_score" in body
    assert "verdict" in body
    assert "judge_results" in body
    assert len(body["judge_results"]) == 3
