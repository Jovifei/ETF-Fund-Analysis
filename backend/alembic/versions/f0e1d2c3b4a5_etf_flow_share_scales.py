"""Persist ETF spot flow fields and exchange share-scale history.

Revision ID: f0e1d2c3b4a5
Revises: e609200001
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f0e1d2c3b4a5"
down_revision: str | None = "e609200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_QUOTE_FLOW_COLUMNS = (
    "iopv",
    "latest_shares",
    "main_net_inflow",
    "super_large_net_inflow",
    "large_net_inflow",
    "medium_net_inflow",
    "small_net_inflow",
)


def upgrade() -> None:
    with op.batch_alter_table("quote_snapshots") as batch_op:
        for name in _QUOTE_FLOW_COLUMNS:
            batch_op.add_column(sa.Column(name, sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("flow_contract", sa.String(length=32), nullable=True))
    op.create_table(
        "etf_share_scales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("previous_trade_date", sa.Date(), nullable=True),
        sa.Column("previous_shares", sa.Float(), nullable=True),
        sa.Column("share_delta", sa.Float(), nullable=True),
        sa.Column("share_delta_ratio", sa.Float(), nullable=True),
        sa.Column("day_over_day", sa.Boolean(), nullable=False),
        sa.Column("proxy", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("exchange", sa.String(length=8), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_hash", sa.String(length=64), nullable=False),
        sa.UniqueConstraint(
            "instrument_id",
            "trade_date",
            "source",
            name="uq_etf_share_scale_instrument_date_source",
        ),
    )
    op.create_index("ix_etf_share_scale_instrument_date", "etf_share_scales", ["instrument_id", "trade_date"])
    op.create_index("ix_etf_share_scales_instrument_id", "etf_share_scales", ["instrument_id"])
    op.create_index("ix_etf_share_scales_trade_date", "etf_share_scales", ["trade_date"])


def downgrade() -> None:
    op.drop_index("ix_etf_share_scales_trade_date", table_name="etf_share_scales")
    op.drop_index("ix_etf_share_scales_instrument_id", table_name="etf_share_scales")
    op.drop_index("ix_etf_share_scale_instrument_date", table_name="etf_share_scales")
    op.drop_table("etf_share_scales")
    with op.batch_alter_table("quote_snapshots") as batch_op:
        batch_op.drop_column("flow_contract")
        for name in reversed(_QUOTE_FLOW_COLUMNS):
            batch_op.drop_column(name)
