import uuid

from sqlalchemy.orm import Session

from models import Workspace, WorkspaceMember


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
