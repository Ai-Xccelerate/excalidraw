"""Trash lifecycle for drawings, end to end over the API.

    cd server && DATABASE_URL=postgresql://localhost/aixdraw_trash_test \
      AUTH_SECRET=<32+ chars> python tests/test_trash.py

Covers what has to hold for a delete to be recoverable: a deleted drawing
leaves the dashboard but keeps its elements, stays out of every read path
(open, save, and the collab socket), comes back whole on restore, purges on demand,
and ages out of the Trash on its own after the retention window.
"""
import asyncio, os, pathlib, sys, uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", f"postgresql://{os.environ['USER']}@localhost:5432/aixdraw_trash_test")
os.environ.setdefault("AUTH_SECRET", "0123456789012345678901234567890123456789")

from fastapi.testclient import TestClient

import main
import sockets
from auth import create_access_token, hash_password
from db import SessionLocal
from models import Drawing, User
from services import TRASH_RETENTION_DAYS, purge_expired_trash

client = TestClient(main.app)
db = SessionLocal()

user = User(email=f"trash-{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("supersecret1"))
user.email_verified_at = datetime.now(timezone.utc)
other = User(email=f"other-{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("supersecret1"))
other.email_verified_at = datetime.now(timezone.utc)
db.add_all([user, other]); db.commit(); db.refresh(user); db.refresh(other)

H = {"Authorization": f"Bearer {create_access_token(user)}"}
H_OTHER = {"Authorization": f"Bearer {create_access_token(other)}"}

ELEMENTS = [{"id": "a1", "type": "rectangle", "version": 3}]

def check(label, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {label}")
    if not cond:
        sys.exit(1)

# ---------------------------------------------------------------- soft delete
r = client.post("/api/drawings", headers=H, json={"title": "Keeper"})
drawing_id = r.json()["id"]
client.put(f"/api/drawings/{drawing_id}", headers=H, json={
    "elements": ELEMENTS, "app_state": {}, "files": {}, "scene_version": 3, "title": "Keeper"})

check("delete answers ok", client.delete(f"/api/drawings/{drawing_id}", headers=H).status_code == 200)
check("gone from the dashboard",
      drawing_id not in [d["id"] for d in client.get("/api/drawings", headers=H).json()])
check("can't be opened while trashed",
      client.get(f"/api/drawings/{drawing_id}", headers=H).status_code == 404)
check("can't be written while trashed",
      client.put(f"/api/drawings/{drawing_id}", headers=H, json={
          "elements": [], "app_state": {}, "files": {}, "scene_version": 9}).status_code == 404)

trash = client.get("/api/drawings/trash", headers=H).json()
check("listed in the Trash", [d["id"] for d in trash] == [drawing_id])
check("carries a purge date", trash[0]["purges_at"] is not None)
check("row still holds the elements",
      db.get(Drawing, uuid.UUID(drawing_id)).elements == ELEMENTS)
check("a collaborator's room link stops working",
      asyncio.run(sockets._role_for_room(drawing_id, user.id)) is None)

# ------------------------------------------------------------------- tenancy
check("someone else can't see it in their Trash",
      client.get("/api/drawings/trash", headers=H_OTHER).json() == [])
check("someone else can't restore it",
      client.post(f"/api/drawings/{drawing_id}/restore", headers=H_OTHER).status_code in (403, 404))
check("someone else can't purge it",
      client.delete(f"/api/drawings/{drawing_id}/purge", headers=H_OTHER).status_code in (403, 404))

# ------------------------------------------------------------------- restore
check("restore answers ok", client.post(f"/api/drawings/{drawing_id}/restore", headers=H).status_code == 200)
restored = client.get(f"/api/drawings/{drawing_id}", headers=H)
check("opens again after restore", restored.status_code == 200)
check("comes back whole", restored.json()["elements"] == ELEMENTS)
check("back on the dashboard",
      drawing_id in [d["id"] for d in client.get("/api/drawings", headers=H).json()])
check("Trash is empty again", client.get("/api/drawings/trash", headers=H).json() == [])

# --------------------------------------------------------------------- purge
check("a live drawing can't be purged",
      client.delete(f"/api/drawings/{drawing_id}/purge", headers=H).status_code == 400)
client.delete(f"/api/drawings/{drawing_id}", headers=H)
check("purge answers ok", client.delete(f"/api/drawings/{drawing_id}/purge", headers=H).status_code == 200)
db.expire_all()
check("row is really gone", db.get(Drawing, uuid.UUID(drawing_id)) is None)

# --------------------------------------------------------------- empty trash
ids = []
for i in range(3):
    d = client.post("/api/drawings", headers=H, json={"title": f"Doomed {i}"}).json()["id"]
    client.delete(f"/api/drawings/{d}", headers=H)
    ids.append(d)
check("three in the Trash", len(client.get("/api/drawings/trash", headers=H).json()) == 3)
check("empty purges all three", client.delete("/api/drawings/trash", headers=H).json()["purged"] == 3)
check("Trash is empty", client.get("/api/drawings/trash", headers=H).json() == [])
db.expire_all()
check("all three rows gone", all(db.get(Drawing, uuid.UUID(i)) is None for i in ids))

# ------------------------------------------------------- automatic expiry
fresh = client.post("/api/drawings", headers=H, json={"title": "Fresh"}).json()["id"]
stale = client.post("/api/drawings", headers=H, json={"title": "Stale"}).json()["id"]
client.delete(f"/api/drawings/{fresh}", headers=H)
client.delete(f"/api/drawings/{stale}", headers=H)
row = db.get(Drawing, uuid.UUID(stale))
db.expire_all()
row = db.get(Drawing, uuid.UUID(stale))
row.deleted_at = datetime.now(timezone.utc) - timedelta(days=TRASH_RETENTION_DAYS + 1)
db.commit()
check("sweep takes only the expired one", purge_expired_trash(db) == 1)
db.expire_all()
check("expired row gone", db.get(Drawing, uuid.UUID(stale)) is None)
check("recent one survives", db.get(Drawing, uuid.UUID(fresh)) is not None)
check("listing the Trash also sweeps",
      [d["id"] for d in client.get("/api/drawings/trash", headers=H).json()] == [fresh])

client.delete("/api/drawings/trash", headers=H)
db.query(User).filter(User.id.in_([user.id, other.id])).delete(synchronize_session=False)
db.commit()
print("\nall trash checks passed")
