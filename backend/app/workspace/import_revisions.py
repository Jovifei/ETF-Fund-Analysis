"""An explicit new preview after undo/cancel; original records remain immutable."""
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import optional_current_user
from app.db.session import get_db
from app.models import AuthUser
from app.services.event_service import emit_event
from app.workspace import imports
from app.workspace.jobs import WorkspaceError, lock_owner, owner_scope
from app.workspace.models import WorkspaceImportBatch
from app.workspace.protocol import StrictModel, content_hash

router = APIRouter(prefix="/workspace")


class RevisionRequest(StrictModel):
    request_key: str = Field(pattern=r"^[a-f0-9]{32}$")


@router.post("/imports/{batch_id}/revision", status_code=201)
def new_revision(batch_id: str, payload: RevisionRequest,
                 db: Annotated[Session, Depends(get_db)],
                 user: Annotated[AuthUser | None, Depends(optional_current_user)]):
    uid, scope = (user.id if user else None), owner_scope(user.id if user else None)
    lock_owner(db, scope)
    original = imports.owned_batch(db, batch_id, scope)
    identity = content_hash({"origin_batch_id": batch_id, "origin_source_hash": original.source_hash, "revision_key": payload.request_key})
    existing = db.scalar(select(WorkspaceImportBatch).where(WorkspaceImportBatch.owner_scope == scope, WorkspaceImportBatch.source_hash == identity))
    if existing:
        return imports.view(existing)
    active = db.scalar(select(func.count()).select_from(WorkspaceImportBatch).where(WorkspaceImportBatch.owner_scope == scope, WorkspaceImportBatch.status == "preview", WorkspaceImportBatch.expires_at > datetime.now(UTC))) or 0
    if active >= 20:
        raise WorkspaceError(429, "cancel_unused_import_previews")
    candidates = [{key: row[key] for key in ("row_index", "ts_code", "shares", "cost_price", "selected")} for row in original.candidates_json]
    row = imports.preview_rows(db, candidates, identity, "revision", uid)
    emit_event(db, "holding_import.revision", {"user_id": uid, "source_batch_id": batch_id, "batch_id": row.batch_id})
    db.commit()
    return imports.view(row)
