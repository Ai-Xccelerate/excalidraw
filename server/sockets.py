import time

import socketio

from auth import get_user_workspace_ids, verify_socket_token
from db import SessionLocal
from models import Drawing, RoomMember

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

# socket id -> {"user_id": str, "room_id": str | None, "username": str}
_connections: dict[str, dict] = {}

# Roles were previously resolved once at join-room and trusted for the life of
# the connection, so removing a member or demoting an editor to viewer left
# them editing until they happened to disconnect. Re-resolve on a short TTL:
# frequent enough that a revocation lands in seconds, cheap enough that pointer
# traffic doesn't hit the database on every event.
_ROLE_TTL_SECONDS = 5.0


# subtypes that only describe where a user is looking/pointing. They carry no
# scene mutation, so a viewer may broadcast them; anything else is an edit.
_PRESENCE_SUBTYPES = {"MOUSE_LOCATION", "IDLE_STATUS", "USER_VISIBLE_SCENE_BOUNDS"}


async def _role_for_room(drawing_id: str, user_id: str) -> str | None:
    """Same access set as GET /api/drawings/{id}, but keeps the *role* — the REST
    layer blocks viewers from PUT, so the socket has to block them too or
    read-only sharing isn't read-only."""
    db = SessionLocal()
    try:
        drawing = db.get(Drawing, drawing_id)
        if not drawing:
            return None
        # in the Trash it is gone as far as everyone is concerned, including a
        # collaborator holding an open room link
        if drawing.deleted_at is not None:
            return None
        if drawing.owner_id == user_id:
            return "owner"
        member = (
            db.query(RoomMember)
            .filter(RoomMember.drawing_id == drawing_id, RoomMember.user_id == user_id)
            .first()
        )
        if member is not None:
            return member.role
        if drawing.workspace_id is not None:
            if drawing.workspace_id in get_user_workspace_ids(db, user_id):
                return "editor"
        return None
    finally:
        db.close()


async def _current_role(conn: dict) -> str | None:
    """Cached role for the connection's room, refreshed every few seconds."""
    now = time.monotonic()
    if conn.get("role_checked_at") is not None and (
        now - conn["role_checked_at"] < _ROLE_TTL_SECONDS
    ):
        return conn.get("role")
    role = await _role_for_room(conn["room_id"], conn["user_id"])
    conn["role"] = role
    conn["role_checked_at"] = now
    return role


def _may_broadcast(role: str | None, payload) -> bool:
    if role in ("owner", "editor"):
        return True
    # both broadcast channels land on the same `client-broadcast` handler, and the
    # client dispatches on payload["type"] regardless of which one carried it — so
    # a viewer restricted on one channel could just mutate the scene over the other.
    subtype = payload.get("type") if isinstance(payload, dict) else None
    return subtype in _PRESENCE_SUBTYPES


@sio.event
async def connect(sid, environ, auth):
    token = (auth or {}).get("token")
    db = SessionLocal()
    try:
        user_id = await verify_socket_token(token, db)
    finally:
        db.close()
    if not user_id:
        raise socketio.exceptions.ConnectionRefusedError("Invalid or missing auth token")
    _connections[sid] = {
        "user_id": user_id,
        "room_id": None,
        "role": None,
        "role_checked_at": None,
        "username": (auth or {}).get("username", "Anonymous"),
    }


@sio.event
async def disconnect(sid):
    conn = _connections.pop(sid, None)
    if conn and conn["room_id"]:
        room_id = conn["room_id"]
        await sio.emit(
            "room-user-change",
            _roster(room_id),
            room=room_id,
        )


def _roster(room_id: str) -> list[dict]:
    return [
        {"socketId": sid, "username": c["username"]}
        for sid, c in _connections.items()
        if c["room_id"] == room_id
    ]


@sio.on("join-room")
async def join_room(sid, room_id):
    conn = _connections.get(sid)
    if not conn:
        return
    role = await _role_for_room(room_id, conn["user_id"])
    if role is None:
        await sio.emit("error", {"message": "Not authorized for this room"}, to=sid)
        return

    existing_in_room = _roster(room_id)
    conn["room_id"] = room_id
    conn["role"] = role
    conn["role_checked_at"] = time.monotonic()
    await sio.enter_room(sid, room_id)

    if existing_in_room:
        await sio.emit("new-user", sid, room=room_id, skip_sid=sid)
    else:
        await sio.emit("first-in-room", to=sid)

    await sio.emit("room-user-change", _roster(room_id), room=room_id)


@sio.on("server-broadcast")
async def server_broadcast(sid, room_id, payload, iv=None):
    conn = _connections.get(sid)
    if not conn or conn["room_id"] != room_id:
        return
    if not _may_broadcast(await _current_role(conn), payload):
        return
    await sio.emit("client-broadcast", payload, room=room_id, skip_sid=sid)


@sio.on("server-volatile-broadcast")
async def server_volatile_broadcast(sid, room_id, payload, iv=None):
    conn = _connections.get(sid)
    if not conn or conn["room_id"] != room_id:
        return
    if not _may_broadcast(await _current_role(conn), payload):
        return
    await sio.emit("client-broadcast", payload, room=room_id, skip_sid=sid)


@sio.on("user-follow")
async def user_follow(sid, payload):
    # without room=, this fanned out to every connected client on the server —
    # i.e. across every customer — rather than to the sender's own room.
    conn = _connections.get(sid)
    if not conn or not conn["room_id"]:
        return
    await sio.emit(
        "user-follow-room-change", payload, room=conn["room_id"], skip_sid=sid
    )
