# PhoenixOS — 2-Min Demo Script

## Setup (before recording)

```bash
# Terminal 1 — start services
cd infra && docker compose up -d
sleep 30   # Neo4j cold start

# Terminal 2 — start API
PYTHONPATH=packages uv run uvicorn core.main:app --reload

# Terminal 3 — seed graph
GITHUB_TOKEN=<your_token> uv run scripts/seed_demo.py

# Terminal 4 — start dashboard
cd packages/dashboard && pnpm dev
# → http://localhost:3000

# Claude Code / Cursor — open project (auto-loads MCP via .mcp.json)
```

---

## Script (2 minutes)

### [0:00–0:20] — The Problem
> "Every time a CI build breaks, your team diagnoses it from scratch.
> No memory of what failed before. No idea where it will fail next.
> PhoenixOS fixes that."

*Show: empty dashboard, no graph yet*

---

### [0:20–0:45] — Trigger a failure
> "Watch what happens when a CI failure lands."

```bash
curl -X POST http://localhost:8000/api/webhooks/github \
  -H "Content-Type: application/json" \
  -d '{
    "action": "completed",
    "workflow_run": {
      "id": "demo-live-001", "name": "CI", "head_branch": "main",
      "conclusion": "failure", "head_sha": "abc123",
      "created_at": "2026-05-31T00:00:00Z",
      "updated_at": "2026-05-31T00:00:00Z",
      "html_url": "https://github.com/demo/repo/actions/runs/1"
    },
    "repository": {"full_name": "demo/repo"}
  }'
```

*Show: Live Feed in dashboard updates in real time — pipeline_started → signature_extracted → graph_updated*

---

### [0:45–1:10] — The Memory Graph
> "The failure was extracted, embedded, deduplicated, and written to the graph.
> Fragility scores recalculated. Red nodes are the most dangerous."

*Show: Memory Graph page, red/amber/green nodes, click a high-fragility node*

---

### [1:10–1:35] — MCP in Claude Code
> "Now open an AI coding tool. PhoenixOS is already registered as an MCP server."

*Switch to Claude Code / Cursor*

```
get_similar_failures("FAIL: test_tls_handshake_mock\nExpected CLIENT_HELLO, TIMEOUT")
```

*Show: response comes back with similar past signatures, fix genealogy depth, suppression warning*

> "The AI tool knows your failure history before you ask."

---

### [1:35–1:50] — Eval a PR
> "Submit an AI-generated PR diff. Three judge agents score it in parallel."

*Switch to dashboard → Evals tab, paste a diff, click Run Eval*

*Show: behavior/security/regression scores appear, aggregate trust score, any flags*

---

### [1:50–2:00] — nanoPhoenix
> "The whole idea in 500 lines. Zero infrastructure required."

```bash
uvicorn nano_phoenix:app --port 8001
curl -X POST http://localhost:8001/eval -d '{"diff": "..."}'
```

> "If you want to understand PhoenixOS, read nano_phoenix.py."
