"""Turns a described diagram into Excalidraw elements.

MCP clients hand us either a structured node/edge graph or a mermaid
`flowchart`, and get back a real scene: boxes with bound labels, arrows bound
to the boxes they connect, laid out in layers. Everything is drawn with the
user's saved editor defaults so an agent-made diagram looks like the ones they
draw by hand.
"""

import random
import re
import time
from typing import Any

# Excalidraw's FONT_FAMILY ids (packages/common/src/constants.ts)
FONT_FAMILY = {
    "hand-drawn": 5,  # Excalifont
    "normal": 6,  # Nunito
    "code": 3,  # Cascadia
}

DEFAULTS: dict[str, Any] = {
    "font_family": "hand-drawn",
    "font_size": 20,
    "stroke_color": "#1e1e1e",
    "background_color": "transparent",
    "fill_style": "solid",
    "stroke_width": 2,
    "stroke_style": "solid",
    "roughness": 1,
    "edges": "round",
    "arrow_type": "round",
    "node_shape": "rectangle",
}

# a character is roughly 0.55em wide in the fonts we ship; enough to size a box
# so its label fits without measuring text on a server with no canvas
CHAR_WIDTH_RATIO = 0.58
LINE_HEIGHT = 1.25

MIN_NODE_WIDTH = 120
MAX_NODE_WIDTH = 300
NODE_PADDING_X = 24
NODE_PADDING_Y = 20
GAP_ALONG = 120  # between layers
GAP_ACROSS = 48  # between siblings in a layer


def _seed() -> int:
    return random.randint(1, 2_000_000_000)


def _element_id() -> str:
    return "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(16))


def _now_ms() -> int:
    return int(time.time() * 1000)


def merged_defaults(user_defaults: dict | None) -> dict:
    merged = dict(DEFAULTS)
    for key, value in (user_defaults or {}).items():
        if key in merged and value is not None:
            merged[key] = value
    return merged


def _base(defaults: dict, **overrides: Any) -> dict:
    element = {
        "id": _element_id(),
        "angle": 0,
        "strokeColor": defaults["stroke_color"],
        "backgroundColor": defaults["background_color"],
        "fillStyle": defaults["fill_style"],
        "strokeWidth": defaults["stroke_width"],
        "strokeStyle": defaults["stroke_style"],
        "roughness": defaults["roughness"],
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": _seed(),
        "version": 1,
        "versionNonce": _seed(),
        "isDeleted": False,
        "boundElements": [],
        "updated": _now_ms(),
        "link": None,
        "locked": False,
    }
    element.update(overrides)
    return element


def _wrap(label: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    for paragraph in label.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            if len(current) + 1 + len(word) <= max_chars:
                current = f"{current} {word}"
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _node_size(label: str, font_size: int) -> tuple[int, int, list[str]]:
    char_width = font_size * CHAR_WIDTH_RATIO
    max_chars = max(8, int((MAX_NODE_WIDTH - NODE_PADDING_X * 2) / char_width))
    lines = _wrap(label, max_chars)
    text_width = max((len(line) for line in lines), default=1) * char_width
    width = int(min(MAX_NODE_WIDTH, max(MIN_NODE_WIDTH, text_width + NODE_PADDING_X * 2)))
    height = int(len(lines) * font_size * LINE_HEIGHT + NODE_PADDING_Y * 2)
    return width, height, lines


# ------------------------------------------------------------------- layout

def _layers(node_ids: list[str], edges: list[dict]) -> list[list[str]]:
    """Longest-path layering: every node sits one level below its deepest
    parent, so arrows point consistently down (or right) and never backwards
    unless the graph really has a cycle."""
    depth = {node_id: 0 for node_id in node_ids}
    incoming: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        if edge["from"] in depth and edge["to"] in depth:
            incoming[edge["to"]].append(edge["from"])

    # relax depths; bounded by node count so a cycle can't spin forever
    for _ in range(len(node_ids)):
        changed = False
        for node_id in node_ids:
            for parent in incoming[node_id]:
                if depth[parent] + 1 > depth[node_id]:
                    depth[node_id] = depth[parent] + 1
                    changed = True
        if not changed:
            break

    layers: list[list[str]] = []
    for node_id in node_ids:
        level = depth[node_id]
        while len(layers) <= level:
            layers.append([])
        layers[level].append(node_id)
    # a cycle can push nodes past levels nothing else lands on, and an empty
    # layer would just draw as a gap
    return [layer for layer in layers if layer]


# ------------------------------------------------------------------ building

def build_flowchart(
    nodes: list[dict],
    edges: list[dict],
    direction: str = "down",
    user_defaults: dict | None = None,
) -> list[dict]:
    """`nodes`: [{id, label, shape?}], `edges`: [{from, to, label?}]."""
    defaults = merged_defaults(user_defaults)
    font_size = int(defaults["font_size"])
    font_family = FONT_FAMILY.get(str(defaults["font_family"]), FONT_FAMILY["hand-drawn"])
    horizontal = direction in ("right", "left", "lr", "rl")

    known = {node["id"]: node for node in nodes}
    edges = [e for e in edges if e.get("from") in known and e.get("to") in known]
    layers = _layers([node["id"] for node in nodes], edges)

    sizes = {}
    for node in nodes:
        label = str(node.get("label") or node["id"])
        sizes[node["id"]] = _node_size(label, font_size)

    # place each layer, centred on the longest one
    positions: dict[str, tuple[int, int, int, int]] = {}
    along = 0
    spans = []
    for layer in layers:
        # "across" is the axis the layer spreads along: heights stack when the
        # chart runs left-to-right, widths when it runs top-down
        spans.append(
            sum(sizes[n][1] if horizontal else sizes[n][0] for n in layer)
            + GAP_ACROSS * (len(layer) - 1)
        )
    widest = max(spans) if spans else 0

    for layer, span in zip(layers, spans):
        deepest = max((sizes[n][1] if not horizontal else sizes[n][0]) for n in layer)
        across = (widest - span) / 2
        for node_id in layer:
            width, height, _ = sizes[node_id]
            if horizontal:
                positions[node_id] = (along, int(across), width, height)
                across += height + GAP_ACROSS
            else:
                positions[node_id] = (int(across), along, width, height)
                across += width + GAP_ACROSS
        along += deepest + GAP_ALONG

    elements: list[dict] = []
    containers: dict[str, dict] = {}

    for node in nodes:
        node_id = node["id"]
        x, y, width, height = positions[node_id]
        label = str(node.get("label") or node_id)
        shape = str(node.get("shape") or defaults["node_shape"])
        if shape not in ("rectangle", "ellipse", "diamond"):
            shape = "rectangle"
        if shape == "diamond":
            # a diamond's label only fits inside the inscribed rectangle
            width, height = int(width * 1.5), int(height * 1.6)

        # a mermaid stadium/round node is rounded whatever the user's corner
        # preference is — the shape is part of what the diagram says
        rounded = bool(node.get("rounded")) or defaults["edges"] == "round"
        container = _base(
            defaults,
            type=shape,
            x=float(x),
            y=float(y),
            width=float(width),
            height=float(height),
            roundness={"type": 3} if shape == "rectangle" and rounded else None,
            strokeColor=node.get("stroke_color", defaults["stroke_color"]),
            backgroundColor=node.get(
                "background_color", defaults["background_color"]
            ),
        )
        text = _base(
            defaults,
            type="text",
            x=float(x + NODE_PADDING_X),
            y=float(y + NODE_PADDING_Y),
            width=float(width - NODE_PADDING_X * 2),
            height=float(height - NODE_PADDING_Y * 2),
            text=label,
            originalText=label,
            fontSize=font_size,
            fontFamily=font_family,
            textAlign="center",
            verticalAlign="middle",
            containerId=container["id"],
            lineHeight=LINE_HEIGHT,
            autoResize=True,
            backgroundColor="transparent",
            strokeColor=node.get("text_color", defaults["stroke_color"]),
        )
        container["boundElements"] = [{"id": text["id"], "type": "text"}]
        containers[node_id] = container
        elements.append(container)
        elements.append(text)

    for edge in edges:
        start = containers[edge["from"]]
        end = containers[edge["to"]]
        arrow = _arrow(start, end, defaults, horizontal, edge)
        start["boundElements"] = list(start["boundElements"]) + [
            {"id": arrow["id"], "type": "arrow"}
        ]
        end["boundElements"] = list(end["boundElements"]) + [
            {"id": arrow["id"], "type": "arrow"}
        ]
        elements.append(arrow)

        label = edge.get("label")
        if label:
            elements.append(_edge_label(arrow, str(label), defaults, font_size, font_family))

    return elements


def _sides(start: dict, end: dict, horizontal: bool) -> tuple[list[float], list[float]]:
    """Which side of each box the arrow leaves and enters, as the ratio-based
    fixed points the editor stores on a binding."""
    if horizontal:
        return ([1, 0.5], [0, 0.5]) if end["x"] >= start["x"] else ([0, 0.5], [1, 0.5])
    return ([0.5, 1], [0.5, 0]) if end["y"] >= start["y"] else ([0.5, 0], [0.5, 1])


def _point_at(element: dict, ratio: list[float]) -> tuple[float, float]:
    return (
        element["x"] + element["width"] * ratio[0],
        element["y"] + element["height"] * ratio[1],
    )


def _arrow(
    start: dict,
    end: dict,
    defaults: dict,
    horizontal: bool,
    edge: dict | None = None,
) -> dict:
    edge = edge or {}
    start_ratio, end_ratio = _sides(start, end, horizontal)
    x1, y1 = _point_at(start, start_ratio)
    x2, y2 = _point_at(end, end_ratio)
    elbowed = defaults["arrow_type"] == "elbow"
    # mermaid says what the link means: dotted for a weak link, thick for an
    # emphasised one, and `---` for a connection with no direction
    stroke_style = "dashed" if edge.get("dashed") else defaults["stroke_style"]
    stroke_width = (
        defaults["stroke_width"] * 2 if edge.get("thick") else defaults["stroke_width"]
    )

    return _base(
        defaults,
        type="arrow",
        strokeStyle=stroke_style,
        strokeWidth=stroke_width,
        x=float(x1),
        y=float(y1),
        width=float(abs(x2 - x1)),
        height=float(abs(y2 - y1)),
        points=[[0, 0], [float(x2 - x1), float(y2 - y1)]],
        lastCommittedPoint=None,
        startArrowhead="arrow" if edge.get("head_start") else None,
        endArrowhead="arrow" if edge.get("head_end", True) else None,
        roundness=None if elbowed or defaults["arrow_type"] == "sharp" else {"type": 2},
        elbowed=elbowed,
        fixedSegments=[] if elbowed else None,
        # binding schema v2: a ratio on the shape plus how the arrow meets it
        startBinding={"elementId": start["id"], "fixedPoint": start_ratio, "mode": "orbit"},
        endBinding={"elementId": end["id"], "fixedPoint": end_ratio, "mode": "orbit"},
        backgroundColor="transparent",
    )


def _edge_label(
    arrow: dict, label: str, defaults: dict, font_size: int, font_family: int
) -> dict:
    small = max(12, int(font_size * 0.8))
    width = len(label) * small * CHAR_WIDTH_RATIO
    text = _base(
        defaults,
        type="text",
        x=float(arrow["x"] + (arrow["points"][1][0] / 2) - width / 2),
        y=float(arrow["y"] + (arrow["points"][1][1] / 2) - small),
        width=float(width),
        height=float(small * LINE_HEIGHT),
        text=label,
        originalText=label,
        fontSize=small,
        fontFamily=font_family,
        textAlign="center",
        verticalAlign="middle",
        containerId=arrow["id"],
        lineHeight=LINE_HEIGHT,
        autoResize=True,
        backgroundColor="transparent",
    )
    arrow["boundElements"] = list(arrow["boundElements"]) + [
        {"id": text["id"], "type": "text"}
    ]
    return text


# ------------------------------------------------------------------- mermaid

_DIRECTIONS = {
    "TD": "down",
    "TB": "down",
    "BT": "up",
    "LR": "right",
    "RL": "left",
}

# Node shapes, longest delimiter first so `([x])` is read as a stadium rather
# than as a round node wrapping "[x]" — that mistake leaks the brackets into
# the label. `rounded` maps a mermaid shape onto our rounded rectangle.
_SHAPE_PAIRS: list[tuple[str, str, str, bool]] = [
    ("(((", ")))", "ellipse", False),
    ("[[", "]]", "rectangle", False),
    ("([", "])", "rectangle", True),
    ("[(", ")]", "rectangle", True),
    ("((", "))", "ellipse", False),
    ("{{", "}}", "diamond", False),
    ("[/", "/]", "rectangle", False),
    ("[\\", "\\]", "rectangle", False),
    ("[/", "\\]", "rectangle", False),
    ("[\\", "/]", "rectangle", False),
    ("[", "]", "rectangle", False),
    ("(", ")", "rectangle", True),
    ("{", "}", "diamond", False),
    (">", "]", "rectangle", False),
]

_ID_RE = re.compile(r"^(?P<id>[A-Za-z0-9_.\-]+)")
# ---, -->, ==>, -.->, with optional heads on either end and an inline label
_EDGE_RE = re.compile(
    r"^(?P<from>.+?)\s*"
    r"(?P<arrow><?(?:-\.-|-\.|--|-|==|=)+>?)"
    r"\s*(?:\|(?P<label>[^|]*)\|\s*)?(?P<to>.+?)$"
)
_STYLE_RE = re.compile(r"(?P<key>[a-zA-Z-]+)\s*:\s*(?P<value>[^,;]+)")
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_TAG_RE = re.compile(r"<[^>]+>")
_BREAK_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)

_ENTITIES = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#35;": "#",
    "&#59;": ";",
}


class MermaidError(ValueError):
    pass


def _clean_label(raw: str) -> str:
    """Mermaid labels carry markup that means nothing on a canvas. `<br/>` is
    the one piece that does — it becomes a real line break, which is why a
    label that reads "RUNG 0<br/>Long context" must not reach the scene."""
    text = _BREAK_RE.sub("\n", raw)
    text = _TAG_RE.sub("", text)
    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    return text.strip()


def _split_shape(token: str) -> tuple[str, str, str, bool]:
    """-> (id, label, shape, rounded). Falls back to a bare id when the token
    carries no shape delimiters."""
    token = token.strip()
    match = _ID_RE.match(token)
    if not match:
        raise MermaidError(f"Could not read node: {token!r}")
    node_id = match.group("id")
    rest = token[match.end():].strip()
    if not rest:
        return node_id, "", "", False

    for open_delim, close_delim, shape, rounded in _SHAPE_PAIRS:
        if rest.startswith(open_delim) and rest.endswith(close_delim):
            inner = rest[len(open_delim) : len(rest) - len(close_delim)]
            return node_id, _clean_label(inner), shape, rounded

    raise MermaidError(f"Could not read node: {token!r}")


def _parse_style(body: str) -> dict:
    """`fill:#f9f,stroke:#333,color:#fff` -> the element properties we honour.
    Anything else in the declaration (stroke-width, stroke-dasharray, ...) is
    left alone rather than guessed at."""
    out: dict = {}
    for match in _STYLE_RE.finditer(body):
        key = match.group("key").lower()
        value = match.group("value").strip()
        if key == "fill" and (_HEX_RE.match(value) or value == "transparent"):
            out["background_color"] = value
        elif key == "stroke" and _HEX_RE.match(value):
            out["stroke_color"] = value
        elif key == "color" and _HEX_RE.match(value):
            # the label colour, which matters once a node is filled dark
            out["text_color"] = value
    return out


def parse_mermaid(source: str) -> tuple[list[dict], list[dict], str, list[str]]:
    """Reads the `flowchart` / `graph` subset agents actually emit: directions,
    every node shape, `<br/>` line breaks, edge labels and styles, `A --> B & C`
    fan-out, and classDef/class/style colouring.

    Returns the nodes, edges, direction, and any notes about what could not be
    represented — a diagram that came through with something dropped should say
    so rather than look complete.
    """
    lines = [
        line.strip()
        for line in source.strip().splitlines()
        if line.strip() and not line.strip().startswith("%%")
    ]
    if not lines:
        raise MermaidError("The mermaid source is empty")

    header = lines[0].lower()
    if not (header.startswith("flowchart") or header.startswith("graph")):
        kind = lines[0].split()[0] if lines[0].split() else "unknown"
        raise MermaidError(
            f"Only mermaid flowcharts are supported here, got '{kind}'. "
            "Use the create_flowchart tool for other shapes."
        )

    parts = lines[0].split()
    direction = _DIRECTIONS.get(parts[1].upper(), "down") if len(parts) > 1 else "down"

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    classes: dict[str, dict] = {}
    notes: list[str] = []
    subgraphs = 0

    def note_node(token: str) -> str:
        token = token.strip()
        # `A:::className` attaches a class inline
        class_name = None
        if ":::" in token:
            token, class_name = token.split(":::", 1)
            class_name = class_name.strip()

        node_id, label, shape, rounded = _split_shape(token)
        existing = nodes.get(node_id)
        if existing is None:
            existing = nodes[node_id] = {
                "id": node_id,
                "label": label or node_id,
                "shape": shape or "rectangle",
                "rounded": rounded,
                "classes": [],
            }
        elif label:
            # a later mention carrying a label defines the node's real look
            existing["label"] = label
            existing["shape"] = shape or existing["shape"]
            existing["rounded"] = rounded
        if class_name:
            existing["classes"].append(class_name)
        return node_id

    for line in lines[1:]:
        line = line.rstrip(";")
        lowered = line.lower()

        if lowered.startswith("subgraph"):
            subgraphs += 1
            continue
        if lowered == "end":
            continue
        if lowered.startswith("classdef "):
            _, _, rest = line.partition(" ")
            name, _, body = rest.strip().partition(" ")
            classes[name.strip()] = _parse_style(body)
            continue
        if lowered.startswith("class "):
            _, _, rest = line.partition(" ")
            targets, _, name = rest.strip().rpartition(" ")
            for target in targets.split(","):
                target = target.strip()
                if target:
                    nodes[note_node(target)]["classes"].append(name.strip())
            continue
        if lowered.startswith("style "):
            _, _, rest = line.partition(" ")
            target, _, body = rest.strip().partition(" ")
            node_id = note_node(target)
            nodes[node_id].update(_parse_style(body))
            continue
        if lowered.startswith(("linkstyle", "click ", "direction ")):
            continue

        match = _EDGE_RE.match(line)
        if match:
            arrow = match.group("arrow")
            label = _clean_label(match.group("label") or "")
            left = match.group("from")
            # `A -- text --> B` puts the label mid-arrow instead of in pipes
            inline = re.match(r"^(?P<from>.+?)\s+--\s*(?P<label>[^-|>]+?)\s*$", left)
            if inline and not label:
                left = inline.group("from")
                label = _clean_label(inline.group("label"))
            style = {
                "dashed": "-." in arrow,
                "thick": "=" in arrow,
                "head_end": arrow.endswith(">"),
                "head_start": arrow.startswith("<"),
            }
            for source_id in [note_node(t) for t in left.split("&")]:
                for target_id in [note_node(t) for t in match.group("to").split("&")]:
                    edges.append(
                        {
                            "from": source_id,
                            "to": target_id,
                            "label": label or None,
                            **style,
                        }
                    )
            continue

        note_node(line)

    # fold the class definitions into the nodes that reference them
    for node in nodes.values():
        for class_name in node.pop("classes", []):
            for key, value in classes.get(class_name, {}).items():
                node.setdefault(key, value)

    if subgraphs:
        notes.append(
            f"{subgraphs} subgraph "
            f"{'group was' if subgraphs == 1 else 'groups were'} flattened — "
            "the nodes are all there, but not boxed together"
        )

    if not nodes:
        raise MermaidError("No nodes found in the mermaid source")
    return list(nodes.values()), edges, direction, notes
