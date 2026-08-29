"""calibration candidate profiles for forecast promotion governance

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calibration_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=64), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("validation_run_id", sa.String(length=64), nullable=False),
        sa.Column("validation_content_hash", sa.String(length=64), nullable=False),
        sa.Column("instrument_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gate_results", sa.JSON(), nullable=True),
        sa.Column("summary_metrics", sa.JSON(), nullable=True),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('candidate', 'approved', 'rejected')",
            name="ck_calibration_profiles_status",
        ),
        sa.UniqueConstraint(
            "validation_content_hash",
            name="uq_calibration_profiles_validation_hash",
        ),
    )
    op.create_index(
        "ix_calibration_profiles_status",
        "calibration_profiles",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_calibration_profiles_status", table_name="calibration_profiles")
    op.drop_table("calibration_profiles")
