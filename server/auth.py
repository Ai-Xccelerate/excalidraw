import hashlib
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from db import get_db
from models import (
    EmailVerificationToken,
    PasswordResetToken,
    PendingInvite,
    RoomMember,
    User,
    WorkspaceMember,
    WorkspacePendingInvite,
)

# Signing key for our own sessions. Refuse to boot without it rather than fall
# back to a default, which would let anyone mint a valid token for any user.
AUTH_SECRET = os.environ["AUTH_SECRET"]
if len(AUTH_SECRET) < 32:
    raise RuntimeError("AUTH_SECRET must be at least 32 characters")

TOKEN_TTL = timedelta(days=int(os.environ.get("AUTH_TOKEN_TTL_DAYS", "30")))
RESET_TTL = timedelta(hours=1)
VERIFY_TTL = timedelta(hours=24)
_ALGO = "HS256"

# bcrypt silently truncates at 72 bytes, so a longer password would make every
# suffix equivalent. Reject instead of quietly accepting a weaker secret.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


@dataclass
class AuthContext:
    user_id: str
    workspace_id: uuid.UUID | None  # active workspace from the X-Workspace-Id header


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(422, f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        raise HTTPException(422, "Password is too long (max 72 bytes)")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:MAX_PASSWORD_BYTES], password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user_id, "iat": now, "exp": now + TOKEN_TTL}, AUTH_SECRET, algorithm=_ALGO
    )


def _decode(token: str) -> dict:
    return jwt.decode(token, AUTH_SECRET, algorithms=[_ALGO])


def _extract_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[len("Bearer ") :]


# ---------------------------------------------------------------- reset tokens

def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_reset_token(db: Session, user: User) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            token_hash=hash_reset_token(raw),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + RESET_TTL,
        )
    )
    db.commit()
    return raw


def consume_reset_token(db: Session, raw: str) -> User | None:
    row = db.get(PasswordResetToken, hash_reset_token(raw))
    if row is None or row.used_at is not None:
        return None
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    row.used_at = datetime.now(timezone.utc)
    return db.get(User, row.user_id)


# --------------------------------------------------------- verification tokens

def invalidate_verification_tokens(db: Session, user: User) -> None:
    """Burns every outstanding verification link for this account."""
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user.id,
        EmailVerificationToken.used_at.is_(None),
    ).delete()
    db.commit()


def issue_verification_token(db: Session, user: User) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(
        EmailVerificationToken(
            token_hash=hash_reset_token(raw),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + VERIFY_TTL,
        )
    )
    db.commit()
    return raw


def consume_verification_token(db: Session, raw: str) -> User | None:
    row = db.get(EmailVerificationToken, hash_reset_token(raw))
    if row is None or row.used_at is not None:
        return None
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    row.used_at = datetime.now(timezone.utc)
    return db.get(User, row.user_id)


# ------------------------------------------------------------- invite claiming

def claim_pending_invites(db: Session, user: User) -> None:
    """Turns invites addressed to this email into real memberships.

    Gated on a verified address: matching on the email string alone would let
    anyone who guesses an invited address register it and inherit that
    workspace's drawings without ever proving they control the inbox."""
    if user.email_verified_at is None:
        return
    email = normalize_email(user.email)

    for invite in db.query(PendingInvite).filter(PendingInvite.email == email).all():
        existing = (
            db.query(RoomMember)
            .filter(RoomMember.drawing_id == invite.drawing_id, RoomMember.user_id == user.id)
            .first()
        )
        if not existing:
            db.add(RoomMember(drawing_id=invite.drawing_id, user_id=user.id, role=invite.role))
        db.delete(invite)

    for invite in (
        db.query(WorkspacePendingInvite).filter(WorkspacePendingInvite.email == email).all()
    ):
        existing = (
            db.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == invite.workspace_id,
                WorkspaceMember.user_id == user.id,
            )
            .first()
        )
        if not existing:
            db.add(
                WorkspaceMember(
                    workspace_id=invite.workspace_id, user_id=user.id, role=invite.role
                )
            )
        db.delete(invite)

    db.commit()


# ---------------------------------------------------------------- dependencies

def _user_id_from_token(token: str) -> str:
    try:
        return _decode(token)["sub"]
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc


async def get_current_user_id(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> str:
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    user_id = _user_id_from_token(token)
    # a token outliving its user (deleted account) must not authorise anything
    if not db.get(User, user_id):
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user_id


async def get_current_user_id_optional(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> str | None:
    token = _extract_token(authorization)
    if not token:
        return None
    try:
        user_id = _decode(token)["sub"]
    except jwt.PyJWTError:
        return None
    return user_id if db.get(User, user_id) else None


async def get_current_context(
    authorization: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthContext:
    user_id = await get_current_user_id(authorization=authorization, db=db)
    workspace_id: uuid.UUID | None = None
    if x_workspace_id:
        try:
            candidate = uuid.UUID(x_workspace_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid X-Workspace-Id") from None
        # only honour it if they're actually a member, so the header can't be
        # used to file drawings into someone else's workspace
        if candidate in get_user_workspace_ids(db, user_id):
            workspace_id = candidate
    return AuthContext(user_id=user_id, workspace_id=workspace_id)


def get_user_workspace_ids(db: Session, user_id: str) -> set[uuid.UUID]:
    rows = (
        db.query(WorkspaceMember.workspace_id)
        .filter(WorkspaceMember.user_id == user_id)
        .all()
    )
    return {r[0] for r in rows}


async def verify_socket_token(token: str | None, db: Session) -> str | None:
    if not token:
        return None
    try:
        user_id = _decode(token)["sub"]
    except jwt.PyJWTError:
        return None
    return user_id if db.get(User, user_id) else None
