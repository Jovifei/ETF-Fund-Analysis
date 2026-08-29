"""forecast corridor and reproducibility provenance

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("quote_snapshots") as batch:
        batch.add_column(sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column(
                "timestamp_verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("indicator_snapshots") as batch:
        batch.add_column(sa.Column("feature_schema_version", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("config_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("git_commit_sha", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("reproducibility_json", sa.JSON(), nullable=True))

    with op.batch_alter_table("forecast_snapshots") as batch:
        batch.add_column(sa.Column("feature_schema_version", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("config_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("git_commit_sha", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("reproducibility_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("interval_method", sa.String(length=64), nullable=True))
        for name in (
            "terminal_price_q10",
            "terminal_price_q50",
            "terminal_price_q90",
            "path_low_price_q10",
            "path_low_price_q50",
            "path_low_price_q90",
            "path_high_price_q10",
            "path_high_price_q50",
            "path_high_price_q90",
            "corridor_position",
            "support_touch_probability",
            "resistance_touch_probability",
        ):
            batch.add_column(sa.Column(name, sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("forecast_snapshots") as batch:
        for name in reversed(
            (
                "terminal_price_q10",
                "terminal_price_q50",
                "terminal_price_q90",
                "path_low_price_q10",
                "path_low_price_q50",
                "path_low_price_q90",
                "path_high_price_q10",
                "path_high_price_q50",
                "path_high_price_q90",
                "corridor_position",
                "support_touch_probability",
                "resistance_touch_probability",
            )
        ):
            batch.drop_column(name)
        batch.drop_column("interval_method")
        batch.drop_column("reproducibility_json")
        batch.drop_column("git_commit_sha")
        batch.drop_column("config_hash")
        batch.drop_column("feature_schema_version")

    with op.batch_alter_table("indicator_snapshots") as batch:
        batch.drop_column("reproducibility_json")
        batch.drop_column("git_commit_sha")
        batch.drop_column("config_hash")
        batch.drop_column("feature_schema_version")

    with op.batch_alter_table("quote_snapshots") as batch:
        batch.drop_column("timestamp_verified")
        batch.drop_column("fetched_at")
