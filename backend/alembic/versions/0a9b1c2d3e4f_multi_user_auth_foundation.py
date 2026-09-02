"""add closed-enrollment multi-user authentication foundations

Revision ID: 0a9b1c2d3e4f
Revises: f7a8b9c0d1e2
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0a9b1c2d3e4f"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _hex_check(column: str) -> str:
    stripped = column
    for character in "0123456789abcdefABCDEF":
        stripped = f"replace({stripped}, '{character}', '')"
    return f"length({column}) = 64 AND {stripped} = ''"


def upgrade() -> None:
    op.create_table(
        "auth_bootstrap_guard",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("id = 1", name="ck_auth_bootstrap_guard_singleton"),
    )
    op.execute(sa.text("INSERT INTO auth_bootstrap_guard (id) VALUES (1)"))

    op.create_table(
        "auth_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="member"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('admin', 'member')", name="ck_auth_users_role"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_auth_users_status"),
        sa.CheckConstraint("length(username) BETWEEN 1 AND 128", name="ck_auth_users_username_length"),
        sa.CheckConstraint("password_hash LIKE '$argon2id$%'", name="ck_auth_users_password_hash"),
        sa.UniqueConstraint("username", name="uq_auth_users_username"),
        sa.UniqueConstraint("email", name="uq_auth_users_email"),
    )
    op.create_index("ix_auth_users_username", "auth_users", ["username"])
    op.create_index("ix_auth_users_email", "auth_users", ["email"])
    op.create_index("ix_auth_users_status", "auth_users", ["status"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=64), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.CheckConstraint(_hex_check("session_hash"), name="ck_auth_sessions_session_hash"),
        sa.CheckConstraint(_hex_check("csrf_hash"), name="ck_auth_sessions_csrf_hash"),
        sa.CheckConstraint("user_agent_hash IS NULL OR " + _hex_check("user_agent_hash"), name="ck_auth_sessions_user_agent_hash"),
        sa.CheckConstraint("ip_hash IS NULL OR " + _hex_check("ip_hash"), name="ck_auth_sessions_ip_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_auth_sessions_expiry"),
        sa.CheckConstraint("revoked_at IS NULL OR revoked_at >= created_at", name="ck_auth_sessions_revoked_at"),
        sa.UniqueConstraint("session_hash", name="uq_auth_sessions_session_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_index("ix_auth_sessions_revoked_at", "auth_sessions", ["revoked_at"])
    op.create_index(
        "ix_auth_sessions_user_revocation_expiry", "auth_sessions", ["user_id", "revoked_at", "expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_user_revocation_expiry", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_revoked_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_auth_users_status", table_name="auth_users")
    op.drop_index("ix_auth_users_email", table_name="auth_users")
    op.drop_index("ix_auth_users_username", table_name="auth_users")
    op.drop_table("auth_users")
    op.drop_table("auth_bootstrap_guard")
