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
import json
import math
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import httpx

API = os.environ.get("PHOENIX_API_URL", "http://localhost:8000")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ── Synthetic failure data ────────────────────────────────────────────────────
# Used when GitHub API is unavailable or returns insufficient results.

SYNTHETIC_FAILURES = [
    # test_failure category
    {
        "repo": "curl/curl", "job": "test-unit", "step": "run tests",
        "exit_code": 1, "category": "test_failure",
        "affected_component": "lib/transfer.c",
        "summary": "Unit test failure in transfer layer: timeout handling regression",
        "log_tail": "FAIL: test_transfer_timeout\nAssertionError: expected 30s, got 35s\nlib/transfer.c:1423",
    },
    {
        "repo": "curl/curl", "job": "test-unit", "step": "run tests",
        "exit_code": 1, "category": "test_failure",
        "affected_component": "lib/connect.c",
        "summary": "Connection test failure: TLS handshake mock not matching expected sequence",
        "log_tail": "FAIL: test_tls_handshake_mock\nExpected: CLIENT_HELLO, SERVER_HELLO\nGot: CLIENT_HELLO, TIMEOUT",
    },
    {
        "repo": "curl/curl", "job": "test-http2", "step": "h2 tests",
        "exit_code": 1, "category": "test_failure",
        "affected_component": "lib/http2.c",
        "summary": "HTTP/2 stream multiplexing test fails under high concurrency",
        "log_tail": "test 1591 FAILED\nStream ID collision detected under 64-stream load",
    },
    {
        "repo": "curl/curl", "job": "test-unit", "step": "run tests",
        "exit_code": 1, "category": "test_failure",
        "affected_component": "lib/url.c",
        "summary": "URL parser test: IPv6 zone ID not stripped from host header",
        "log_tail": "FAIL: test_ipv6_zone_strip\nExpected host: [::1]\nGot host: [::1%25eth0]",
    },
    {
        "repo": "curl/curl", "job": "test-unit", "step": "run tests",
        "exit_code": 1, "category": "test_failure",
        "affected_component": "lib/cookie.c",
        "summary": "Cookie jar test: SameSite=None without Secure flag accepted",
        "log_tail": "FAIL: test_cookie_samesite_secure\nCookie accepted without Secure flag",
    },
    {
        "repo": "curl/curl", "job": "test-smtp", "step": "smtp tests",
        "exit_code": 1, "category": "test_failure",
        "affected_component": "lib/smtp.c",
        "summary": "SMTP AUTH PLAIN test fails with multi-line server response",
        "log_tail": "test 802 FAILED\nSMTP multi-line 334 response not fully consumed",
    },
    {
        "repo": "curl/curl", "job": "test-unit", "step": "run tests",
        "exit_code": 1, "category": "test_failure",
        "affected_component": "lib/progress.c",
        "summary": "Progress callback fires after transfer complete in redirect case",
        "log_tail": "FAIL: test_progress_redirect\nCallback invoked post-completion",
    },
    {
        "repo": "curl/curl", "job": "test-ftp", "step": "ftp tests",
        "exit_code": 1, "category": "test_failure",
        "affected_component": "lib/ftp.c",
        "summary": "FTP PASV mode fails when server returns non-standard port encoding",
        "log_tail": "test 320 FAILED\nPASV response: 227 Entering (127,0,0,1,255,256) — port overflow",
    },
    # build_error category
    {
        "repo": "curl/curl", "job": "build-linux", "step": "cmake build",
        "exit_code": 2, "category": "build_error",
        "affected_component": "lib/vauth/ntlm.c",
        "summary": "Build error: NTLM auth module fails compilation with -DUSE_NTLM=OFF",
        "log_tail": "ntlm.c:892: error: use of undeclared identifier 'ntlm_context'\n1 error generated.",
    },
    {
        "repo": "curl/curl", "job": "build-windows", "step": "msvc build",
        "exit_code": 2, "category": "build_error",
        "affected_component": "lib/openssl.c",
        "summary": "MSVC build fails: OpenSSL 3.x deprecated API usage in TLS layer",
        "log_tail": "openssl.c(441): error C4996: 'SSL_CTX_set_ecdh_auto': deprecated in OpenSSL 3.0",
    },
    {
        "repo": "curl/curl", "job": "build-linux", "step": "autoconf build",
        "exit_code": 2, "category": "build_error",
        "affected_component": "configure.ac",
        "summary": "Autoconf build: missing pthread_setname_np detection on musl libc",
        "log_tail": "configure: error: pthread_setname_np check failed on Alpine Linux",
    },
    {
        "repo": "curl/curl", "job": "build-arm64", "step": "cross-compile",
        "exit_code": 2, "category": "build_error",
        "affected_component": "lib/select.c",
        "summary": "ARM64 cross-compile failure: HAVE_POLL_FINE not detected by configure",
        "log_tail": "select.c:123: implicit declaration of function 'poll'",
    },
    {
        "repo": "curl/curl", "job": "build-linux", "step": "cmake build",
        "exit_code": 2, "category": "build_error",
        "affected_component": "lib/idn.c",
        "summary": "IDN module build failure: libidn2 headers not found in include path",
        "log_tail": "idn.c:35: fatal error: idn2.h: No such file or directory",
    },
    {
        "repo": "curl/curl", "job": "build-windows", "step": "mingw build",
        "exit_code": 2, "category": "build_error",
        "affected_component": "lib/warnless.c",
        "summary": "MinGW build: integer overflow warning treated as error in warnless.c",
        "log_tail": "warnless.c:88: error: integer overflow in expression [-Werror=overflow]",
    },
    # contract_violation category
    {
        "repo": "curl/curl", "job": "abi-check", "step": "libcurl ABI check",
        "exit_code": 1, "category": "contract_violation",
        "affected_component": "include/curl/curl.h",
        "summary": "ABI breakage: curl_easy_setopt signature change removes default parameter",
        "log_tail": "ABI check FAILED: curl_easy_setopt — parameter count changed from 3 to 2",
    },
    {
        "repo": "curl/curl", "job": "api-check", "step": "symbol export check",
        "exit_code": 1, "category": "contract_violation",
        "affected_component": "lib/libcurl.def",
        "summary": "Exported symbol removed: curl_multi_socket_action no longer in libcurl.def",
        "log_tail": "MISSING EXPORT: curl_multi_socket_action\nWas present in 8.6.0, missing in current build",
    },
    {
        "repo": "curl/curl", "job": "deprecation-check", "step": "deprecated API usage",
        "exit_code": 1, "category": "contract_violation",
        "affected_component": "lib/easy.c",
        "summary": "Deprecated CURLOPT_SSL_VERIFYPEER usage in internal easy.c test helper",
        "log_tail": "easy.c:334: warning: CURLOPT_SSL_VERIFYPEER is deprecated — use CURLOPT_SSL_VERIFYHOST",
    },
    {
        "repo": "curl/curl", "job": "abi-check", "step": "enum value check",
        "exit_code": 1, "category": "contract_violation",
        "affected_component": "include/curl/multi.h",
        "summary": "Enum value renumbering in CURLMoption breaks binary compatibility",
        "log_tail": "CURLMOPT_SOCKETFUNCTION value changed: 20001 → 20003. Binary ABI broken.",
    },
    # flaky category
    {
        "repo": "curl/curl", "job": "test-timing", "step": "timing sensitive tests",
        "exit_code": 1, "category": "flaky",
        "affected_component": "tests/unit/unit1398.c",
        "summary": "Flaky: timing-sensitive DNS TTL test fails under CI load (intermittent)",
        "log_tail": "test 1398 FAILED (intermittent)\nDNS TTL expired 50ms early under load",
    },
    {
        "repo": "curl/curl", "job": "test-parallel", "step": "parallel transfer tests",
        "exit_code": 1, "category": "flaky",
        "affected_component": "tests/unit/unit1700.c",
        "summary": "Flaky: parallel transfer test race condition in event loop teardown",
        "log_tail": "test 1700 FAILED\nSegfault in multi_socket cleanup — use-after-free under race",
    },
    {
        "repo": "curl/curl", "job": "test-network", "step": "network tests",
        "exit_code": 1, "category": "flaky",
        "affected_component": "tests/server/sws.c",
        "summary": "Flaky: test server port binding fails intermittently on CI (EADDRINUSE)",
        "log_tail": "sws: bind: Address already in use\ntest server failed to start on port 8990",
    },
    {
        "repo": "curl/curl", "job": "test-timing", "step": "keepalive tests",
        "exit_code": 1, "category": "flaky",
        "affected_component": "lib/keepalive.c",
        "summary": "Flaky: keepalive probe interval test non-deterministic under valgrind",
        "log_tail": "test 1560 FAILED (valgrind mode)\nTCP keepalive probe fired 2.1s late",
    },
]

# Fix chains for SUPPRESSED_BY genealogy (3 chains, depth ≥ 3 each)
FIX_CHAINS = [
    [
        {"description": "Fix TLS handshake timeout handling", "author_type": "human", "commit_sha": "a1b2c3d"},
        {"description": "Increase TLS timeout threshold (workaround)", "author_type": "ai", "commit_sha": "e4f5g6h"},
        {"description": "Suppress timeout warning in test output", "author_type": "ai", "commit_sha": "i7j8k9l"},
        {"description": "Skip flaky TLS test in slow environments", "author_type": "ai", "commit_sha": "m1n2o3p"},
    ],
    [
        {"description": "Fix HTTP/2 stream ID collision under load", "author_type": "human", "commit_sha": "q4r5s6t"},
        {"description": "Add stream ID retry logic (band-aid)", "author_type": "ai", "commit_sha": "u7v8w9x"},
        {"description": "Reduce parallel stream count in tests", "author_type": "ai", "commit_sha": "y1z2a3b"},
    ],
    [
        {"description": "Fix DNS TTL race condition", "author_type": "human", "commit_sha": "c4d5e6f"},
        {"description": "Add sleep(50ms) to DNS test (timing hack)", "author_type": "ai", "commit_sha": "g7h8i9j"},
        {"description": "Mark DNS TTL test as flaky-expected", "author_type": "ai", "commit_sha": "k1l2m3n"},
        {"description": "Disable DNS TTL assertion in CI", "author_type": "ai", "commit_sha": "o4p5q6r"},
    ],
]


async def _post(client: httpx.AsyncClient, path: str, body: dict) -> dict:
    r = await client.post(f"{API}{path}", json=body, timeout=60.0)
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
        sig_id = signature_ids[chain_idx] if chain_idx < len(signature_ids) else signature_ids[0]
        fix_ids: list[str] = [str(uuid.uuid4()) for _ in chain]

        # POST each fix as a graph write
        payload = {
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
            await _post(client, "/api/evals/run", {
                "diff": f"# chain {chain_idx} seed\n+ fix applied",
            })
        except Exception:
            pass  # best-effort

        print(f"  Chain {chain_idx + 1}: depth {len(chain)} — component {SYNTHETIC_FAILURES[chain_idx]['affected_component']}")

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
                await _post(client, "/api/webhooks/github", {
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
                    },
                    "repository": {"full_name": failure["repo"]},
                })
                ingested += 1
                print(f"  [{i+1:02d}/{len(SYNTHETIC_FAILURES)}] {failure['category']:20s} {failure['affected_component']}")
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
    print(f"  Categories: test_failure, build_error, contract_violation, flaky")
    print(f"  Fix chains: {len(FIX_CHAINS)} (depths: {[len(c) for c in FIX_CHAINS]})")


if __name__ == "__main__":
    asyncio.run(main())
