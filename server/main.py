import logging
import os

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from db import Base, engine
import models  # noqa: F401  (ensures models are registered before create_all)
from routers import auth_routes, collections, drawings, shared_scenes
from sockets import sio

Base.metadata.create_all(bind=engine)


def _run_lightweight_migrations() -> None:
    """create_all() only creates new tables; it never adds columns to an
    existing one. These idempotent ALTERs bring a pre-existing database up to
    the current shape, including the Clerk -> local-auth change (no Alembic yet)."""
    statements = [
        # local auth replaces the mirrored Clerk record
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT",
        "ALTER TABLE users ALTER COLUMN email SET NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_unique ON users (email)",
        # workspaces are owned locally now, not backed by a Clerk org
        "ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS owner_id TEXT REFERENCES users(id)",
        "ALTER TABLE workspaces DROP COLUMN IF EXISTS clerk_org_id",
        "ALTER TABLE password_reset_tokens ALTER COLUMN expires_at TYPE TIMESTAMPTZ",
        "ALTER TABLE password_reset_tokens ALTER COLUMN used_at TYPE TIMESTAMPTZ",
        "ALTER TABLE drawings ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL",
        "ALTER TABLE drawings ADD COLUMN IF NOT EXISTS collection_id UUID REFERENCES collections(id) ON DELETE SET NULL",
        "ALTER TABLE drawings ADD COLUMN IF NOT EXISTS thumbnail TEXT",
        "CREATE INDEX IF NOT EXISTS ix_drawings_workspace_id ON drawings (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_drawings_collection_id ON drawings (collection_id)",
    ]
    # each in its own transaction: a statement that can't apply to legacy data
    # shouldn't abort the rest of the batch or stop the service from booting
    for stmt in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception:
            logging.getLogger(__name__).exception("migration skipped: %s", stmt)


_run_lightweight_migrations()

app = FastAPI(title="AIXDraw API")

CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
allow_origins = (
    ["*"] if CORS_ORIGIN == "*" else [o.strip() for o in CORS_ORIGIN.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(drawings.router)
app.include_router(collections.router)
app.include_router(shared_scenes.router)
# Invites for addresses without an account yet are claimed at signup/login
# (see auth.claim_pending_invites) rather than by an identity-provider webhook.


@app.get("/health")
def health():
    return {"ok": True}


asgi_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/socket.io")
