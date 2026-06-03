# PhoenixOS — Design Spec

**Date:** 2026-05-20  
**Version:** 1.1 (Hackathon Build)  
**Team:** 2 engineers, 1 week  
**Hackathon Theme:** AI-Powered Production Function (primary), Agent Swarms (secondary)

---

## 1. Problem

Software teams shipping AI-written code have no memory layer for failures. Every CI break is diagnosed from scratch. No tool tracks why something failed, where it will fail next, or whether an AI-generated fix is trustworthy. GitHub Copilot ships one-click fixes. Gitar does autonomous resolution. Neither builds institutional memory. Neither evaluates whether the fix is safe. Both treat symptoms.

PhoenixOS treats the root cause: the absence of a semantic, temporal knowledge graph that accumulates failure intelligence across every run.

---

## 2. What We Build

A self-healing knowledge substrate for AI-native engineering teams. Two layers ship as working code. Three layers ship as convincing mocks.

### Ship (working)

| Layer | What it does |
|---|---|
| **Memory Graph** | Semantic failure signatures embedded in Neo4j, queryable by any AI tool via MCP |
| **Eval Mesh** | 3 judge agents (Behavior, Security, Regression) scoring every AI-generated PR |

### Mock (pre-computed, real data, not live)

| Layer | Mock approach |
|---|---|
| **Intent Compiler** | Pre-run NL → spec conversion shown as input/output |
| **Behavior Twin** | Static blast radius visualization on demo repo |
| **Trust Ledger** | JSON provenance chain viewer |

---

## 3. Architecture

**Option B: MCP-First Modular Monolith** (selected)

Single FastAPI Python monolith with clear module boundaries. TypeScript MCP server as primary integration surface. Next.js dashboard. Neo4j for graph. SQLite for metadata.

### Why not microservices

Microservices = 8 moving parts to wire in 1 week. Demo risk too high. Option B demos cleanly, integrates with real AI tools via MCP, and presents identically to judges. The multi-agent swarm exists inside the LangGraph orchestrator — it is not negated by the monolith boundary.

### System diagram

```
┌──────────────────────────────────────────────────────────────┐
│                  PhoenixOS Core (FastAPI :8000)              │
│  ┌────────────┐ ┌─────────────┐ ┌──────────┐ ┌───────────┐ │
│  │  Ingestor  │ │  Predictor  │ │  Judge   │ │  Graph    │ │
│  │   module   │ │   module    │ │  module  │ │  Writer   │ │
│  └────────────┘ └─────────────┘ └──────────┘ └───────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              LangGraph Orchestrator                      │ │
│  └──────────────────────────────────────────────────────────┘ │
├──────────────────────────┬───────────────────────────────────┤
│  TypeScript MCP :8001    │  Next.js 14 Dashboard :3000       │
├──────────────┬───────────┴───────────────────────────────────┤
│  Neo4j :7687 │  SQLite ./data/phoenix.db                     │
└──────────────┴───────────────────────────────────────────────┘
```

---

## 4. Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| Agents + API | Python 3.11 + FastAPI | LangGraph, NetworkX, OpenAI SDK all native Python |
| Orchestration | LangGraph | State machine for multi-agent pipeline |
| MCP server | TypeScript + `@modelcontextprotocol/sdk` | Claude Code + Cursor expect TypeScript MCP |
| Frontend | Next.js 14 (TypeScript) | Fast to build, react-force-graph for viz |
| Graph DB | `neo4j:5-community` (Docker) | Free image; no GDS dependency — PageRank via manual traversal |
| Metadata DB | SQLite → Postgres path | Zero config for dev/demo |
| Embeddings | OpenAI `text-embedding-3-small` | Fast, cheap, sufficient for semantic dedup |
| Graph viz | react-force-graph | Interactive, colored by FragilityScore |

---

## 5. Folder Structure

```
phoenixos/
├── packages/
│   ├── core/                          # Python — FastAPI monolith
│   │   ├── main.py                    # App entry, router registration
│   │   ├── api/
│   │   │   ├── webhooks.py            # GitHub Actions webhook receiver
│   │   │   ├── graph.py               # Graph query REST endpoints
│   │   │   ├── evals.py               # Judge eval trigger + results
│   │   │   └── ws.py                  # WebSocket → live event feed
│   │   ├── agents/
│   │   │   ├── predictor.py           # Failure prediction from graph
│   │   │   ├── graph_writer.py        # Neo4j write after each event
│   │   │   └── judge/
│   │   │       ├── base.py            # Base judge class + output schema
│   │   │       ├── behavior.py        # Behavioral contract judge
│   │   │       ├── security.py        # Security judge
│   │   │       └── regression.py      # Regression judge (cross-refs graph)
│   │   ├── graph/
│   │   │   ├── schema.py              # Node + relationship type definitions
│   │   │   ├── queries.py             # Cypher query library
│   │   │   ├── scoring.py             # FragilityScore (manual PageRank), FlakinessTrajectory
│   │   │   └── genealogy.py           # FixGenealogy chain traversal
│   │   ├── ingestor/
│   │   │   ├── parser.py              # CI event payload → FailureEvent
│   │   │   └── signature.py           # LLM extraction → FailureSignature + embedding
│   │   ├── embeddings/
│   │   │   ├── pipeline.py            # Text → OpenAI vector
│   │   │   └── dedup.py               # Cosine similarity dedup before write
│   │   ├── orchestrator/
│   │   │   └── pipeline.py            # LangGraph state machine
│   │   ├── models/
│   │   │   ├── failure.py             # FailureSignature, FailureEvent (Pydantic)
│   │   │   ├── eval.py                # JudgeResult, AggregateScore
│   │   │   └── graph.py               # GraphNode, GraphEdge typed dicts
│   │   └── db/
│   │       ├── neo4j.py               # Neo4j driver + session context manager
│   │       └── sqlite.py              # SQLite — pipeline_runs, metadata
│   │
│   ├── mcp/                           # TypeScript — MCP server (localhost only)
│   │   ├── src/
│   │   │   ├── index.ts               # Server entry, tool registration
│   │   │   ├── client.ts              # HTTP client → core API at localhost:8000
│   │   │   └── tools/
│   │   │       ├── fragility.ts       # get_fragility_score(file_path)
│   │   │       ├── similar-failures.ts # get_similar_failures(stack_trace)
│   │   │       ├── fix-genealogy.ts   # get_fix_genealogy(component)
│   │   │       └── blast-radius.ts    # predict_blast_radius(changed_files[])
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── dashboard/                     # TypeScript — Next.js 14
│       ├── app/
│       │   ├── page.tsx               # Main: graph viz + live feed
│       │   ├── evals/page.tsx         # Judge scorecards per PR
│       │   └── mocks/
│       │       ├── intent-compiler/   # Mock: NL → spec
│       │       ├── behavior-twin/     # Mock: blast radius viz
│       │       └── trust-ledger/      # Mock: provenance chain
│       ├── components/
│       │   ├── FailureGraph.tsx       # react-force-graph, FragilityScore color
│       │   ├── JudgeScorecard.tsx     # Per-judge result breakdown
│       │   ├── LiveFeed.tsx           # SSE event stream
│       │   └── FragilityBadge.tsx     # Score chip
│       └── package.json
│
├── nano/
│   ├── nano_phoenix.py                # Entire core in ~500 LOC (self-contained, no imports from packages/)
│   └── README.md
│
├── infra/
│   ├── docker-compose.yml             # Neo4j + core + mcp + dashboard
│   └── .env.example
│
├── scripts/
│   ├── seed_demo.py                   # Load OSS repo CI failure history into graph
│   └── test_mcp.sh                    # End-to-end MCP smoke test
│
├── tests/
│   ├── unit/
│   │   ├── test_scoring.py
│   │   ├── test_dedup.py
│   │   └── test_judges.py
│   └── integration/
│       ├── test_webhook_flow.py
│       └── test_mcp_tools.py
│
├── .github/
│   └── workflows/
│       └── self_test.yml
│
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-05-20-phoenixos-design.md
│
├── pyproject.toml
├── package.json                       # pnpm workspaces root
└── README.md
```

---

## 6. Data Models

### 6a. Pydantic models (Python — `packages/core/models/`)

```python
class FailureEvent(BaseModel):
    id: str                        # UUID
    repo: str                      # "owner/repo"
    run_id: str                    # GitHub Actions run ID
    workflow: str                  # Workflow name
    job: str                       # Job name
    step: str                      # Step name
    exit_code: int
    log_tail: str                  # Last 2000 chars of step log
    changed_files: list[str]       # Files changed in triggering commit
    timestamp: datetime

class FailureSignature(BaseModel):
    id: str                        # UUID
    summary: str                   # LLM-extracted 1-sentence description
    category: str                  # "test_failure" | "build_error" | "contract_violation" | "flaky"
    affected_component: str        # File path or module name
    embedding: list[float]         # 1536-dim vector (text-embedding-3-small)
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int

class JudgeResult(BaseModel):
    judge: str                     # "behavior" | "security" | "regression"
    score: float                   # 0.0 (fail) – 1.0 (pass)
    verdict: str                   # "pass" | "warn" | "block"
    reasoning: str                 # 1-3 sentence explanation
    flags: list[str]               # Specific issues found

class AggregateScore(BaseModel):
    trust_score: float             # Weighted: behavior*0.4 + security*0.4 + regression*0.2
    verdict: str                   # "pass" if >= 0.7 | "warn" if >= 0.4 and < 0.7 | "block" if < 0.4
    judge_results: list[JudgeResult]

class GraphWrite(BaseModel):
    node_type: str                 # "FailureSignature" | "Fix" | "ContractViolation"
    node_id: str
    properties: dict[str, Any]
    relationships: list[dict]      # [{"type": "CAUSED_BY", "from": id, "to": id, "props": {}}]
```

### 6b. SQLite schema (`./data/phoenix.db`)

```sql
CREATE TABLE pipeline_runs (
    id          TEXT PRIMARY KEY,   -- GitHub Actions run ID
    repo        TEXT NOT NULL,
    workflow    TEXT NOT NULL,
    status      TEXT NOT NULL,      -- "success" | "failure" | "in_progress"
    triggered_at DATETIME NOT NULL,
    completed_at DATETIME,
    commit_sha  TEXT
);

CREATE TABLE failure_events (
    id              TEXT PRIMARY KEY,
    run_id          TEXT REFERENCES pipeline_runs(id),
    signature_id    TEXT,           -- Neo4j FailureSignature node ID (denormalized)
    job             TEXT NOT NULL,
    step            TEXT NOT NULL,
    exit_code       INTEGER,
    log_tail        TEXT,
    created_at      DATETIME NOT NULL
);
```

**Split rule:** SQLite stores run/event provenance (what ran, when, raw log). Neo4j stores semantic structure (what it means, how it relates, how fragile). No duplication except `signature_id` as a cross-store foreign key.

### 6c. Neo4j node properties (full)

| Node | Property | Type | Notes |
|---|---|---|---|
| `FailureSignature` | `id` | string | UUID |
| | `summary` | string | LLM-extracted |
| | `category` | string | test_failure / build_error / contract_violation / flaky |
| | `embedding` | float[] | 1536-dim, stored as Neo4j list |
| | `first_seen` | datetime | |
| | `last_seen` | datetime | |
| | `occurrence_count` | integer | |
| | `fragility_score` | float | PageRank result, updated after each write |
| `Component` | `id` | string | file path or module name |
| | `path` | string | relative to repo root |
| | `fragility_score` | float | aggregated from linked FailureSignatures |
| | `flakiness_trajectory` | float | slope of 7-run failure frequency window |
| `Fix` | `id` | string | UUID |
| | `commit_sha` | string | |
| | `author_type` | string | "human" / "ai" |
| | `description` | string | commit message summary |
| | `timestamp` | datetime | |
| | `suppression_depth` | integer | length of SUPPRESSED_BY chain from this node |
| `ContractViolation` | `id` | string | UUID |
| | `interface_name` | string | function/class name |
| | `expected` | string | expected signature or behavior |
| | `actual` | string | actual observed value |
| | `first_seen` | datetime | |

### 6d. MCP return types (TypeScript)

```typescript
interface FailureSummary {
  id: string;
  summary: string;
  category: string;
  occurrence_count: number;
  fragility_score: number;
  last_seen: string;           // ISO datetime
  affected_component: string;
}

interface FixChainItem {
  id: string;
  commit_sha: string;
  author_type: "human" | "ai";
  description: string;
  timestamp: string;
  suppression_depth: number;
}
```

---

## 7. Graph Scoring

### Fix Node Lifecycle

Fix nodes are created by two paths:
1. **`seed_demo.py`:** Synthetically generates Fix nodes from `curl/curl` commit history — fetch commits that mention "fix" in message, create `Fix` nodes with `author_type="human"`, link via `FIXED_BY` to the closest temporally-matching `FailureSignature`. Seed at least 3 `SUPPRESSED_BY` chains of depth ≥ 3 for the genealogy demo moment.
2. **Webhook `pull_request` event (merged):** `webhooks.py` handles `action: "closed", merged: true` — creates a `Fix` node from the merged PR, links it to any `FailureSignature` whose `affected_component` matches changed files in the PR.

Both paths use `GraphWrite` objects and the same Graph Writer module.

### BlastRadius Algorithm

Traverse from `Component` nodes matching `changed_files` paths via `CAUSED_BY` edges to linked `FailureSignature` nodes, then back out to all other `Component` nodes connected to those signatures (depth ≤ 2). Collect unique component paths. Sort by `fragility_score` descending. Cap at 10 results. Return component paths + their fragility scores.

### FragilityScore (manual PageRank — no GDS required)

Uses `neo4j:5-community` Docker image. GDS not available. PageRank computed in Python via NetworkX after fetching adjacency from Neo4j:

```python
# Fetch CAUSED_BY + RECURS_IN edges → build networkx DiGraph → nx.pagerank()
# Write scores back to Component.fragility_score and FailureSignature.fragility_score
# Triggered after every Graph Writer run
```

### FlakinessTrajectory

Rolling window: fetch last 7 `pipeline_run` outcomes per component from SQLite. Compute linear slope of failure rate. Store on `Component.flakiness_trajectory`. Positive slope = flag in dashboard.

### FixGenealogy

Recursive Cypher:
```cypher
MATCH path = (f:Fix)-[:SUPPRESSED_BY*]->(root:Fix)
WHERE f.id = $fix_id
RETURN length(path) AS depth, nodes(path) AS chain
```
Depth > 2 → `warning: "symptom suppression chain detected"` returned in MCP response.

### Dedup threshold

Cosine similarity > **0.92** → existing signature. Do not create new node. Increment `occurrence_count` and update `last_seen`.  
Cosine similarity 0.80–0.92 → create new node **and** add `RECURS_IN` edge with `similarity_score` property.  
Cosine similarity < 0.80 → new independent signature, no edge.

---

## 8. Judge Agents

All judges output `JudgeResult`. Score range: **0.0–1.0**. Aggregate: `behavior * 0.4 + security * 0.4 + regression * 0.2`.

### Behavior Judge

- **Input:** PR diff (added/removed lines) + test file contents for changed modules (fetched via GitHub Contents API in T18)
- **Checks:** Does the change break observable behavior contracts? Are tests updated to match changed logic? Does the diff introduce silent behavioral changes (return type shifts, default value changes, interface narrowing)?
- **Output:** `JudgeResult` with `score`, `verdict`, and `flags: list[str]` naming specific contract breaks
- **Timeout:** 10s. On timeout → `score=0.5`, `verdict="warn"`, `flags=["judge_timeout"]`

### Security Judge

- **Input:** PR diff only
- **Checks:** SSRF risk (user-controlled URL), injection vectors (SQL, shell, template), hardcoded secrets or API keys, unsafe deserialization, dependency additions from PR
- **Output:** `JudgeResult`. Any SSRF or injection flag forces `score=0.2`, `verdict="block"` regardless of other findings
- **Timeout:** 10s. On timeout → `score=0.3`, `verdict="block"`, `flags=["judge_timeout"]` (security uncertainty defaults to block)

### Regression Judge

- **Input:** PR diff + top-5 similar `FailureSignature` nodes fetched from Memory Graph
- **Checks:** Does this diff resemble patterns that caused past failures? Does it touch components with `fragility_score > 0.7`? Does the fix chain for this component show suppression depth > 2?
- **Output:** `JudgeResult` with `flags` citing specific past signature IDs that match
- **Timeout:** 10s. On timeout → `score=0.5`, `verdict="warn"`, `flags=["judge_timeout"]`

---

## 9. WebSocket Contract

**Endpoint:** `ws://localhost:8000/ws/events`  
**Protocol:** JSON messages, one per pipeline event  
**Message schema:**

```typescript
interface PhoenixEvent {
  type: "pipeline_started" | "signature_extracted" | "judge_complete" | "graph_updated" | "eval_complete";
  timestamp: string;          // ISO datetime
  run_id: string;
  payload: {
    // type-specific fields:
    // judge_complete: { judge: string, score: number, verdict: string }
    // graph_updated: { node_type: string, node_id: string, fragility_score?: number }
    // eval_complete: { trust_score: number, verdict: string }
    [key: string]: unknown;
  };
}
```

Dashboard `LiveFeed.tsx` connects on mount, renders events in reverse-chronological order.

**SSE proxy contract (`/api/events`):** Next.js route at `app/api/events/route.ts` opens a WebSocket connection to `ws://localhost:8000/ws/events` and re-emits each JSON message as an SSE event:
```
event: phoenix
data: {"type":"judge_complete","run_id":"...","timestamp":"...","payload":{...}}
retry: 3000
```
On WebSocket disconnect the SSE route sends `event: error\ndata: {"reconnecting":true}` and retries connection with 2s backoff. Browser client uses `EventSource('/api/events')` and listens on `message` + `phoenix` event types.

---

## 10. Multi-Agent Orchestration (LangGraph)

```
CI Event (webhook)
    │
    ▼
[Ingestor] → FailureEvent → FailureSignature → embed → dedup
    │
    ▼
[Predictor] → similar_failures[] + blast_radius[]
    │
    ▼
[Judge × 3] → parallel fan-out: Behavior | Security | Regression
    │         (each has 10s timeout, fallback score on timeout)
    ▼
[Aggregator] → AggregateScore (behavior*0.4 + security*0.4 + regression*0.2)
    │
    ▼
[Graph Writer] → Cypher MERGE writes → FragilityScore recompute
    │
    ▼
[WebSocket broadcast] → ws://localhost:8000/ws/events
```

Shared state object:

```python
class PhoenixState(TypedDict):
    event: FailureEvent             # Parsed CI event
    signature: FailureSignature     # LLM-extracted + embedded
    similar_failures: list[FailureSignature]  # Top-5 from graph
    blast_radius: list[str]         # At-risk component paths
    judge_results: list[JudgeResult]
    aggregate_score: AggregateScore
    graph_writes: list[GraphWrite]  # Pending Cypher writes
```

---

## 11. MCP Tools (TypeScript)

MCP server runs at `localhost:8001`. Localhost-only binding — no auth token required for hackathon demo (air-gapped). All tools call `http://localhost:8000` (core API).

### Eval Trigger API (`packages/core/api/evals.py`)

```
POST /api/evals/run
Request:  { "pr_url": str, "diff": str }
Response: AggregateScore (trust_score, verdict, judge_results[])
```

Used by `self_test.yml` (T38). Also callable manually during demo to trigger eval without a real PR webhook.

```typescript
get_fragility_score(file_path: string): { score: number, trend: "up"|"down"|"stable" }

get_similar_failures(stack_trace: string): FailureSummary[]

get_fix_genealogy(component: string): {
  depth: number,
  chain: FixChainItem[],
  warning?: string    // present if depth > 2
}

predict_blast_radius(changed_files: string[]): {
  at_risk: string[],
  fragility_scores: Record<string, number>
}
```

---

## 12. Task Breakdown (with dependencies)

### Engineer 1 — Graph + Agents + Orchestrator

| Task | Description | Blocks | Blocked by |
|---|---|---|---|
| T01 | Monorepo setup — pyproject.toml, pnpm workspace, pre-commit | T02–T16 | — |
| T02 | Docker Compose — `neo4j:5-community` + FastAPI skeleton | T08+ | T01 |
| T03 | SQLite schema — `pipeline_runs`, `failure_events` | T04, T11 | T01 |
| T04 | Webhook endpoint — parse GitHub Actions payload → `FailureEvent` | T05 | T03 |
| T05 | `FailureSignature` extractor — LLM call → Pydantic model | T06 | T04 |
| T06 | Embedding pipeline — signature text → OpenAI vector | T07 | T05 |
| T07 | Dedup logic — cosine sim check (0.92 / 0.80 thresholds) | T09 | T06 |
| T08 | Neo4j schema — 4 node types + 5 relationship types | T09 | T02 |
| T09 | Graph Writer — Cypher MERGE writes from `GraphWrite` objects | T10, T13 | T07, T08 |
| T10 | FragilityScore — NetworkX PageRank, write back to Neo4j | T15 | T09 |
| T11 | FlakinessTrajectory — rolling 7-run slope on SQLite data | T15 | T03, T09 |
| T12 | FixGenealogy — recursive Cypher `SUPPRESSED_BY` traversal | T15 | T09 |
| T13 | Predictor — embedding similarity search → ranked results | T15 | T09 |
| T14 | Blast radius — graph traversal from changed files | T15 | T09 |
| T15 | LangGraph state machine — wire T04–T14 with `PhoenixState` | T16 | T10–T14 |
| T16 | WebSocket broadcast endpoint (`ws.py`) | T32 (Eng 2) | T15 |
| T17 | Unit tests — scoring, dedup, genealogy | — | T10, T12 |

### Engineer 2 — Judges + MCP + Dashboard

| Task | Description | Blocks | Blocked by |
|---|---|---|---|
| T18 | PR diff parser — GitHub API → structured diff object **+ test file contents** for changed modules via GitHub Contents API. Output type: `{ diff: str, changed_files: list[str], test_contents: dict[str, str] }` | T19–T21 | — |
| T19 | Base judge class — prompt template, structured output, 10s timeout | T20–T22 | T18 |
| T20 | Behavior Judge | T23 | T19 |
| T21 | Security Judge | T23 | T19 |
| T22 | Regression Judge (needs graph query → use Day 2 stub until T09* live) | T23 | T19, stub* |
| T23 | Aggregate scorer — weighted trust score (>=0.7 pass / >=0.4 warn / <0.4 block) | T24+ | T20, T21, T22 |
| T24 | Judge output → Graph Write pipeline | — | T23 |
| T25 | TypeScript MCP server scaffold | T26–T29 | — |
| T26 | `get_fragility_score` tool (use Day 2 stub until T10* live) | T30 | T25 |
| T27 | `get_similar_failures` tool (use Day 2 stub until T09* live) | T30 | T25 |
| T28 | `get_fix_genealogy` tool (use Day 2 stub until T12* live) | T30 | T25 |
| T29 | `predict_blast_radius` tool (use Day 2 stub until T14* live) | T30 | T25 |
| T30 | Integration test MCP in Claude Code + Cursor | — | T26–T29 |
| T31 | Next.js scaffold + layout | T32–T35 | — |
| T32 | `FailureGraph.tsx` — react-force-graph, colored by FragilityScore | — | T31 |
| T33 | `LiveFeed.tsx` — SSE proxy from WebSocket (`/api/events` route) | — | T31 |
| T34 | `JudgeScorecard.tsx` — per-judge result + aggregate | — | T31 |
| T35 | Mock screens — Intent Compiler, Behavior Twin, Trust Ledger | — | T31 |
| T36 | `nano_phoenix.py` — self-contained 500 LOC distillation. Includes: ingest → graph write → Security Judge (no graph dependency, simplest). Uses in-memory dict if Neo4j unavailable. Exposes `POST /ingest` + `POST /eval` CLI. Zero imports from `packages/`. | — | T15* |
| T37 | `seed_demo.py` — (a) fetch `curl/curl` CI failure logs via GitHub API, parse into `FailureEvent` objects, bulk-ingest → **minimum 20 FailureSignatures across 3 categories, 3 RECURS_IN edges, 2 components with fragility_score > 0.7**; (b) synthetically generate Fix nodes from commit history with 3 SUPPRESSED_BY chains of depth ≥ 3 for genealogy demo. | — | T15* |
| T38 | `self_test.yml` — GitHub Actions: (1) trigger synthetic failure webhook to `POST /api/webhooks/github`, (2) call `POST /api/evals/run` with a prepared diff, (3) assert HTTP 200 + `trust_score` field in response JSON. Passing = PhoenixOS evaluates its own PRs. | — | T23* |
| T39 | README + 5-slide pitch deck | — | T37, T38 |
| T40 | 2-min video fallback recording | — | T39 |

**Cross-engineer stub protocol:** By end of Day 2, Engineer 1 ships stub endpoints returning hardcoded fixture JSON so Engineer 2 can build MCP tools and dashboard against real HTTP contracts without blocking:
- `GET /api/graph/fragility/{path}` → `{"score": 0.72, "trend": "up"}`
- `POST /api/graph/similar` → `[{"id":"...","summary":"...","occurrence_count":12,...}]`
- `GET /api/graph/genealogy/{component}` → `{"depth": 3, "chain": [...], "warning": "symptom suppression"}`
- `POST /api/graph/blast-radius` → `{"at_risk": ["src/auth.py"], "fragility_scores": {...}}`

Replace stubs with real implementations as T09–T14 land. Engineer 2 needs no code changes — only the response data changes.

---

## 13. Demo Environment

- All LLM judge calls are **live** during demo (not pre-cached)
- Per-judge timeout: **10 seconds**. Behavior/Regression fallback: `score=0.5 / warn`. Security fallback: `score=0.3 / block`
- Demo repo: `curl/curl` failure history pre-seeded via `seed_demo.py` (T37)
- Demo PR: prepared in advance, triggered live during presentation
- Fallback: if live eval fails, `seed_demo.py` output is pre-recorded in 2-min video (T40)
- MCP server: localhost-only, no auth, tested in Claude Code + Cursor before demo (T30)

---

## 14. Demo Script (5 minutes)

1. **[30s]** Show AI-generated PR diff landing in PhoenixOS repo
2. **[60s]** Eval Mesh fires — 3 judges score in parallel, Regression Judge flags blast radius using seeded failure history
3. **[60s]** Memory Graph updates live — new `FailureSignature` node, `FragilityScore` recalculates on graph
4. **[60s]** Open Cursor → MCP `get_similar_failures` query → "similar failure seen 47x, fix genealogy depth 3 — symptom suppression warning"
5. **[60s]** Walk mock screens — Intent Compiler, Behavior Twin, Trust Ledger
6. **[30s]** Show `self_test.yml` passing — PhoenixOS evaluating its own PRs

---

## 15. Win Criteria

Three things judges remember:

1. **MCP moment** — real AI tool integration, live during demo. No other team will have this.
2. **Graph is alive** — failure nodes update in real time during demo. Judges see working system, not slides.
3. **nanoPhoenix on GitHub** — public, 500 LOC, linkable. Shows taste. Shows Karpathy-style distillation principle.

**Riskiest assumptions — de-risk first:**
- Neo4j Docker (`neo4j:5-community`) runs clean on demo machine → T02, day 1
- MCP registers in Claude Code without friction → T30 before T31
- Judge structured output reliable enough → T19–T22 before UI work
- `seed_demo.py` produces realistic graph before demo → T37 by day 5

---

## 16. Out of Scope (v1)

- Auth / multi-tenant
- Live Intent Compiler (mock only)
- Live Behavior Twin (mock only)
- Live Trust Ledger (mock only)
- Production deployment / Kubernetes
- Non-GitHub CI systems
- Neo4j GDS (use manual NetworkX PageRank)
