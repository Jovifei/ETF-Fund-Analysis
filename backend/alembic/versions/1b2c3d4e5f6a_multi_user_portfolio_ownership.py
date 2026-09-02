"""add nullable owner boundaries for private portfolio records

Revision ID: 1b2c3d4e5f6a
Revises: 0a9b1c2d3e4f
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1b2c3d4e5f6a"
down_revision: str | None = "0a9b1c2d3e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _legacy_holding_unique() -> tuple[str, str]:
    """Resolve the pre-ownership uniqueness across SQLite and PostgreSQL.

    Older revisions emitted an unnamed SQLite UNIQUE while PostgreSQL commonly
    materialized a named constraint.  Batch mode applies ``_NAMING`` to the
    former, so the generated name is a portability fallback rather than an
    assumption about the original DDL.
    """

    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("holdings"):
        if constraint.get("column_names") == ["instrument_id"]:
            # SQLite's original anonymous UNIQUE is assigned this deterministic
            # name by the batch naming convention below.
            return "constraint", str(constraint.get("name") or "uq_holdings_instrument_id")
    for index in inspector.get_indexes("holdings"):
        if index.get("unique") and index.get("column_names") == ["instrument_id"] and index.get("name"):
            return "index", str(index["name"])
    raise RuntimeError("legacy holdings.instrument_id uniqueness was not found")


def _assert_global_holding_uniqueness_restorable() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            "SELECT instrument_id FROM holdings GROUP BY instrument_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "cannot downgrade ownership migration: multiple users hold the same instrument"
        )


def upgrade() -> None:
    # Nullable ownership deliberately preserves legacy rows until an active
    # admin runs the explicit audited backfill command.
    unique_kind, unique_name = _legacy_holding_unique()
    with op.batch_alter_table("holdings", naming_convention=_NAMING) as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_holdings_user_id_auth_users", "auth_users", ["user_id"], ["id"], ondelete="RESTRICT")
        if unique_kind == "constraint":
            batch.drop_constraint(unique_name, type_="unique")
        else:
            batch.drop_index(unique_name)
        batch.create_unique_constraint("uq_holdings_user_instrument", ["user_id", "instrument_id"])
        batch.create_index("ix_holdings_user_id", ["user_id"])
        batch.create_index("ix_holdings_instrument_id", ["instrument_id"])

    with op.batch_alter_table("holding_import_sessions") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_holding_import_sessions_user_id_auth_users", "auth_users", ["user_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_index("ix_holding_import_sessions_user_id", ["user_id"])
    op.create_index(
        "ix_holding_import_sessions_user_status_expires", "holding_import_sessions", ["user_id", "status", "expires_at"]
    )

    with op.batch_alter_table("report_artifacts") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_report_artifacts_user_id_auth_users", "auth_users", ["user_id"], ["id"], ondelete="RESTRICT")
        batch.create_index("ix_report_artifacts_user_id", ["user_id"])


def downgrade() -> None:
    _assert_global_holding_uniqueness_restorable()
    with op.batch_alter_table("report_artifacts") as batch:
        batch.drop_index("ix_report_artifacts_user_id")
        batch.drop_constraint("fk_report_artifacts_user_id_auth_users", type_="foreignkey")
        batch.drop_column("user_id")
    op.drop_index("ix_holding_import_sessions_user_status_expires", table_name="holding_import_sessions")
    with op.batch_alter_table("holding_import_sessions") as batch:
        batch.drop_index("ix_holding_import_sessions_user_id")
        batch.drop_constraint("fk_holding_import_sessions_user_id_auth_users", type_="foreignkey")
        batch.drop_column("user_id")
    with op.batch_alter_table("holdings", naming_convention=_NAMING) as batch:
        batch.drop_index("ix_holdings_instrument_id")
        batch.drop_index("ix_holdings_user_id")
        batch.drop_constraint("uq_holdings_user_instrument", type_="unique")
        batch.create_unique_constraint("uq_holdings_instrument_id", ["instrument_id"])
        batch.drop_constraint("fk_holdings_user_id_auth_users", type_="foreignkey")
        batch.drop_column("user_id")
