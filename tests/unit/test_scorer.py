from core.models.failure import JudgeResult


def _result(judge: str, score: float, verdict: str) -> JudgeResult:
    return JudgeResult(judge=judge, score=score, verdict=verdict, reasoning="", flags=[])


def test_aggregate_pass_all_high_scores() -> None:
    from core.judge.scorer import aggregate

    results = [
        _result("behavior", 0.9, "pass"),
        _result("security", 0.9, "pass"),
        _result("regression", 0.9, "pass"),
    ]
    score = aggregate(results)

    assert score.verdict == "pass"
    assert score.trust_score >= 0.7


def test_aggregate_warn_mid_range() -> None:
    from core.judge.scorer import aggregate

    results = [
        _result("behavior", 0.6, "warn"),
        _result("security", 0.6, "warn"),
        _result("regression", 0.6, "warn"),
    ]
    score = aggregate(results)

    assert score.verdict == "warn"
    assert 0.4 <= score.trust_score < 0.7


def test_aggregate_block_low_scores() -> None:
    from core.judge.scorer import aggregate

    results = [
        _result("behavior", 0.2, "block"),
        _result("security", 0.2, "block"),
        _result("regression", 0.2, "block"),
    ]
    score = aggregate(results)

    assert score.verdict == "block"
    assert score.trust_score < 0.4


def test_aggregate_security_block_overrides_high_score() -> None:
    """Even if behavior and regression are high, a security block forces block."""
    from core.judge.scorer import aggregate

    results = [
        _result("behavior", 1.0, "pass"),
        JudgeResult(judge="security", score=0.2, verdict="block",
                    reasoning="SSRF found", flags=["SSRF"]),
        _result("regression", 1.0, "pass"),
    ]
    score = aggregate(results)

    # trust_score = 1.0*0.4 + 0.2*0.4 + 1.0*0.2 = 0.68 → would be warn without override
    assert score.verdict == "block"


def test_aggregate_weights_sum_correctly() -> None:
    from core.judge.scorer import aggregate

    results = [
        _result("behavior", 1.0, "pass"),   # 1.0 * 0.4 = 0.4
        _result("security", 0.0, "block"),  # 0.0 * 0.4 = 0.0
        _result("regression", 1.0, "pass"), # 1.0 * 0.2 = 0.2
    ]
    score = aggregate(results)

    assert abs(score.trust_score - 0.6) < 0.001


def test_aggregate_missing_judge_defaults_to_neutral() -> None:
    """Only 2 judges provided — missing one defaults to 0.5."""
    from core.judge.scorer import aggregate

    results = [
        _result("behavior", 1.0, "pass"),
        _result("security", 1.0, "pass"),
        # regression missing
    ]
    score = aggregate(results)

    # 1.0*0.4 + 1.0*0.4 + 0.5*0.2 = 0.90
    assert abs(score.trust_score - 0.9) < 0.001
    assert score.verdict == "pass"
