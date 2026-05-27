import asyncio
import json
import logging
import os
import uuid

from openai import AsyncOpenAI

from core.models.failure import FailureEvent, FailureSignature, FailureSignatureExtract

logger = logging.getLogger(__name__)

_TIMEOUT: float = 15.0
_MODEL = "minimaxai/minimax-m2.7"
_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
_API_KEY = os.environ.get("NVIDIA_API_KEY", "")

_SYSTEM_PROMPT = (
    "You are a CI failure analyst. Given a failed CI step log, extract:\n"
    "- summary: one sentence describing the root cause\n"
    "- category: one of test_failure, build_error, contract_violation, flaky\n"
    "- affected_component: the primary file path or module name that caused the failure\n\n"
    "Be specific. Use the actual error in the log, not generic descriptions.\n"
    "Respond with a JSON object containing exactly these fields: summary, category, affected_component."
)

_openai_client: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(base_url=_BASE_URL, api_key=_API_KEY)
    return _openai_client


async def extract(event: FailureEvent) -> FailureSignature | None:
    user_content = (
        f"Workflow: {event.workflow}\n"
        f"Job: {event.job}\n"
        f"Step: {event.step}\n\n"
        f"Log (last 2000 chars):\n{event.log_tail or '(no log available)'}"
    )

    try:
        response = await asyncio.wait_for(
            _get_openai().chat.completions.create(
                model=_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=512,
            ),
            timeout=_TIMEOUT,
        )
        raw = response.choices[0].message.content or ""
        llm = FailureSignatureExtract.model_validate(json.loads(raw))
    except Exception as exc:
        logger.error("Signature extraction failed for run %s: %s", event.run_id, exc)
        return None

    return FailureSignature(
        id=str(uuid.uuid4()),
        summary=llm.summary,
        category=llm.category,
        affected_component=llm.affected_component,
        embedding=[],
        first_seen=event.timestamp,
        last_seen=event.timestamp,
        occurrence_count=1,
    )
