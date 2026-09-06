import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, load_only

from auth import AuthContext, get_current_context, get_user_workspace_ids
from db import get_db
from models import Collection, Drawing, PendingInvite, RoomMember, User
from services import ensure_personal_workspace

router = APIRouter(prefix="/api/drawings", tags=["drawings"])


class DrawingSummary(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: str
    role: str
    thumbnail: str | None = None
    workspace_id: uuid.UUID | None = None
    collection_id: uuid.UUID | None = None

    class Config:
        from_attributes = True


class DrawingCreate(BaseModel):
    title: str = "Untitled"
    collection_id: uuid.UUID | None = None


class DrawingSave(BaseModel):
    title: str | None = None
    elements: list
    app_state: dict = {}
    files: dict = {}
    scene_version: int
    thumbnail: str | None = None


class DrawingUpdate(BaseModel):
    title: str | None = None
    collection_id: uuid.UUID | None = None


class DrawingOut(BaseModel):
    id: uuid.UUID
    title: str
    elements: list
    app_state: dict
    files: dict
    scene_version: int
    is_room_active: bool
    role: str
    workspace_id: uuid.UUID | None = None
    collection_id: uuid.UUID | None = None

    class Config:
        from_attributes = True


class MemberInvite(BaseModel):
    email: str
    role: str = "editor"


class MemberOut(BaseModel):
    user_id: str | None = None
    email: str
    role: str
    pending: bool


def _out(drawing: Drawing, role: str) -> DrawingOut:
    return DrawingOut(
        id=drawing.id,
        title=drawing.title,
        elements=drawing.elements,
        app_state=drawing.app_state,
        files=drawing.files,
        scene_version=drawing.scene_version,
        is_room_active=drawing.is_room_active,
        role=role,
        workspace_id=drawing.workspace_id,
        collection_id=drawing.collection_id,
    )


def _summary(drawing: Drawing, role: str) -> DrawingSummary:
    return DrawingSummary(
        id=drawing.id,
        title=drawing.title,
        updated_at=drawing.updated_at.isoformat(),
        role=role,
        thumbnail=drawing.thumbnail,
        workspace_id=drawing.workspace_id,
        collection_id=drawing.collection_id,
    )


async def _accessible_workspace_ids(db: Session, user_id: str) -> set[uuid.UUID]:
    return get_user_workspace_ids(db, user_id)


def _role_for(drawing: Drawing, user_id: str, workspace_ids: set[uuid.UUID]) -> str | None:
    if drawing.owner_id == user_id:
        return "owner"
    for m in drawing.members:
        if m.user_id == user_id:
            return m.role
    if drawing.workspace_id is not None and drawing.workspace_id in workspace_ids:
        return "editor"
    return None


def _assert_collection_writable(
    db: Session, ctx: AuthContext, collection_id: uuid.UUID | None
) -> None:
    """A collection id arrives straight from the client, so it has to be
    checked: without this, knowing another tenant's collection UUID was enough
    to file a drawing into their folder."""
    if collection_id is None:
        return
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    if collection.workspace_id is not None:
        if collection.workspace_id not in get_user_workspace_ids(db, ctx.user_id):
            raise HTTPException(status_code=403, detail="Not your collection")
    elif collection.owner_id != ctx.user_id:
        raise HTTPException(status_code=403, detail="Not your collection")


async def _get_drawing_or_404(
    db: Session, drawing_id: uuid.UUID, user_id: str
) -> tuple[Drawing, str]:
    drawing = db.get(Drawing, drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")
    ws_ids = await _accessible_workspace_ids(db, user_id)
    role = _role_for(drawing, user_id, ws_ids)
    if role is None:
        raise HTTPException(status_code=403, detail="Not a member of this drawing")
    return drawing, role


# summary cards never need the heavy JSONB blobs (elements/app_state/files),
# so load only the columns we serialize — critical now that the workspace query
# can pull in every team drawing (each with inline base64 images in `files`).
_SUMMARY_COLS = load_only(
    Drawing.id,
    Drawing.title,
    Drawing.updated_at,
    Drawing.thumbnail,
    Drawing.workspace_id,
    Drawing.collection_id,
    Drawing.owner_id,
)


@router.get("", response_model=list[DrawingSummary])
async def list_drawings(
    ctx: AuthContext = Depends(get_current_context), db: Session = Depends(get_db)
):
    user_id = ctx.user_id
    ws_ids = await _accessible_workspace_ids(db, user_id)

    shared_roles = {
        m.drawing_id: m.role
        for m in db.query(RoomMember).filter(RoomMember.user_id == user_id).all()
    }

    by_id: dict[uuid.UUID, Drawing] = {}
    for d in (
        db.query(Drawing).options(_SUMMARY_COLS).filter(Drawing.owner_id == user_id).all()
    ):
        by_id[d.id] = d
    if shared_roles:
        for d in (
            db.query(Drawing)
            .options(_SUMMARY_COLS)
            .filter(Drawing.id.in_(list(shared_roles)))
            .all()
        ):
            by_id[d.id] = d
    if ws_ids:
        for d in (
            db.query(Drawing)
            .options(_SUMMARY_COLS)
            .filter(Drawing.workspace_id.in_(ws_ids))
            .all()
        ):
            by_id[d.id] = d

    def role(d: Drawing) -> str:
        if d.owner_id == user_id:
            return "owner"
        if d.id in shared_roles:
            return shared_roles[d.id]
        return "editor"  # workspace member

    return [_summary(d, role(d)) for d in by_id.values()]


@router.post("", response_model=DrawingOut)
async def create_drawing(
    body: DrawingCreate,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    workspace_id = ctx.workspace_id
    _assert_collection_writable(db, ctx, body.collection_id)
    drawing = Drawing(
        owner_id=ctx.user_id,
        workspace_id=workspace_id,
        collection_id=body.collection_id,
        title=body.title,
        elements=[],
        app_state={},
        files={},
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return _out(drawing, "owner")


@router.get("/{drawing_id}", response_model=DrawingOut)
async def get_drawing(
    drawing_id: uuid.UUID,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    drawing, role = await _get_drawing_or_404(db, drawing_id, ctx.user_id)
    return _out(drawing, role)


@router.put("/{drawing_id}", response_model=DrawingOut)
async def save_drawing(
    drawing_id: uuid.UUID,
    body: DrawingSave,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    drawing, role = await _get_drawing_or_404(db, drawing_id, ctx.user_id)
    if role not in ("owner", "editor"):
        raise HTTPException(status_code=403, detail="Read-only access")
    if body.title is not None:
        drawing.title = body.title
    if body.thumbnail is not None:
        drawing.thumbnail = body.thumbnail
    drawing.elements = body.elements
    drawing.app_state = body.app_state
    drawing.files = {**drawing.files, **body.files}
    # server-assigned and monotonic. `body.scene_version` is a *sum* of element
    # versions, which drops whenever an element leaves the syncable set — most
    # commonly when a deleted element's tombstone ages out after 24h. Comparing
    # it against the stored value rejected perfectly good writes (returning 200
    # with the old row, so the client never noticed) and silently lost the
    # session's work on the next reload. It also failed at the one job it had:
    # a foreign scene's larger sum sailed straight past the guard.
    drawing.scene_version = drawing.scene_version + 1
    db.commit()
    db.refresh(drawing)
    return _out(drawing, role)


@router.delete("/{drawing_id}")
async def delete_drawing(
    drawing_id: uuid.UUID,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    drawing, role = await _get_drawing_or_404(db, drawing_id, ctx.user_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can delete")
    db.delete(drawing)
    db.commit()
    return {"ok": True}


@router.patch("/{drawing_id}", response_model=DrawingSummary)
async def update_drawing(
    drawing_id: uuid.UUID,
    body: DrawingUpdate,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    drawing, role = await _get_drawing_or_404(db, drawing_id, ctx.user_id)
    if role not in ("owner", "editor"):
        raise HTTPException(status_code=403, detail="Read-only access")
    fields = body.model_fields_set
    if "title" in fields and body.title is not None:
        drawing.title = body.title
    if "collection_id" in fields:
        _assert_collection_writable(db, ctx, body.collection_id)
        drawing.collection_id = body.collection_id
    db.commit()
    db.refresh(drawing)
    return _summary(drawing, role)


@router.get("/{drawing_id}/members", response_model=list[MemberOut])
async def list_members(
    drawing_id: uuid.UUID,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    drawing, _role = await _get_drawing_or_404(db, drawing_id, ctx.user_id)
    owner = db.get(User, drawing.owner_id)
    result = [
        MemberOut(user_id=owner.id, email=owner.email or "", role="owner", pending=False)
    ]
    for m in drawing.members:
        user = db.get(User, m.user_id)
        result.append(
            MemberOut(user_id=user.id, email=user.email or "", role=m.role, pending=False)
        )
    for p in drawing.pending_invites:
        result.append(MemberOut(user_id=None, email=p.email, role=p.role, pending=True))
    return result


@router.post("/{drawing_id}/members")
async def invite_member(
    drawing_id: uuid.UUID,
    body: MemberInvite,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    drawing, role = await _get_drawing_or_404(db, drawing_id, ctx.user_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can invite")

    email = body.email.strip().lower()
    invitee = db.query(User).filter(User.email == email).first()

    # same rule as workspace invites: an unverified account is not proof of
    # address ownership, so the invite waits in pending_invites instead
    if invitee is not None and invitee.email_verified_at is None:
        invitee = None

    if invitee:
        existing = (
            db.query(RoomMember)
            .filter(RoomMember.drawing_id == drawing_id, RoomMember.user_id == invitee.id)
            .first()
        )
        if existing:
            existing.role = body.role
        else:
            db.add(RoomMember(drawing_id=drawing_id, user_id=invitee.id, role=body.role))
        drawing.is_room_active = True
        db.commit()
        return {"ok": True, "pending": False}

    # no account yet: record a pending invite, auto-applied on their first sign-in
    existing_pending = (
        db.query(PendingInvite)
        .filter(PendingInvite.drawing_id == drawing_id, PendingInvite.email == email)
        .first()
    )
    if existing_pending:
        existing_pending.role = body.role
    else:
        db.add(PendingInvite(drawing_id=drawing_id, email=email, role=body.role))
    drawing.is_room_active = True
    db.commit()
    return {"ok": True, "pending": True}


@router.delete("/{drawing_id}/members/{member_user_id}")
async def remove_member(
    drawing_id: uuid.UUID,
    member_user_id: str,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    drawing, role = await _get_drawing_or_404(db, drawing_id, ctx.user_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can remove members")
    db.query(RoomMember).filter(
        RoomMember.drawing_id == drawing_id, RoomMember.user_id == member_user_id
    ).delete()
    db.commit()
    return {"ok": True}


@router.delete("/{drawing_id}/pending-invites/{email}")
async def remove_pending_invite(
    drawing_id: uuid.UUID,
    email: str,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    drawing, role = await _get_drawing_or_404(db, drawing_id, ctx.user_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can remove invites")
    db.query(PendingInvite).filter(
        PendingInvite.drawing_id == drawing_id, PendingInvite.email == email.strip().lower()
    ).delete()
    db.commit()
    return {"ok": True}
