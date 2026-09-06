from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.workspace.jobs import WorkspaceError, lock_owner, owner_scope
from app.workspace.models import WorkspaceDataJob
from app.workspace.protocol import DataRequest, content_hash


def view(row: WorkspaceDataJob) -> dict:
    return {"job_id": row.job_id, "task": row.request_json["task"], "codes": row.request_json.get("codes", []), "status": row.status, "created_at": row.created_at.isoformat(), "started_at": row.started_at.isoformat() if row.started_at else None, "finished_at": row.finished_at.isoformat() if row.finished_at else None, "result": row.result_json, "failure_reason": row.failure_reason}


def enqueue(db: Session, payload: DataRequest, user_id: int | None) -> tuple[WorkspaceDataJob, bool]:
    scope = owner_scope(user_id)
    lock_owner(db, "workspace-data-queue")
    key = content_hash({"scope": scope, "key": payload.request_key})
    request = payload.model_dump(exclude={"request_key"})
    existing = db.scalar(select(WorkspaceDataJob).where(WorkspaceDataJob.idempotency_key == key))
    if existing:
        if existing.request_json != request:
            raise WorkspaceError(409, "data_idempotency_conflict")
        return existing, False
    count = db.scalar(select(func.count()).select_from(WorkspaceDataJob).where(WorkspaceDataJob.status.in_(("queued", "running")))) or 0
    if count >= 10:
        raise WorkspaceError(429, "data_queue_full")
    if payload.task == "onboard" and not payload.codes:
        raise WorkspaceError(422, "onboarding_requires_explicit_codes")
    row = WorkspaceDataJob(job_id=uuid4().hex, user_id=user_id, owner_scope=scope, idempotency_key=key, request_json=request)
    db.add(row)
    db.flush()
    return row, True


def claim(db: Session) -> str | None:
    lock_owner(db, "workspace-data-queue")
    now = datetime.now(UTC)
    db.execute(update(WorkspaceDataJob).where(WorkspaceDataJob.status == "running", WorkspaceDataJob.lease_until < now).values(status="failed", failure_reason="worker_lease_expired", finished_at=now))
    if db.scalar(select(WorkspaceDataJob.job_id).where(WorkspaceDataJob.status == "running").limit(1)):
        return None
    row = db.scalar(select(WorkspaceDataJob).where(WorkspaceDataJob.status == "queued").order_by(WorkspaceDataJob.created_at).with_for_update(skip_locked=True).limit(1))
    if row is None:
        return None
    changed = db.execute(update(WorkspaceDataJob).where(WorkspaceDataJob.job_id == row.job_id, WorkspaceDataJob.status == "queued").values(status="running", started_at=now, lease_until=now + timedelta(minutes=35)))
    return row.job_id if changed.rowcount == 1 else None
