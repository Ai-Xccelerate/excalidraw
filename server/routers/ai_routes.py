import json
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import ai
from auth import AuthContext, get_current_context
from db import get_db
from models import AIUsage

router = APIRouter(prefix="/v1/ai", tags=["ai"])

# These calls are billed per request upstream, so they are gated behind a
# signed-in user and a daily cap rather than left open the way the public
# Excalidraw demo backend is.
DAILY_LIMIT = int(os.environ.get("AI_DAILY_LIMIT", "50"))

MAX_IMAGE_BYTES = 6 * 1024 * 1024  # a frame export well beyond this is a mistake

D2C_SYSTEM = """You convert hand-drawn UI wireframes into a single working HTML page.

Rules:
- Return ONE complete HTML document and nothing else. No prose, no markdown fences.
- Inline all CSS in a <style> tag and all JS in a <script> tag. No external requests.
- Treat the image as the layout spec and the supplied text as the exact copy to use.
- Infer obvious interactive behaviour (tabs switch, buttons toggle, inputs accept text).
- Make it responsive and readable; use system fonts.
- If the wireframe is ambiguous, choose the most conventional interpretation."""

T2D_SYSTEM = """You turn a description into a Mermaid diagram.

Rules:
- Reply with a single ```mermaid fenced code block and nothing else.
- Prefer flowchart TD unless the request clearly implies sequence, class, state,
  ER or gantt.
- Keep node labels short. Quote any label containing spaces or punctuation.
- Never invent steps the user did not describe."""


class DiagramToCodeRequest(BaseModel):
    texts: list = []
    image: str
    theme: str | None = None


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message] = []


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _consume_quota(db: Session, user_id: str, feature: str) -> tuple[int, int]:
    """Reserves one generation. Returns (limit, remaining_after)."""
    row = db.get(AIUsage, {"user_id": user_id, "day": _today(), "feature": feature})
    if row is None:
        row = AIUsage(user_id=user_id, day=_today(), feature=feature, count=0)
        db.add(row)
    if row.count >= DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail={
                "statusCode": 429,
                "message": "You've hit today's AI generation limit. It resets at midnight UTC.",
            },
        )
    row.count += 1
    db.commit()
    return DAILY_LIMIT, max(DAILY_LIMIT - row.count, 0)


def _extract_html(raw: str) -> str:
    """Models like to wrap output in a fence even when told not to."""
    fenced = re.search(r"```(?:html)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1).strip() if fenced else raw.strip()
    if "<" not in candidate:
        raise HTTPException(status_code=502, detail="Model did not return HTML")
    return candidate


@router.post("/diagram-to-code/generate")
async def diagram_to_code(
    body: DiagramToCodeRequest,
    response: Response,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    if not ai.is_configured():
        raise HTTPException(
            status_code=503,
            detail={"statusCode": 503, "message": "The AI backend is not configured yet."},
        )
    if not body.image.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Expected an image data URL")
    if len(body.image) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Wireframe image is too large")

    limit, remaining = _consume_quota(db, ctx.user_id, "d2c")
    response.headers["X-Ratelimit-Limit"] = str(limit)
    response.headers["X-Ratelimit-Remaining"] = str(remaining)

    labels = [t for t in (body.texts or []) if isinstance(t, str) and t.strip()]
    user_content = [
        {
            "type": "text",
            "text": (
                "Build this wireframe as HTML."
                + (f"\n\nText in the wireframe:\n{chr(10).join(labels)}" if labels else "")
                + (f"\n\nPrefer a {body.theme} colour scheme." if body.theme else "")
            ),
        },
        {"type": "image_url", "image_url": {"url": body.image}},
    ]

    try:
        raw = await ai.complete(
            [
                {"role": "system", "content": D2C_SYSTEM},
                {"role": "user", "content": user_content},
            ]
        )
    except ai.AIUnavailable as exc:
        raise HTTPException(
            status_code=exc.status, detail={"statusCode": exc.status, "message": str(exc)}
        ) from exc

    return {"html": _extract_html(raw)}


@router.post("/text-to-diagram/chat-streaming")
async def text_to_diagram(
    body: ChatRequest,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    if not ai.is_configured():
        raise HTTPException(
            status_code=503,
            detail={"statusCode": 503, "message": "The AI backend is not configured yet."},
        )
    if not body.messages:
        raise HTTPException(status_code=400, detail="No messages supplied")

    limit, remaining = _consume_quota(db, ctx.user_id, "t2d")

    messages = [{"role": "system", "content": T2D_SYSTEM}] + [
        {"role": m.role, "content": m.content} for m in body.messages
    ]

    async def event_stream():
        # the client parses `data: <StreamChunk json>` lines and dispatches on
        # .type, so errors have to travel inside the stream once it has opened
        try:
            async for delta in ai.stream(messages):
                yield f"data: {json.dumps({'type': 'content', 'delta': delta})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'finishReason': 'stop'})}\n\n"
        except ai.AIUnavailable as exc:
            yield "data: " + json.dumps(
                {"type": "error", "error": {"message": str(exc), "status": exc.status}}
            ) + "\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Ratelimit-Limit": str(limit),
            "X-Ratelimit-Remaining": str(remaining),
        },
    )
