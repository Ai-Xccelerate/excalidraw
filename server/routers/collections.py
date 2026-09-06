import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import AuthContext, get_current_context, get_user_workspace_ids, normalize_email
from db import get_db
from models import Collection, User, Workspace, WorkspaceMember, WorkspacePendingInvite

router = APIRouter(prefix="/api", tags=["workspaces"])


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str = "member"

    class Config:
        from_attributes = True


class CollectionOut(BaseModel):
    id: uuid.UUID
    name: str
    workspace_id: uuid.UUID | None = None

    class Config:
        from_attributes = True


class CollectionCreate(BaseModel):
    name: str = "Untitled"
    workspace_id: uuid.UUID | None = None


class CollectionRename(BaseModel):
    name: str


class WorkspaceCreate(BaseModel):
    name: str = "Workspace"


class WorkspaceMemberInvite(BaseModel):
    email: str
    role: str = "member"


class WorkspaceMemberOut(BaseModel):
    user_id: str | None = None
    email: str
    role: str
    pending: bool


async def _assert_workspace_access(db: Session, user_id: str, workspace_id: uuid.UUID) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace_id not in get_user_workspace_ids(db, user_id):
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return workspace


@router.get("/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(
    ctx: AuthContext = Depends(get_current_context), db: Session = Depends(get_db)
):
    # No auto-created workspace: a solo account's drawings are personal, and
    # inventing a "My Workspace" alongside "Personal" only offered two names
    # for the same place. A workspace now exists when someone makes one to
    # share with a team.
    ws_ids = get_user_workspace_ids(db, ctx.user_id)
    roles = {
        m.workspace_id: m.role
        for m in db.query(WorkspaceMember).filter(WorkspaceMember.user_id == ctx.user_id).all()
    }
    return [
        WorkspaceOut(id=w.id, name=w.name, role=roles.get(w.id, "member"))
        for w in db.query(Workspace).filter(Workspace.id.in_(ws_ids)).all()
    ]


@router.get("/collections", response_model=list[CollectionOut])
async def list_collections(
    workspace_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    if workspace_id is not None:
        await _assert_workspace_access(db, ctx.user_id, workspace_id)
        return db.query(Collection).filter(Collection.workspace_id == workspace_id).all()
    return (
        db.query(Collection)
        .filter(Collection.workspace_id.is_(None), Collection.owner_id == ctx.user_id)
        .all()
    )


@router.post("/collections", response_model=CollectionOut)
async def create_collection(
    body: CollectionCreate,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    if body.workspace_id is not None:
        await _assert_workspace_access(db, ctx.user_id, body.workspace_id)
        collection = Collection(name=body.name, workspace_id=body.workspace_id)
    else:
        collection = Collection(name=body.name, owner_id=ctx.user_id)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


@router.patch("/collections/{collection_id}", response_model=CollectionOut)
async def rename_collection(
    collection_id: uuid.UUID,
    body: CollectionRename,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    collection = await _get_collection_or_404(db, ctx.user_id, collection_id)
    collection.name = body.name
    db.commit()
    db.refresh(collection)
    return collection


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: uuid.UUID,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    collection = await _get_collection_or_404(db, ctx.user_id, collection_id)
    db.delete(collection)
    db.commit()
    return {"ok": True}


async def _get_collection_or_404(
    db: Session, user_id: str, collection_id: uuid.UUID
) -> Collection:
    collection = db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    if collection.workspace_id is not None:
        await _assert_workspace_access(db, user_id, collection.workspace_id)
    elif collection.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Not your collection")
    return collection


def _assert_workspace_admin(db: Session, user_id: str, workspace_id: uuid.UUID) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    if member is None or member.role != "admin":
        raise HTTPException(status_code=403, detail="Only a workspace admin can do that")
    return workspace


@router.post("/workspaces", response_model=WorkspaceOut)
async def create_workspace(
    body: WorkspaceCreate,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    workspace = Workspace(id=uuid.uuid4(), owner_id=ctx.user_id, name=body.name.strip() or "Workspace")
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=ctx.user_id, role="admin"))
    db.commit()
    db.refresh(workspace)
    return WorkspaceOut(id=workspace.id, name=workspace.name, role="admin")


@router.get("/workspaces/{workspace_id}/members", response_model=list[WorkspaceMemberOut])
async def list_workspace_members(
    workspace_id: uuid.UUID,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    await _assert_workspace_access(db, ctx.user_id, workspace_id)
    result: list[WorkspaceMemberOut] = []
    for m in (
        db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).all()
    ):
        user = db.get(User, m.user_id)
        result.append(
            WorkspaceMemberOut(
                user_id=m.user_id, email=user.email if user else "", role=m.role, pending=False
            )
        )
    for p in (
        db.query(WorkspacePendingInvite)
        .filter(WorkspacePendingInvite.workspace_id == workspace_id)
        .all()
    ):
        result.append(
            WorkspaceMemberOut(user_id=None, email=p.email, role=p.role, pending=True)
        )
    return result


@router.post("/workspaces/{workspace_id}/members")
async def invite_workspace_member(
    workspace_id: uuid.UUID,
    body: WorkspaceMemberInvite,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    _assert_workspace_admin(db, ctx.user_id, workspace_id)
    role = body.role if body.role in ("admin", "member") else "member"
    email = normalize_email(body.email)
    invitee = db.query(User).filter(User.email == email).first()

    # An unverified account proves nothing about who owns the address, so it is
    # treated exactly like "no account yet": the invite stays pending until the
    # address is verified. Granting it here would let anyone who pre-registers a
    # colleague's email walk straight into the workspace.
    if invitee is not None and invitee.email_verified_at is None:
        invitee = None

    if invitee:
        existing = (
            db.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == invitee.id,
            )
            .first()
        )
        if existing:
            existing.role = role
        else:
            db.add(
                WorkspaceMember(workspace_id=workspace_id, user_id=invitee.id, role=role)
            )
        db.commit()
        return {"ok": True, "pending": False}

    existing_pending = (
        db.query(WorkspacePendingInvite)
        .filter(
            WorkspacePendingInvite.workspace_id == workspace_id,
            WorkspacePendingInvite.email == email,
        )
        .first()
    )
    if existing_pending:
        existing_pending.role = role
    else:
        db.add(
            WorkspacePendingInvite(workspace_id=workspace_id, email=email, role=role)
        )
    db.commit()
    return {"ok": True, "pending": True}


@router.delete("/workspaces/{workspace_id}/members/{member_user_id}")
async def remove_workspace_member(
    workspace_id: uuid.UUID,
    member_user_id: str,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    workspace = _assert_workspace_admin(db, ctx.user_id, workspace_id)
    if member_user_id == workspace.owner_id:
        raise HTTPException(status_code=400, detail="The workspace owner can't be removed")
    db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == member_user_id,
    ).delete()
    db.commit()
    return {"ok": True}
