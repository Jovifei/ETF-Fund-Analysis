from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def now() -> datetime:
    return datetime.now(UTC)


class WorkspaceResearchJob(Base):
    __tablename__ = "workspace_research_jobs"
    __table_args__ = (
        UniqueConstraint("owner_scope", "idempotency_key", name="uq_workspace_research_idempotency"),
        CheckConstraint("status IN ('queued','running','completed','failed','cancelled','expired')", name="ck_workspace_research_status"),
        CheckConstraint("review_status IN ('pending','accepted','rejected')", name="ck_workspace_research_review"),
    )
    job_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_users.id", ondelete="CASCADE"))
    owner_scope: Mapped[str] = mapped_column(String(48), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    ts_code: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    quality: Mapped[str] = mapped_column(String(32), default="incomplete")
    review_status: Mapped[str] = mapped_column(String(16), default="pending")
    review_note: Mapped[str | None] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(64))
    bundle_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    lease_device_id: Mapped[str | None] = mapped_column(String(32))
    lease_id: Mapped[str | None] = mapped_column(String(32))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkspaceBridgeDevice(Base):
    __tablename__ = "workspace_bridge_devices"
    device_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_users.id", ondelete="CASCADE"))
    owner_scope: Mapped[str] = mapped_column(String(48), index=True)
    label: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    pairing_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    pairing_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class WorkspaceDataJob(Base):
    __tablename__ = "workspace_data_jobs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_workspace_data_idempotency"),)
    job_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_users.id", ondelete="SET NULL"))
    owner_scope: Mapped[str] = mapped_column(String(48), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkspaceImportBatch(Base):
    __tablename__ = "workspace_import_batches"
    __table_args__ = (UniqueConstraint("owner_scope", "source_hash", name="uq_workspace_import_source"),)
    batch_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_users.id", ondelete="CASCADE"))
    owner_scope: Mapped[str] = mapped_column(String(48), index=True)
    source_hash: Mapped[str] = mapped_column(String(64))
    source_kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="preview")
    candidates_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkspacePreference(Base):
    __tablename__ = "workspace_preferences"
    owner_scope: Mapped[str] = mapped_column(String(48), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_users.id", ondelete="CASCADE"))
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
