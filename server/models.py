import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Boolean, Integer, JSON, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    # citext isn't enabled on the box, so addresses are normalised to lowercase
    # on the way in and every lookup goes through auth.normalize_email().
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str | None] = mapped_column(String)
    avatar_url: Mapped[str | None] = mapped_column(String)
    # until this is set, the account has not proven control of the address, so
    # invites addressed to that email must not convert into real access
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # bumped whenever the account's ownership changes hands (password set,
    # reset, or email verified). Tokens carry the value they were minted with,
    # so bumping it invalidates every session issued before that moment.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class EmailVerificationToken(Base):
    """Single-use email-ownership proof. Same hashed-at-rest shape as
    PasswordResetToken so a database leak can't be replayed."""

    __tablename__ = "email_verification_tokens"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Workspace(Base):
    """A team workspace. Membership lives in `workspace_members`; personal
    (non-team) drawings simply have workspace_id = NULL."""

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String, default="Workspace")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class WorkspaceMember(Base):
    """Replaces Clerk org membership. `admin` may invite and remove members."""

    __tablename__ = "workspace_members"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String, default="member")  # admin | member
    joined_at: Mapped[datetime] = mapped_column(default=_now)


class WorkspacePendingInvite(Base):
    """Workspace invite for an address with no account yet. Converted into a
    WorkspaceMember on that user's first sign-in (see auth.claim_pending_invites)."""

    __tablename__ = "workspace_pending_invites"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String, default="member")
    invited_at: Mapped[datetime] = mapped_column(default=_now)


class PasswordResetToken(Base):
    """Single-use reset token. Only the SHA-256 hash is stored, so a database
    leak can't be replayed against the reset endpoint."""

    __tablename__ = "password_reset_tokens"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # tz-aware on purpose: a naive column is written in the session's local
    # timezone, so reading it back as UTC makes every token look hours expired
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Collection(Base):
    """A folder for organizing drawings. Belongs to a workspace when shared with
    a team, or to a single user (owner_id) for a personal folder."""

    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=True
    )
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String, default="Untitled")
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Drawing(Base):
    __tablename__ = "drawings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), index=True, nullable=True
    )
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String, default="Untitled")
    elements: Mapped[list] = mapped_column(JSONB, default=list)
    app_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    files: Mapped[dict] = mapped_column(JSONB, default=dict)
    thumbnail: Mapped[str | None] = mapped_column(String, nullable=True)
    scene_version: Mapped[int] = mapped_column(Integer, default=0)
    is_room_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    members: Mapped[list["RoomMember"]] = relationship(
        back_populates="drawing", cascade="all, delete-orphan"
    )
    pending_invites: Mapped[list["PendingInvite"]] = relationship(
        back_populates="drawing", cascade="all, delete-orphan"
    )


class SharedScene(Base):
    """An anonymous, read-only "Export to Link" snapshot. The body is an
    end-to-end encrypted, compressed blob produced by the client; the decryption
    key never reaches us (it lives in the link's URL hash). No owner and no auth:
    anyone with the link can read it, which is the whole point of a share link."""

    __tablename__ = "shared_scenes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class RoomMember(Base):
    __tablename__ = "room_members"

    drawing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drawings.id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String, default="editor")  # owner | editor | viewer
    invited_at: Mapped[datetime] = mapped_column(default=_now)

    drawing: Mapped["Drawing"] = relationship(back_populates="members")


class PendingInvite(Base):
    """An invite by email for someone who hasn't signed up yet. Converted into
    a RoomMember automatically the first time they sign in (see auth._ensure_user_exists)."""

    __tablename__ = "pending_invites"

    drawing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drawings.id"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String, default="editor")
    invited_at: Mapped[datetime] = mapped_column(default=_now)

    drawing: Mapped["Drawing"] = relationship(back_populates="pending_invites")
