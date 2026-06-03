"""
nano_phoenix.py — self-contained PhoenixOS distillation (~500 LOC)

Ingest CI failures → extract signature → Security Judge → in-memory graph.
Zero imports from packages/. Runs standalone with: uvicorn nano_phoenix:app

Endpoints:
  POST /ingest   { repo, run_id, job, step, exit_code, log_tail, changed_files }
  POST /eval     { diff }            → AggregateScore
  GET  /graph    → all signatures + fragility scores
  GET  /health   → {"status": "ok"}
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────

_MODEL = os.environ.get("NVIDIA_MODEL", "minimaxai/minimax-m2.7")
_EMBED_MODEL = os.environ.get("NVIDIA_EMBED_MODEL", "nvidia/nv-embed-v1")
_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
_DEDUP_EXACT = 0.92
_DEDUP_SIMILAR = 0.80
_JUDGE_TIMEOUT = 10.0

_client: AsyncOpenAI | None = None


def _llm() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=_BASE_URL, api_key=_API_KEY)
    return _client


# ── In-memory store ───────────────────────────────────────────────────────────

class _Store:
    def __init__(self) -> None:
        self.signatures: dict[str, dict[str, Any]] = {}   # id → sig
        self.events: list[dict[str, Any]] = []            # raw failure events
        self.eval_results: list[dict[str, Any]] = []      # eval history

    def fragility(self, sig_id: str) -> float:
        """Simple occurrence-count based fragility (0–1)."""
        sig = self.signatures.get(sig_id, {})
        count = sig.get("occurrence_count", 1)
        return round(min(1.0, math.log1p(count) / math.log1p(20)), 3)

    def all_fragility(self) -> list[dict[str, Any]]:
        return [
            {"id": sid, "fragility_score": self.fragility(sid), **s}
            for sid, s in self.signatures.items()
        ]


_store = _Store()

# ── Pydantic models ───────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    repo: str
    run_id: str
    job: str
    step: str
    exit_code: int
    log_tail: str
    changed_files: list[str] = []


class EvalRequest(BaseModel):
    diff: str


class JudgeResult(BaseModel):
    judge: str
    score: float
    verdict: str
    reasoning: str
    flags: list[str]


class AggregateScore(BaseModel):
    trust_score: float
    verdict: str
    judge_results: list[JudgeResult]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


async def _embed(text: str) -> list[float]:
    resp = await _llm().embeddings.create(model=_EMBED_MODEL, input=[text])
    return resp.data[0].embedding


async def _stream(messages: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    stream = await _llm().chat.completions.create(
        model=_MODEL,
        messages=messages,  # type: ignore[arg-type]
        temperature=1,
        top_p=0.95,
        max_tokens=8192,
        stream=True,
    )
    async for chunk in stream:  # type: ignore[union-attr]
        if getattr(chunk, "choices", None):
            delta = chunk.choices[0].delta.content
            if delta:
                chunks.append(delta)
    return "".join(chunks)


def _strip_json(text: str) -> str:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return text.strip()


# ── Signature extraction ──────────────────────────────────────────────────────

async def _extract_signature(event: dict[str, Any]) -> dict[str, Any]:
    prompt = f"""You are a CI failure analyst. Extract a failure signature from this log.
Return JSON with keys: summary (str), category (test_failure|build_error|contract_violation|flaky), affected_component (str).

Log tail:
{event['log_tail'][:1500]}

Return JSON only."""

    raw = await asyncio.wait_for(
        _stream([{"role": "user", "content": prompt}]),
        timeout=30.0,
    )
    try:
        data = json.loads(_strip_json(raw))
    except Exception:
        data = {
            "summary": event["log_tail"][:120],
            "category": "build_error",
            "affected_component": event.get("changed_files", ["unknown"])[0],
        }

    embedding = await _embed(data["summary"])
    return {
        "id": str(uuid.uuid4()),
        "summary": data.get("summary", ""),
        "category": data.get("category", "build_error"),
        "affected_component": data.get("affected_component", "unknown"),
        "embedding": embedding,
        "first_seen": datetime.now(timezone.utc).isoformat(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "occurrence_count": 1,
        "repo": event["repo"],
    }


async def _dedup_and_store(sig: dict[str, Any]) -> str:
    """Return id of stored or matched signature."""
    emb = sig["embedding"]
    for existing_id, existing in _store.signatures.items():
        sim = _cosine(emb, existing["embedding"])
        if sim >= _DEDUP_EXACT:
            # exact match — increment count only
            _store.signatures[existing_id]["occurrence_count"] += 1
            _store.signatures[existing_id]["last_seen"] = sig["last_seen"]
            return existing_id
        if sim >= _DEDUP_SIMILAR:
            # similar — store new but note relation (in-memory only)
            sig["similar_to"] = existing_id
            break
    _store.signatures[sig["id"]] = sig
    return sig["id"]


# ── Security Judge (inline, no graph dependency) ──────────────────────────────

_SSRF_KW = {"ssrf", "server-side request", "open redirect", "user.*url", "fetch.*input"}
_INJECT_KW = {"sql injection", "shell injection", "template injection", "xss", "prototype pollution"}


def _has_critical(flags: list[str]) -> bool:
    lowered = " ".join(f.lower() for f in flags)
    return any(kw in lowered for kw in _SSRF_KW | _INJECT_KW)


async def _security_judge(diff: str) -> JudgeResult:
    prompt = f"""You are a security code reviewer. Analyze this diff for:
- SSRF risk (user-controlled URLs passed to HTTP clients)
- Injection vectors (SQL, shell, template, XSS)
- Hardcoded secrets or API keys
- Unsafe deserialization

Return JSON: {{"score": 0.0-1.0, "verdict": "pass|warn|block", "reasoning": "...", "flags": ["..."]}}
Score 1.0 = clean. Any SSRF or injection = block regardless of score.

Diff:
{diff[:3000]}"""

    try:
        raw = await asyncio.wait_for(
            _stream([{"role": "user", "content": prompt}]),
            timeout=_JUDGE_TIMEOUT,
        )
        data = json.loads(_strip_json(raw))
        flags: list[str] = data.get("flags", [])
        score: float = float(data.get("score", 0.5))
        verdict: str = data.get("verdict", "warn")
        reasoning: str = data.get("reasoning", "")

        if _has_critical(flags):
            score = 0.2
            verdict = "block"

        return JudgeResult(
            judge="security", score=score, verdict=verdict,
            reasoning=reasoning, flags=flags,
        )
    except asyncio.TimeoutError:
        return JudgeResult(
            judge="security", score=0.3, verdict="block",
            reasoning="Security judge timed out — defaulting to block.",
            flags=["judge_timeout"],
        )
    except Exception as exc:
        return JudgeResult(
            judge="security", score=0.3, verdict="block",
            reasoning=f"Security judge error: {exc}",
            flags=["judge_error"],
        )


def _aggregate(security: JudgeResult) -> AggregateScore:
    score = security.score
    if score >= 0.7:
        verdict = "pass"
    elif score >= 0.4:
        verdict = "warn"
    else:
        verdict = "block"
    return AggregateScore(
        trust_score=round(score, 3),
        verdict=verdict,
        judge_results=[security],
    )


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def _lifespan(app: FastAPI):  # type: ignore[type-arg]
    yield


app = FastAPI(title="nano_phoenix", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "signatures": str(len(_store.signatures))}


@app.post("/ingest")
async def ingest(body: IngestRequest) -> dict[str, Any]:
    event = body.model_dump()
    event["id"] = str(uuid.uuid4())
    event["timestamp"] = datetime.now(timezone.utc).isoformat()
    _store.events.append(event)

    try:
        sig = await _extract_signature(event)
        sig_id = await _dedup_and_store(sig)
        return {"status": "ingested", "signature_id": sig_id, "event_id": event["id"]}
    except Exception as exc:
        # store event even if LLM fails
        return {"status": "stored_without_signature", "error": str(exc), "event_id": event["id"]}


@app.post("/eval", response_model=AggregateScore)
async def eval_diff(body: EvalRequest) -> AggregateScore:
    if not body.diff:
        raise HTTPException(status_code=422, detail="diff is required")
    security = await _security_judge(body.diff)
    result = _aggregate(security)
    _store.eval_results.append(result.model_dump())
    return result


@app.get("/graph")
async def graph() -> list[dict[str, Any]]:
    return [
        {k: v for k, v in s.items() if k != "embedding"}
        for s in _store.all_fragility()
    ]


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("nano_phoenix:app", host="0.0.0.0", port=8001, reload=True)
