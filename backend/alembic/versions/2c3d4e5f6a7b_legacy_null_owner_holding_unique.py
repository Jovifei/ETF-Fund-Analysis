"""enforce one legacy/system holding per instrument

Revision ID: 2c3d4e5f6a7b
Revises: 1b2c3d4e5f6a
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2c3d4e5f6a7b"
down_revision: str | None = "1b2c3d4e5f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _reject_duplicate_legacy_holdings() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            "SELECT instrument_id FROM holdings "
            "WHERE user_id IS NULL GROUP BY instrument_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "cannot enforce legacy holding ownership: duplicate NULL-owner holdings require audited reconciliation"
        )


def upgrade() -> None:
    # Never pick an owner or discard a position during schema migration.  An
    # old inconsistent database stops before the invariant is introduced.
    _reject_duplicate_legacy_holdings()
    dialect = op.get_bind().dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        raise RuntimeError("legacy NULL-owner holding uniqueness is unsupported for this database dialect")
    op.create_index(
        "uq_holdings_legacy_instrument",
        "holdings",
        ["instrument_id"],
        unique=True,
        **{f"{dialect}_where": sa.text("user_id IS NULL")},
    )


def downgrade() -> None:
    op.drop_index("uq_holdings_legacy_instrument", table_name="holdings")
