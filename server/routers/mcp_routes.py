"""The MCP endpoint.

Streamable HTTP transport, JSON-RPC 2.0 over a single POST. Authorized with the
OAuth 2.1 bearer tokens minted in oauth_routes, so any MCP host — Claude,
ChatGPT, Cursor — can connect by discovering /.well-known/oauth-protected-resource
and running the normal flow.

The tools are deliberately about the user's own drawings: list them, read one,
and create diagrams. Diagram tools render through the same builder the app
would use and pick up the user's saved editor defaults, so what an agent draws
matches what they draw.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from db import get_db
from diagrams import MermaidError, build_flowchart, merged_defaults, parse_mermaid
from models import Drawing, UserSettings
from oauth import PUBLIC_APP_URL, McpContext, get_mcp_context
from services import ensure_personal_workspace

router = APIRouter(tags=["mcp"])

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "aixdraw", "title": "AIXDraw", "version": "1.0.0"}

_NODE_SCHEMA = {
    "type": "object",
    "required": ["id", "label"],
    "properties": {
        "id": {"type": "string", "description": "Short unique id used by edges"},
        "label": {"type": "string"},
        "shape": {
            "type": "string",
            "enum": ["rectangle", "ellipse", "diamond"],
            "description": "diamond for decisions, ellipse for start/end",
        },
    },
}

_EDGE_SCHEMA = {
    "type": "object",
    "required": ["from", "to"],
    "properties": {
        "from": {"type": "string"},
        "to": {"type": "string"},
        "label": {"type": "string", "description": "Text on the arrow, e.g. yes / no"},
    },
}

TOOLS = [
    {
        "name": "list_drawings",
        "title": "List drawings",
        "description": "List the drawings in the user's AIXDraw account, newest first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}
            },
        },
    },
    {
        "name": "get_drawing",
        "title": "Read a drawing",
        "description": (
            "Read one drawing: its title, how many elements it holds, and the text "
            "written on the canvas."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["drawing_id"],
            "properties": {"drawing_id": {"type": "string"}},
        },
    },
    {
        "name": "get_editor_defaults",
        "title": "Get drawing preferences",
        "description": (
            "The user's saved editor defaults (font, stroke, arrow style). Diagram "
            "tools already apply these; read them when you need to describe or "
            "deliberately override the look."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_flowchart",
        "title": "Create a flowchart",
        "description": (
            "Draw a flowchart from nodes and edges and save it as a new drawing. "
            "Boxes are laid out in layers, labels are bound to their box, and arrows "
            "are bound to the shapes they connect, so the result stays editable. "
            "Prefer this over create_mermaid_diagram when you are composing the "
            "diagram yourself."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["title", "nodes", "edges"],
            "properties": {
                "title": {"type": "string"},
                "nodes": {"type": "array", "items": _NODE_SCHEMA},
                "edges": {"type": "array", "items": _EDGE_SCHEMA},
                "direction": {
                    "type": "string",
                    "enum": ["down", "up", "right", "left"],
                    "default": "down",
                },
            },
        },
    },
    {
        "name": "create_mermaid_diagram",
        "title": "Create a diagram from mermaid",
        "description": (
            "Render a mermaid flowchart (`flowchart TD` / `graph LR`, including node "
            "shapes and edge labels) as a new AIXDraw drawing. Subgraphs and non-"
            "flowchart mermaid diagrams are not supported yet."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["title", "mermaid"],
            "properties": {
                "title": {"type": "string"},
                "mermaid": {"type": "string", "description": "Mermaid flowchart source"},
            },
        },
    },
    {
        "name": "create_drawing",
        "title": "Create an empty drawing",
        "description": "Create a new, empty drawing and return its link.",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string", "default": "Untitled"}},
        },
    },
]


def _drawing_url(drawing: Drawing) -> str:
    return f"{PUBLIC_APP_URL}/d/{drawing.id}"


def _text(body: str) -> dict:
    return {"content": [{"type": "text", "text": body}], "isError": False}


def _error(body: str) -> dict:
    return {"content": [{"type": "text", "text": body}], "isError": True}


def _user_defaults(db: Session, user_id: str) -> dict:
    row = db.get(UserSettings, user_id)
    return merged_defaults(row.editor_defaults if row else None)


def _save(db: Session, ctx: McpContext, title: str, elements: list[dict]) -> Drawing:
    workspace = ensure_personal_workspace(db, ctx.user_id)
    drawing = Drawing(
        owner_id=ctx.user_id,
        workspace_id=workspace.id if workspace else None,
        title=title or "Untitled",
        elements=elements,
        app_state={},
        files={},
        scene_version=1,
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


# ----------------------------------------------------------------- the tools

def _call_tool(name: str, args: dict, ctx: McpContext, db: Session) -> dict:
    if name == "list_drawings":
        ctx.require("drawings:read")
        limit = min(int(args.get("limit", 20) or 20), 100)
        rows = (
            db.query(Drawing)
            .filter(Drawing.owner_id == ctx.user_id)
            .order_by(Drawing.updated_at.desc())
            .limit(limit)
            .all()
        )
        if not rows:
            return _text("No drawings yet.")
        listing = "\n".join(
            f"- {row.title} — {_drawing_url(row)} (updated {row.updated_at:%Y-%m-%d %H:%M})"
            for row in rows
        )
        return _text(listing)

    if name == "get_drawing":
        ctx.require("drawings:read")
        try:
            drawing_id = uuid.UUID(str(args.get("drawing_id", "")))
        except ValueError:
            return _error("drawing_id must be a drawing UUID")
        drawing = db.get(Drawing, drawing_id)
        # scoped to what this account owns: a token must not read someone
        # else's canvas just because the id was guessed
        if drawing is None or drawing.owner_id != ctx.user_id:
            return _error("No drawing with that id")
        texts = [
            element.get("text")
            for element in (drawing.elements or [])
            if element.get("type") == "text" and element.get("text")
        ]
        body = [
            f"{drawing.title} — {_drawing_url(drawing)}",
            f"{len(drawing.elements or [])} elements",
        ]
        if texts:
            body.append("Text on the canvas:\n" + "\n".join(f"- {t}" for t in texts))
        return _text("\n".join(body))

    if name == "get_editor_defaults":
        ctx.require("profile")
        defaults = _user_defaults(db, ctx.user_id)
        return _text(
            "\n".join(f"{key}: {value}" for key, value in sorted(defaults.items()))
        )

    if name == "create_flowchart":
        ctx.require("drawings:write")
        nodes = args.get("nodes") or []
        edges = args.get("edges") or []
        if not nodes:
            return _error("At least one node is required")
        elements = build_flowchart(
            nodes,
            edges,
            str(args.get("direction") or "down"),
            _user_defaults(db, ctx.user_id),
        )
        drawing = _save(db, ctx, str(args.get("title") or "Flowchart"), elements)
        return _text(
            f"Created '{drawing.title}' with {len(nodes)} nodes and {len(edges)} "
            f"connections: {_drawing_url(drawing)}"
        )

    if name == "create_mermaid_diagram":
        ctx.require("drawings:write")
        try:
            nodes, edges, direction = parse_mermaid(str(args.get("mermaid") or ""))
        except MermaidError as exc:
            return _error(str(exc))
        elements = build_flowchart(
            nodes, edges, direction, _user_defaults(db, ctx.user_id)
        )
        drawing = _save(db, ctx, str(args.get("title") or "Diagram"), elements)
        return _text(
            f"Created '{drawing.title}' with {len(nodes)} nodes and {len(edges)} "
            f"connections: {_drawing_url(drawing)}"
        )

    if name == "create_drawing":
        ctx.require("drawings:write")
        drawing = _save(db, ctx, str(args.get("title") or "Untitled"), [])
        return _text(f"Created '{drawing.title}': {_drawing_url(drawing)}")

    return _error(f"Unknown tool: {name}")


# ------------------------------------------------------------------ JSON-RPC

def _result(request_id: Any, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _rpc_error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _handle(message: dict, ctx: McpContext, db: Session) -> dict | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    # notifications carry no id and expect no response
    if request_id is None and method and method.startswith("notifications/"):
        return None

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "Drawings live in the signed-in user's AIXDraw account. Use "
                    "create_flowchart to compose a diagram yourself, or "
                    "create_mermaid_diagram when you already have mermaid source. "
                    "Both apply the user's saved editor defaults."
                ),
            },
        )

    if method == "ping":
        return _result(request_id, {})

    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            return _result(request_id, _call_tool(name, args, ctx, db))
        except Exception as exc:  # a tool blowing up is a tool result, not a
            # transport failure — the client should see why and can retry
            return _result(request_id, _error(f"{name} failed: {exc}"))

    return _rpc_error(request_id, -32601, f"Method not found: {method}")


@router.post("/mcp")
async def mcp_endpoint(
    request: Request,
    ctx: McpContext = Depends(get_mcp_context),
    db: Session = Depends(get_db),
):
    # read the body by hand: a JSON-RPC payload is either one message or a
    # batch, and FastAPI would otherwise treat a `dict | list` parameter as a
    # named field inside the body rather than the body itself
    try:
        payload = await request.json()
    except Exception:
        return _rpc_error(None, -32700, "Request body is not valid JSON")
    if not isinstance(payload, (dict, list)):
        return _rpc_error(None, -32600, "A JSON-RPC message must be an object or array")

    if isinstance(payload, list):
        responses = [r for r in (_handle(m, ctx, db) for m in payload) if r is not None]
        return responses or Response(status_code=202)
    response = _handle(payload, ctx, db)
    if response is None:
        return Response(status_code=202)
    return response


@router.get("/mcp")
async def mcp_stream_unsupported():
    # no server-initiated messages, so the optional SSE channel is declined
    # rather than left hanging open
    return Response(status_code=405, headers={"Allow": "POST"})
