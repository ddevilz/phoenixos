# PhoenixOS — Architecture

## System Overview

PhoenixOS has three independent layers that compose into a single system. Each layer can be understood and tested on its own.

```mermaid
flowchart TD
    GH[GitHub Actions\nCI Webhook] -->|POST /api/webhooks/github| WH[Webhook Ingestor]
    WH -->|FailureEvent| PL[LangGraph Pipeline]
    PL -->|extract → embed → write → predict| NEO[Neo4j Memory Graph]
    NEO -->|fragility scores\nSIMILAR_TO edges| NEO

    NEO -->|REST queries| GAPI[Graph API\n/api/graph/*]
    GAPI -->|fragility\ngenealogy\nblast radius| MCP[TypeScript MCP Server]
    MCP -->|4 tools over stdio| CC[Claude Code\nCursor\nany MCP client]

    EVAL[Eval API\nPOST /api/evals/run] -->|PR diff| JUDGES[3 Judge Agents\nin parallel]
    JUDGES -->|scores| AGG[Aggregate Scorer\nweighted trust score]
    AGG -->|EvalResult node| NEO

    WS[WebSocket\n/ws/events] -->|live events| DASH[React Dashboard\nlocalhost:3000]
    GAPI --> DASH
    EVAL --> DASH
```

---

## Layer 1 — Ingest Pipeline (LangGraph)

Every CI failure triggers this 4-node state machine.

```mermaid
stateDiagram-v2
    [*] --> extract
    extract --> embed : signature != None
    extract --> [*] : signature is None
    embed --> write
    write --> predict
    predict --> [*]

    extract : Extract\nLLM → FailureSignature\n(NVIDIA NIM minimax-m2.7)
    embed : Embed\ntext → 4096-dim vector\n(NVIDIA NIM nv-embed-v1)
    write : Write\ncosine dedup → Neo4j\nPageRank recompute
    predict : Predict\nblast radius + ranked failures\n(graph traversal)
```

**State object (`PhoenixState`):**
| Field | Type | Set by |
|---|---|---|
| `event` | `FailureEvent` | Webhook ingestor |
| `signature` | `FailureSignature \| None` | `extract` node |
| `predictions` | `list[dict]` | `predict` node |
| `at_risk` | `list[str]` | `predict` node |
| `fragility_scores` | `dict[str, float]` | `predict` node |

**Deduplication thresholds:**
- `≥ 0.92` cosine → `EXACT` (increment occurrence_count, no new node)
- `0.80 – 0.92` → `SIMILAR` (new node + `SIMILAR_TO` edge)
- `< 0.80` → `NEW` (isolated new node)

---

## Layer 2 — Neo4j Memory Graph

### Node Types

```mermaid
erDiagram
    FailureSignature {
        string id PK
        string summary
        string category
        string affected_component
        float[] embedding
        datetime first_seen
        datetime last_seen
        int occurrence_count
        float fragility_score
    }
    Fix {
        string id PK
        string commit_sha
        string author_type
        string description
        datetime timestamp
    }
    EvalResult {
        string id PK
        string pr_url
        float trust_score
        string verdict
        datetime evaluated_at
        string[] changed_files
    }
    ContractViolation {
        string id PK
        string description
        string eval_id
        datetime detected_at
    }

    FailureSignature ||--o{ FailureSignature : "SIMILAR_TO (similarity: float)"
    Fix ||--o{ Fix : "SUPPRESSED_BY"
    EvalResult ||--o{ ContractViolation : "FLAGGED"
    EvalResult ||--o{ FailureSignature : "COVERS"
```

### Relationship Types

| Relationship | From → To | Meaning |
|---|---|---|
| `SIMILAR_TO` | FailureSignature → FailureSignature | Cosine similarity 0.80–0.92 |
| `SUPPRESSED_BY` | Fix → Fix | Deeper fix suppresses shallower one |
| `FLAGGED` | EvalResult → ContractViolation | Behavioral issue found in eval |
| `COVERS` | EvalResult → FailureSignature | Eval touched this component |
| `RECURS_IN` | FailureSignature → FailureSignature | Same failure recurred (future) |

### Fragility Score

PageRank over the `SIMILAR_TO` edge graph, normalized by graph size:

```
raw_scores = nx.pagerank(G, weight="similarity", alpha=0.85)
fragility  = min(1.0, raw_score × N/2)
```

A node scoring 2× the graph average → fragility 1.0 (red). Average node → ~0.5 (amber).

---

## Layer 3 — Eval Mesh (3 Judge Agents)

```mermaid
flowchart LR
    PR[PR Diff\n+ changed files] --> PARSE[diff_parser\nGitHub API or raw]
    PARSE --> SIG[Fetch similar\nFailureSignatures\nfrom Neo4j]

    subgraph parallel["asyncio.gather — runs in parallel"]
        BJ[Behavior Judge\ncontract breaks\ntest coverage]
        SJ[Security Judge\nSSRF / injection\nhardcoded secrets]
        RJ[Regression Judge\nmatches past failures\nhigh-fragility components]
    end

    PARSE --> BJ
    PARSE --> SJ
    SIG --> RJ

    BJ --> AGG[Aggregate Scorer]
    SJ --> AGG
    RJ --> AGG

    AGG -->|"trust = behavior×0.4\n+ security×0.4\n+ regression×0.2"| RESULT[AggregateScore\ntrust_score + verdict]
    RESULT --> NEO[Write EvalResult\nto Neo4j]
```

**Verdict rules:**
- `trust ≥ 0.7` → **pass**
- `0.4 ≤ trust < 0.7` → **warn**
- `trust < 0.4` → **block**
- Security judge flags SSRF or injection → **block** regardless of weighted score

---

## Layer 4 — MCP Integration

```mermaid
sequenceDiagram
    participant CC as Claude Code / Cursor
    participant MCP as MCP Server (Node.js)
    participant API as FastAPI Core (Python)
    participant NEO as Neo4j

    CC->>MCP: get_similar_failures("FAIL: test_tls_handshake...")
    MCP->>MCP: extractFilePaths(stackTrace)
    MCP->>API: POST /api/graph/predict {changed_files}
    API->>NEO: MATCH FailureSignature WHERE component IN files
    NEO-->>API: ranked signatures with fragility scores
    API-->>MCP: [{id, summary, category, fragility_score, confidence}]
    MCP-->>CC: JSON result with past failures + confidence

    CC->>MCP: predict_blast_radius(["src/auth.py"])
    MCP->>API: POST /api/graph/blast-radius
    API->>NEO: traverse SIMILAR_TO edges from changed components
    NEO-->>API: at_risk components + scores
    API-->>MCP: {at_risk: [...], fragility_scores: {...}}
    MCP-->>CC: blast radius result
```

**4 tools registered via `.mcp.json`:**

| Tool | Core endpoint | Purpose |
|---|---|---|
| `get_fragility_score` | `GET /api/graph/fragility?component=` | Score + trend for a file |
| `get_similar_failures` | `POST /api/graph/predict` | Past failures matching a stack trace |
| `get_fix_genealogy` | `GET /api/graph/genealogy/{fix_id}` | Fix chain depth + suppression warning |
| `predict_blast_radius` | `POST /api/graph/blast-radius` | At-risk components from changed files |

---

## Data Persistence

```mermaid
flowchart LR
    subgraph sqlite["SQLite (aiosqlite)"]
        PR_TBL[pipeline_runs\nid, repo, workflow\nstatus, triggered_at, commit_sha]
        FE_TBL[failure_events\nid, run_id, signature_id\njob, step, exit_code, log_tail]
    end

    subgraph neo4j["Neo4j 5 (bolt://localhost:7687)"]
        FS[FailureSignature\nwith 4096-dim embedding]
        FX[Fix nodes]
        ER[EvalResult]
        CV[ContractViolation]
    end

    WH[Webhook] -->|INSERT| PR_TBL
    WH -->|INSERT| FE_TBL
    PL[Pipeline] -->|MERGE CYPHER| FS
    EVAL[Eval] -->|MERGE CYPHER| ER
    EVAL -->|MERGE CYPHER| CV
```

SQLite stores raw pipeline metadata (immutable audit log). Neo4j stores the semantic graph (mutable — scores recomputed on every new write).

---

## WebSocket Live Feed

```mermaid
sequenceDiagram
    participant WH as Webhook
    participant PL as LangGraph Pipeline
    participant WS as WebSocket Manager
    participant DASH as React Dashboard

    DASH->>WS: connect ws://localhost:8000/ws/events
    WH->>PL: ainvoke(event)
    PL->>WS: broadcast "pipeline_started"
    WS->>DASH: {type: "pipeline_started", run_id, payload}
    PL->>WS: broadcast "signature_extracted"
    WS->>DASH: {type: "signature_extracted", ...}
    PL->>WS: broadcast "graph_updated"
    WS->>DASH: {type: "graph_updated", node_id, node_type}
```

Events: `pipeline_started`, `signature_extracted`, `graph_updated`, `eval_complete`

---

## Runtime Topology

```
┌─────────────────────────────────────────────────────────┐
│  Developer machine / CI                                  │
│                                                          │
│  ┌─────────────────────────┐    ┌─────────────────────┐ │
│  │  FastAPI (port 8000)    │    │  React Vite (3000)  │ │
│  │  PYTHONPATH=packages    │    │  /api → :8000 proxy │ │
│  │  uv run uvicorn ...     │    │  /ws  → :8000 proxy │ │
│  └────────────┬────────────┘    └────────────┬────────┘ │
│               │                              │          │
│  ┌────────────▼────────────┐    ┌────────────▼────────┐ │
│  │  Neo4j 5 (port 7687)    │    │  MCP Server         │ │
│  │  Docker container       │    │  node dist/index.js │ │
│  │  neo4j:5-community      │    │  stdio transport    │ │
│  └─────────────────────────┘    └─────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

| Decision | Choice | Why |
|---|---|---|
| Graph database | Neo4j 5 | Native graph traversal for SIMILAR_TO and SUPPRESSED_BY chains; Cypher is expressive for genealogy recursion |
| LLM / embeddings | NVIDIA NIM | Single API key for both streaming LLM and 4096-dim embeddings; no OpenAI dependency |
| Orchestrator | LangGraph | Built-in conditional edges (skip embed/write if extraction failed); state is typed via TypedDict |
| Dedup | Cosine similarity | Embedding-space dedup finds semantically identical failures with different error messages |
| Fragility scoring | PageRank × N/2 | PageRank naturally rewards nodes with many similar failures linking to them; N/2 normalization makes scores human-readable |
| MCP transport | stdio | Simplest transport; works with Claude Code and Cursor without a separate HTTP server |
| Frontend | React + Vite | No SSR needed; Vite's dev proxy eliminates CORS config; simpler than Next.js for a monitoring dashboard |
| Metadata DB | SQLite | Append-only audit log; zero ops; aiosqlite keeps it async |
