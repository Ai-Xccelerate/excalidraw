"""Everything behind the app's Settings page: profile, preferences, and the
MCP connections the user has authorized.

Password changes stay in auth_routes — they belong with the rest of the
credential handling.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import AuthContext, get_current_context
from db import get_db
from diagrams import merged_defaults
from models import OAuthClient, OAuthToken, User, UserSettings
from oauth import PUBLIC_API_URL, now

router = APIRouter(prefix="/api/settings", tags=["settings"])

NOTIFICATION_DEFAULTS = {
    "product_updates": True,
    "collaboration_invites": True,
    "comment_mentions": True,
    "weekly_digest": False,
    "security_alerts": True,
}

# what a preference may be set to; anything outside this is rejected rather
# than stored, so the editor never has to defend against junk on load
EDITOR_CHOICES = {
    "font_family": ["hand-drawn", "normal", "code"],
    "fill_style": ["hachure", "cross-hatch", "solid"],
    "stroke_style": ["solid", "dashed", "dotted"],
    "edges": ["sharp", "round"],
    "arrow_type": ["sharp", "round", "elbow"],
    "node_shape": ["rectangle", "ellipse", "diamond"],
}
EDITOR_RANGES = {
    "font_size": (8, 96),
    "stroke_width": (1, 8),
    "roughness": (0, 2),
}
COLOR_KEYS = ("stroke_color", "background_color")


class SettingsOut(BaseModel):
    email: str
    username: str | None
    email_verified: bool
    notifications: dict
    editor_defaults: dict
    mcp_endpoint: str


class ProfileUpdate(BaseModel):
    username: str | None = Field(default=None, max_length=80)


class NotificationsUpdate(BaseModel):
    notifications: dict


class EditorDefaultsUpdate(BaseModel):
    editor_defaults: dict


def _settings_row(db: Session, user_id: str) -> UserSettings:
    row = db.get(UserSettings, user_id)
    if row is None:
        row = UserSettings(user_id=user_id, notifications={}, editor_defaults={})
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _out(user: User, row: UserSettings) -> SettingsOut:
    return SettingsOut(
        email=user.email,
        username=user.username,
        email_verified=user.email_verified_at is not None,
        notifications={**NOTIFICATION_DEFAULTS, **(row.notifications or {})},
        editor_defaults=merged_defaults(row.editor_defaults),
        mcp_endpoint=f"{PUBLIC_API_URL}/mcp",
    )


def _load(db: Session, ctx: AuthContext) -> tuple[User, UserSettings]:
    user = db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(401, "Session is no longer valid")
    return user, _settings_row(db, ctx.user_id)


@router.get("", response_model=SettingsOut)
async def read_settings(
    ctx: AuthContext = Depends(get_current_context), db: Session = Depends(get_db)
):
    user, row = _load(db, ctx)
    return _out(user, row)


@router.patch("/profile", response_model=SettingsOut)
async def update_profile(
    body: ProfileUpdate,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    user, row = _load(db, ctx)
    if body.username is not None:
        username = body.username.strip()
        # the email stays the account's identity; changing it would need a
        # re-verification round trip, so it isn't editable here
        user.username = username or None
    db.commit()
    return _out(user, row)


@router.patch("/notifications", response_model=SettingsOut)
async def update_notifications(
    body: NotificationsUpdate,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    user, row = _load(db, ctx)
    updated = dict(row.notifications or {})
    for key, value in body.notifications.items():
        if key in NOTIFICATION_DEFAULTS:
            updated[key] = bool(value)
    row.notifications = updated
    db.commit()
    return _out(user, row)


@router.patch("/editor-defaults", response_model=SettingsOut)
async def update_editor_defaults(
    body: EditorDefaultsUpdate,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    user, row = _load(db, ctx)
    updated = dict(row.editor_defaults or {})

    for key, value in body.editor_defaults.items():
        if key in EDITOR_CHOICES:
            if value not in EDITOR_CHOICES[key]:
                raise HTTPException(422, f"{value!r} is not a valid {key}")
            updated[key] = value
        elif key in EDITOR_RANGES:
            low, high = EDITOR_RANGES[key]
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise HTTPException(422, f"{key} must be a number") from None
            if not low <= number <= high:
                raise HTTPException(422, f"{key} must be between {low} and {high}")
            updated[key] = int(number)
        elif key in COLOR_KEYS:
            text = str(value)
            if text != "transparent" and not _is_hex_color(text):
                raise HTTPException(422, f"{key} must be a hex color or 'transparent'")
            updated[key] = text

    row.editor_defaults = updated
    db.commit()
    return _out(user, row)


def _is_hex_color(value: str) -> bool:
    return (
        value.startswith("#")
        and len(value) in (4, 7)
        and all(c in "0123456789abcdefABCDEF" for c in value[1:])
    )


# ------------------------------------------------------------ MCP connections

class ConnectionOut(BaseModel):
    client_id: str
    client_name: str
    client_uri: str | None
    scope: str
    connected_at: str
    last_used_at: str | None
    expires_at: str


@router.get("/connections", response_model=list[ConnectionOut])
async def list_connections(
    ctx: AuthContext = Depends(get_current_context), db: Session = Depends(get_db)
):
    """Live MCP tokens, newest first — one row per authorization the user has
    granted to an agent."""
    rows = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == ctx.user_id, OAuthToken.revoked_at.is_(None))
        .order_by(OAuthToken.created_at.desc())
        .all()
    )
    out: list[ConnectionOut] = []
    seen: set[str] = set()
    for row in rows:
        if row.client_id in seen:
            continue
        seen.add(row.client_id)
        client = db.get(OAuthClient, row.client_id)
        out.append(
            ConnectionOut(
                client_id=row.client_id,
                client_name=client.client_name if client else "Unknown client",
                client_uri=client.client_uri if client else None,
                scope=row.scope,
                connected_at=row.created_at.isoformat(),
                last_used_at=row.last_used_at.isoformat() if row.last_used_at else None,
                expires_at=row.expires_at.isoformat(),
            )
        )
    return out


@router.delete("/connections/{client_id}")
async def revoke_connection(
    client_id: str,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    """Revokes every token this client holds for this account, so disconnecting
    in the UI actually cuts access rather than waiting for expiry."""
    rows = (
        db.query(OAuthToken)
        .filter(
            OAuthToken.user_id == ctx.user_id,
            OAuthToken.client_id == client_id,
            OAuthToken.revoked_at.is_(None),
        )
        .all()
    )
    for row in rows:
        row.revoked_at = now()
    db.commit()
    return {"ok": True, "revoked": len(rows)}
