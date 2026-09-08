"""The canvas agent's contract with the model and with the board.

No network: these drive the parsing and compiling around the model call, which
is where the behaviour that matters lives — what the model is told about the
board, what it is allowed to change, and what reaches the canvas.

    DATABASE_URL=postgresql://localhost/aixdraw_test AUTH_SECRET=<32+ chars> \
      python tests/test_canvas_agent.py
"""

import itertools
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault(
    "DATABASE_URL", f"postgresql://{os.environ['USER']}@localhost:5432/aixdraw_test"
)
os.environ.setdefault("AUTH_SECRET", "0123456789012345678901234567890123456789")

import agent


def check(label, condition, extra=""):
    print(("PASS  " if condition else "FAIL  ") + label + ("" if condition else f"  <- {extra}"))
    return condition


ok = True

BOARD = {
    "elements": [
        {"id": "box1", "type": "rectangle", "x": 10, "y": 20, "backgroundColor": "#fef3bd"},
        {"id": "t1", "type": "text", "text": "Qualified?", "containerId": "box1"},
        {"id": "box2", "type": "diamond", "x": 200, "y": 20},
        {
            "id": "arrow1",
            "type": "arrow",
            "startBinding": {"elementId": "box1"},
            "endBinding": {"elementId": "box2"},
        },
    ],
    "selected_ids": [],
}

# --------------------------------------------------------------- the board

described = agent.describe_board(BOARD)
ok &= check("bound text is folded into the shape it labels", '"Qualified?"' in described, described)
ok &= check("ids are given so the model can point back at them", "box1" in described, described)
ok &= check("arrows are described by what they connect", "box1 -> box2" in described, described)
ok &= check("an empty board says so", "empty" in agent.describe_board({"elements": []}))

selected = agent.describe_board({**BOARD, "selected_ids": ["box2"]})
ok &= check("a selection is called out", "selected" in selected.lower(), selected)
ok &= check("and the description narrows to it", "box1 [" not in selected, selected)

huge = {"elements": [{"id": f"n{i}", "type": "rectangle"} for i in range(500)]}
ok &= check(
    "a huge board is summarised by counts rather than listed",
    "Too many to list" in agent.describe_board(huge),
)

# ------------------------------------------------------------- the message

messages = agent.build_messages(
    [{"role": "user", "content": "draw our sales flow"}],
    BOARD,
    [{"name": "notes.md", "text": "Stages: lead, demo, close"}],
)
ok &= check("the standing instructions lead", messages[0]["role"] == "system")
ok &= check("the board is given to the model", "box1" in messages[1]["content"])
ok &= check("an attachment travels with it", "Stages: lead" in messages[1]["content"])
ok &= check("the user's words come last", messages[-1]["content"] == "draw our sales flow")

with_image = agent.build_messages(
    [{"role": "user", "content": "like this", "images": ["data:image/png;base64,AAA"]}],
    None,
    None,
)
ok &= check(
    "a pasted image is sent as multimodal content",
    isinstance(with_image[-1]["content"], list)
    and with_image[-1]["content"][1]["type"] == "image_url",
    with_image[-1],
)

# -------------------------------------------------------------- the action

prose, action = agent.split_action(
    'Here is the flow.\n\n```json\n{"action": "draw", "nodes": [{"id": "a", "label": "Start"}]}\n```'
)
ok &= check("the block is taken out of what the user reads", "```" not in prose, prose)
ok &= check("and parsed", action and action["nodes"][0]["label"] == "Start", action)

ok &= check(
    "a conversational turn carries no action",
    agent.split_action("Which part should I emphasise?")[1] is None,
)
ok &= check(
    "a malformed block does not lose the reply",
    agent.split_action("Sure.\n```json\n{oops\n```")[0].startswith("Sure."),
)

# ------------------------------------------------------------- compiling

drawn = agent.compile_action(
    {
        "action": "draw",
        "direction": "right",
        "nodes": [
            {"id": "a", "label": "Lead", "shape": "ellipse", "fill": "#d3f9d8"},
            {"id": "b", "label": "Qualified?", "shape": "diamond"},
        ],
        "edges": [{"from": "a", "to": "b", "label": "yes"}],
    },
    None,
    {"elements": [], "selected_ids": []},
)
kinds = [element["type"] for element in drawn["elements"]]
ok &= check("nodes become real elements", kinds.count("ellipse") == 1 and kinds.count("diamond") == 1, kinds)
ok &= check("edges become bound arrows", kinds.count("arrow") == 1, kinds)
ok &= check(
    "a colour the model chose is honoured",
    any(e.get("backgroundColor") == "#d3f9d8" for e in drawn["elements"]),
)

# a selection fences what the agent may touch
fenced = agent.compile_action(
    {"action": "draw", "delete": ["box1", "box2"], "update": [{"id": "box1", "fill": "#ffc9c9"}]},
    None,
    {**BOARD, "selected_ids": ["box2"]},
)
ok &= check("deletes outside the selection are dropped", fenced["delete_ids"] == ["box2"], fenced)
ok &= check("so are updates outside it", fenced["updates"] == [], fenced)

unfenced = agent.compile_action(
    {"action": "draw", "update": [{"id": "box1", "label": "Renamed", "fill": "#a5d8ff"}]},
    None,
    BOARD,
)
ok &= check(
    "with nothing selected the whole board is in play",
    unfenced["updates"][0]["label"] == "Renamed"
    and unfenced["updates"][0]["backgroundColor"] == "#a5d8ff",
    unfenced,
)

invented = agent.compile_action(
    {"action": "draw", "delete": ["not-on-the-board"]}, None, BOARD
)
ok &= check("an id that isn't on the board is ignored", invented is None, invented)

junk = agent.compile_action(
    {
        "action": "draw",
        "nodes": [{"id": "a", "label": "A", "fill": "drop table"}],
        "edges": [{"from": "a", "to": "ghost"}],
    },
    None,
    None,
)
ok &= check(
    "a bad colour is dropped rather than written to the canvas",
    all(e.get("backgroundColor") != "drop table" for e in junk["elements"]),
)
ok &= check(
    "an edge to a node that doesn't exist is dropped",
    not any(e["type"] == "arrow" for e in junk["elements"]),
)

ok &= check("nothing to do compiles to nothing", agent.compile_action({"action": "draw"}, None, None) is None)

# the user's own defaults reach an agent-drawn diagram
styled = agent.compile_action(
    {"action": "draw", "nodes": [{"id": "a", "label": "Start"}]},
    {"font_family": "code", "arrow_type": "elbow"},
    None,
)
label = next(e for e in styled["elements"] if e["type"] == "text")
ok &= check("agent diagrams use the user's saved font", label["fontFamily"] == 3, label["fontFamily"])

# ---------------------------------------------------------------- lanes

laned = agent.compile_action(
    {
        "action": "draw",
        "direction": "right",
        "groups": [
            {"label": "Indexing", "nodes": ["a", "b"]},
            {"label": "Serving", "nodes": ["c"]},
        ],
        "nodes": [
            {"id": "a", "label": "Ingest"},
            {"id": "b", "label": "Embed"},
            {"id": "c", "label": "Answer"},
        ],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
    },
    None,
    None,
)
frames = [
    element
    for element in laned["elements"]
    if element["type"] == "rectangle" and element["strokeStyle"] == "dashed"
]
titles = [
    element["text"]
    for element in laned["elements"]
    if element["type"] == "text" and not element.get("containerId")
]
ok &= check("a lane is drawn behind its members", len(frames) == 2, len(frames))
ok &= check("and titled", titles == ["Indexing", "Serving"], titles)
ok &= check(
    "the lane sits behind the nodes it holds",
    laned["elements"].index(frames[0]) == 0,
    "frames must come first in z-order",
)
ok &= check("the summary counts the lanes", laned["summary"]["grouped"] == 2, laned["summary"])

boxes = [
    element
    for element in laned["elements"]
    if element["type"] in ("rectangle", "ellipse", "diamond")
    and element["strokeStyle"] != "dashed"
]
labels = {
    text["containerId"]: text["text"]
    for text in laned["elements"]
    if text["type"] == "text" and text.get("containerId")
}


def within(box, frame):
    return (
        frame["x"] <= box["x"]
        and box["x"] + box["width"] <= frame["x"] + frame["width"]
        and frame["y"] <= box["y"]
        and box["y"] + box["height"] <= frame["y"] + frame["height"]
    )


indexing = {"Ingest", "Embed"}
in_first = {labels[box["id"]] for box in boxes if within(box, frames[0])}
ok &= check("a lane's frame contains exactly its members", in_first == indexing, in_first)

# and the lanes are laid out as bands rather than stacked on each other
def overlaps(a, b):
    return not (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )


ok &= check("lanes do not sit on top of each other", not overlaps(frames[0], frames[1]))

# lanes keep the flow moving one way: the earlier layout restarted each lane at
# its own left edge, so every cross-lane edge ran backwards across the diagram
chain_nodes = [{"id": f"n{i}", "label": f"Step {i}"} for i in range(12)]
chain_edges = [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(11)]
lanes_for_chain = [
    {"label": "Start", "nodes": [f"n{i}" for i in range(4)]},
    {"label": "Middle", "nodes": [f"n{i}" for i in range(4, 8)]},
    {"label": "End", "nodes": [f"n{i}" for i in range(8, 12)]},
]

chained = agent.compile_action(
    {
        "action": "draw",
        "direction": "down",
        "nodes": chain_nodes,
        "edges": chain_edges,
        "groups": lanes_for_chain,
    },
    None,
    None,
)["elements"]
placed = {
    text["text"]: next(
        shape for shape in chained if shape["id"] == text["containerId"]
    )
    for text in chained
    if text["type"] == "text" and text.get("containerId")
}
forward = all(
    placed[f"Step {i}"]["y"] < placed[f"Step {i + 1}"]["y"] for i in range(11)
)
ok &= check("every step sits after the one that feeds it", forward, "flow runs backwards")

lane_frames = [
    e for e in chained if e["type"] == "rectangle" and e["strokeStyle"] == "dashed"
]
ok &= check(
    "the lanes are separate bands",
    len(lane_frames) == 3
    and not any(
        overlaps(a, b) for a, b in itertools.combinations(lane_frames, 2)
    ),
)

ok &= check(
    "a lane naming nodes that don't exist is dropped",
    agent.compile_action(
        {"action": "draw", "groups": [{"label": "Ghost", "nodes": ["nope"]}],
         "nodes": [{"id": "a", "label": "A"}]},
        None,
        None,
    )["summary"]["grouped"]
    == 0,
)

# ------------------------------------------------------------- the wiring


def _legs(arrow):
    points = arrow["points"]
    return [
        (
            (arrow["x"] + points[i][0], arrow["y"] + points[i][1]),
            (arrow["x"] + points[i + 1][0], arrow["y"] + points[i + 1][1]),
        )
        for i in range(len(points) - 1)
    ]


def _through_boxes(elements):
    """Arrows drawn over a shape they do not connect — the thing that made the
    reported diagram unreadable."""
    arrows = [e for e in elements if e["type"] == "arrow"]
    shapes = [
        e
        for e in elements
        if e["type"] in ("rectangle", "ellipse", "diamond")
        and e["strokeStyle"] != "dashed"
    ]
    hits = 0
    for arrow in arrows:
        bound = {
            (arrow.get("startBinding") or {}).get("elementId"),
            (arrow.get("endBinding") or {}).get("elementId"),
        }
        for (x1, y1), (x2, y2) in _legs(arrow):
            for shape in shapes:
                if shape["id"] in bound:
                    continue
                left, top = shape["x"] + 4, shape["y"] + 4
                right = shape["x"] + shape["width"] - 4
                bottom = shape["y"] + shape["height"] - 4
                for step in range(41):
                    t = step / 40
                    px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                    if left < px < right and top < py < bottom:
                        hits += 1
                        break
    return hits


pipeline_nodes = [
    {"id": i, "label": l}
    for i, l in [
        ("ds", "Data sources"), ("ld", "Load documents"), ("ct", "Chunk text"),
        ("emb", "Embed chunks"), ("ee", "Extract entities"), ("br", "Build relations"),
        ("vdb", "Vector DB"), ("gdb", "Graph DB"), ("uq", "User query"),
        ("vs", "Vector search"), ("gt", "Graph traversal"), ("fuse", "Fuse & rerank"),
        ("rel", "Relevant?"), ("llm", "LLM generate"), ("fa", "Final answer"),
    ]
]
pipeline_edges = [
    {"from": a, "to": b, "label": l}
    for a, b, l in [
        ("ds", "ld", None), ("ld", "ct", None), ("ct", "emb", None), ("ct", "ee", None),
        ("ee", "br", None), ("emb", "vdb", "upsert"), ("br", "gdb", "upsert"),
        ("uq", "vs", None), ("uq", "gt", None), ("vdb", "vs", None),
        ("gdb", "gt", "neighbours"), ("vs", "fuse", None), ("gt", "fuse", None),
        ("fuse", "rel", None), ("rel", "llm", "yes"), ("rel", "vs", "no"),
        ("llm", "fa", None),
    ]
]
pipeline_groups = [
    {"label": "Ingestion", "nodes": ["ds", "ld", "ct"]},
    {"label": "Indexing", "nodes": ["emb", "ee", "br"]},
    {"label": "Storage", "nodes": ["vdb", "gdb"]},
    {"label": "Retrieval", "nodes": ["uq", "vs", "gt", "fuse", "rel"]},
    {"label": "Generation", "nodes": ["llm", "fa"]},
]

wired = agent.compile_action(
    {
        "action": "draw",
        "direction": "right",
        "nodes": pipeline_nodes,
        "edges": pipeline_edges,
        "groups": pipeline_groups,
    },
    None,
    None,
)["elements"]
ok &= check(
    "no arrow is drawn over a shape it doesn't connect",
    _through_boxes(wired) == 0,
    _through_boxes(wired),
)

corners = [
    len(e["points"])
    for e in wired
    if e["type"] == "arrow" and len(e["points"]) > 2
]
ok &= check(
    "long connections are routed around rather than cut across",
    len(corners) > 0,
    "expected some multi-segment routes",
)

# a detailed request means a detailed diagram — there is no node budget
big_nodes = [{"id": f"s{i}", "label": f"Stage {i}"} for i in range(26)]
big_edges = [{"from": f"s{i}", "to": f"s{i + 1}"} for i in range(25)]
big_groups = [
    {"label": f"Phase {phase}", "nodes": [f"s{i}" for i in range(phase * 7, min(phase * 7 + 7, 26))]}
    for phase in range(4)
]
big = agent.compile_action(
    {
        "action": "draw",
        "direction": "right",
        "nodes": big_nodes,
        "edges": big_edges,
        "groups": big_groups,
    },
    None,
    None,
)
ok &= check("a 26-node diagram draws", big["summary"]["created"] == 26, big["summary"])
ok &= check(
    "and its wiring still avoids the shapes",
    _through_boxes(big["elements"]) == 0,
    _through_boxes(big["elements"]),
)

ok &= check(
    "everything is drawn clean, whatever the user's sloppiness setting",
    {e["roughness"] for e in agent.compile_action(
        {"action": "draw", "nodes": [{"id": "a", "label": "A"}]},
        {"roughness": 2},
        None,
    )["elements"]}
    == {0},
)

# ------------------------------------------------------- through the route

# The parsing above all passes with the route itself broken: the first version
# shipped with the handler shadowing the module it called, and only a real
# request through the app would have caught it. So drive one.
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

import ai
import main
from auth import create_access_token, hash_password
from db import SessionLocal
from models import User

db = SessionLocal()
user = User(
    email=f"agent-{uuid.uuid4().hex[:6]}@example.com",
    password_hash=hash_password("supersecret1"),
)
user.email_verified_at = datetime.now(timezone.utc)
db.add(user)
db.commit()
db.refresh(user)
AUTH = {"Authorization": f"Bearer {create_access_token(user)}"}
client = TestClient(main.app)

REPLY = (
    "Two lanes, decision in the middle.\n\n"
    '```json\n{"action": "draw", "nodes": [{"id": "a", "label": "Start", '
    '"shape": "ellipse"}, {"id": "b", "label": "Done"}], '
    '"edges": [{"from": "a", "to": "b"}]}\n```'
)

_real_complete, _real_configured = ai.complete, ai.is_configured
captured: dict = {}


async def fake_complete(messages, **kwargs):
    captured["messages"] = messages
    return REPLY


ai.complete = fake_complete
ai.is_configured = lambda: True

try:
    response = client.post(
        "/v1/ai/canvas-agent",
        headers=AUTH,
        json={
            "messages": [{"role": "user", "content": "draw a two step flow"}],
            "board": {"elements": [], "selected_ids": []},
            "attachments": [],
        },
    )
    ok &= check("the route answers", response.status_code == 200, response.text)
    payload = response.json() if response.status_code == 200 else {}
    ok &= check(
        "the prose comes back without the action block",
        "```" not in payload.get("reply", "```"),
        payload.get("reply"),
    )
    ok &= check(
        "and the drawing comes back as elements",
        payload.get("operations", {}).get("summary", {}).get("created") == 2,
        payload.get("operations"),
    )
    ok &= check(
        "the model was given the standing instructions and the board",
        captured["messages"][0]["role"] == "system" and len(captured["messages"]) >= 3,
        captured.get("messages"),
    )

    # the transcript that prompted this: the model says it is drawing, attaches
    # nothing, and the user has to ask "did you create". Ask it once instead.
    calls: list[int] = []

    async def forgets_then_remembers(messages, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return "Drawing it now — 3 lanes, blue steps, amber decisions."
        return '```json\n{"action": "draw", "nodes": [{"id": "a", "label": "Start"}]}\n```'

    ai.complete = forgets_then_remembers
    recovered = client.post(
        "/v1/ai/canvas-agent",
        headers=AUTH,
        json={"messages": [{"role": "user", "content": "yes"}]},
    ).json()
    ok &= check(
        "a claimed drawing with no block is asked for again",
        len(calls) == 2 and recovered["operations"]["summary"]["created"] == 1,
        (len(calls), recovered.get("operations")),
    )
    ok &= check(
        "and the user still reads the original explanation",
        recovered["reply"].startswith("Drawing it now"),
        recovered["reply"],
    )

    # a question must not trigger a retry — that is a model call per turn for
    # nothing, on every conversational message
    calls.clear()

    async def just_asks(messages, **kwargs):
        calls.append(1)
        return "Which stage should it emphasise — scoring, or handoff?"

    ai.complete = just_asks
    asked = client.post(
        "/v1/ai/canvas-agent",
        headers=AUTH,
        json={"messages": [{"role": "user", "content": "draw our funnel"}]},
    ).json()
    ok &= check(
        "a question is answered in one call",
        len(calls) == 1 and asked["operations"] is None,
        len(calls),
    )

    ai.complete = fake_complete
    unauthorised = client.post("/v1/ai/canvas-agent", json={"messages": []})
    ok &= check("and it needs a session", unauthorised.status_code == 401, unauthorised.status_code)

    # a crash must come back as a response, or the browser just says
    # "Failed to fetch" and the real error never reaches anyone
    async def blow_up(messages, **kwargs):
        raise RuntimeError("boom")

    ai.complete = blow_up
    # the real browser gets a response, not an exception, so ask the test
    # client for the same
    crashing_client = TestClient(main.app, raise_server_exceptions=False)
    crashed = crashing_client.post(
        "/v1/ai/canvas-agent",
        headers=AUTH,
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    ok &= check(
        "an unexpected failure answers 500 rather than dropping the connection",
        crashed.status_code == 500 and "message" in crashed.json(),
        crashed.status_code,
    )
finally:
    ai.complete, ai.is_configured = _real_complete, _real_configured

print("\n" + ("ALL PASS" if ok else "SOME FAILURES"))
sys.exit(0 if ok else 1)
