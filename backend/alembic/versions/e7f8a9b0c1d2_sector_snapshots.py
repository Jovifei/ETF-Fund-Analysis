"""sector snapshots for kline stabilization workbench

Revision ID: e7f8a9b0c1d2
Revises: 2c3d4e5f6a7b
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "2c3d4e5f6a7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sector_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sector_name", sa.String(length=64), nullable=False, index=True),
        sa.Column("trade_date", sa.Date(), nullable=False, index=True),
        sa.Column("up_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("down_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flat_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pct_change", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="akshare"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_hash", sa.String(length=64), nullable=False, index=True),
        sa.UniqueConstraint(
            "sector_name",
            "trade_date",
            "source",
            name="uq_sector_name_date_source",
        ),
    )
    op.create_index("ix_sector_name_date", "sector_snapshots", ["sector_name", "trade_date"])


def downgrade() -> None:
    op.drop_index("ix_sector_name_date", table_name="sector_snapshots")
    op.drop_table("sector_snapshots")
