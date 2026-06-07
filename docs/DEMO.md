# PhoenixOS — Demo Guide

## What is PhoenixOS?

PhoenixOS is a CI failure intelligence layer that sits between your GitHub Actions and your engineering team.

Every time a CI run fails, PhoenixOS ingests the log, extracts a structured failure signature using an LLM (NVIDIA minimax-m2.7), embeds it into vector space (nv-embed-v1), and deduplicates it against everything that has ever failed before. Over time it builds a **memory graph** of your failure history — not a list of red builds, but a semantic map of *why* things break and what they affect.

On top of that memory graph, it scores every incoming pull request through three judges before the code merges.

---

## How it helps

| Without PhoenixOS | With PhoenixOS |
|---|---|
| PR merges, breaks prod, team scrambles | PR scored before merge — regression risk surfaced inline |
| Same bug pattern recurs across sprints | Failure deduplicated on first occurrence; future hits increment the counter |
| "This has happened before" — no one knows where | Memory Graph shows the exact prior failure node, its history, and what else it touched |
| AI-generated code merges silently | Trust Ledger records provenance; bot-authored code flagged with its own eval chain |

---

## The five panels

### Memory Graph
The live view of every failure PhoenixOS has seen. Each node is a `FailureSignature` — a deduplicated, LLM-extracted record of a failure pattern. Nodes are colored by **fragility score** (PageRank over the similarity graph):

- 🔴 **Red ≥ 0.7** — high fragility, frequently fails or deeply connected
- 🟡 **Amber 0.4–0.7** — moderate, worth watching
- 🟢 **Green < 0.4** — stable, isolated

Edges (`SIMILAR_TO`) connect signatures whose embeddings land within cosine 0.80–0.92. A cosine ≥ 0.92 is an exact duplicate — the counter increments, no new node. Below 0.80 is a novel failure — new node, no edge.

Click any node to open the inspector: **Overview** (summary, component, occurrence count) → **Neighbors** (similar failures with cosine scores) → **Flakiness** (rolling trend over 28 days) → **Blast Radius** (components transitively at risk).

### Evals
Paste a PR URL or a raw diff and click **Run Eval**. Three judges run in parallel:

| Judge | What it checks | Weight |
|---|---|---|
| **Behavior** | Contract breaks, missing test coverage, return-type shifts | 40% |
| **Security** | SSRF, injection, hardcoded secrets, OWASP Top 10 | 40% |
| **Regression** | Matches past failures in the Memory Graph, touches high-fragility components | 20% |

Trust score = `behavior × 0.4 + security × 0.4 + regression × 0.2`. Security `block` overrides the weighted score regardless. The Regression judge outputs clickable graph-link chips — each chip navigates to the exact Memory Graph node that matches the changed component, closing the loop between the eval verdict and the failure history.

### Intent Compiler
Takes a natural-language feature request and compiles it into a formal spec: **preconditions**, **invariants**, **postconditions**, **edge cases**. The goal is to catch ambiguity before code is written, not after it breaks. The live version diffs the compiled spec against the actual implementation at PR creation time.

*Example: "Add rate limiting to /api/evals/run, max 10 req/min per IP" → spec with sliding-window invariant, 429 + Retry-After postcondition, shared-NAT edge case.*

### Behavior Twin
Given the files changed in a PR, the Behavior Twin walks the Memory Graph to find every component transitively at risk. It returns a ranked list with fragility scores and reasons ("imports auth.validate_token", "shares DB connection pool"). This is the blast radius view — what could break if this PR has a bug.

*Backed by `POST /api/graph/blast-radius` — the same traversal the Regression judge runs internally.*

### Trust Ledger
An immutable, time-ordered provenance chain of every eval result: PR URL, timestamp, author, per-judge scores, flags, and final verdict. Bot-authored code (GitHub Copilot, etc.) appears with its own `author` tag so AI-generated changes are never anonymous in the audit trail.

---

## Running the demo

### Prerequisites

Copy `infra/.env.example` to `.env` at the project root. Required variables:

| Variable | Value |
|---|---|
| `NVIDIA_API_KEY` | From [build.nvidia.com](https://build.nvidia.com) → API Keys |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` |
| `GITHUB_WEBHOOK_SECRET` | Any random string — must match the GitHub webhook secret |
| `NEO4J_URI` | `bolt://localhost:7687` |
| `NEO4J_AUTH` | `none` |
| `SQLITE_PATH` | `./data/phoenix.db` |

Tools needed: Docker, `uv`, Node.js + `pnpm`, `cloudflared` or `ngrok`.

---

### Step 1 — Start the stack

```bash
docker compose -f infra/docker-compose.yml up --build
```

Wait for:
```
INFO:     Application startup complete.
```

Confirm Neo4j is ready:
```bash
curl -s http://localhost:8000/health
# → {"status": "ok", "neo4j": "ok"}
```

---

### Step 2 — Seed the baseline graph

```bash
GITHUB_WEBHOOK_SECRET=<your-secret> uv run scripts/seed_demo.py
```

Seeds 22 synthetic failure signatures across `test_failure`, `build_error`, `contract_violation`, and `flaky` categories. Takes ~2–4 minutes (two NIM calls per event: extraction + embedding, 2 s throttle). After seeding, trigger fragility recompute:

```bash
curl -s -X POST http://localhost:8000/api/graph/fragility/recompute
```

The graph now has varied node colors — red, amber, and green nodes with `SIMILAR_TO` edges.

---

### Step 3 — Start the dashboard

```bash
pnpm --filter @phoenixos/dashboard dev
```

Open **http://localhost:3000**.

---

### Step 4 — Start the tunnel

```bash
cloudflared tunnel --url http://localhost:8000
```

Copy the printed HTTPS URL (e.g. `https://abc123.trycloudflare.com`).

---

### Step 5 — Register the GitHub webhook

On **https://github.com/ddevilz/phoenix-demo** → Settings → Webhooks → Add webhook:

| Field | Value |
|---|---|
| Payload URL | `<tunnel-url>/api/webhooks/github` |
| Content type | `application/json` |
| Secret | Value of `GITHUB_WEBHOOK_SECRET` |
| Events | Workflow runs only |

Or via CLI:
```bash
gh api repos/ddevilz/phoenix-demo/hooks -X POST \
  -f name=web -F active=true -f 'events[]=workflow_run' \
  -f config[url]="<tunnel-url>/api/webhooks/github" \
  -f config[content_type]=json \
  -f config[secret]="$GITHUB_WEBHOOK_SECRET"
```

---

### The live demo beats

**Beat 1 — Push the breaking commit (0:00)**

```bash
cd ~/Desktop/phoenix-demo && ./break.sh
```

This injects three simultaneous regressions:
- `src/transfer.py` — timeout regression (elapsed 42s > 30s budget)
- `src/connection.py` — pool limit set to 0 (all acquire() calls throw)
- `src/auth.py` — HMAC prefix corrupted (`sha1=` instead of `sha256=`)

20 tests, multiple failures, rich log output for NIM to extract from.

> After the demo: `./reset.sh` restores green for replay.

**Beat 2 — Watch the Live Feed (0:30–1:00)**

In the dashboard, watch the Live Feed ticker. Events arrive in order:
```
pipeline_started       run_id: …
signature_extracted    category: test_failure, component: src/transfer.py
graph_updated          node_id: …
```

> "The pipeline makes two NVIDIA NIM calls per failure — minimax-m2.7 extracts the structured signature, nv-embed-v1 embeds it in 4096-dimensional space for dedup. That's the 30–60 second latency."

**Beat 3 — Node pulses into the graph (1:00)**

Switch to the Memory Graph tab. The new node pulses in and is auto-selected. It's colored by fragility score — a fresh node starts green, rises to amber or red as it accumulates connections and recurrences.

**Beat 4 — Walk the inspector (1:00–2:00)**

Click the node. Show all four tabs: Overview → Neighbors → Flakiness → Blast Radius.

> "Neighbors shows `SIMILAR_TO` edges — these are failures that embedded within cosine 0.80–0.92 of this one. The score in the edge label is the raw cosine similarity. This is how PhoenixOS knows a new `src/connection.py` pool exhaustion is related to the seeded `lib/openssl.c` TLS failure — both are auth/transport layer failures, semantically."

**Beat 5 — Run an eval (2:00–3:00)**

Navigate to **Evals**. Paste the `break.sh` diff or the PR URL. Click **Run Eval**. Three judges run in parallel.

**Beat 6 — JudgeScorecard (3:00–3:30)**

Point out:
- Regression judge shows graph-link chips → click one → Memory Graph selects that node
- Trust score formula at the bottom
- If security flagged anything → verdict is `block` regardless of weighted score

---

### Fallback (if webhook doesn't arrive)

Re-run the seed script. It re-ingests all 22 events and nodes pulse into the dashboard in real time — visually identical to the live webhook path.

```bash
GITHUB_WEBHOOK_SECRET=<your-secret> uv run scripts/seed_demo.py
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Webhook 401 | `GITHUB_WEBHOOK_SECRET` in `.env` doesn't match GitHub webhook secret — update one or the other |
| Node never appears after 90s | Check core logs: `docker compose logs core --tail 50` — look for NIM 401/429; verify `NVIDIA_API_KEY` |
| All nodes same color | Run `curl -s -X POST http://localhost:8000/api/graph/fragility/recompute` |
| Graph empty | Confirm `/health` shows `neo4j: ok`, then run seed script |
| Live Feed dot grey | WebSocket dropped — restart dashboard (`pnpm --filter @phoenixos/dashboard dev`) |
| Tunnel URL changed | Update GitHub webhook: `gh api repos/ddevilz/phoenix-demo/hooks/<id> -X PATCH -f config[url]="<new-url>/api/webhooks/github" -f config[content_type]=json -f config[secret]="$GITHUB_WEBHOOK_SECRET"` |
