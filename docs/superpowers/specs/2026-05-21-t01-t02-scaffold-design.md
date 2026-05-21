# PhoenixOS — T01+T02 Scaffold Design

**Date:** 2026-05-21
**Scope:** Engineer 1, Tasks T01 (monorepo setup) + T02 (Docker + FastAPI skeleton)
**Parent spec:** `../../2026-05-20-phoenixos-design.md`

---

## Goal

Produce a working, committed monorepo scaffold so T03+ (SQLite schema, webhook, agents) can proceed without setup friction.

---

## T01 — Monorepo Setup

### Python (uv)

- `pyproject.toml` at repo root — declares `packages/core` as the editable package
- `uv.lock` generated on first `uv sync`
- Dependencies declared upfront: `fastapi`, `uvicorn`, `pydantic`, `neo4j`, `openai`, `langgraph`, `networkx`, `python-dotenv`, `aiosqlite`
- Dev deps: `ruff`, `mypy`, `pytest`, `httpx`

### Node (pnpm workspaces)

- `package.json` at root with `"workspaces": ["packages/mcp", "packages/dashboard"]`
- `pnpm-workspace.yaml` listing same paths
- No packages installed yet — workspace scaffold only

### pre-commit

- `.pre-commit-config.yaml` with:
  - `ruff` (lint + autofix + format via `ruff format` — replaces black)
  - `mypy` (type check, non-blocking on stubs)

### Folder skeleton

```
phoenixos/
├── packages/
│   ├── core/
│   │   ├── __init__.py      # makes packages/core a proper Python package
│   │   ├── main.py          # FastAPI stub
│   │   ├── api/
│   │   │   └── __init__.py
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   └── judge/
│   │   │       └── __init__.py
│   │   ├── graph/
│   │   │   └── __init__.py
│   │   ├── ingestor/
│   │   │   └── __init__.py
│   │   ├── embeddings/
│   │   │   └── __init__.py
│   │   ├── orchestrator/
│   │   │   └── __init__.py
│   │   ├── models/
│   │   │   └── __init__.py
│   │   └── db/
│   │       └── __init__.py
│   ├── mcp/
│   │   └── src/
│   └── dashboard/
│       └── app/
├── nano/
├── infra/
│   ├── Dockerfile           # builds the core FastAPI service
│   ├── docker-compose.yml
│   └── .env.example
├── scripts/
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   └── superpowers/specs/
├── .github/
│   └── workflows/
├── .pre-commit-config.yaml
├── pyproject.toml
├── pnpm-workspace.yaml
└── package.json
```

---

## T02 — Docker Compose + FastAPI Skeleton

### docker-compose.yml (`infra/`)

| Service | Image | Ports | Notes |
|---|---|---|---|
| `neo4j` | `neo4j:5-community` | 7474, 7687 | `NEO4J_AUTH=none` for dev, named volume for data |
| `core` | local Dockerfile | 8000 | mounts `packages/core`, hot-reload via uvicorn |

MCP and dashboard services added in later tasks — stubs only in compose for now.

### FastAPI skeleton (`packages/core/main.py`)

- Single `GET /health` endpoint → `{"status": "ok", "neo4j": "pending"}` (`neo4j` field hardcoded `"pending"` in T02; live driver check added in T08)
- Router registration stubs for `api/webhooks`, `api/graph`, `api/evals`, `api/ws`
- Lifespan handler (startup/shutdown hooks for Neo4j driver)

### DB stubs

**`packages/core/db/neo4j.py`**
- `AsyncNeo4jDriver` context manager wrapping `neo4j.AsyncGraphDatabase.driver()`
- `get_session()` async generator for dependency injection

**`packages/core/db/sqlite.py`**
- `get_db()` returning aiosqlite connection
- Path read from `SQLITE_PATH` env var (default `./data/phoenix.db`)

### `infra/.env.example`

```
NEO4J_URI=bolt://localhost:7687
NEO4J_AUTH=none
OPENAI_API_KEY=sk-...
SQLITE_PATH=./data/phoenix.db
```

---

## Success Criteria

- `docker compose up` starts Neo4j without error
- `uv run uvicorn core.main:app --reload` starts FastAPI (editable install exposes `core.main`, not `packages.core.main`)
- `GET /health` returns 200
- All empty module dirs have `__init__.py` (importable)
- `pre-commit run --all-files` passes

---

## What This Does NOT Include

- SQLite schema creation (T03)
- Actual Neo4j schema / Cypher (T08)
- Any agent logic (T04+)
- pnpm package installs for mcp/dashboard (T25, T31)
