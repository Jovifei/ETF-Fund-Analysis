"""Outbound-only local bridge API with revocable, owner-scoped device credentials.

A device may lease one research job and submit a hash-bound candidate. It cannot
approve reports, mutate holdings, run market tasks, or call legacy private APIs.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import LoginThrottle
from app.db.session import get_db
from app.models import AuthUser
from app.workspace.config import workspace_settings
from app.workspace.jobs import WorkspaceError, accept_result, job_view, owner_scope, utc
from app.workspace.models import WorkspaceBridgeDevice, WorkspaceResearchJob
from app.workspace.protocol import DeviceFailure, DeviceResult, Heartbeat, PairRequest, StrictModel

router = APIRouter(prefix="/api/bridge")
DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
_pair_throttle = LoginThrottle(max_entries=1024, max_failures=6, window_seconds=60)


def enabled(request: Request, settings: Settings) -> None:
    if not workspace_settings().bridge_enabled:
        raise HTTPException(503, "local_bridge_disabled")
    if settings.app_env == "production" and request.url.scheme != "https":
        raise HTTPException(400, "bridge_requires_https")


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def device_view(row: WorkspaceBridgeDevice) -> dict:
    return {"device_id": row.device_id, "label": row.label, "status": row.status, "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None, "heartbeat": row.heartbeat_json, "status_basis": "self_reported_not_model_qualification", "token_expires_at": row.token_expires_at.isoformat() if row.token_expires_at else None}


def new_pairing(db: Session, label: str, user_id: int | None) -> dict:
    scope = owner_scope(user_id)
    count = db.scalar(select(func.count()).select_from(WorkspaceBridgeDevice).where(WorkspaceBridgeDevice.owner_scope == scope, WorkspaceBridgeDevice.status.in_(("active", "pending")))) or 0
    if count >= 5:
        raise WorkspaceError(429, "revoke_unused_devices_before_pairing")
    code = secrets.token_urlsafe(24)
    row = WorkspaceBridgeDevice(device_id=uuid4().hex, user_id=user_id, owner_scope=scope, label=label, pairing_hash=secret_hash(code), pairing_expires_at=datetime.now(UTC) + timedelta(minutes=10))
    db.add(row)
    db.flush()
    return {"device": device_view(row), "pairing_code": code, "expires_in_seconds": 600, "note": "一次性配对码仅用于本地连接器；不是模型密钥。关闭此页面后不再显示。"}


@router.post("/pair")
def pair(payload: PairRequest, request: Request, db: DB, settings: Config) -> dict:
    enabled(request, settings)
    ip = request.client.host if request.client else "unknown"
    throttle_key = secret_hash(ip)
    if _pair_throttle.is_limited(throttle_key):
        raise HTTPException(429, "pairing_rate_limited")
    now = datetime.now(UTC)
    row = db.scalar(select(WorkspaceBridgeDevice).where(WorkspaceBridgeDevice.pairing_hash == secret_hash(payload.pairing_code), WorkspaceBridgeDevice.status == "pending", WorkspaceBridgeDevice.pairing_expires_at > now).with_for_update())
    if row is None:
        _pair_throttle.record_failure(throttle_key)
        raise HTTPException(401, "invalid_or_expired_pairing_code")
    if row.user_id is not None:
        user = db.get(AuthUser, row.user_id)
        if user is None or user.status != "active":
            raise HTTPException(401, "invalid_or_expired_pairing_code")
    elif settings.auth_enabled or settings.app_env == "production":
        raise HTTPException(401, "database_user_required")
    token = secrets.token_urlsafe(32)
    changed = db.execute(update(WorkspaceBridgeDevice).where(WorkspaceBridgeDevice.device_id == row.device_id, WorkspaceBridgeDevice.status == "pending").values(status="active", token_hash=secret_hash(token), token_expires_at=now + timedelta(days=30), pairing_hash=None, pairing_expires_at=None))
    if changed.rowcount != 1:
        raise HTTPException(409, "pairing_already_used")
    db.commit()
    _pair_throttle.record_success(throttle_key)
    return {"device_id": row.device_id, "device_token": token, "expires_in_days": 30, "scopes": ["research:claim", "research:submit", "device:heartbeat"]}


async def require_device(request: Request, db: DB, settings: Config) -> WorkspaceBridgeDevice:
    enabled(request, settings)
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,128}", token):
        raise HTTPException(401, "invalid_device_credential")
    now = datetime.now(UTC)
    row = db.scalar(select(WorkspaceBridgeDevice).where(WorkspaceBridgeDevice.token_hash == secret_hash(token), WorkspaceBridgeDevice.status == "active", WorkspaceBridgeDevice.token_expires_at > now))
    if row is None:
        raise HTTPException(401, "invalid_device_credential")
    if row.user_id is not None:
        user = db.get(AuthUser, row.user_id)
        if user is None or user.status != "active":
            raise HTTPException(401, "invalid_device_credential")
    elif settings.auth_enabled or settings.app_env == "production":
        raise HTTPException(401, "database_user_required")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        timestamp = request.headers.get("x-bridge-time", "")
        signature = request.headers.get("x-bridge-signature", "")
        try:
            valid_time = abs(time.time() - int(timestamp)) <= 300
        except ValueError:
            valid_time = False
        body_hash = hashlib.sha256(await request.body()).hexdigest()
        message = f"{request.method}\n{request.url.path}\n{timestamp}\n{body_hash}".encode()
        expected = hmac.new(token.encode(), message, hashlib.sha256).hexdigest()
        if not valid_time or not hmac.compare_digest(expected, signature):
            raise HTTPException(401, "invalid_device_signature")
    return row


Device = Annotated[WorkspaceBridgeDevice, Depends(require_device)]


class LeaseRequest(StrictModel):
    claim_id: str = Field(pattern=r"^[a-f0-9]{32}$")


@router.post("/heartbeat")
def heartbeat(payload: Heartbeat, db: DB, device: Device) -> dict:
    device.last_seen_at, device.heartbeat_json = datetime.now(UTC), payload.model_dump()
    db.commit()
    return device_view(device)


@router.post("/claim")
def claim(payload: LeaseRequest, db: DB, device: Device) -> dict:
    now = datetime.now(UTC)
    existing = db.scalar(select(WorkspaceResearchJob).where(WorkspaceResearchJob.lease_device_id == device.device_id, WorkspaceResearchJob.lease_id == payload.claim_id))
    if existing:
        if existing.status != "running" or existing.lease_until is None or utc(existing.lease_until) <= now:
            raise HTTPException(409, "claim_already_closed")
        return _lease_view(existing)
    db.execute(update(WorkspaceResearchJob).where(WorkspaceResearchJob.owner_scope == device.owner_scope, WorkspaceResearchJob.status == "running", WorkspaceResearchJob.lease_until < now).values(status="failed", failure_reason="lease_expired"))
    running = db.scalar(select(WorkspaceResearchJob.job_id).where(WorkspaceResearchJob.lease_device_id == device.device_id, WorkspaceResearchJob.status == "running").limit(1))
    if running:
        raise HTTPException(409, "device_already_running")
    row = db.scalar(select(WorkspaceResearchJob).where(WorkspaceResearchJob.owner_scope == device.owner_scope, WorkspaceResearchJob.status == "queued", WorkspaceResearchJob.expires_at > now).order_by(WorkspaceResearchJob.created_at).with_for_update(skip_locked=True).limit(1))
    if row is None:
        db.commit()
        return {"job": None}
    changed = db.execute(update(WorkspaceResearchJob).where(WorkspaceResearchJob.job_id == row.job_id, WorkspaceResearchJob.status == "queued").values(status="running", lease_device_id=device.device_id, lease_id=payload.claim_id, lease_until=now + timedelta(minutes=workspace_settings().job_lease_minutes), attempts=WorkspaceResearchJob.attempts + 1))
    if changed.rowcount != 1:
        raise HTTPException(409, "job_claim_race")
    db.commit()
    db.refresh(row)
    return _lease_view(row)


def _lease_view(row: WorkspaceResearchJob) -> dict:
    return {"job": job_view(row), "lease_id": row.lease_id, "lease_until": row.lease_until.isoformat(), "package": {"job_id": row.job_id, "input_hash": row.input_hash, "bundle": row.bundle_json}}


def leased_job(db: Session, job_id: str, device: WorkspaceBridgeDevice) -> WorkspaceResearchJob:
    row = db.scalar(select(WorkspaceResearchJob).where(WorkspaceResearchJob.job_id == job_id, WorkspaceResearchJob.owner_scope == device.owner_scope, WorkspaceResearchJob.lease_device_id == device.device_id).with_for_update())
    if row is None:
        raise HTTPException(404, "device_job_not_found")
    return row


@router.get("/jobs/{job_id}")
def status(job_id: str, db: DB, device: Device) -> dict:
    return job_view(leased_job(db, job_id, device))


@router.post("/jobs/{job_id}/result")
def result(job_id: str, payload: DeviceResult, db: DB, device: Device) -> dict:
    row = leased_job(db, job_id, device)
    try:
        accept_result(db, row, payload.result, device_id=device.device_id, lease_id=payload.lease_id)
    except WorkspaceError as exc:
        raise HTTPException(exc.status, exc.code) from None
    db.commit()
    return job_view(row)


@router.post("/jobs/{job_id}/failure")
def failure(job_id: str, payload: DeviceFailure, db: DB, device: Device) -> dict:
    row = leased_job(db, job_id, device)
    if row.lease_id != payload.lease_id or row.status not in {"running", "failed"}:
        raise HTTPException(409, "research_lease_inactive")
    row.status, row.failure_reason = "failed", payload.reason
    db.commit()
    return job_view(row)
