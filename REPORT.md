# PhoenixOS — Project Report

**Project:** PhoenixOS  
**Status:** Complete (T01–T40)  
**Stack:** Python 3.11 · FastAPI · LangGraph · Neo4j 5 · NVIDIA NIM · TypeScript MCP · React + Vite  
**Tests:** 116 Python · 16 TypeScript  
**Date:** May 2026

---

## 1. Problem Statement

Every CI break is diagnosed from scratch. When a test fails in CI, engineers open the logs, identify the error, and hunt for context. There is no memory of what failed before, no prediction of what will fail next, and no automatic validation of whether an AI-generated fix is trustworthy.

Three compounding problems:

1. **No institutional memory** — the same failure patterns recur across sprints with no signal that they've been seen before.
2. **No prediction** — changing a file in a fragile component triggers failures with no prior warning.
3. **No AI PR trust model** — GitHub Copilot and Cursor generate fixes and features, but there is no system that scores whether an AI-generated diff introduces regressions, security issues, or contract breaks before it merges.

---

## 2. What PhoenixOS Builds

Three working layers on top of a shared Neo4j memory graph:

### Layer 1 — Memory Graph
A semantic failure knowledge base. Every CI failure is:
- Extracted into a structured `FailureSignature` (summary, category, affected component) via LLM
- Embedded into a 4096-dimensional vector via NVIDIA NIM
- Deduplicated against existing signatures by cosine similarity
- Written to Neo4j with `SIMILAR_TO` edges for near-matches
- Scored with PageRank-based fragility (normalized to 0–1 scale)

### Layer 2 — Eval Mesh
3 judge agents run in parallel to score any PR diff:
- **Behavior Judge** — silent contract breaks, missing test updates
- **Security Judge** — SSRF, injection, hardcoded secrets (hard block if found)
- **Regression Judge** — cross-references the failure graph to detect patterns matching past failures

Weighted aggregate: `trust = behavior×0.4 + security×0.4 + regression×0.2`

### Layer 3 — MCP Integration
4 tools exposed to Claude Code and Cursor via the Model Context Protocol:
- `get_fragility_score` — fragility score + trend for any file path
- `get_similar_failures` — past failures matching a stack trace
- `get_fix_genealogy` — fix chain depth + symptom suppression warning
- `predict_blast_radius` — which components are at risk given changed files

---

## 3. Architecture Summary

See [ARCHITECTURE.md](ARCHITECTURE.md) for full diagrams. High-level:

```
GitHub Actions
     │
     ▼ POST /api/webhooks/github
Webhook Ingestor (FastAPI)
     │
     ▼ background task
LangGraph Pipeline: extract → embed → write → predict
     │
     ▼ Cypher MERGE
Neo4j Memory Graph ←──── PageRank fragility recompute
     │
     ├──▶ REST API (/api/graph/*)
     │         │
     │         ▼
     │    TypeScript MCP Server (stdio)
     │         │
     │         ▼
     │    Claude Code / Cursor
     │
     ├──▶ Eval API (/api/evals/run)
     │         │
     │         ▼
     │    3 Judge Agents (asyncio.gather)
     │         │
     │         ▼
     │    Aggregate Scorer → EvalResult node
     │
     └──▶ WebSocket (/ws/events) → React Dashboard
```

---

## 4. Implementation Detail

### 4.1 Webhook Ingestor (`packages/core/api/webhooks.py`)

- Accepts `POST /api/webhooks/github`
- Validates optional HMAC-SHA256 webhook signature (`GITHUB_WEBHOOK_SECRET`)
- Filters: only `action=completed` + `conclusion=failure` events are processed
- Fetches changed files from GitHub Commits API (optional, falls back gracefully)
- Persists raw event to SQLite (`pipeline_runs`, `failure_events` tables)
- Launches `_run_pipeline(event)` as a FastAPI `BackgroundTask`
- Returns `202 Accepted` immediately

### 4.2 LangGraph Pipeline (`packages/core/orchestrator/pipeline.py`)

State machine compiled from 4 nodes:

**`extract` node** — calls `ingestor/signature.py`
- Sends log tail + workflow context to NVIDIA NIM (`minimaxai/minimax-m2.7`, streaming)
- System prompt instructs the model to output JSON with `summary`, `category`, `affected_component`
- Strips markdown fences from response before JSON parse
- Normalizes unknown categories to `test_failure`
- Broadcasts `signature_extracted` event over WebSocket on success
- Returns `signature=None` on any failure → pipeline terminates early

**`embed` node** — calls `embeddings/pipeline.py`
- Constructs text: `"{category} {summary} {affected_component}"`
- Calls NVIDIA NIM `nvidia/nv-embed-v1` embeddings endpoint
- Returns 4096-dimensional float vector
- Logs error and returns unchanged signature on failure (empty embedding → dedup routes to NEW)

**`write` node** — calls `embeddings/dedup.py` + `graph/writer.py` + `graph/scoring.py`
- Loads all existing `FailureSignature` embeddings from Neo4j
- Computes cosine similarity against each (pure Python, no numpy for the comparison loop)
- Decision: EXACT (≥0.92) → increment occurrence_count; SIMILAR (0.80–0.92) → new node + SIMILAR_TO edge; NEW (<0.80) → isolated new node
- Writes result via Cypher MERGE (idempotent)
- Recomputes PageRank fragility scores for the whole graph after every write
- Broadcasts `graph_updated` over WebSocket

**`predict` node** — calls `agents/predictor.py` + `graph/blast_radius.py`
- Queries Neo4j for signatures affecting the event's `changed_files` (direct + SIMILAR_TO hop)
- Ranks by `confidence = fragility_score × (1.0 for direct, 0.7 for similar)`
- Returns top-10 predictions + blast radius components

### 4.3 Neo4j Graph Schema

**4 node labels:**

| Label | Key properties |
|---|---|
| `FailureSignature` | `id`, `summary`, `category`, `affected_component`, `embedding` (4096-dim), `fragility_score`, `occurrence_count`, `first_seen`, `last_seen` |
| `Fix` | `id`, `commit_sha`, `author_type` ("human"/"ai"), `description`, `timestamp` |
| `EvalResult` | `id`, `pr_url`, `trust_score`, `verdict`, `evaluated_at`, `changed_files` |
| `ContractViolation` | `id`, `description`, `eval_id`, `detected_at` |

**5 relationship types:**

| Relationship | Semantics |
|---|---|
| `SIMILAR_TO` | Semantic similarity 0.80–0.92; carries `similarity` and `created_at` |
| `SUPPRESSED_BY` | Fix chain — deeper fix suppresses shallower one |
| `FLAGGED` | EvalResult → ContractViolation |
| `COVERS` | EvalResult → FailureSignature (eval touched this component) |
| `RECURS_IN` | Reserved for future recurring failure detection |

**Constraints:**
```cypher
CREATE CONSTRAINT failure_signature_id IF NOT EXISTS
FOR (s:FailureSignature) REQUIRE s.id IS UNIQUE
```

### 4.4 Fragility Scoring (`packages/core/graph/scoring.py`)

- Loads all `FailureSignature` nodes and `SIMILAR_TO` edges
- Builds a NetworkX `DiGraph` with edge weights = similarity scores
- Runs `nx.pagerank(G, weight="weight", alpha=0.85)`
- Normalizes: `fragility = min(1.0, raw_pagerank × N/2)` where N = number of nodes
  - Average node (uniform PageRank = 1/N) → fragility ≈ 0.5 (amber)
  - Node with 2× average PageRank → fragility = 1.0 (red)
  - Isolated node → fragility ≈ 0.05–0.08 (green)
- Writes updated scores back to Neo4j via UNWIND batch Cypher

**FlakinessTrajectory** (`GET /api/graph/flakiness/{component}`) — partitions a 28-day window into 4 equal buckets, compares first vs. last bucket, returns `rising` / `falling` / `stable`.

**FixGenealogy** (`GET /api/graph/genealogy/{fix_id}`) — recursive `MATCH path = (f)-[:SUPPRESSED_BY*0..]->` traversal, returns chain depth + suppression warning if depth > 2.

### 4.5 Eval Pipeline (`packages/core/api/evals.py`)

`POST /api/evals/run` accepts either:
- `pr_url` — fetches diff from GitHub API, discovers related test files
- `diff` — raw unified diff string

**Execution:**
1. Parse diff via `ingestor/diff_parser.py` (changed files, test file content)
2. Fetch similar `FailureSignature` nodes from Neo4j for the changed files
3. Fan out to 3 judges via `asyncio.gather` — all run in parallel
4. Aggregate with `judge/scorer.py` — weighted score, security block override
5. Write `EvalResult` + `ContractViolation` nodes to Neo4j
6. Broadcast `eval_complete` event over WebSocket
7. Return `AggregateScore` with `trust_score`, `verdict`, `judge_results`

### 4.6 Judge Agents (`packages/core/judge/`)

All judges extend `BaseJudge`:
- Hard 10-second timeout per judge (`asyncio.wait_for`)
- On timeout/error: returns a safe default (`warn` for behavior/regression, `block` for security)
- Streaming response from NVIDIA NIM (`minimaxai/minimax-m2.7`, `stream=True`)
- JSON extraction strips markdown fences

**BehaviorJudge** — checks: silent return type changes, missing test updates, observable contract breaks. Includes related test file source in context.

**SecurityJudge** — checks: SSRF (user-controlled URLs to HTTP clients), SQL/shell/template/command injection, hardcoded secrets, unsafe deserialization. `_has_critical_flag()` post-processes flags — if SSRF or injection appears, forces `score=0.2, verdict=block` regardless of LLM output.

**RegressionJudge** — cross-references the diff against the top-5 past `FailureSignature` nodes for the changed files. Includes fragility scores in context so the LLM knows which components are historically fragile.

**Aggregate scoring:**
```python
trust = behavior×0.4 + security×0.4 + regression×0.2
verdict = "pass" if trust >= 0.7 else "warn" if trust >= 0.4 else "block"
# Security block always propagates:
if any(r.judge == "security" and r.verdict == "block"):
    verdict = "block"
```

### 4.7 TypeScript MCP Server (`packages/mcp/`)

- Built with `@modelcontextprotocol/sdk`
- stdio transport (no HTTP server needed)
- Registered via `.mcp.json` at project root — Claude Code and Cursor auto-load it when the project is opened
- `client.ts` — typed HTTP client to `PHOENIX_API_URL` (defaults `http://localhost:8000`)
- `tools.ts` — 4 tool implementations
- `tools.test.ts` — 16 vitest tests using `vi.spyOn(globalThis, "fetch")`

Tool detail:
- `get_similar_failures(stackTrace)` — extracts file paths from stack trace text using regex, POSTs to `/api/graph/predict`, returns ranked past failures with confidence scores
- `predict_blast_radius(changedFiles)` — POSTs to `/api/graph/blast-radius`, returns at-risk components
- `get_fragility_score(filePath)` — GETs `/api/graph/fragility?component=`, returns score + trend
- `get_fix_genealogy(component)` — GETs `/api/graph/genealogy/{component}`, returns chain + suppression warning

### 4.8 React Dashboard (`packages/dashboard/`)

Vite + React 18 + TailwindCSS + react-force-graph-2d + react-router-dom

**Routes:**
- `/` — Memory Graph page (FailureGraph + LiveFeed components)
- `/evals` — Evals page (JudgeScorecard component)
- `/mocks/intent-compiler` — Intent Compiler mock screen
- `/mocks/behavior-twin` — Behavior Twin mock screen
- `/mocks/trust-ledger` — Trust Ledger mock screen

**FailureGraph** — polls `GET /api/graph/fragility`, renders nodes with `react-force-graph-2d`. Node color: red (≥0.7), amber (0.4–0.7), green (<0.4). `ResizeObserver` makes canvas responsive. Empty state shows seed instructions. Click a node → detail panel with fragility score.

**LiveFeed** — native `WebSocket` to `ws://localhost:8000/ws/events`. Status dot (green Live / grey Disconnected). Maintains 100-event ring buffer. Displays event type, run_id, payload inline.

**JudgeScorecard** — form for `pr_url` or raw diff. POST to `/api/evals/run`. Score bars for each judge, color-coded verdict badges. Aggregate trust score display.

**Vite proxy config:**
```
/api → http://localhost:8000
/ws  → ws://localhost:8000 (WebSocket proxy)
```

### 4.9 SQLite Schema

```sql
CREATE TABLE pipeline_runs (
    id           TEXT PRIMARY KEY,
    repo         TEXT NOT NULL,
    workflow     TEXT NOT NULL,
    status       TEXT NOT NULL,
    triggered_at DATETIME NOT NULL,
    completed_at DATETIME,
    commit_sha   TEXT
);

CREATE TABLE failure_events (
    id           TEXT PRIMARY KEY,
    run_id       TEXT REFERENCES pipeline_runs(id),
    signature_id TEXT,
    job          TEXT NOT NULL,
    step         TEXT NOT NULL,
    exit_code    INTEGER,
    log_tail     TEXT,
    created_at   DATETIME NOT NULL
);
```

SQLite is an append-only audit log. All semantic data lives in Neo4j.

### 4.10 nano_phoenix.py

A single-file (~500 LOC) self-contained distillation of the entire concept. Zero imports from `packages/`. Uses an in-memory `_Store` class (dict-based). Implements:
- `POST /ingest` — LLM extraction + cosine dedup
- `POST /eval` — all 3 judge prompts + inline Security `_has_critical()` check
- `GET /graph` — returns in-memory store contents
- `GET /health`

Run with: `uv run uvicorn nano_phoenix:app --port 8001`

---

## 5. API Reference

### Webhooks
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/webhooks/github` | GitHub Actions webhook receiver |

### Graph
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/graph/fragility` | All FailureSignature nodes with fragility scores |
| `POST` | `/api/graph/fragility/recompute` | Force PageRank recompute |
| `GET` | `/api/graph/flakiness/{component}` | Flakiness trajectory (28-day window) |
| `GET` | `/api/graph/genealogy/{fix_id}` | Fix chain depth + suppression warning |
| `POST` | `/api/graph/predict` | Ranked failure predictions for changed files |
| `POST` | `/api/graph/blast-radius` | At-risk components for changed files |

### Evals
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/evals/run` | Run 3-judge eval on a PR diff |

### Infrastructure
| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | API + Neo4j connection status |
| `WS` | `/ws/events` | Live pipeline events stream |

---

## 6. Configuration

All configuration via environment variables (loaded from `.env` via `python-dotenv`):

| Variable | Required | Default | Description |
|---|---|---|---|
| `NVIDIA_API_KEY` | Yes | — | NVIDIA NIM API key (`nvapi-...`) |
| `NVIDIA_BASE_URL` | No | `https://integrate.api.nvidia.com/v1` | NIM endpoint |
| `NEO4J_URI` | No | `bolt://localhost:7687` | Neo4j Bolt URI |
| `NEO4J_AUTH` | No | `none` | `none` or `user/password` |
| `SQLITE_PATH` | No | `./data/phoenix.db` | SQLite file path |
| `GITHUB_TOKEN` | No | — | For fetching PR diffs from GitHub API |
| `GITHUB_WEBHOOK_SECRET` | No | — | HMAC secret for webhook signature verification |
| `PHOENIX_API_URL` | No | `http://localhost:8000` | Used by MCP server and seed script |

---

## 7. Testing

### Python — 116 unit tests (`uv run pytest tests/ -v`)

| Test file | Coverage |
|---|---|
| `test_webhook.py` (10) | Webhook routing, HMAC verification, background task dispatch |
| `test_pipeline.py` (4) | LangGraph state transitions, early exit on None signature |
| `test_scoring.py` (9) | PageRank computation, flakiness trajectory buckets |
| `test_graph_api.py` (7) | All graph REST endpoints, Neo4j error handling |
| `test_judges.py` (11) | BehaviorJudge, SecurityJudge (SSRF override), RegressionJudge |
| `test_scorer.py` (6) | Weighted aggregate, security block propagation |
| `test_signature.py` (4) | LLM extraction, JSON parse, markdown fence stripping |
| `test_embedding_pipeline.py` (5) | Embed call, error fallback, empty vector handling |
| `test_graph_writer.py` (5) | Cypher write for NEW / EXACT / SIMILAR cases |
| `test_eval_graph_writer.py` (5) | EvalResult + ContractViolation node writes |
| `test_genealogy.py` (4) | Fix chain traversal, depth calculation, suppression flag |
| `test_predictor.py` (4) | Direct + similar match, confidence ranking |
| `test_failure_models.py` (4) | Pydantic model validation |
| `test_ws.py` (4) | WebSocket connect, broadcast, disconnect |
| `test_health.py` (2) | Health endpoint with Neo4j status |
| `test_neo4j_schema.py` (2) | Schema init, constraint creation |
| `test_sqlite.py` (4) | Table creation, get_db generator |
| `test_judge_base.py` (5) | Timeout handling, JSON extraction, streaming |

### TypeScript — 16 integration tests (`pnpm test` in `packages/mcp`)

| Test group | Count | Coverage |
|---|---|---|
| `getFragilityScore` | 5 | Success, missing score, trend normalization, error |
| `getSimilarFailures` | 4 | Success, empty result, file path extraction from trace |
| `getFixGenealogy` | 3 | Success, no chain, suppression warning |
| `predictBlastRadius` | 4 | Success, empty files, error handling |

All tests mock `globalThis.fetch` via `vi.spyOn`.

### GitHub Actions CI (`self_test.yml`)

3 jobs:
1. **unit-tests** — `uv run pytest tests/ -v --tb=short`
2. **mcp-tests** — `cd packages/mcp && pnpm test`
3. **integration** (needs unit-tests) — starts Neo4j service container, boots API, triggers synthetic webhook, runs eval, asserts response shapes

---

## 8. NVIDIA NIM Integration

### LLM — `minimaxai/minimax-m2.7`
- Used for: failure signature extraction, all 3 judge agents
- Mode: streaming only (`stream=True`, `max_tokens=8192`)
- `temperature=1` for extraction (creative/varied), `temperature=0.2` for judges (deterministic)
- Timeout: 60s for extraction, 10s for judges
- Response format: JSON (sometimes wrapped in markdown fences — stripped before parse)

### Embeddings — `nvidia/nv-embed-v1`
- Used for: failure signature embedding
- Output: 4096-dimensional float vector
- Timeout: 10s
- Used via OpenAI-compatible SDK (`AsyncOpenAI(base_url=NVIDIA_BASE_URL)`)
- On failure: returns empty `[]` vector → dedup routes to `NEW` (safe degradation)

---

## 9. Deployment

### Docker Compose (production-like)
```bash
cd infra && docker compose up --build
```
Starts Neo4j 5 Community + core API. Neo4j cold start ~30s (health check polls until ready).

### Local Development
```bash
# Terminal 1
cd infra && docker compose up -d neo4j
# wait ~30s
# Terminal 2
PYTHONPATH=packages uv run uvicorn core.main:app --reload
# Terminal 3
cd packages/dashboard && pnpm dev
# Terminal 4
cd packages/mcp && pnpm build  # builds dist/index.js for .mcp.json
```

### Seeding Demo Data
```bash
uv run scripts/seed_demo.py
# Ingest 22 synthetic failures, wait 30s for extraction, write fix chains
# Graph gets ~10-12 FailureSignature nodes, 3 red after fragility recompute
```

---

## 10. Known Limitations

| Limitation | Impact | Path to fix |
|---|---|---|
| Cosine dedup loads all embeddings into memory | O(N) per ingest; fine up to ~10K nodes | Approximate NN search (FAISS / Neo4j vector index) |
| No real log tail in webhook | Signature extraction works on synthetic summaries only | Parse GitHub Actions log artifact URL |
| NVIDIA NIM rate limits (429) | Seed script throttles at 2s/event; rapid live events may still hit limits | Exponential backoff + queue |
| Security judge SSRF/injection detection | LLM-based with keyword post-processing; not a full static analysis | Integrate semgrep as a pre-filter |
| No authentication on API | All endpoints are open | Add API key middleware or OAuth (E3 plan) |
| PageRank normalization | N/2 scale is heuristic; very large graphs may produce different distributions | Tune scale or switch to min-max normalization |
| Dashboard mock screens | IntentCompiler, BehaviorTwin, TrustLedger are UI mockups with no backend | Build backend for each in future engineering cycles |

---

## 11. File Map

```
phoenixos/
├── packages/
│   ├── core/                          Python FastAPI monolith
│   │   ├── main.py                    App + lifespan (init Neo4j, SQLite)
│   │   ├── api/
│   │   │   ├── webhooks.py            GitHub webhook → FailureEvent → background task
│   │   │   ├── graph.py               6 REST graph endpoints
│   │   │   ├── evals.py               POST /api/evals/run — 3-judge pipeline
│   │   │   └── ws.py                  WebSocket manager + broadcast_event()
│   │   ├── orchestrator/
│   │   │   └── pipeline.py            LangGraph: extract→embed→write→predict
│   │   ├── ingestor/
│   │   │   ├── signature.py           LLM → FailureSignatureExtract via NVIDIA NIM
│   │   │   └── diff_parser.py         GitHub PR diff + test file discovery
│   │   ├── embeddings/
│   │   │   ├── pipeline.py            text → 4096-dim vector via nv-embed-v1
│   │   │   └── dedup.py               cosine similarity → DedupResult (EXACT/SIMILAR/NEW)
│   │   ├── graph/
│   │   │   ├── writer.py              Cypher MERGE for all dedup cases
│   │   │   ├── scoring.py             PageRank fragility + FlakinessTrajectory
│   │   │   ├── genealogy.py           SUPPRESSED_BY recursive traversal
│   │   │   └── blast_radius.py        at-risk components from changed files
│   │   ├── judge/
│   │   │   ├── base.py                BaseJudge ABC (streaming, timeout, JSON parse)
│   │   │   ├── behavior.py            contract break detection
│   │   │   ├── security.py            SSRF/injection + hard block override
│   │   │   ├── regression.py          past failure cross-reference
│   │   │   ├── scorer.py              weighted aggregate + security propagation
│   │   │   └── graph_writer.py        EvalResult + ContractViolation → Neo4j
│   │   ├── agents/
│   │   │   └── predictor.py           ranked failure predictions from graph
│   │   ├── models/
│   │   │   └── failure.py             Pydantic: FailureEvent, FailureSignature, JudgeResult, AggregateScore
│   │   └── db/
│   │       ├── neo4j.py               async driver + neo4j_session() context manager
│   │       └── sqlite.py              aiosqlite + pipeline_runs/failure_events schema
│   │
│   ├── mcp/                           TypeScript MCP server
│   │   └── src/
│   │       ├── index.ts               server entry, 4 tool registrations
│   │       ├── client.ts              typed HTTP client to core API
│   │       ├── tools.ts               4 tool implementations
│   │       └── tools.test.ts          16 vitest tests
│   │
│   └── dashboard/                     React + Vite dashboard
│       └── src/
│           ├── App.tsx                router + nav (5 routes)
│           ├── components/
│           │   ├── FailureGraph.tsx   react-force-graph-2d + ResizeObserver
│           │   ├── LiveFeed.tsx       native WebSocket + 100-event ring buffer
│           │   └── JudgeScorecard.tsx eval form + score bars + verdict badges
│           ├── pages/
│           │   ├── MemoryGraph.tsx    graph + live feed layout
│           │   ├── Evals.tsx          eval page
│           │   └── mocks/            3 future feature mockups
│           └── lib/api.ts             apiFetch<T> + shared types
│
├── tests/unit/                        116 pytest unit tests
├── scripts/
│   ├── seed_demo.py                   seed 22 synthetic failures (throttled, 2s/request)
│   └── demo_script.md                 2-min recording script
├── nano_phoenix.py                    500 LOC self-contained distillation
├── infra/
│   ├── docker-compose.yml             neo4j:5-community + core service
│   ├── Dockerfile                     uv-based Python image
│   └── .env.example                   environment template
├── .github/workflows/self_test.yml    3-job CI: unit + mcp + integration
├── .mcp.json                          Claude Code / Cursor MCP auto-registration
└── 2026-05-20-phoenixos-design.md     original design document (v1.2)
```

---

## 12. Build History (Task Log)

| Tasks | What Was Built |
|---|---|
| T01–T02 | Python monorepo (uv + hatchling), Docker Compose (Neo4j 5 + core) |
| T03–T04 | SQLite schema (`pipeline_runs`, `failure_events`), GitHub Actions webhook ingestor |
| T05–T07 | LLM signature extractor (NVIDIA NIM streaming), embedding pipeline (nv-embed-v1, 4096-dim), cosine dedup |
| T08–T09 | Neo4j 4-node schema + 5-relationship schema, Cypher MERGE graph writer |
| T10–T14 | FragilityScore (PageRank), FlakinessTrajectory (rolling slope), FixGenealogy (SUPPRESSED_BY traversal), Predictor (embedding similarity), BlastRadius (graph traversal) |
| T15–T17 | LangGraph orchestrator (4-node state machine), WebSocket broadcast (`/ws/events`), pipeline integration tests |
| T18–T24 | PR diff parser (GitHub API + test file discovery), BehaviorJudge, SecurityJudge (SSRF/injection block), RegressionJudge (graph cross-ref), Aggregate scorer, EvalResult graph writer, `POST /api/evals/run` endpoint |
| T25–T30 | TypeScript MCP server (4 tools), `.mcp.json` Claude Code registration, 16 vitest integration tests |
| T31–T35 | React + Vite dashboard: FailureGraph, LiveFeed, JudgeScorecard, mock screens (IntentCompiler, BehaviorTwin, TrustLedger) |
| T36 | `nano_phoenix.py` — 500 LOC self-contained distillation |
| T37 | `seed_demo.py` — 22 synthetic failures, throttled ingest, fix chain genealogy |
| T38 | `self_test.yml` — GitHub Actions: unit tests + MCP tests + integration (Neo4j service container) |
| T39–T40 | README, ARCHITECTURE.md, REPORT.md, 2-min demo script |

---

## 13. Quick Reference

**Start everything:**
```bash
cd infra && docker compose up -d neo4j
PYTHONPATH=packages uv run uvicorn core.main:app --reload
cd packages/dashboard && pnpm dev
```

**Seed graph:**
```bash
uv run scripts/seed_demo.py      # ~2 min (throttled for NIM rate limits)
```

**Run tests:**
```bash
uv run pytest tests/ -v          # 116 Python tests
cd packages/mcp && pnpm test     # 16 TypeScript tests
```

**Trigger a failure webhook:**
```bash
curl -X POST http://localhost:8000/api/webhooks/github \
  -H "Content-Type: application/json" \
  -d '{"action":"completed","workflow_run":{"id":"demo-001","name":"CI","head_branch":"main","conclusion":"failure","head_sha":"abc123","created_at":"2026-05-31T10:00:00Z","updated_at":"2026-05-31T10:00:00Z","html_url":"https://github.com/demo/repo/actions/runs/1"},"repository":{"full_name":"demo/repo"}}'
```

**Score a PR diff:**
```bash
curl -X POST http://localhost:8000/api/evals/run \
  -H "Content-Type: application/json" \
  -d '{"diff": "diff --git a/src/auth.py ...\n+    requests.get(user_url)"}'
```

**Check graph:**
```bash
curl http://localhost:8000/api/graph/fragility | python3 -m json.tool
```
