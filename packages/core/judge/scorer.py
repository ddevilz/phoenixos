from typing import Literal

from core.models.failure import AggregateScore, JudgeResult

_WEIGHTS = {"behavior": 0.4, "security": 0.4, "regression": 0.2}

Verdict = Literal["pass", "warn", "block"]


def aggregate(judge_results: list[JudgeResult]) -> AggregateScore:
    """
    Weighted average: behavior*0.4 + security*0.4 + regression*0.2.
    Missing judges default to 0.5 (neutral).
    Verdict: pass >= 0.7 | warn >= 0.4 | block < 0.4
    """
    scores: dict[str, float] = {name: 0.5 for name in _WEIGHTS}
    for r in judge_results:
        if r.judge in scores:
            scores[r.judge] = r.score

    trust_score = round(sum(scores[name] * w for name, w in _WEIGHTS.items()), 4)

    verdict: Verdict
    if trust_score >= 0.7:
        verdict = "pass"
    elif trust_score >= 0.4:
        verdict = "warn"
    else:
        verdict = "block"

    # Security block always propagates regardless of weighted score
    if any(r.judge == "security" and r.verdict == "block" for r in judge_results):
        verdict = "block"

    return AggregateScore(
        trust_score=trust_score,
        verdict=verdict,
        judge_results=judge_results,
    )
