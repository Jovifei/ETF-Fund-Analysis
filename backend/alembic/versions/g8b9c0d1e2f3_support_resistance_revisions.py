"""append-only support/resistance snapshot revisions

Revision ID: g8b9c0d1e2f3
Revises: f7a8b9c0d1e2
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g8b9c0d1e2f3"
down_revision: tuple[str, str] = ("0a9b1c2d3e4f", "e609200001")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_resistance_snapshot_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False, server_default="1d"),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("method_version", sa.String(length=32), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=True),
        sa.Column("price_basis_id", sa.String(length=64), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("source_bars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_by", sa.String(length=16), nullable=False, server_default="scheduled"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("revision_id", name="uq_sr_revision_id"),
    )
    op.create_index(
        "ix_sr_revisions_instrument_date",
        "support_resistance_snapshot_revisions",
        ["instrument_id", "interval", "as_of_date", "generated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sr_revisions_instrument_date", table_name="support_resistance_snapshot_revisions")
    op.drop_table("support_resistance_snapshot_revisions")
