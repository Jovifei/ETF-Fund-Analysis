"""user watchlist entries (user-scoped fund watchlists)

Revision ID: b0c1d2e3f4a5
Revises: a9b8c7d6e5f4
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b0c1d2e3f4a5"
down_revision: str | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_watchlist_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("auth_users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "instrument_id", name="uq_watchlist_user_instrument"),
    )
    op.create_index(
        "ix_user_watchlist_entries_user_id",
        "user_watchlist_entries",
        ["user_id"],
    )
    op.create_index(
        "ix_user_watchlist_entries_instrument_id",
        "user_watchlist_entries",
        ["instrument_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_watchlist_entries_instrument_id", table_name="user_watchlist_entries"
    )
    op.drop_index("ix_user_watchlist_entries_user_id", table_name="user_watchlist_entries")
    op.drop_table("user_watchlist_entries")
