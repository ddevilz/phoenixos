# PhoenixOS — Live Demo Runbook

This runbook walks through a live demo: push a breaking commit to a real GitHub repo → its Actions workflow fails → the webhook fires into a local PhoenixOS instance via a tunnel → the LangGraph pipeline runs → a node pulses into the FailureGraph dashboard → open a PR and run an eval so three judges score it live, with the regression judge's graph-link chips tying back to the graph.

---

## 1. Prerequisites

### Required environment variables

Copy `infra/.env.example` to `.env` at the project root and fill in every value below.

| Variable | Where it comes from | Required for |
|---|---|---|
| `NVIDIA_API_KEY` | [build.nvidia.com](https://build.nvidia.com) → API Keys | LLM extraction (minimax-m2.7) + embeddings (nv-embed-v1) |
| `NVIDIA_BASE_URL` | Set to `https://integrate.api.nvidia.com/v1` | NIM base URL |
| `GITHUB_WEBHOOK_SECRET` | A random string you choose — must match the secret you register on GitHub | HMAC signature verification on all incoming webhooks |
| `GITHUB_TOKEN` | A GitHub PAT with `repo` and `read:org` scopes | Fetching changed files per commit SHA; optional for seed script |
| `NEO4J_URI` | `bolt://localhost:7687` (local) | Core API → Neo4j connection |
| `NEO4J_AUTH` | `none` | Neo4j auth (Community edition, no password) |
| `SQLITE_PATH` | `./data/phoenix.db` | SQLite pipeline audit log |

> **Note:** `infra/.env.example` shows `OPENAI_API_KEY` as a placeholder — that field is unused by the current pipeline. The real key you need is `NVIDIA_API_KEY`. When Docker Compose starts the `core` service it reads from `.env` at the project root (the `env_file: - ../.env` directive in `infra/docker-compose.yml`).

### Tools

| Tool | Version | Install |
|---|---|---|
| Docker + Docker Compose plugin | Docker Desktop 4.x or Docker Engine + Compose v2 | [docs.docker.com](https://docs.docker.com/get-docker/) |
| `uv` | 0.4+ | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js + `pnpm` | Node 20+, pnpm 9+ | `npm i -g pnpm` |
| Tunnel tool | `cloudflared` or `ngrok` | See note below |

**Tunnel assumption:** The commands below use `cloudflared tunnel --url http://localhost:8000`. If you use `ngrok`, substitute `ngrok http 8000` — the resulting HTTPS URL is the same shape. Neither tool requires an account for a temporary URL; `cloudflared` quick tunnels work without login.

### Demo repo

A ready-made demo repo already exists: **https://github.com/ddevilz/phoenix-demo**. It has a real GitHub Actions test suite (green on `main`) plus `break.sh` / `reset.sh` to fail and restore it on cue. Clone it next to this project:

```bash
git clone https://github.com/ddevilz/phoenix-demo.git ~/Desktop/phoenix-demo
```

Section 3 documents its layout. (If you'd rather build your own, the same structure works.)

---

## 2. Startup order

Run each step in a separate terminal tab and wait for each to be ready before proceeding.

### Step 1 — Start Neo4j + core API

```bash
# From the project root
docker compose -f infra/docker-compose.yml up --build
```

Neo4j takes ~30 s on cold start. The `core` service waits for Neo4j's healthcheck before starting. Watch for the uvicorn startup line:

```
INFO:     Application startup complete.
```

### Step 2 — Confirm /health

```bash
curl -s http://localhost:8000/health
```

Expected response:

```json
{"status": "ok", "neo4j": "ok"}
```

Do not proceed until `neo4j` is `"ok"`. If it shows `"pending"`, Neo4j is still initialising — wait 10 s and retry.

### Step 3 — Seed the baseline graph

The seed script ingests 22 synthetic failure signatures across four categories (`test_failure`, `build_error`, `contract_violation`, `flaky`), waits 30 s for background extraction tasks, then writes three `SUPPRESSED_BY` fix chains.

```bash
# From the project root
GITHUB_TOKEN=ghp_... PHOENIX_API_URL=http://localhost:8000 uv run scripts/seed_demo.py
```

`GITHUB_TOKEN` is optional; without it the script skips the live GitHub fetch and uses only synthetic data (still produces the full seeded graph). Seeding takes roughly 2–4 minutes because each event triggers two NVIDIA NIM calls (extraction + embedding) with a 2 s throttle between events.

### Step 4 — Start the dashboard

```bash
# From the project root
pnpm --filter @phoenixos/dashboard dev
```

Dashboard available at **http://localhost:3000**. The Vite dev server proxies `/api` and `/ws` to `localhost:8000`, so no CORS configuration is needed.

### Step 5 — Start the tunnel

```bash
# Option A — cloudflared (no account needed for a quick tunnel)
cloudflared tunnel --url http://localhost:8000

# Option B — ngrok
ngrok http 8000
```

Both tools print a public HTTPS URL, e.g. `https://abc123.trycloudflare.com`. Copy it — you need it in the next step.

### Step 6 — Register the webhook on GitHub

In your demo repo on GitHub: **Settings → Webhooks → Add webhook**

| Field | Value |
|---|---|
| Payload URL | `<tunnel-url>/api/webhooks/github` (e.g. `https://abc123.trycloudflare.com/api/webhooks/github`) |
| Content type | `application/json` |
| Secret | The value of `GITHUB_WEBHOOK_SECRET` in your `.env` |
| Which events | Select **Workflow runs** only |

Click **Add webhook**. GitHub will send a ping event; the core API returns 200 and logs it.

**Faster (CLI, no clicking)** — register the webhook on `ddevilz/phoenix-demo` in one command once the tunnel URL is known:

```bash
gh api repos/ddevilz/phoenix-demo/hooks -X POST \
  -f name=web -F active=true -f 'events[]=workflow_run' \
  -f config[url]="<tunnel-url>/api/webhooks/github" \
  -f config[content_type]=json \
  -f config[secret]="$GITHUB_WEBHOOK_SECRET"
```

To update the URL on a later tunnel restart: `gh api repos/ddevilz/phoenix-demo/hooks` to list (grab the hook `id`), then `gh api repos/ddevilz/phoenix-demo/hooks/<id> -X PATCH -f config[url]="<new-url>/api/webhooks/github" -f config[content_type]=json -f config[secret]="$GITHUB_WEBHOOK_SECRET"`.

> **Why this path?** The webhook router is mounted at prefix `/api/webhooks` (see `packages/core/api/webhooks.py` line 19) and the POST endpoint is `/github` (line 57). The full path is therefore `/api/webhooks/github`.

---

## 3. Demo repo setup (`ddevilz/phoenix-demo`)

The repo at **https://github.com/ddevilz/phoenix-demo** is ready to use.

### Layout

```
phoenix-demo/
├── .github/workflows/ci.yml   # runs pytest on every push / PR
├── src/transfer.py            # transfer layer with a 30s budget
├── tests/test_transfer.py     # asserts elapsed <= 30s
├── break.sh                   # introduce the regression + push (run LIVE)
└── reset.sh                   # restore green to re-run the demo
```

### How it fails on cue

`main` is green: `simulate_transfer()` returns `12` (≤ 30s budget). `break.sh` flips that return to `42` and pushes, so the test fails with:

```
transfer timeout regression: elapsed exceeded 30s budget
```

That message is deliberately **timeout-themed** — PhoenixOS extracts a signature whose embedding lands next to the seeded `curl/curl` `lib/transfer.c` timeout cluster, so the new node arrives **with a real `SIMILAR_TO` edge** and a populated blast radius rather than floating alone.

### One-time prep

```bash
git clone https://github.com/ddevilz/phoenix-demo.git ~/Desktop/phoenix-demo
```

No editing needed. Just keep this checkout handy; you run `break.sh` during the demo.

---

## 4. Live script (the actual demo)

### Beat 1 — Push the breaking commit (~0:00)

```bash
cd ~/Desktop/phoenix-demo && ./break.sh
```

`break.sh` introduces the regression, commits, and pushes to `main`. GitHub Actions picks it up immediately. The workflow runs, the test fails, and the `workflow_run` webhook fires with `action: completed` and `conclusion: failure`.

> After the demo, run `./reset.sh` to restore green so you can replay.

### Beat 2 — Watch the LiveFeed ticker (~0:30–1:00)

In the dashboard, open the **LiveFeed** panel (bottom of the screen or sidebar). You will see three events arrive in sequence over ~30–60 seconds:

```
pipeline_started       run_id: …
signature_extracted    category: test_failure, component: …
graph_updated          node_id: …, node_type: FailureSignature
```

> **Narration:** "The pipeline is making two NVIDIA NIM calls — one to minimax-m2.7 to extract the structured failure signature from the log, and one to nv-embed-v1 to get a 4096-dimension embedding for dedup and similarity search. That's why it takes 30–60 seconds, not instant."

The status dot in the LiveFeed header is orange (live/connected to WebSocket). If it is grey, the WebSocket connection to `localhost:8000/ws/events` dropped — see Troubleshooting.

### Beat 3 — Node pulses into the graph (~1:00)

After the `graph_updated` event, switch to the **FailureGraph** tab. The new node pulses (brief scale animation) and is auto-selected. The node is coloured by fragility score: grey (new, low score) through amber to red (high fragility).

### Beat 4 — Walk the inspector tabs (~1:00–2:00)

Click the node. The right-side inspector opens with four tabs:

| Tab | What to show |
|---|---|
| **Overview** | `summary`, `category`, `affected_component`, `occurrence_count`, `first_seen` / `last_seen` |
| **Neighbors** | `SIMILAR_TO` edges to related signatures; edge labels show cosine similarity (0.80–0.92 range) |
| **Flakiness** | Rolling 7-run slope — useful if this pattern has appeared before |
| **Blast radius** | Components transitively at risk via `SIMILAR_TO` traversal |

> **Narration:** "Every new failure is deduplicated in embedding space. Cosine ≥ 0.92 = exact duplicate (counter increments, no new node). 0.80–0.92 = similar (new node + SIMILAR_TO edge). Below 0.80 = novel failure. This node got a SIMILAR_TO edge to the seeded `lib/transfer.c` timeout signature because the test message is semantically close."

### Beat 5 — Run an eval (~2:00–3:00)

In the dashboard, navigate to **Evals** (top nav). Two ways to feed it:

- **Open a PR**: instead of `break.sh` (which pushes to `main`), make the same regression on a branch and open a PR to `main`, then paste the PR URL into the eval input. Best for the full story.
- **Paste a diff**: skip GitHub entirely — paste the `break.sh` diff (the `return 12` → `return 42` change in `src/transfer.py`) straight into the diff box. Fastest, no network dependency.

Click **Run Eval**.

The three judges run in parallel (asyncio.gather):

| Judge | What it checks |
|---|---|
| **Behavior** | Contract breaks, missing test coverage |
| **Security** | SSRF, injection, hardcoded secrets |
| **Regression** | Matches past failures, touches high-fragility components |

### Beat 6 — JudgeScorecard results (~3:00–3:30)

The **JudgeScorecard** renders after all three judges complete. Point out:

- The **Regression judge** section shows graph-link chips labelled `Touches graph nodes: <node-id>` — these link directly back to the FailureSignature nodes in the graph.
- Aggregate trust score formula: `behavior × 0.4 + security × 0.4 + regression × 0.2`.
- If the security judge flagged anything (SSRF / injection), the verdict is `block` regardless of the weighted score.

> **Narration:** "The regression judge queried the graph for signatures whose `affected_component` overlaps the files changed in this PR. The chips you see are clickable — each one navigates to the Memory Graph and selects the graph node whose component matches the chip (matched by `affected_component`; if several signatures share a component, the first is selected), closing the loop between the eval verdict and the failure history."

---

## 5. Fallback

If the tunnel goes down, GitHub Actions is flaky, or the webhook does not arrive mid-demo, replay the graph population live:

```bash
GITHUB_TOKEN=ghp_... PHOENIX_API_URL=http://localhost:8000 uv run scripts/seed_demo.py
```

This re-ingests all 22 synthetic events and re-runs the pipeline for each. The graph will repopulate and nodes will pulse into the dashboard in real time — the visual effect is identical to the live webhook path.

The dashboard's LiveFeed header dot shows **green/orange = live** (WebSocket connected to the running core API) and **grey = offline** (disconnected). You can narrate this dot as the "heartbeat" indicator. Even in offline mode, previously written graph data is still queryable from Neo4j, so the FailureGraph, inspector tabs, and Evals all work.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Webhook returns **401 Unauthorized** | `GITHUB_WEBHOOK_SECRET` mismatch — the value in `.env` does not match the secret registered on GitHub | Re-check `.env` → `GITHUB_WEBHOOK_SECRET`; update the GitHub webhook secret to match; or temporarily clear the secret in `.env` (the code skips HMAC if the variable is empty) |
| Node never appears in FailureGraph after ~90 s | `NVIDIA_API_KEY` invalid or rate-limited, or the pipeline timed out | Check core container logs: `docker compose -f infra/docker-compose.yml logs core --tail 50`; look for `401` or `429` from NIM; verify `NVIDIA_API_KEY` in `.env` |
| Graph is empty / no nodes render | Neo4j not ready, or seed not run | Confirm `/health` returns `neo4j: "ok"`; run the seed script (Section 2, Step 3) |
| Dashboard shows **"Graph unavailable"** | Core API down, or `VITE_API_URL` / Vite proxy misconfigured | Ensure `docker compose up` is running and `http://localhost:8000/health` responds; the Vite proxy config in `packages/dashboard/vite.config.ts` forwards `/api` and `/ws` to `localhost:8000` — if you changed the core port you must update the proxy target |
| LiveFeed dot is grey (offline) | WebSocket connection to `ws://localhost:8000/ws/events` dropped | Restart the dashboard (`pnpm --filter @phoenixos/dashboard dev`); ensure the core service is running and not restarting |
| Seed script exits with `API not reachable` | Core API not yet started | Start Docker Compose first (Step 1); wait for `/health` to return `neo4j: ok` before running the seed |
| Tunnel URL changes between demo sections | `cloudflared` quick tunnels generate a new URL on restart | Use a named tunnel (requires a Cloudflare account) or keep the same terminal open; if the URL changes, update the GitHub webhook Payload URL in repo Settings |
