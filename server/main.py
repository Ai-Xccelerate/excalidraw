import logging
import os

import socketio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from db import Base, engine
import models  # noqa: F401  (ensures models are registered before create_all)
from routers import (
    ai_routes,
    auth_routes,
    collections,
    drawings,
    mcp_routes,
    oauth_routes,
    settings_routes,
    shared_scenes,
)
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
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0",
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
    # MCP clients read the auth challenge off a 401 to find the authorization
    # server; without this the browser hides the header from them
    expose_headers=["WWW-Authenticate", "MCP-Protocol-Version"],
)

@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """A crash has to come back as a response, not a dropped connection.

    Starlette's default handler re-raises, which skips the CORS middleware —
    so the browser reports "Failed to fetch" and the real error is invisible to
    whoever is using the app. Answering here keeps the CORS headers on and
    gives the client something it can show."""
    logging.getLogger(__name__).exception(
        "unhandled error on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "statusCode": 500,
            "message": "Something went wrong on our side. It has been logged.",
        },
    )


app.include_router(auth_routes.router)
app.include_router(ai_routes.router)
app.include_router(drawings.router)
app.include_router(collections.router)
app.include_router(shared_scenes.router)
app.include_router(settings_routes.router)
app.include_router(oauth_routes.router)
app.include_router(mcp_routes.router)
# Invites for addresses without an account yet are claimed at signup/login
# (see auth.claim_pending_invites) rather than by an identity-provider webhook.


@app.get("/health")
def health():
    return {"ok": True}


asgi_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/socket.io")
