"""Isolated workspace research, device, import and asynchronous task state.

Revision ID: d40609090001
Revises: c2d3e4f5a6b7
Frozen column definitions: deliberately does not import application ORM models.
"""
from alembic import op
import sqlalchemy as sa

revision = "d40609090001"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def _text(name, length=64, nullable=False):
    return sa.Column(name, sa.String(length), nullable=nullable)


def _time(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _owner(ondelete="CASCADE"):
    return sa.Column("user_id", sa.Integer(), sa.ForeignKey("auth_users.id", ondelete=ondelete), nullable=True)


def upgrade():
    op.create_table("workspace_research_jobs",
        sa.Column("job_id", sa.String(32), primary_key=True), _owner(), _text("owner_scope", 48),
        _text("idempotency_key"), _text("kind", 16), _text("ts_code", 32, True),
        _text("status", 16), _text("quality", 32), _text("review_status", 16),
        sa.Column("review_note", sa.Text(), nullable=True), _text("input_hash"),
        sa.Column("bundle_json", sa.JSON(), nullable=False), sa.Column("result_json", sa.JSON(), nullable=True),
        _text("result_hash", 64, True), _text("lease_device_id", 32, True), _text("lease_id", 32, True),
        _time("lease_until", True), sa.Column("attempts", sa.Integer(), nullable=False),
        _text("failure_reason", 64, True), _time("created_at"), _time("expires_at"),
        _time("completed_at", True), _time("reviewed_at", True),
        sa.UniqueConstraint("owner_scope", "idempotency_key", name="uq_workspace_research_idempotency"),
        sa.CheckConstraint("status IN ('queued','running','completed','failed','cancelled','expired')", name="ck_workspace_research_status"),
        sa.CheckConstraint("review_status IN ('pending','accepted','rejected')", name="ck_workspace_research_review"),
    )
    for column in ("owner_scope", "ts_code", "status"):
        op.create_index(f"ix_workspace_research_jobs_{column}", "workspace_research_jobs", [column])
    op.create_table("workspace_bridge_devices",
        sa.Column("device_id", sa.String(32), primary_key=True), _owner(), _text("owner_scope", 48),
        _text("label", 64), _text("status", 16), _text("pairing_hash", 64, True),
        _time("pairing_expires_at", True), _text("token_hash", 64, True), _time("token_expires_at", True),
        _time("created_at"), _time("last_seen_at", True), sa.Column("heartbeat_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("pairing_hash"), sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_workspace_bridge_devices_owner_scope", "workspace_bridge_devices", ["owner_scope"])
    op.create_table("workspace_data_jobs",
        sa.Column("job_id", sa.String(32), primary_key=True), _owner("SET NULL"), _text("owner_scope", 48),
        _text("idempotency_key"), _text("status", 16), sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True), _text("failure_reason", 64, True),
        _time("created_at"), _time("started_at", True), _time("finished_at", True), _time("lease_until", True),
        sa.UniqueConstraint("idempotency_key", name="uq_workspace_data_idempotency"),
    )
    for column in ("owner_scope", "status"):
        op.create_index(f"ix_workspace_data_jobs_{column}", "workspace_data_jobs", [column])
    op.create_table("workspace_import_batches",
        sa.Column("batch_id", sa.String(32), primary_key=True), _owner(), _text("owner_scope", 48),
        _text("source_hash"), _text("source_kind", 16), _text("status", 16),
        sa.Column("candidates_json", sa.JSON(), nullable=False), sa.Column("before_json", sa.JSON(), nullable=True),
        _text("after_hash", 64, True), _time("created_at"), _time("expires_at"), _time("confirmed_at", True),
        sa.UniqueConstraint("owner_scope", "source_hash", name="uq_workspace_import_source"),
    )
    op.create_index("ix_workspace_import_batches_owner_scope", "workspace_import_batches", ["owner_scope"])
    op.create_table("workspace_preferences",
        sa.Column("owner_scope", sa.String(48), primary_key=True), _owner(),
        sa.Column("settings_json", sa.JSON(), nullable=False), _time("updated_at"),
    )


def downgrade():
    for table in ("workspace_preferences", "workspace_import_batches", "workspace_data_jobs", "workspace_bridge_devices", "workspace_research_jobs"):
        op.drop_table(table)
