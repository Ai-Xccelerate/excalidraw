"""Meta Model API client (Muse Spark).

The service is OpenAI-compatible, so this speaks /v1/chat/completions rather
than pulling in another SDK. Two shapes are needed: a blocking call for
diagram-to-code, and a token stream for text-to-diagram.
"""

import json
import os
from collections.abc import AsyncIterator

import httpx

MODEL_API_KEY = os.environ.get("MODEL_API_KEY")
MODEL_API_BASE = os.environ.get("MODEL_API_BASE", "https://api.meta.ai/v1").rstrip("/")
# pinned via env so a newer Muse revision is a config change, not a deploy
MUSE_MODEL = os.environ.get("MUSE_MODEL", "muse-spark-1.3")

REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)


class AIUnavailable(RuntimeError):
    """Raised when the upstream model can't serve the request."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def is_configured() -> bool:
    return bool(MODEL_API_KEY)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {MODEL_API_KEY}",
        "Content-Type": "application/json",
    }


def _require_key() -> None:
    if not MODEL_API_KEY:
        raise AIUnavailable("The AI backend is not configured", status=503)


# Muse Spark is a reasoning model: it spends most of its completion budget on
# internal reasoning before emitting anything. A wireframe that needs ~400
# tokens of HTML burned ~1450 reasoning tokens first, and an 900-token cap
# returned content: null. Budget generously or the answer never arrives.
DEFAULT_MAX_TOKENS = int(os.environ.get("MUSE_MAX_TOKENS", "16000"))


async def complete(messages: list[dict], max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """Single blocking completion. Returns the assistant's text."""
    _require_key()
    payload = {
        "model": MUSE_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{MODEL_API_BASE}/chat/completions", headers=_headers(), json=payload
            )
    except httpx.HTTPError as exc:
        raise AIUnavailable(f"Could not reach the model: {exc}") from exc

    if response.status_code == 429:
        raise AIUnavailable("Upstream rate limit reached", status=429)
    if response.status_code >= 400:
        raise AIUnavailable(
            f"Model returned {response.status_code}: {response.text[:500]}",
            status=502,
        )

    data = response.json()
    try:
        choice = data["choices"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIUnavailable("Model returned an unexpected response shape") from exc

    content = (choice.get("message") or {}).get("content")
    if not content:
        # the usual cause is the reasoning phase consuming the whole budget
        if choice.get("finish_reason") == "length":
            raise AIUnavailable(
                "The model ran out of budget before answering. Try a simpler frame.",
                status=502,
            )
        raise AIUnavailable("Model returned an empty response", status=502)
    return content


async def stream(
    messages: list[dict], max_tokens: int = DEFAULT_MAX_TOKENS
) -> AsyncIterator[str]:
    """Yields text deltas as they arrive."""
    _require_key()
    payload = {
        "model": MUSE_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{MODEL_API_BASE}/chat/completions",
                headers=_headers(),
                json=payload,
            ) as response:
                if response.status_code == 429:
                    raise AIUnavailable("Upstream rate limit reached", status=429)
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise AIUnavailable(
                        f"Model returned {response.status_code}: {body[:500]}", status=502
                    )
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        return
                    try:
                        parsed = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    for choice in parsed.get("choices") or []:
                        delta = (choice.get("delta") or {}).get("content")
                        if delta:
                            yield delta
    except httpx.HTTPError as exc:
        raise AIUnavailable(f"Could not reach the model: {exc}") from exc
