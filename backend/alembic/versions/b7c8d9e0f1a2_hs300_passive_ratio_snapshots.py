"""Persist the research-only HS300 passive-holdings ratio snapshot.

Revision ID: b7c8d9e0f1a2
Revises: f0e1d2c3b4a5
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "f0e1d2c3b4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hs300_passive_ratio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("index_code", sa.String(length=16), nullable=False),
        sa.Column("basis", sa.String(length=32), nullable=False),
        sa.Column("numerator_basis", sa.String(length=32), nullable=False),
        sa.Column("numerator", sa.Float(), nullable=False),
        sa.Column("denominator", sa.Float(), nullable=False),
        sa.Column("ratio", sa.Float(), nullable=False),
        sa.Column("fund_count", sa.Integer(), nullable=False),
        sa.Column("universe_hash", sa.String(length=64), nullable=False),
        sa.Column("constituent_count", sa.Integer(), nullable=False),
        sa.Column("constituent_as_of", sa.Date(), nullable=True),
        sa.Column("numerator_source", sa.String(length=96), nullable=False),
        sa.Column("denominator_source", sa.String(length=64), nullable=False),
        sa.Column("lag_days", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_hash", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("trade_date", "numerator_basis", name="uq_hs300_ratio_date_basis"),
    )
    op.create_index("ix_hs300_ratio_trade_date", "hs300_passive_ratio_snapshots", ["trade_date"])


def downgrade() -> None:
    op.drop_index("ix_hs300_ratio_trade_date", table_name="hs300_passive_ratio_snapshots")
    op.drop_table("hs300_passive_ratio_snapshots")
