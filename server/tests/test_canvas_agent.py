"""The canvas agent's contract with the model and with the board.

No network: these drive the parsing and compiling around the model call, which
is where the behaviour that matters lives — what the model is told about the
board, what it is allowed to change, and what reaches the canvas.

    DATABASE_URL=postgresql://localhost/aixdraw_test AUTH_SECRET=<32+ chars> \
      python tests/test_canvas_agent.py
"""

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
