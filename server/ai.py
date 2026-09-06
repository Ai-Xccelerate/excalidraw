"""Meta Model API client (Muse Spark).

The service is OpenAI-compatible, so this speaks /v1/chat/completions rather
than pulling in another SDK. Two shapes are needed: a blocking call for
diagram-to-code, and a token stream for text-to-diagram.
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator

import httpx

MODEL_API_KEY = (os.environ.get("MODEL_API_KEY") or "").strip() or None
MODEL_API_BASE = os.environ.get("MODEL_API_BASE", "https://api.meta.ai/v1").strip().rstrip("/")
# pinned via env so a newer Muse revision is a config change, not a deploy
MUSE_MODEL = (os.environ.get("MUSE_MODEL") or "muse-spark-1.3").strip()

REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)

# muse-spark-1.3 intermittently answers model_not_found -- measured at roughly
# 1 call in 12 while 1.1 was stable across the same sample. It reads like a
# partial rollout rather than a config error, so a rejected model is retried
# and then failed over rather than surfaced to the user.
MUSE_FALLBACK_MODEL = (
    os.environ.get("MUSE_FALLBACK_MODEL") or "muse-spark-1.1"
).strip()
MAX_ATTEMPTS = int(os.environ.get("MUSE_MAX_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = 0.6


logger = logging.getLogger(__name__)


def _model_attempts() -> list[str]:
    """The model to try, then the fallback, without repeating one model."""
    models = [MUSE_MODEL]
    if MUSE_FALLBACK_MODEL and MUSE_FALLBACK_MODEL != MUSE_MODEL:
        models.append(MUSE_FALLBACK_MODEL)
    return models


def _is_model_missing(status: int, body: str) -> bool:
    return status == 404 and "model_not_found" in body


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
    last: AIUnavailable | None = None

    for model in _model_attempts():
        for attempt in range(MAX_ATTEMPTS):
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": False,
            }
            try:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                    response = await client.post(
                        f"{MODEL_API_BASE}/chat/completions",
                        headers=_headers(),
                        json=payload,
                    )
            except httpx.HTTPError as exc:
                last = AIUnavailable(f"Could not reach the model: {exc}")
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue

            if response.status_code == 429:
                # a real quota signal: retrying just burns it further
                raise AIUnavailable("Upstream rate limit reached", status=429)

            if response.status_code >= 400:
                body = response.text[:300]
                last = AIUnavailable(
                    f"Model {model!r} returned {response.status_code}: {body}", status=502
                )
                if _is_model_missing(response.status_code, body) or response.status_code >= 500:
                    logger.warning(
                        "transient model failure (%s, attempt %s): %s",
                        model,
                        attempt + 1,
                        body,
                    )
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                    continue
                raise last  # a genuine bad request won't get better on retry

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
                        "The model ran out of budget before answering. "
                        "Try a simpler frame.",
                        status=502,
                    )
                raise AIUnavailable("Model returned an empty response", status=502)
            return content

    raise last or AIUnavailable("The model could not be reached")


async def stream(
    messages: list[dict], max_tokens: int = DEFAULT_MAX_TOKENS
) -> AsyncIterator[str]:
    """Yields text deltas as they arrive.

    Retrying is only safe before the first byte reaches the caller; once
    deltas have been emitted a failure is surfaced rather than restarted,
    which would duplicate the output.
    """
    _require_key()
    last: AIUnavailable | None = None

    for model in _model_attempts():
        for attempt in range(MAX_ATTEMPTS):
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": True,
            }
            emitted = False
            try:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                    async with client.stream(
                        "POST",
                        f"{MODEL_API_BASE}/chat/completions",
                        headers=_headers(),
                        json=payload,
                    ) as response:
                        if response.status_code == 429:
                            raise AIUnavailable(
                                "Upstream rate limit reached", status=429
                            )
                        if response.status_code >= 400:
                            body = (await response.aread()).decode("utf-8", "replace")[:300]
                            last = AIUnavailable(
                                f"Model {model!r} returned {response.status_code}: {body}",
                                status=502,
                            )
                            if (
                                _is_model_missing(response.status_code, body)
                                or response.status_code >= 500
                            ):
                                logger.warning(
                                    "transient model failure (%s, attempt %s): %s",
                                    model,
                                    attempt + 1,
                                    body,
                                )
                                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                                continue
                            raise last

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
                                    emitted = True
                                    yield delta
                        return
            except httpx.HTTPError as exc:
                if emitted:
                    raise AIUnavailable(f"Stream interrupted: {exc}") from exc
                last = AIUnavailable(f"Could not reach the model: {exc}")
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue

    raise last or AIUnavailable("The model could not be reached")
