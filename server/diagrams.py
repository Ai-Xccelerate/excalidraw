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

        container = _base(
            defaults,
            type=shape,
            x=float(x),
            y=float(y),
            width=float(width),
            height=float(height),
            roundness=(
                {"type": 3} if shape == "rectangle" and defaults["edges"] == "round" else None
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
        )
        container["boundElements"] = [{"id": text["id"], "type": "text"}]
        containers[node_id] = container
        elements.append(container)
        elements.append(text)

    for edge in edges:
        start = containers[edge["from"]]
        end = containers[edge["to"]]
        arrow = _arrow(start, end, defaults, horizontal)
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


def _arrow(start: dict, end: dict, defaults: dict, horizontal: bool) -> dict:
    start_ratio, end_ratio = _sides(start, end, horizontal)
    x1, y1 = _point_at(start, start_ratio)
    x2, y2 = _point_at(end, end_ratio)
    elbowed = defaults["arrow_type"] == "elbow"

    return _base(
        defaults,
        type="arrow",
        x=float(x1),
        y=float(y1),
        width=float(abs(x2 - x1)),
        height=float(abs(y2 - y1)),
        points=[[0, 0], [float(x2 - x1), float(y2 - y1)]],
        lastCommittedPoint=None,
        startArrowhead=None,
        endArrowhead="arrow",
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

# A --> B, A -- text --> B, A -->|text| B, A --- B, A -.-> B, A ==> B
_EDGE_RE = re.compile(
    r"^(?P<from>.+?)\s*(?P<arrow>-{2,3}>|-{3}|-\.->|={2,3}>)\s*"
    r"(?:\|(?P<label1>[^|]*)\|\s*)?(?P<to>.+?)$"
)
_NODE_RE = re.compile(
    r"^(?P<id>[A-Za-z0-9_\-]+)\s*"
    r"(?:(?P<open>\[\[|\[|\(\(|\(|\{|>)(?P<label>.*?)(?P<close>\]\]|\]|\)\)|\)|\}))?$"
)
_SHAPES = {"[": "rectangle", "[[": "rectangle", "(": "ellipse", "((": "ellipse", "{": "diamond", ">": "rectangle"}


class MermaidError(ValueError):
    pass


def parse_mermaid(source: str) -> tuple[list[dict], list[dict], str]:
    """Understands the `flowchart` / `graph` subset agents actually emit:
    directions, the common node shapes, edge labels, and `A --> B & C` fan-out.
    Anything else (subgraphs, class definitions, other diagram types) is
    reported rather than silently half-drawn."""
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
    if any(line.lower().startswith("subgraph") for line in lines):
        raise MermaidError("Mermaid subgraphs are not supported yet")

    parts = lines[0].split()
    direction = _DIRECTIONS.get(parts[1].upper(), "down") if len(parts) > 1 else "down"

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def note(token: str) -> str:
        match = _NODE_RE.match(token.strip())
        if not match:
            raise MermaidError(f"Could not read node: {token.strip()!r}")
        node_id = match.group("id")
        label = (match.group("label") or "").strip().strip('"')
        shape = _SHAPES.get(match.group("open") or "", "rectangle")
        existing = nodes.get(node_id)
        if existing is None:
            nodes[node_id] = {"id": node_id, "label": label or node_id, "shape": shape}
        elif label:
            existing["label"] = label
            existing["shape"] = shape
        return node_id

    for line in lines[1:]:
        line = line.rstrip(";")
        if line.lower().startswith(("style ", "classdef", "class ", "linkstyle", "click ")):
            continue
        match = _EDGE_RE.match(line)
        if match:
            label = (match.group("label1") or "").strip().strip('"')
            # `A -- text --> B` puts the label in the middle of the arrow
            left = match.group("from")
            inline = re.match(r"^(?P<from>.+?)\s*--\s*(?P<label>[^-|>]+)$", left)
            if inline and not label:
                left = inline.group("from")
                label = inline.group("label").strip().strip('"')
            for source_id in [note(t) for t in left.split("&")]:
                for target_id in [note(t) for t in match.group("to").split("&")]:
                    edges.append({"from": source_id, "to": target_id, "label": label or None})
            continue
        # a bare node declaration
        note(line)

    if not nodes:
        raise MermaidError("No nodes found in the mermaid source")
    return list(nodes.values()), edges, direction
