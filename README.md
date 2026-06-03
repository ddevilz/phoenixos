# PhoenixOS

Self-healing knowledge substrate for AI-native engineering teams. Builds a semantic failure graph from CI events, scores AI-generated PRs with 3 judge agents, and exposes everything via MCP so AI coding tools can query failure history in real time.

**Docs:** [REPORT.md](REPORT.md) — full implementation report · [ARCHITECTURE.md](ARCHITECTURE.md) — system diagrams

---

## What's Built

| Layer | Status |
|---|---|
| Python monorepo (uv + hatchling) | ✅ |
| Docker Compose (Neo4j 5 + core) | ✅ |
| SQLite schema — pipeline_runs, failure_events | ✅ |
| GitHub Actions webhook → FailureEvent | ✅ |
| LLM failure signature extractor (NVIDIA NIM streaming) | ✅ |
| NVIDIA NIM embedding pipeline (nv-embed-v1, 4096-dim) | ✅ |
| Cosine dedup (0.92 exact / 0.80 similar thresholds) | ✅ |
| Neo4j schema — 4 node types, 5 relationship types | ✅ |
| Graph Writer — Cypher MERGE writes | ✅ |
| FragilityScore — NetworkX PageRank | ✅ |
| FlakinessTrajectory — rolling 7-run slope | ✅ |
| FixGenealogy — recursive SUPPRESSED_BY traversal | ✅ |
| Predictor — embedding similarity → ranked failures | ✅ |
| Blast radius — graph traversal from changed files | ✅ |
| LangGraph orchestrator — full ingest → judge pipeline | ✅ |
| WebSocket broadcast (`/ws/events`) | ✅ |
| PR diff parser — GitHub API + test file discovery | ✅ |
| Behavior Judge | ✅ |
| Security Judge (SSRF/injection block override) | ✅ |
| Regression Judge (cross-refs graph) | ✅ |
| Aggregate scorer — weighted trust score | ✅ |
| Eval graph writer — EvalResult + ContractViolation nodes | ✅ |
| `POST /api/evals/run` — full eval pipeline endpoint | ✅ |
| TypeScript MCP server — 4 tools | ✅ |
| MCP integration tests (16 passing) | ✅ |
| Python unit tests (116 passing) | ✅ |
| React (Vite) dashboard — FailureGraph, LiveFeed, JudgeScorecard | ✅ |
| `nano_phoenix.py` — 500 LOC self-contained distillation | ✅ |
| GitHub Actions self-test — PhoenixOS evaluates its own PRs | ✅ |

---

## Quickstart

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 20+, pnpm, Docker

```bash
# 1. Python deps
uv sync --extra dev

# 2. TypeScript MCP server
cd packages/mcp && pnpm install && pnpm build && cd ../..

# 3. Environment
cp infra/.env.example .env
# Add NVIDIA_API_KEY to .env

# 4. Start services (Neo4j + core API)
cd infra && docker compose up --build
# Neo4j cold start ~30s
# → http://localhost:8000/health
# → http://localhost:7474 (Neo4j browser)

# 5. Or run locally without Docker
uv run uvicorn core.main:app --reload
```

---

## Run Tests

```bash
# Python (116 tests)
uv run pytest tests/ -v

# TypeScript MCP (16 tests)
cd packages/mcp && pnpm test
```

---

## MCP Integration (Claude Code / Cursor)

The `.mcp.json` at the project root auto-registers the PhoenixOS MCP server with Claude Code and Cursor. Start the core API, then open this project — 4 tools become available immediately:

| Tool | Description |
|---|---|
| `get_fragility_score` | Fragility score + trend for a file path |
| `get_similar_failures` | Past failures similar to a stack trace |
| `get_fix_genealogy` | Fix chain — how deep is the symptom suppression? |
| `predict_blast_radius` | Which components are at risk given changed files? |

---

## Project Structure

```
phoenixos/
├── packages/
│   ├── core/                     # Python — FastAPI monolith
│   │   ├── main.py               # App entry, router registration
│   │   ├── api/
│   │   │   ├── webhooks.py       # GitHub Actions webhook → FailureEvent
│   │   │   ├── graph.py          # Graph query REST endpoints
│   │   │   ├── evals.py          # Eval trigger + judge pipeline
│   │   │   └── ws.py             # WebSocket live event feed
│   │   ├── agents/
│   │   │   └── predictor.py      # Failure prediction from graph
│   │   ├── judge/
│   │   │   ├── base.py           # BaseJudge ABC — streaming, timeout, JSON parse
│   │   │   ├── behavior.py       # Behavioral contract judge
│   │   │   ├── security.py       # Security judge (SSRF/injection block)
│   │   │   ├── regression.py     # Regression judge (cross-refs graph)
│   │   │   ├── scorer.py         # Weighted aggregate trust score
│   │   │   └── graph_writer.py   # EvalResult + ContractViolation → Neo4j
│   │   ├── graph/
│   │   │   ├── writer.py         # Cypher MERGE writes
│   │   │   ├── scoring.py        # FragilityScore (PageRank), FlakinessTrajectory
│   │   │   ├── genealogy.py      # FixGenealogy SUPPRESSED_BY traversal
│   │   │   └── blast_radius.py   # Blast radius traversal
│   │   ├── ingestor/
│   │   │   ├── signature.py      # LLM extraction → FailureSignature + embedding
│   │   │   └── diff_parser.py    # GitHub PR diff + test file discovery
│   │   ├── embeddings/
│   │   │   ├── pipeline.py       # Text → NVIDIA nv-embed-v1 vector (4096-dim)
│   │   │   └── dedup.py          # Cosine similarity dedup
│   │   ├── orchestrator/
│   │   │   └── pipeline.py       # LangGraph state machine
│   │   ├── models/
│   │   │   └── failure.py        # FailureEvent, FailureSignature, JudgeResult, AggregateScore
│   │   └── db/
│   │       ├── neo4j.py          # Async Neo4j driver + session context manager
│   │       └── sqlite.py         # aiosqlite — pipeline_runs, failure_events
│   │
│   ├── mcp/                      # TypeScript — MCP server
│   │   ├── src/
│   │   │   ├── index.ts          # Server entry, 4 tool registrations
│   │   │   ├── client.ts         # HTTP client → core API at localhost:8000
│   │   │   ├── tools.ts          # Tool implementations
│   │   │   └── tools.test.ts     # 16 vitest tests
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── dashboard/                # React (Vite) — monitoring dashboard
│       ├── src/
│       │   ├── App.tsx           # Router + nav
│       │   ├── components/       # FailureGraph, LiveFeed, JudgeScorecard
│       │   ├── pages/            # MemoryGraph, Evals, mock screens
│       │   └── lib/api.ts        # apiFetch + shared types
│       └── vite.config.ts        # Proxy → localhost:8000
│
├── infra/
│   ├── Dockerfile
│   ├── docker-compose.yml        # neo4j:5-community + core
│   └── .env.example
│
├── tests/
│   └── unit/                     # 116 pytest tests
│
├── scripts/
│   ├── seed_demo.py              # Seed 20+ synthetic failure signatures
│   └── demo_script.md            # 2-min recording script
│
├── nano_phoenix.py               # 500 LOC self-contained PhoenixOS distillation
├── .github/workflows/self_test.yml  # CI: unit + MCP + integration jobs
├── .mcp.json                     # Claude Code / Cursor MCP registration
├── pyproject.toml
└── package.json                  # pnpm workspaces root
```

---

## Docs

| Document | What's in it |
|---|---|
| [REPORT.md](REPORT.md) | Full implementation report — every layer, every decision, API reference, test coverage, limitations |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Mermaid diagrams — ingest pipeline, Neo4j schema, eval mesh, MCP sequence, runtime topology |

---

## Environment Variables

Copy `infra/.env.example` to `.env`:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_AUTH=none
NVIDIA_API_KEY=nvapi-...
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
SQLITE_PATH=./data/phoenix.db
GITHUB_TOKEN=ghp-...        # optional — for fetching PR diffs
```

---

## Tech Stack

| Layer | Tech |
|---|---|
| API + agents | Python 3.11, FastAPI, LangGraph |
| LLM calls | NVIDIA NIM — `minimaxai/minimax-m2.7` (streaming) |
| Embeddings | NVIDIA NIM — `nvidia/nv-embed-v1` (4096-dim) |
| Graph DB | Neo4j 5 Community (Docker) |
| Metadata DB | SQLite via aiosqlite |
| MCP server | TypeScript, @modelcontextprotocol/sdk |
| Package mgmt | uv (Python), pnpm workspaces (TS) |

---

## The Pitch (5 slides)

### Slide 1 — Problem
Every CI break is diagnosed from scratch. GitHub Copilot ships one-click fixes. Neither builds memory. Teams ship AI-written code with no institutional knowledge of what has failed before, where it will fail next, or whether the fix is trustworthy.

### Slide 2 — What PhoenixOS Does
Three working layers:
- **Memory Graph** — semantic failure signatures in Neo4j. Every CI failure is embedded, deduplicated, and linked. Fragility scores recompute after every write.
- **Eval Mesh** — 3 judge agents (Behavior, Security, Regression) score every AI-generated PR in parallel. Security blocks propagate regardless of other scores.
- **MCP Integration** — 4 tools live in Claude Code and Cursor today. Ask `get_similar_failures` and get "this pattern has appeared 47 times, fix chain depth 3 — symptom suppression warning."

### Slide 3 — The MCP Moment
Open Cursor on any repo with PhoenixOS running. Type a stack trace. The `get_similar_failures` tool returns ranked past failures with genealogy depth. The AI coding tool already knows your failure history before you do.

### Slide 4 — Architecture
```
CI Webhook → LangGraph pipeline → Neo4j Memory Graph
                                        ↕
                              MCP server (TypeScript)
                                        ↕
                           Claude Code / Cursor / any MCP client
```
Single FastAPI monolith. Neo4j for graph. NVIDIA NIM for LLM + embeddings. 116 Python tests + 16 TypeScript tests.

### Slide 5 — nanoPhoenix
`nano_phoenix.py` — the entire concept in 500 lines. Self-contained. Zero external dependencies beyond FastAPI. Run it on any machine in 30 seconds. Shows the idea is real, not just architecture slides.
