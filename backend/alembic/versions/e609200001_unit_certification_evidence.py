"""Persist independently recomputable volume and amount evidence."""
from alembic import op
import sqlalchemy as sa

revision = "e609200001"
down_revision = "d40609090002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "unit_certification_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False), sa.Column("adjust", sa.String(8), nullable=False),
        sa.Column("daily_bar_quality_hash", sa.String(64), nullable=False),
        sa.Column("primary_source", sa.String(64), nullable=False), sa.Column("independent_source", sa.String(64), nullable=False),
        sa.Column("primary_upstream", sa.String(64), nullable=False), sa.Column("independent_upstream", sa.String(64), nullable=False),
        sa.Column("primary_endpoint_version", sa.String(64), nullable=False), sa.Column("independent_endpoint_version", sa.String(64), nullable=False),
        sa.Column("primary_close", sa.Float(), nullable=False), sa.Column("independent_close", sa.Float(), nullable=False),
        sa.Column("primary_raw_volume", sa.Float()), sa.Column("primary_raw_amount", sa.Float()),
        sa.Column("independent_raw_volume", sa.Float()), sa.Column("independent_raw_amount", sa.Float()),
        sa.Column("primary_volume_unit", sa.String(32)), sa.Column("primary_amount_unit", sa.String(32)),
        sa.Column("independent_volume_unit", sa.String(32)), sa.Column("independent_amount_unit", sa.String(32)),
        sa.Column("converted_volume", sa.Float()), sa.Column("converted_amount", sa.Float()),
        sa.Column("primary_input_hash", sa.String(64), nullable=False), sa.Column("independent_input_hash", sa.String(64), nullable=False),
        sa.Column("certified", sa.Boolean(), nullable=False), sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("instrument_id", "trade_date", "adjust", "daily_bar_quality_hash", "primary_input_hash", "independent_input_hash", name="uq_unit_evidence_binding"),
    )
    op.create_index("ix_unit_evidence_instrument_date", "unit_certification_evidence", ["instrument_id", "trade_date"])


def downgrade():
    op.drop_table("unit_certification_evidence")
