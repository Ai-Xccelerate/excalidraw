import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import Drawing, Workspace, WorkspaceMember


def ensure_personal_workspace(db: Session, user_id: str, name: str = "My Workspace") -> Workspace:
    """Returns the user's own workspace, creating it on first use so a team
    workspace always exists to file drawings into."""
    workspace = (
        db.query(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(Workspace.owner_id == user_id, WorkspaceMember.user_id == user_id)
        .first()
    )
    if workspace:
        return workspace
    workspace = Workspace(id=uuid.uuid4(), owner_id=user_id, name=name)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user_id, role="admin"))
    db.commit()
    db.refresh(workspace)
    return workspace


TRASH_RETENTION_DAYS = 90


def purge_expired_trash(db: Session) -> int:
    """Deletes for real the drawings that have sat in Trash past the retention
    window. Returns how many went. Idempotent, so it is safe to run from more
    than one worker."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRASH_RETENTION_DAYS)
    expired = db.query(Drawing).filter(Drawing.deleted_at.isnot(None), Drawing.deleted_at < cutoff).all()
    for drawing in expired:
        db.delete(drawing)
    db.commit()
    return len(expired)
