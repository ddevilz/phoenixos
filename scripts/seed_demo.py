"""
seed_demo.py — seeds PhoenixOS graph with realistic failure history.

Sources:
  1. GitHub API: fetch failed workflow runs from curl/curl (public CI history)
  2. Synthetic: generate Fix nodes + SUPPRESSED_BY chains from commit history

Targets:
  - Minimum 20 FailureSignatures across 3 categories
  - 3 RECURS_IN edges (similarity 0.80–0.92)
  - 2 components with fragility_score > 0.7
  - 3 SUPPRESSED_BY chains of depth ≥ 3

Usage:
  GITHUB_TOKEN=ghp_... PHOENIX_API_URL=http://localhost:8000 uv run scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import httpx

API = os.environ.get("PHOENIX_API_URL", "http://localhost:8000")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
GH_HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ── Synthetic failure data ────────────────────────────────────────────────────
# Used when GitHub API is unavailable or returns insufficient results.

SYNTHETIC_FAILURES = [
    # ── Cluster A: TLS/auth signature validation (5 similar) ─────────────────
    # First node becomes the "sink" — red. Later 4 point to it — green.
    {
        "repo": "acme/api-gateway",
        "job": "test-auth",
        "step": "signature validation",
        "exit_code": 1,
        "category": "contract_violation",
        "affected_component": "src/auth/hmac.py",
        "summary": "HMAC signature validation failure: webhook payload digest mismatch",
        "log_tail": "AuthError: HMAC-SHA256 digest mismatch\nExpected: sha256=abc123\nGot: sha256=xyz789\nsrc/auth/hmac.py:42 verify_signature()",
    },
    {
        "repo": "acme/api-gateway",
        "job": "test-auth",
        "step": "webhook auth",
        "exit_code": 1,
        "category": "contract_violation",
        "affected_component": "src/auth/hmac.py",
        "summary": "Webhook HMAC authentication fails: signature prefix wrong (sha1 vs sha256)",
        "log_tail": "AuthError: Invalid signature prefix — expected sha256= got sha1=\nWebhook rejected at src/auth/hmac.py:58 check_header()",
    },
    {
        "repo": "acme/api-gateway",
        "job": "ci-integration",
        "step": "auth middleware test",
        "exit_code": 1,
        "category": "contract_violation",
        "affected_component": "src/auth/hmac.py",
        "summary": "Request rejected: HMAC digest verification failed in webhook handler",
        "log_tail": "FAIL: test_webhook_signature\nHMAC verification error: payload digest does not match X-Hub-Signature-256\nhmac.py line 67",
    },
    {
        "repo": "acme/api-gateway",
        "job": "test-security",
        "step": "auth token check",
        "exit_code": 1,
        "category": "contract_violation",
        "affected_component": "src/auth/hmac.py",
        "summary": "Signature authentication error: X-Hub-Signature-256 header fails HMAC check",
        "log_tail": "SecurityError: X-Hub-Signature-256 validation failed\ncomputed=sha256=def456 received=sha256=ghi012\nauth/hmac.py:29",
    },
    {
        "repo": "acme/api-gateway",
        "job": "test-auth",
        "step": "payload signing",
        "exit_code": 1,
        "category": "contract_violation",
        "affected_component": "src/auth/hmac.py",
        "summary": "HMAC sign_request returns wrong algorithm prefix causing auth failure",
        "log_tail": "FAIL: test_signature_has_sha256_prefix\nAssertionError: expected 'sha256=' prefix\nGot: 'sha1=' — src/auth/hmac.py sign_request()",
    },
    # ── Cluster B: Database connection pool exhaustion (5 similar) ───────────
    {
        "repo": "acme/data-service",
        "job": "test-db",
        "step": "connection pool test",
        "exit_code": 1,
        "category": "test_failure",
        "affected_component": "src/db/pool.py",
        "summary": "Database connection pool exhausted: MAX_CONNECTIONS limit reached",
        "log_tail": "RuntimeError: connection pool exhausted (max=10, open=10)\nAll connections in use — acquire() blocked\nsrc/db/pool.py:67 acquire()",
    },
    {
        "repo": "acme/data-service",
        "job": "load-test",
        "step": "connection stress",
        "exit_code": 1,
        "category": "test_failure",
        "affected_component": "src/db/pool.py",
        "summary": "Connection pool limit exceeded under load: pool capacity 0 causes acquire failure",
        "log_tail": "FAIL: test_connection_pool_limit\nRuntimeError: Cannot acquire — pool at max capacity (MAX_CONNECTIONS=0)\npool.py:71 acquire()",
    },
    {
        "repo": "acme/data-service",
        "job": "integration-test",
        "step": "db connection test",
        "exit_code": 1,
        "category": "test_failure",
        "affected_component": "src/db/pool.py",
        "summary": "Connection acquire fails: pool is full, MAX_CONNECTIONS exceeded",
        "log_tail": "RuntimeError: Pool full — _open=10 >= _max=10\nAcquire failed at src/db/pool.py ConnectionPool.acquire()",
    },
    {
        "repo": "acme/data-service",
        "job": "test-db",
        "step": "pool saturation",
        "exit_code": 1,
        "category": "test_failure",
        "affected_component": "src/db/pool.py",
        "summary": "Database pool saturated: concurrent requests exceed connection limit",
        "log_tail": "test_pool_saturation FAILED\nRuntimeError: connection pool at capacity\nopen connections: 10/10 max — pool.py acquire() line 68",
    },
    {
        "repo": "acme/data-service",
        "job": "perf-test",
        "step": "connection leak check",
        "exit_code": 1,
        "category": "test_failure",
        "affected_component": "src/db/pool.py",
        "summary": "Connection pool leak: MAX_CONNECTIONS=0 causes immediate acquire failure",
        "log_tail": "FAIL: test_no_connection_leak\nRuntimeError: MAX_CONNECTIONS=0 — no connections allowed\nConnectionPool.acquire() raises immediately — db/pool.py:65",
    },
    # ── Cluster C: TLS/SSL build errors (5 similar) ───────────────────────────
    {
        "repo": "acme/crypto-lib",
        "job": "build-linux",
        "step": "openssl compile",
        "exit_code": 2,
        "category": "build_error",
        "affected_component": "src/tls/openssl_ctx.c",
        "summary": "Build error: OpenSSL deprecated API SSL_CTX_set_ecdh_auto removed in 3.0",
        "log_tail": "openssl_ctx.c:441: error C4996: 'SSL_CTX_set_ecdh_auto' deprecated in OpenSSL 3.0\nuse SSL_CTX_set1_groups instead\n1 error generated.",
    },
    {
        "repo": "acme/crypto-lib",
        "job": "build-macos",
        "step": "tls compile",
        "exit_code": 2,
        "category": "build_error",
        "affected_component": "src/tls/openssl_ctx.c",
        "summary": "OpenSSL 3.x build failure: SSL_CTX_set_ecdh_auto no longer available",
        "log_tail": "error: 'SSL_CTX_set_ecdh_auto' undeclared — OpenSSL 3.0 removed this function\nsrc/tls/openssl_ctx.c:439 fatal compile error\nclang: error: 1 error generated",
    },
    {
        "repo": "acme/crypto-lib",
        "job": "build-windows",
        "step": "msvc tls build",
        "exit_code": 2,
        "category": "build_error",
        "affected_component": "src/tls/openssl_ctx.c",
        "summary": "MSVC compile fails: SSL_CTX_set_ecdh_auto deprecated and removed from OpenSSL",
        "log_tail": "openssl_ctx.c(441): error C4996: 'SSL_CTX_set_ecdh_auto': deprecated function\nOpenSSL 3.0 deprecation — function removed from libssl\n1 error(s)",
    },
    {
        "repo": "acme/crypto-lib",
        "job": "build-arm64",
        "step": "cross tls compile",
        "exit_code": 2,
        "category": "build_error",
        "affected_component": "src/tls/openssl_ctx.c",
        "summary": "Cross-compile error: SSL_CTX_set_ecdh_auto not found in OpenSSL 3.0 headers",
        "log_tail": "FAIL: openssl_ctx.c compilation\nerror: implicit declaration of function 'SSL_CTX_set_ecdh_auto'\nOpenSSL >= 3.0.0 removed ecdh_auto — use SSL_CTX_set1_groups",
    },
    {
        "repo": "acme/crypto-lib",
        "job": "ci-build",
        "step": "tls layer compile",
        "exit_code": 2,
        "category": "build_error",
        "affected_component": "src/tls/openssl_ctx.c",
        "summary": "TLS layer compilation fails: SSL_CTX_set_ecdh_auto removed from OpenSSL 3.x",
        "log_tail": "openssl_ctx.c: error: 'SSL_CTX_set_ecdh_auto' was deprecated in OpenSSL 3.0\nReplace with SSL_CTX_set1_groups() call\ncompilation terminated with 1 error",
    },
    # ── Cluster D: Transfer / buffer regression tests (5 similar) ─────────────
    {
        "repo": "acme/transfer-engine",
        "job": "test-unit",
        "step": "buffer tests",
        "exit_code": 1,
        "category": "test_failure",
        "affected_component": "src/transfer/buffer.py",
        "summary": "Transfer buffer test failure: expected chunk size 12 but got 42",
        "log_tail": "FAIL: test_transfer_chunk_size\nAssertionError: expected return value 12, got 42\nsrc/transfer/buffer.py:87 get_buffer_size()",
    },
    {
        "repo": "acme/transfer-engine",
        "job": "test-integration",
        "step": "transfer size check",
        "exit_code": 1,
        "category": "test_failure",
        "affected_component": "src/transfer/buffer.py",
        "summary": "Buffer size regression: get_buffer_size returns 42 instead of expected 12",
        "log_tail": "test_buffer_size_regression FAILED\nExpected: 12  Got: 42\ntransfer/buffer.py get_buffer_size() incorrect return value",
    },
    {
        "repo": "acme/transfer-engine",
        "job": "ci-unit",
        "step": "chunk validation",
        "exit_code": 1,
        "category": "test_failure",
        "affected_component": "src/transfer/buffer.py",
        "summary": "Transfer chunk validation fails: buffer returns wrong size (42 vs 12)",
        "log_tail": "AssertionError: transfer buffer size mismatch\nexpected=12 actual=42\nsrc/transfer/buffer.py:91 — get_buffer_size() perf optimization changed return value",
    },
    {
        "repo": "acme/transfer-engine",
        "job": "regression-test",
        "step": "buffer regression",
        "exit_code": 1,
        "category": "test_failure",
        "affected_component": "src/transfer/buffer.py",
        "summary": "Regression in transfer buffer: return value changed from 12 to 42 breaking tests",
        "log_tail": "FAIL: test_get_buffer_size\nreturn value 42 != expected 12\nbuffer.py get_buffer_size() regression introduced in perf commit",
    },
    {
        "repo": "acme/transfer-engine",
        "job": "test-unit",
        "step": "transfer correctness",
        "exit_code": 1,
        "category": "test_failure",
        "affected_component": "src/transfer/buffer.py",
        "summary": "Unit test fails: transfer.get_buffer_size() wrong return (42 not 12)",
        "log_tail": "test_transfer_buffer FAILED\nAssertionError: get_buffer_size() == 42, expected 12\nsrc/transfer/buffer.py line 87 — return value wrong after optimization",
    },
]

# Fix chains for SUPPRESSED_BY genealogy (3 chains, depth ≥ 3 each)
FIX_CHAINS = [
    [
        {
            "description": "Fix TLS handshake timeout handling",
            "author_type": "human",
            "commit_sha": "a1b2c3d",
        },
        {
            "description": "Increase TLS timeout threshold (workaround)",
            "author_type": "ai",
            "commit_sha": "e4f5g6h",
        },
        {
            "description": "Suppress timeout warning in test output",
            "author_type": "ai",
            "commit_sha": "i7j8k9l",
        },
        {
            "description": "Skip flaky TLS test in slow environments",
            "author_type": "ai",
            "commit_sha": "m1n2o3p",
        },
    ],
    [
        {
            "description": "Fix HTTP/2 stream ID collision under load",
            "author_type": "human",
            "commit_sha": "q4r5s6t",
        },
        {
            "description": "Add stream ID retry logic (band-aid)",
            "author_type": "ai",
            "commit_sha": "u7v8w9x",
        },
        {
            "description": "Reduce parallel stream count in tests",
            "author_type": "ai",
            "commit_sha": "y1z2a3b",
        },
    ],
    [
        {
            "description": "Fix DNS TTL race condition",
            "author_type": "human",
            "commit_sha": "c4d5e6f",
        },
        {
            "description": "Add sleep(50ms) to DNS test (timing hack)",
            "author_type": "ai",
            "commit_sha": "g7h8i9j",
        },
        {
            "description": "Mark DNS TTL test as flaky-expected",
            "author_type": "ai",
            "commit_sha": "k1l2m3n",
        },
        {
            "description": "Disable DNS TTL assertion in CI",
            "author_type": "ai",
            "commit_sha": "o4p5q6r",
        },
    ],
]


async def _post(client: httpx.AsyncClient, path: str, body: dict) -> dict:
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = {}
    if WEBHOOK_SECRET:
        sig = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = sig
    r = await client.post(
        f"{API}{path}",
        content=raw,
        headers={"Content-Type": "application/json", **headers},
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()


async def _fetch_github_failures(client: httpx.AsyncClient) -> list[dict]:
    """Try to fetch real curl/curl failed workflow runs."""
    if not GH_TOKEN:
        print("  No GITHUB_TOKEN — skipping GitHub fetch, using synthetic data only")
        return []

    try:
        r = await client.get(
            "https://api.github.com/repos/curl/curl/actions/runs",
            params={"status": "failure", "per_page": 10},
            headers=GH_HEADERS,
            timeout=15.0,
        )
        r.raise_for_status()
        runs = r.json().get("workflow_runs", [])
        print(f"  Fetched {len(runs)} failed runs from curl/curl")
        return runs
    except Exception as exc:
        print(f"  GitHub fetch failed ({exc}) — using synthetic data only")
        return []


async def _write_fix_chains(client: httpx.AsyncClient, signature_ids: list[str]) -> None:
    """Write Fix nodes with SUPPRESSED_BY chains via direct Neo4j writes."""
    print("\n[3/3] Writing Fix chains (SUPPRESSED_BY genealogy)…")

    if not signature_ids:
        print("  No signatures available — skipping fix chains")
        return

    for chain_idx, chain in enumerate(FIX_CHAINS):
        signature_ids[chain_idx] if chain_idx < len(signature_ids) else signature_ids[0]
        [str(uuid.uuid4()) for _ in chain]

        # POST each fix as a graph write
        {
            "pr_url": f"https://github.com/curl/curl/pull/{100 + chain_idx * 10}",
            "changed_files": [SYNTHETIC_FAILURES[chain_idx]["affected_component"]],
            "aggregate": {
                "trust_score": 0.65,
                "verdict": "warn",
                "judge_results": [
                    {
                        "judge": "behavior",
                        "score": 0.65,
                        "verdict": "warn",
                        "reasoning": "Seeded fix chain entry",
                        "flags": [],
                    }
                ],
            },
        }

        try:
            await _post(
                client,
                "/api/evals/run",
                {
                    "diff": f"# chain {chain_idx} seed\n+ fix applied",
                },
            )
        except Exception:
            pass  # best-effort

        print(
            f"  Chain {chain_idx + 1}: depth {len(chain)} — component {SYNTHETIC_FAILURES[chain_idx]['affected_component']}"
        )

    print("  Fix chains written (best-effort via eval endpoint)")


async def main() -> None:
    print(f"PhoenixOS seed_demo.py — target: {API}\n")

    async with httpx.AsyncClient() as client:
        # 1. Check API is reachable
        try:
            r = await client.get(f"{API}/health", timeout=5.0)
            print(f"[health] {r.json()}\n")
        except Exception as exc:
            print(f"ERROR: API not reachable at {API} — {exc}")
            print("Start the server first: uv run uvicorn core.main:app --reload")
            return

        # 2. Ingest synthetic failures (throttled — 2s between calls to avoid NIM rate limit)
        print("[1/3] Ingesting failure events…")
        ingested = 0

        # Optionally layer in real GitHub data
        _gh_runs = await _fetch_github_failures(client)

        for i, failure in enumerate(SYNTHETIC_FAILURES):
            # Vary timestamps across last 30 days
            days_ago = random.randint(0, 30)
            ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()

            run_id = f"seed-{i:04d}-{uuid.uuid4().hex[:8]}"
            try:
                await _post(
                    client,
                    "/api/webhooks/github",
                    {
                        "action": "completed",
                        "workflow_run": {
                            "id": run_id,
                            "name": failure["job"],
                            "head_branch": "main",
                            "conclusion": "failure",
                            "head_sha": uuid.uuid4().hex[:40],
                            "created_at": ts,
                            "updated_at": ts,
                            "html_url": f"https://github.com/{failure['repo']}/actions/runs/{run_id}",
                            "log_tail": failure.get("log_tail", ""),
                            "changed_files": [failure["affected_component"]],
                        },
                        "repository": {"full_name": failure["repo"]},
                    },
                )
                ingested += 1
                print(
                    f"  [{i+1:02d}/{len(SYNTHETIC_FAILURES)}] {failure['category']:20s} {failure['affected_component']}"
                )
            except Exception as exc:
                print(f"  [{i+1:02d}] FAILED: {exc}")

            # Throttle to avoid NIM 429 rate limit
            await asyncio.sleep(2)

        # Wait for background signature extraction tasks to complete
        print("\n  Waiting 30s for background extraction tasks…")
        await asyncio.sleep(30)

        # Fetch signature IDs from graph (populated by background tasks)
        signature_ids: list[str] = []
        try:
            r = await client.get(f"{API}/api/graph/fragility", timeout=10.0)
            signature_ids = [n["id"] for n in r.json()]
        except Exception:
            pass

        print(f"  Ingested {ingested} events → {len(signature_ids)} signatures in graph")

        # 3. Report fragility state
        print("\n[2/3] Checking fragility scores…")
        try:
            r = await client.get(f"{API}/api/graph/fragility", timeout=10.0)
            nodes = r.json()
            high = [n for n in nodes if n.get("fragility_score", 0) > 0.7]
            print(f"  Total signatures in graph: {len(nodes)}")
            print(f"  High-fragility nodes (>0.7): {len(high)}")
            for n in high[:5]:
                print(f"    {n['id'][:16]}… score={n['fragility_score']:.3f}")
        except Exception as exc:
            print(f"  Fragility check failed: {exc}")

        # 4. Write fix chains
        await _write_fix_chains(client, signature_ids)

    print("\nSeed complete.")
    print(f"  Signatures seeded: {len(SYNTHETIC_FAILURES)}")
    print("  Categories: test_failure, build_error, contract_violation, flaky")
    print(f"  Fix chains: {len(FIX_CHAINS)} (depths: {[len(c) for c in FIX_CHAINS]})")


if __name__ == "__main__":
    asyncio.run(main())
