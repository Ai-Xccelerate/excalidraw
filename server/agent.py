"""The canvas agent.

A conversation, not a one-shot prompt: it asks what it needs to know, proposes
a shape for the diagram, and only draws once the user says go. It sees the
board — everything on it, or just the selection when there is one — so "make
the failure path red" or "add a retry step after validation" mean something.

The model talks in prose, and attaches a fenced ```json block when it is ready
to change the canvas. That block is parsed out here and turned into real
elements through the same builder the MCP tools use, so an agent-drawn diagram
is laid out and bound exactly like a hand-drawn one.
"""

import json
import re
from typing import Any

from diagrams import build_flowchart, merged_defaults

# How much of the board to describe. A scene far past this is summarised by
# counts instead: the model does not need every element to answer "add a step
# after Qualification", and the token cost of a 2000-element board is real.
MAX_DESCRIBED_ELEMENTS = 120
MAX_LABEL_CHARS = 80

SYSTEM = """You are the drawing partner inside AIXDraw, a whiteboard app. You \
talk with the user about what they want to show, then draw it on their canvas.

# How you work

1. Understand first. If the request is vague, ask at most two focused questions \
— the ones that would change the shape of the diagram, not decoration. Never \
ask more than two at once, and never ask what you can reasonably assume.
2. Propose before you draw. Say in a few lines what you would draw: the spine \
of the flow, roughly how many boxes, and what each colour or shape will mean. \
Then ask for a go-ahead.
3. Draw only once the user agrees. "yes", "go", "do it", "sounds good" — that \
is your cue to attach the action block. Never attach one before it.
4. After drawing, say what you drew in two or three lines and offer the single \
most useful next step.

Keep your prose short. You are talking beside a canvas, not writing a document.

# What makes a diagram worth reading

- One idea per node. Labels are 2-5 words. Detail belongs on the edge or in a \
following node, never in a paragraph inside a box.
- Shape carries meaning: rectangle for a step, diamond for a decision, \
ellipse for a start or end point, and keep it consistent.
- Colour carries meaning too, and never more than four fills in one diagram. \
Use a fill to group a lane or mark a state (success, failure, in progress), and \
say what it means in your reply. Pale fills with dark text; never a dark fill \
with dark text.
- Label every edge leaving a decision, at minimum "yes" and "no".
- A flow deeper than about six levels reads better left-to-right than \
top-down.
- Prefer the diagram the user asked for over a more elaborate one.

# Changing what is already there

The board is described to you before each message. When the user has selected \
something, your changes must stay within that selection — that is what they \
are pointing at. With nothing selected, the whole board is yours to work with, \
but still change only what the request implies.

# The action block

When and only when you are drawing, end your message with a fenced json block:

```json
{
  "action": "draw",
  "direction": "down",
  "nodes": [
    {"id": "a", "label": "Lead arrives", "shape": "ellipse", "fill": "#d3f9d8"},
    {"id": "b", "label": "Qualified?", "shape": "diamond"}
  ],
  "edges": [{"from": "a", "to": "b", "label": "yes"}],
  "delete": ["existing-element-id"],
  "update": [{"id": "existing-element-id", "label": "New label", "fill": "#ffc9c9"}]
}
```

- `nodes`/`edges` draw something new. Shapes: rectangle, ellipse, diamond. \
`fill`, `stroke` and `text_color` are hex, and optional.
- `delete` removes elements by the ids you were shown. Deleting and redrawing \
is how you restructure something.
- `update` changes an existing element's `label`, `fill`, `stroke` or \
`text_color` — use it for recolouring and renaming rather than redrawing.
- Every field is optional except `action`. Send only what changes.
- Edge labels: "yes"/"no" on decisions. `"dashed": true` for a weak link.

Nothing outside the block is parsed, so explain yourself in prose as usual."""


class AgentError(RuntimeError):
    pass


# ------------------------------------------------------------ board summary

def _label_of(element: dict, by_container: dict[str, str]) -> str:
    text = element.get("text") or by_container.get(element.get("id", ""), "")
    text = " ".join(str(text).split())
    return text[:MAX_LABEL_CHARS]


def describe_board(board: dict | None) -> str:
    """A compact, id-carrying picture of the canvas. The ids matter: they are
    how the model points back at something it wants changed."""
    board = board or {}
    elements = board.get("elements") or []
    selected = set(board.get("selected_ids") or [])

    if not elements:
        return "The board is empty."

    # bound text lives in its own element; fold it into the shape it labels
    by_container: dict[str, str] = {}
    for element in elements:
        container = element.get("containerId")
        if container and element.get("text"):
            by_container[container] = element["text"]

    described = [
        element
        for element in elements
        if element.get("type") != "text" or not element.get("containerId")
    ]

    focus = [e for e in described if e.get("id") in selected] if selected else described
    lines: list[str] = []

    if selected:
        lines.append(
            f"{len(selected)} of {len(described)} objects are selected. "
            "Work only on these unless the user says otherwise."
        )
    else:
        lines.append(f"{len(described)} objects on the board, nothing selected.")

    if len(focus) > MAX_DESCRIBED_ELEMENTS:
        kinds: dict[str, int] = {}
        for element in focus:
            kinds[element.get("type", "?")] = kinds.get(element.get("type", "?"), 0) + 1
        lines.append(
            "Too many to list individually: "
            + ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
            + ". Ask the user to select the part they mean."
        )
        return "\n".join(lines)

    for element in focus:
        kind = element.get("type", "?")
        parts = [f"- {element.get('id')} [{kind}]"]
        label = _label_of(element, by_container)
        if label:
            parts.append(f'"{label}"')
        if kind == "arrow":
            start = (element.get("startBinding") or {}).get("elementId")
            end = (element.get("endBinding") or {}).get("elementId")
            if start or end:
                parts.append(f"{start or '?'} -> {end or '?'}")
        else:
            parts.append(
                f"at ({round(element.get('x', 0))},{round(element.get('y', 0))})"
            )
            background = element.get("backgroundColor")
            if background and background != "transparent":
                parts.append(f"fill {background}")
        lines.append(" ".join(parts))

    return "\n".join(lines)


def build_messages(
    history: list[dict],
    board: dict | None,
    attachments: list[dict] | None,
) -> list[dict]:
    """The conversation as the model sees it: the standing instructions, the
    board as it is right now, then the exchange so far."""
    messages: list[dict] = [{"role": "system", "content": SYSTEM}]

    context = [f"The canvas right now:\n{describe_board(board)}"]
    for attachment in attachments or []:
        text = (attachment.get("text") or "").strip()
        if text:
            context.append(
                f"Attached file {attachment.get('name', 'document')}:\n{text[:20000]}"
            )
    messages.append({"role": "system", "content": "\n\n".join(context)})

    for turn in history:
        role = turn.get("role")
        if role not in ("user", "assistant"):
            continue
        content = turn.get("content")
        images = turn.get("images") or []
        if images:
            # the model takes multimodal content the same way diagram-to-code does
            parts: list[dict] = [{"type": "text", "text": str(content or "")}]
            for image in images[:4]:
                parts.append({"type": "image_url", "image_url": {"url": image}})
            messages.append({"role": role, "content": parts})
        else:
            messages.append({"role": role, "content": str(content or "")})

    return messages


# ----------------------------------------------------------- action parsing

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def split_action(raw: str) -> tuple[str, dict | None]:
    """Separates what the user reads from what the canvas does."""
    match = _JSON_BLOCK.search(raw)
    if not match:
        return raw.strip(), None
    try:
        action = json.loads(match.group(1))
    except json.JSONDecodeError:
        # a malformed block is not worth failing the whole turn over: the prose
        # is still useful, and the user can ask again
        return raw.strip(), None
    prose = (raw[: match.start()] + raw[match.end() :]).strip()
    return prose, action if isinstance(action, dict) else None


_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _color(value: Any) -> str | None:
    return value if isinstance(value, str) and _HEX.match(value) else None


def _clean_nodes(raw: Any) -> list[dict]:
    nodes = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        node = {
            "id": str(item["id"]),
            "label": str(item.get("label") or item["id"]),
            "shape": item.get("shape")
            if item.get("shape") in ("rectangle", "ellipse", "diamond")
            else "rectangle",
        }
        for key, target in (
            ("fill", "background_color"),
            ("stroke", "stroke_color"),
            ("text_color", "text_color"),
        ):
            color = _color(item.get(key))
            if color:
                node[target] = color
        nodes.append(node)
    return nodes


def _clean_edges(raw: Any, known: set[str]) -> list[dict]:
    edges = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        source, target = str(item.get("from") or ""), str(item.get("to") or "")
        if source not in known or target not in known:
            continue
        edges.append(
            {
                "from": source,
                "to": target,
                "label": str(item["label"]) if item.get("label") else None,
                "dashed": bool(item.get("dashed")),
                "thick": bool(item.get("thick")),
                "head_end": True,
                "head_start": False,
            }
        )
    return edges


def _clean_updates(raw: Any, allowed: set[str] | None) -> list[dict]:
    updates = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        element_id = str(item["id"])
        # a selection is a fence: the model must not reach past it
        if allowed is not None and element_id not in allowed:
            continue
        update: dict = {"id": element_id}
        if item.get("label") is not None:
            update["label"] = str(item["label"])
        for key, target in (
            ("fill", "backgroundColor"),
            ("stroke", "strokeColor"),
            ("text_color", "textColor"),
        ):
            color = _color(item.get(key))
            if color:
                update[target] = color
        if len(update) > 1:
            updates.append(update)
    return updates


def compile_action(
    action: dict, defaults: dict | None, board: dict | None
) -> dict | None:
    """Turns the model's block into something the canvas can apply: real
    elements for anything new, plus id lists for what changes or goes."""
    board = board or {}
    selected = set(board.get("selected_ids") or [])
    on_board = {
        element.get("id") for element in (board.get("elements") or []) if element.get("id")
    }
    # with a selection, the model may only touch what is selected
    allowed = selected if selected else (on_board or None)

    nodes = _clean_nodes(action.get("nodes"))
    edges = _clean_edges(action.get("edges"), {node["id"] for node in nodes})
    updates = _clean_updates(action.get("update"), allowed)
    deletes = [
        str(item)
        for item in (action.get("delete") or [])
        if isinstance(item, (str, int))
        and (allowed is None or str(item) in allowed)
    ]

    elements = (
        build_flowchart(
            nodes,
            edges,
            str(action.get("direction") or "down"),
            merged_defaults(defaults),
        )
        if nodes
        else []
    )

    if not elements and not updates and not deletes:
        return None

    return {
        "elements": elements,
        "updates": updates,
        "delete_ids": deletes,
        "summary": {
            "created": len(nodes),
            "connected": len(edges),
            "updated": len(updates),
            "deleted": len(deletes),
        },
    }
