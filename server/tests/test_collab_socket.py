"""Live collaboration over the socket, end to end.

Needs the API running locally and a throwaway Postgres:

    DATABASE_URL=postgresql://localhost/aixdraw_test AUTH_SECRET=<32+ chars> \
      python -m uvicorn main:asgi_app --port 8123
    python tests/test_collab_socket.py

It checks the things that would silently break sharing a session: two people
reaching the same room, an edit travelling between them, and the two ways in
that must stay shut — a stranger joining a room they have no access to, and a
socket with no token at all.
"""
import asyncio, sys, uuid
from datetime import datetime, timezone

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import os
os.environ.setdefault("DATABASE_URL", f"postgresql://{os.environ['USER']}@localhost:5432/aixdraw_test")
os.environ.setdefault("AUTH_SECRET", "0123456789012345678901234567890123456789")

import socketio
from db import SessionLocal
from models import User, Drawing, RoomMember
from auth import hash_password, create_access_token

db = SessionLocal()
owner = User(email=f"host-{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("supersecret1"))
owner.email_verified_at = datetime.now(timezone.utc)
guest = User(email=f"guest-{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("supersecret1"))
guest.email_verified_at = datetime.now(timezone.utc)
db.add_all([owner, guest]); db.commit(); db.refresh(owner); db.refresh(guest)

drawing = Drawing(owner_id=owner.id, title="Collab", elements=[], app_state={}, files={}, scene_version=1)
db.add(drawing); db.commit(); db.refresh(drawing)
db.add(RoomMember(drawing_id=drawing.id, user_id=guest.id, role="editor")); db.commit()

room = str(drawing.id)
URL = os.environ.get("COLLAB_URL", "http://localhost:8123")

async def main():
    ok = True
    received = asyncio.Queue()
    roster_seen = asyncio.Queue()

    host = socketio.AsyncClient()
    visitor = socketio.AsyncClient()

    @visitor.on("client-broadcast")
    async def on_broadcast(data, iv=None):
        await received.put(data)

    @host.on("room-user-change")
    async def on_roster(users):
        await roster_seen.put(users)

    await host.connect(URL, auth={"token": create_access_token(owner), "username": "Host"},
                       transports=["websocket"])
    await visitor.connect(URL, auth={"token": create_access_token(guest), "username": "Guest"},
                          transports=["websocket"])
    print("PASS  both clients connected")

    await host.emit("join-room", room)
    await visitor.emit("join-room", room)
    users = await asyncio.wait_for(roster_seen.get(), timeout=5)
    while len(users) < 2:
        users = await asyncio.wait_for(roster_seen.get(), timeout=5)
    print(f"PASS  the room shows both people: {[u['username'] for u in users]}")

    await host.emit("server-broadcast", (room, b"scene-update-payload", b"iv"))
    payload = await asyncio.wait_for(received.get(), timeout=5)
    print(f"PASS  an edit from one reaches the other ({len(payload)} bytes)")

    # someone with no access must not get in
    outsider_user = User(email=f"out-{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("supersecret1"))
    outsider_user.email_verified_at = datetime.now(timezone.utc)
    db.add(outsider_user); db.commit(); db.refresh(outsider_user)
    outsider = socketio.AsyncClient()
    errors = asyncio.Queue()
    @outsider.on("error")
    async def on_error(data):
        await errors.put(data)
    await outsider.connect(URL, auth={"token": create_access_token(outsider_user), "username": "Outsider"},
                           transports=["websocket"])
    await outsider.emit("join-room", room)
    err = await asyncio.wait_for(errors.get(), timeout=5)
    print(f"PASS  a stranger is refused the room: {err['message']}")

    # and no token at all
    refused = socketio.AsyncClient()
    try:
        await refused.connect(URL, auth={}, transports=["websocket"])
        print("FAIL  an unauthenticated socket was allowed in")
        ok = False
    except Exception:
        print("PASS  an unauthenticated socket is refused")

    for client in (host, visitor, outsider):
        await client.disconnect()
    print("\n" + ("COLLAB OK" if ok else "COLLAB PROBLEMS"))

asyncio.run(main())
