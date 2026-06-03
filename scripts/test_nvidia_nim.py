"""
Quick test for NVIDIA NIM API using both sync and async OpenAI clients.
Run: uv run python scripts/test_nvidia_nim.py
"""
import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

load_dotenv()

BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
API_KEY = os.environ.get("NVIDIA_API_KEY", "")
MODEL = "minimaxai/minimax-m2.7"

PROMPT = "You are a helpful assistant. What is 2+2? Please provide a detailed explanation."


# ── Sync ──────────────────────────────────────────────────────────────────────
def test_sync():
    print("\n[SYNC] Testing OpenAI (sync)...")
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.1,
        max_tokens=400,
        stream=False,
    )
    content = completion.choices[0].message.content
    print(f"  model:          {MODEL}")
    print(f"  response:       {content!r}")
    print(f"  finish_reason:  {completion.choices[0].finish_reason}")
    print(f"  usage:          {completion.usage}")
    print("  ✓ Sync OK")


# ── Sync streaming ────────────────────────────────────────────────────────────
def test_sync_stream():
    print("\n[SYNC STREAM] Testing OpenAI (sync streaming)...")
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=1,
        top_p=0.95,
        max_tokens=400,
        stream=True,
    )
    print("  response: ", end="", flush=True)
    for chunk in completion:
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)
    print()
    print("  ✓ Sync stream OK")


# ── Async ─────────────────────────────────────────────────────────────────────
async def test_async():
    print("\n[ASYNC] Testing AsyncOpenAI...")
    client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
    completion = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.1,
        max_tokens=400,
        stream=False,
    )
    content = completion.choices[0].message.content
    print(f"  model:          {MODEL}")
    print(f"  response:       {content!r}")
    print(f"  finish_reason:  {completion.choices[0].finish_reason}")
    print(f"  usage:          {completion.usage}")
    print("  ✓ Async OK")


# ── Async streaming ───────────────────────────────────────────────────────────
async def test_async_stream():
    print("\n[ASYNC STREAM] Testing AsyncOpenAI (streaming)...")
    client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
    stream = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=1,
        top_p=0.95,
        max_tokens=400,
        stream=True,
    )
    print("  response: ", end="", flush=True)
    async for chunk in stream:
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)
    print()
    print("  ✓ Async stream OK")


if __name__ == "__main__":
    print("=" * 55)
    print("NVIDIA NIM API Test")
    print(f"  base_url: {BASE_URL}")
    print(f"  model:    {MODEL}")
    print("=" * 55)

    test_sync()
    test_sync_stream()
    asyncio.run(test_async())
    asyncio.run(test_async_stream())

    print("\n" + "=" * 55)
    print("All tests passed.")
    print("=" * 55)
