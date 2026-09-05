"""support resistance snapshots (unified single-source S/R store)

Revision ID: a9b8c7d6e5f4
Revises: a3b4c5d6e7f8
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9b8c7d6e5f4"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_resistance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("interval", sa.String(length=8), nullable=False, server_default="1d"),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("qualified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "method_version", sa.String(length=32), nullable=False,
            server_default="support-resistance-v1",
        ),
        sa.Column("config_hash", sa.String(length=64), nullable=True),
        sa.Column("source_bars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_by", sa.String(length=16), nullable=False, server_default="scheduled"),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("instrument_id", "interval", "as_of_date", name="uq_sr_key"),
    )
    op.create_index(
        "ix_support_resistance_snapshots_instrument",
        "support_resistance_snapshots",
        ["instrument_id", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_resistance_snapshots_instrument", table_name="support_resistance_snapshots"
    )
    op.drop_table("support_resistance_snapshots")
