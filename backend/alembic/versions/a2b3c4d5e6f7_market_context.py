"""Add configuration-backed market context registry and observations.

Revision ID: a2b3c4d5e6f7
Revises: 9f1c2b3a4d5e
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "9f1c2b3a4d5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_context_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("context_id", sa.String(length=96), nullable=False),
        sa.Column("label", sa.String(length=512), nullable=False),
        sa.Column("region", sa.String(length=512), nullable=False),
        sa.Column("context_kind", sa.String(length=32), nullable=False),
        sa.Column("source_symbol", sa.String(length=128), nullable=True),
        sa.Column("display_code", sa.String(length=128), nullable=True),
        sa.Column("is_tradable_proxy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("source_priority", sa.JSON(), nullable=False),
        sa.Column("freshness_rule", sa.String(length=512), nullable=False, server_default="provider_defined"),
        sa.Column("verification_status", sa.String(length=16), nullable=False, server_default="unverified"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.UniqueConstraint("context_id", name="uq_market_context_registry_context_id"),
        sa.UniqueConstraint("display_order", name="uq_market_context_registry_display_order"),
        sa.CheckConstraint(
            "context_kind IN ('sector_breadth', 'index', 'tradable_proxy')",
            name="ck_market_context_registry_context_kind",
        ),
        sa.CheckConstraint(
            "verification_status IN ('verified', 'unverified')",
            name="ck_market_context_registry_verification_status",
        ),
        sa.CheckConstraint(
            "length(trim(context_id)) BETWEEN 1 AND 96 AND length(trim(label)) BETWEEN 1 AND 512 AND "
            "length(trim(region)) BETWEEN 1 AND 512 AND length(trim(freshness_rule)) BETWEEN 1 AND 512",
            name="ck_market_context_registry_text_bounded",
        ),
        sa.CheckConstraint("display_order BETWEEN 1 AND 10000", name="ck_market_context_registry_display_order_bounded"),
        sa.CheckConstraint(
            "NOT enabled OR (verification_status = 'verified' AND source_symbol IS NOT NULL)",
            name="ck_market_context_registry_enabled_verified",
        ),
        sa.CheckConstraint(
            "(context_kind = 'tradable_proxy' AND is_tradable_proxy) OR "
            "(context_kind <> 'tradable_proxy' AND NOT is_tradable_proxy)",
            name="ck_market_context_registry_proxy_kind_equivalent",
        ),
        sa.CheckConstraint(
            "is_tradable_proxy OR display_code IS NULL",
            name="ck_market_context_registry_nonproxy_display_code_null",
        ),
        sa.CheckConstraint(
            "NOT is_tradable_proxy OR "
            "(verification_status = 'verified' AND display_code IS NOT NULL) OR "
            "(verification_status = 'unverified' AND source_symbol IS NULL AND display_code IS NULL)",
            name="ck_market_context_registry_proxy_code_coherent",
        ),
        sa.CheckConstraint(
            "source_symbol IS NULL OR length(trim(source_symbol)) BETWEEN 1 AND 128",
            name="ck_market_context_registry_source_symbol_bounded",
        ),
        sa.CheckConstraint(
            "display_code IS NULL OR length(trim(display_code)) BETWEEN 1 AND 128",
            name="ck_market_context_registry_display_code_bounded",
        ),
    )
    op.create_index(
        "ix_market_context_registry_enabled_order", "market_context_registry", ["enabled", "display_order"], unique=False
    )

    op.create_table(
        "market_context_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("source_symbol", sa.String(length=128), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("today_pct_change", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=512), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("freshness", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("verification_status", sa.String(length=16), nullable=False, server_default="unverified"),
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("degraded_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["registry_id"], ["market_context_registry.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "registry_id", "source_symbol", "source", "source_timestamp", name="uq_market_context_snapshot_idempotency"
        ),
        sa.CheckConstraint(
            "length(trim(source_symbol)) BETWEEN 1 AND 128", name="ck_market_context_snapshot_source_symbol_bounded"
        ),
        sa.CheckConstraint(
            "observed_value BETWEEN -1000000000000000 AND 1000000000000000 AND "
            "today_pct_change BETWEEN -100000 AND 100000",
            name="ck_market_context_snapshot_values_finite_bounded",
        ),
        sa.CheckConstraint(
            "price IS NULL OR price BETWEEN 0 AND 1000000000000000",
            name="ck_market_context_snapshot_price_finite_bounded",
        ),
        sa.CheckConstraint(
            "freshness IN ('fresh', 'stale', 'degraded', 'unknown', 'unavailable')",
            name="ck_market_context_snapshot_freshness",
        ),
        sa.CheckConstraint(
            "verification_status IN ('verified', 'unverified')",
            name="ck_market_context_snapshot_verification_status",
        ),
        sa.CheckConstraint("length(trim(source)) BETWEEN 1 AND 512", name="ck_market_context_snapshot_source_bounded"),
        sa.CheckConstraint(
            "freshness NOT IN ('degraded', 'unavailable') OR degraded_reason IS NOT NULL",
            name="ck_market_context_snapshot_degraded_reason",
        ),
        sa.CheckConstraint(
            "freshness NOT IN ('fresh', 'stale') OR degraded_reason IS NULL",
            name="ck_market_context_snapshot_fresh_stale_no_degraded_reason",
        ),
        sa.CheckConstraint(
            "degraded_reason IS NULL OR length(trim(degraded_reason)) BETWEEN 1 AND 512",
            name="ck_market_context_snapshot_degraded_reason_bounded",
        ),
        sa.CheckConstraint(
            "source_timestamp <= fetched_at",
            name="ck_market_context_snapshot_source_before_fetch",
        ),
        sa.CheckConstraint(
            "NOT is_mock OR (verification_status = 'unverified' AND freshness = 'degraded' AND degraded_reason IS NOT NULL)",
            name="ck_market_context_snapshot_mock_provenance",
        ),
    )
    op.create_index(
        "ix_market_context_snapshots_registry_id", "market_context_snapshots", ["registry_id"], unique=False
    )
    op.create_index(
        "ix_market_context_snapshot_registry_symbol_source_time",
        "market_context_snapshots",
        ["registry_id", "source_symbol", "source_timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_market_context_snapshots_source_timestamp", "market_context_snapshots", ["source_timestamp"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_market_context_snapshots_source_timestamp", table_name="market_context_snapshots")
    op.drop_index("ix_market_context_snapshot_registry_symbol_source_time", table_name="market_context_snapshots")
    op.drop_index("ix_market_context_snapshots_registry_id", table_name="market_context_snapshots")
    op.drop_table("market_context_snapshots")
    op.drop_index("ix_market_context_registry_enabled_order", table_name="market_context_registry")
    op.drop_table("market_context_registry")
