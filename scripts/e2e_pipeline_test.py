"""
End-to-end pipeline test: real NVIDIA NIM calls + real Neo4j writes.
Run: PYTHONPATH=packages uv run python scripts/e2e_pipeline_test.py
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages"))


async def main():
    from core.db.neo4j import close_driver, init_driver, init_schema
    from core.models.failure import FailureEvent
    from core.orchestrator.pipeline import pipeline

    print("=" * 60)
    print("PhoenixOS End-to-End Pipeline Test")
    print("=" * 60)

    # ── 1. Init Neo4j ────────────────────────────────────────────
    print("\n[1] Connecting to Neo4j...")
    await init_driver()
    await init_schema()
    print("    ✓ Connected")

    # ── 2. Build a realistic FailureEvent with a real log ────────
    log_tail = """\
FAILED tests/unit/test_auth.py::test_login_returns_jwt - AssertionError: assert 401 == 200
tests/unit/test_auth.py:45: AssertionError
--- Captured stderr call ---
Traceback (most recent call last):
  File "src/auth.py", line 82, in validate_token
    decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
  File "/venv/lib/python3.11/site-packages/jose/jwt.py", line 149, in decode
    raise JWTError("Signature verification failed.")
jose.exceptions.JWTError: Signature verification failed.
"""

    event = FailureEvent(
        id="e2e-test-001",
        repo="owner/phoenixos",
        run_id="e2e-run-001",
        workflow="CI",
        job="test",
        step="pytest",
        exit_code=1,
        log_tail=log_tail,
        changed_files=["src/auth.py", "tests/unit/test_auth.py"],
        timestamp=datetime.now(timezone.utc),
    )
    print(f"\n[2] Event built — run_id={event.run_id}, repo={event.repo}")

    # ── 3. Run the full LangGraph pipeline ───────────────────────
    print("\n[3] Running LangGraph pipeline...")
    print("    → _extract_node  (NVIDIA NIM: minimaxai/minimax-m2.7)")
    print("    → _embed_node    (NVIDIA NIM: nvidia/nv-embed-v1)")
    print("    → _write_node    (Neo4j write + fragility recompute)")
    print("    → _predict_node  (blast radius query)")

    state = await pipeline.ainvoke(
        {
            "event": event,
            "signature": None,
            "predictions": [],
            "at_risk": [],
            "fragility_scores": {},
        }
    )

    # ── 4. Print results ─────────────────────────────────────────
    print("\n[4] Pipeline complete. Results:")
    sig = state.get("signature")
    if sig:
        print("\n    FailureSignature written to Neo4j:")
        print(f"      id:                 {sig.id}")
        print(f"      summary:            {sig.summary}")
        print(f"      category:           {sig.category}")
        print(f"      affected_component: {sig.affected_component}")
        print(f"      embedding dims:     {len(sig.embedding)}")
        print(f"      occurrence_count:   {sig.occurrence_count}")
    else:
        print("\n    ⚠  signature is None — extraction returned nothing")

    preds = state.get("predictions", [])
    if preds:
        print(f"\n    Failure predictions ({len(preds)}):")
        for p in preds[:3]:
            print(
                f"      • {p.get('affected_component')} [{p.get('category')}] confidence={p.get('confidence', 0):.2f}"
            )
    else:
        print("\n    predictions: [] (no prior graph data yet — expected on first run)")

    at_risk = state.get("at_risk", [])
    if at_risk:
        print(f"\n    At-risk components: {at_risk}")

    print("\n[5] Querying Neo4j to verify node was written...")
    from core.db.neo4j import neo4j_session

    async with neo4j_session() as session:
        result = await session.run(
            "MATCH (s:FailureSignature) RETURN s.id AS id, s.category AS cat, "
            "s.affected_component AS comp, s.fragility_score AS fs ORDER BY s.last_seen DESC LIMIT 5"
        )
        rows = await result.data()

    if rows:
        print(f"    ✓ {len(rows)} FailureSignature node(s) in graph:")
        for r in rows:
            print(f"      • {r['id'][:8]}… [{r['cat']}] {r['comp']}  fragility={r['fs']}")
    else:
        print("    ✗ No nodes found in Neo4j")

    await close_driver()
    print("\n" + "=" * 60)
    print("Done.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
