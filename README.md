# PhoenixOS

Self-healing knowledge substrate for AI-native engineering teams. Builds a semantic failure graph from CI events, scores AI-generated PRs with 3 judge agents, and exposes everything via MCP so AI coding tools can query failure history in real time.

---

## What's Built (T01–T02)

Monorepo scaffold + FastAPI skeleton. No agent logic yet — just the working foundation.

| Layer | Status |
|---|---|
| Python monorepo (uv + hatchling) | ✅ |
| pnpm workspace (mcp, dashboard) | ✅ scaffold only |
| pre-commit (ruff + mypy) | ✅ |
| FastAPI core service | ✅ `/health` only |
| Neo4j async driver stub | ✅ stub, no schema |
| SQLite aiosqlite stub | ✅ stub, no schema |
| Docker Compose (Neo4j + core) | ✅ config valid |

---

## Quickstart

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker

```bash
# Install Python deps
uv sync --extra dev

# Run FastAPI locally
uv run uvicorn core.main:app --reload
# → http://localhost:8000/health

# Run with Docker (Neo4j + core)
cd infra
docker compose up --build
# Neo4j cold start ~30s, then core starts
# → http://localhost:8000/health
# → http://localhost:7474 (Neo4j browser)
```

---

## Run Tests

```bash
uv run pytest tests/ -v
```

---

## Project Structure

```
phoenixos/
├── packages/
│   ├── core/               # Python — FastAPI monolith (active)
│   │   ├── main.py         # App entry, /health endpoint
│   │   ├── api/            # Webhooks, graph, evals, ws (T04+)
│   │   ├── agents/         # Predictor, judge agents (T05+)
│   │   ├── graph/          # Neo4j schema, Cypher, scoring (T08+)
│   │   ├── ingestor/       # CI event parser (T04+)
│   │   ├── embeddings/     # OpenAI vector pipeline (T06+)
│   │   ├── orchestrator/   # LangGraph state machine (T15+)
│   │   ├── models/         # Pydantic models (T04+)
│   │   └── db/
│   │       ├── neo4j.py    # Async driver stub
│   │       └── sqlite.py   # aiosqlite stub
│   ├── mcp/                # TypeScript — MCP server (T25+)
│   └── dashboard/          # TypeScript — Next.js 14 (T31+)
├── nano/                   # Self-contained 500-LOC distillation (T36+)
├── infra/
│   ├── Dockerfile
│   ├── docker-compose.yml  # neo4j:5-community + core
│   └── .env.example
├── tests/
│   └── unit/test_health.py
└── pyproject.toml
```

---

## Environment Variables

Copy `infra/.env.example` to `.env`:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_AUTH=none
OPENAI_API_KEY=sk-...
SQLITE_PATH=./data/phoenix.db
```

---

## Tech Stack

| Layer | Tech |
|---|---|
| API + agents | Python 3.12, FastAPI, LangGraph |
| Graph DB | Neo4j 5 Community (Docker) |
| Metadata DB | SQLite via aiosqlite |
| Embeddings | OpenAI text-embedding-3-small |
| MCP server | TypeScript, @modelcontextprotocol/sdk |
| Dashboard | Next.js 14 |
| Package mgmt | uv (Python), pnpm workspaces (TS) |

---

## Roadmap

| Task | Description |
|---|---|
| T03 | SQLite schema — pipeline_runs, failure_events |
| T04 | GitHub Actions webhook → FailureEvent |
| T05 | LLM failure signature extractor |
| T06 | OpenAI embedding pipeline |
| T07 | Cosine dedup (0.92/0.80 thresholds) |
| T08 | Neo4j schema + Graph Writer |
| T09–T14 | FragilityScore, FlakinessTrajectory, FixGenealogy, Predictor, BlastRadius |
| T15 | LangGraph orchestrator |
| T16 | WebSocket broadcast |
| T18–T24 | Judge agents (Behavior, Security, Regression) + Eval Mesh |
| T25–T29 | TypeScript MCP server + 4 tools |
| T31–T35 | Next.js dashboard + mock screens |
