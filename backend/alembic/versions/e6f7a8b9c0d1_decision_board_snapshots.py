"""persist unified decision-board snapshots and isolated provisional input

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_board_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("freshness", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "freshness IN ('fresh', 'stale', 'missing', 'degraded', 'unknown')",
            name="ck_decision_board_snapshots_freshness",
        ),
        sa.UniqueConstraint("snapshot_id", name="uq_decision_board_snapshots_snapshot_id"),
    )
    op.create_index("ix_decision_board_snapshots_snapshot_id", "decision_board_snapshots", ["snapshot_id"])
    op.create_index("ix_decision_board_snapshots_generated_at", "decision_board_snapshots", ["generated_at"])

    op.create_table(
        "decision_board_provisional_inputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("timestamp_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("open_price", sa.Float(), nullable=True),
        sa.Column("high_price", sa.Float(), nullable=True),
        sa.Column("low_price", sa.Float(), nullable=True),
        sa.Column("last_price", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("pct_change_percent_points", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("instrument_id", "observed_at", "source", name="uq_decision_board_provisional_input"),
    )
    op.create_index(
        "ix_decision_board_provisional_inputs_instrument_id",
        "decision_board_provisional_inputs",
        ["instrument_id"],
    )
    op.create_index(
        "ix_decision_board_provisional_input_instrument_time",
        "decision_board_provisional_inputs",
        ["instrument_id", "observed_at"],
    )

    op.create_table(
        "decision_board_slot_runs",
        sa.Column("slot_key", sa.String(length=32), primary_key=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("decision_board_slot_runs")
    op.drop_index("ix_decision_board_provisional_input_instrument_time", table_name="decision_board_provisional_inputs")
    op.drop_index("ix_decision_board_provisional_inputs_instrument_id", table_name="decision_board_provisional_inputs")
    op.drop_table("decision_board_provisional_inputs")
    op.drop_index("ix_decision_board_snapshots_generated_at", table_name="decision_board_snapshots")
    op.drop_index("ix_decision_board_snapshots_snapshot_id", table_name="decision_board_snapshots")
    op.drop_table("decision_board_snapshots")
