import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI

from core.models.failure import JudgeResult

logger = logging.getLogger(__name__)

_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
_MODEL = "minimaxai/minimax-m2.7"
_JUDGE_TIMEOUT = 10.0

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=_BASE_URL, api_key=_API_KEY)
    return _client


async def _stream_text(messages: list[dict[str, Any]]) -> str:
    """Stream a response from NVIDIA NIM and return the accumulated text."""
    chunks: list[str] = []
    stream = await _get_client().chat.completions.create(  # type: ignore[call-overload]
        model=_MODEL,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.2,
        top_p=0.95,
        max_tokens=8192,
        stream=True,
    )
    async for chunk in stream:  # type: ignore[union-attr]
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta.content
        if delta is not None:
            chunks.append(delta)
    return "".join(chunks)


def _extract_json(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from a string (strips markdown fences)."""
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


class BaseJudge(ABC):
    """
    Abstract base for all judge agents.

    Subclasses implement:
      - name: str — "behavior" | "security" | "regression"
      - timeout_result: JudgeResult — returned on timeout or LLM error
      - _build_messages(context) → list[dict]  — assemble the prompt
      - _parse_response(raw) → JudgeResult     — parse raw LLM text
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def timeout_result(self) -> JudgeResult: ...

    @abstractmethod
    def _build_messages(self, context: dict[str, Any]) -> list[dict[str, Any]]: ...

    @abstractmethod
    def _parse_response(self, raw: str) -> JudgeResult: ...

    async def judge(self, context: dict[str, Any]) -> JudgeResult:
        """Run the judge with a hard 10-second timeout. Never raises."""
        try:
            messages = self._build_messages(context)
            raw = await asyncio.wait_for(_stream_text(messages), timeout=_JUDGE_TIMEOUT)
            return self._parse_response(raw)
        except asyncio.TimeoutError:
            logger.warning("%s judge timed out", self.name)
            return self.timeout_result
        except Exception as exc:
            logger.error("%s judge failed: %s", self.name, exc)
            return self.timeout_result
