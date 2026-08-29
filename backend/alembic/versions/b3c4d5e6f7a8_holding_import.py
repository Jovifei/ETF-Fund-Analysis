"""Add bounded transient holding-import OCR records.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _hex_check(column: str, name: str) -> sa.CheckConstraint:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        expression = f"length({column}) = 64 AND {column} NOT GLOB '*[^0-9A-Fa-f]*'"
    elif dialect == "postgresql":
        expression = f"{column} ~ '^[0-9A-Fa-f]{{64}}$'"
    else:
        raise RuntimeError(f"unsupported migration dialect: {dialect}")
    return sa.CheckConstraint(expression, name=name)


def _opaque_check(column: str, name: str, maximum: int) -> sa.CheckConstraint:
    stripped = column
    for character in "0123456789abcdef":
        stripped = f"replace({stripped}, '{character}', '')"
    return sa.CheckConstraint(
        f"length({column}) BETWEEN 16 AND {maximum} AND lower({column}) = {column} AND {stripped} = ''",
        name=name,
    )


def _etf_code_check(column: str, name: str) -> sa.CheckConstraint:
    stripped = column
    for character in "0123456789":
        stripped = f"replace({stripped}, '{character}', '')"
    stripped = f"replace({stripped}, '.', '')"
    return sa.CheckConstraint(
        f"length({column}) = 9 AND substr({column}, 7, 1) = '.' AND {stripped} IN ('SH', 'SZ', 'BJ')",
        name=name,
    )


def _safe_text_check(column: str, name: str, maximum: int) -> sa.CheckConstraint:
    blocked = (
        "http://", "https://", "www.", "bearer ", "token=", "token ", "secret=", "password", "passwd",
        "api_key", "authorization", "cookie", "traceback", "powershell", "cmd ", "bash ", "../", "..\\", "/", ":",
        "\n", "\r", "\t",
    )
    checks = [f"{column} = trim({column})", f"length({column}) BETWEEN 1 AND {maximum}"]
    checks.extend(f"lower({column}) NOT LIKE '%{item}%'" for item in blocked)
    return sa.CheckConstraint(" AND ".join(checks), name=name)


def _no_backslash_check(column: str, name: str) -> sa.CheckConstraint:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        expression = f"instr({column}, char(92)) = 0"
    elif dialect == "postgresql":
        expression = f"position(chr(92) in {column}) = 0"
    else:
        raise RuntimeError(f"unsupported migration dialect: {dialect}")
    return sa.CheckConstraint(expression, name=name)


def upgrade() -> None:
    op.create_table(
        "holding_import_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("image_sha256", sa.String(length=64), nullable=False),
        sa.Column("detected_mime", sa.String(length=32), nullable=False),
        sa.Column("image_bytes", sa.Integer(), nullable=False),
        sa.Column("image_width", sa.Integer(), nullable=False),
        sa.Column("image_height", sa.Integer(), nullable=False),
        sa.Column("ocr_mode", sa.String(length=32), nullable=False),
        sa.Column("ocr_backend", sa.String(length=128), nullable=False),
        sa.Column("ocr_model", sa.String(length=128), nullable=False),
        sa.Column("ocr_version", sa.String(length=128), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cloud_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cloud_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("storage_key", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("session_id", name="uq_holding_import_sessions_session_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'editing', 'confirming', 'confirmed', 'cancelled', 'expired', 'failed')",
            name="ck_holding_import_sessions_status",
        ),
        _opaque_check("session_id", "ck_holding_import_sessions_session_id_opaque", 96),
        _hex_check("image_sha256", "ck_holding_import_sessions_image_sha256"),
        sa.CheckConstraint("detected_mime IN ('image/png', 'image/jpeg', 'image/webp')", name="ck_holding_import_sessions_detected_mime"),
        sa.CheckConstraint("image_bytes BETWEEN 1 AND 52428800", name="ck_holding_import_sessions_bytes_bounded"),
        sa.CheckConstraint("image_width BETWEEN 1 AND 50000 AND image_height BETWEEN 1 AND 50000", name="ck_holding_import_sessions_dimensions_bounded"),
        sa.CheckConstraint("candidate_count BETWEEN 0 AND 10000", name="ck_holding_import_sessions_candidate_count_bounded"),
        sa.CheckConstraint(
            "length(trim(session_id)) BETWEEN 16 AND 96 AND length(trim(ocr_mode)) BETWEEN 1 AND 32 AND "
            "length(trim(ocr_backend)) BETWEEN 1 AND 128 AND length(trim(ocr_model)) BETWEEN 1 AND 128 AND "
            "length(trim(ocr_version)) BETWEEN 1 AND 128",
            name="ck_holding_import_sessions_text_bounded",
        ),
        sa.CheckConstraint("(cloud_consent IS TRUE AND cloud_consent_at IS NOT NULL) OR (cloud_consent IS FALSE AND cloud_consent_at IS NULL)", name="ck_holding_import_sessions_cloud_consent_coherent"),
        sa.CheckConstraint("status <> 'confirmed' OR (confirmed_at IS NOT NULL AND cancelled_at IS NULL)", name="ck_holding_import_sessions_confirmed_timestamp"),
        sa.CheckConstraint("status <> 'cancelled' OR (cancelled_at IS NOT NULL AND confirmed_at IS NULL)", name="ck_holding_import_sessions_cancelled_timestamp"),
        sa.CheckConstraint("confirmed_at IS NULL OR status = 'confirmed'", name="ck_holding_import_sessions_confirmed_status_bidirectional"),
        sa.CheckConstraint("cancelled_at IS NULL OR status = 'cancelled'", name="ck_holding_import_sessions_cancelled_status_bidirectional"),
        sa.CheckConstraint("status NOT IN ('pending', 'processing', 'ready', 'failed', 'expired') OR (confirmed_at IS NULL AND cancelled_at IS NULL)", name="ck_holding_import_sessions_nonterminal_timestamps"),
        sa.CheckConstraint("status NOT IN ('confirmed', 'cancelled', 'expired') OR expires_at IS NOT NULL", name="ck_holding_import_sessions_expiry_required"),
        sa.CheckConstraint("storage_key IS NULL OR (" + _opaque_check("storage_key", "tmp", 256).sqltext.text + ")", name="ck_holding_import_sessions_storage_key_bounded"),
    )
    op.create_index("ix_holding_import_sessions_status", "holding_import_sessions", ["status"], unique=False)
    op.create_index("ix_holding_import_sessions_expires_at", "holding_import_sessions", ["expires_at"], unique=False)
    op.create_index("ix_holding_import_sessions_status_expires", "holding_import_sessions", ["status", "expires_at"], unique=False)
    op.create_index("ix_holding_import_sessions_image_sha256", "holding_import_sessions", ["image_sha256"], unique=False)

    op.create_table(
        "holding_import_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("ts_code", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("shares", sa.Numeric(20, 4), nullable=True),
        sa.Column("cost_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("target_weight", sa.Float(), nullable=True),
        sa.Column("user_note", sa.String(length=2000), nullable=True),
        sa.Column("match_status", sa.String(length=24), nullable=False, server_default="unmatched"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("action", sa.String(length=16), nullable=False, server_default="none"),
        sa.Column("safe_alternatives_json", sa.Text(), nullable=False),
        sa.Column("field_confidence_json", sa.Text(), nullable=False),
        sa.Column("normalized_ocr_text_hash", sa.String(length=64), nullable=False),
        sa.Column("selected_code", sa.String(length=32), nullable=True),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["holding_import_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", "row_index", name="uq_holding_import_candidate_session_row"),
        sa.CheckConstraint("row_index BETWEEN 0 AND 10000", name="ck_holding_import_candidates_row_index_bounded"),
        sa.CheckConstraint("match_status IN ('matched', 'ambiguous', 'unmatched', 'low_confidence', 'duplicate')", name="ck_holding_import_candidates_match_status"),
        sa.CheckConstraint("status IN ('pending', 'reviewed', 'rejected', 'confirmed')", name="ck_holding_import_candidates_status"),
        sa.CheckConstraint("action IN ('none', 'confirm', 'reject')", name="ck_holding_import_candidates_action"),
        sa.CheckConstraint("(status IN ('pending', 'reviewed') AND action = 'none') OR (status = 'rejected' AND action = 'reject') OR (status = 'confirmed' AND action = 'confirm')", name="ck_holding_import_candidates_status_action_coherent"),
        sa.CheckConstraint("(selected_code IS NULL AND selected_at IS NULL) OR (selected_code IS NOT NULL AND selected_at IS NOT NULL)", name="ck_holding_import_candidates_selection_bidirectional"),
        sa.CheckConstraint("status <> 'confirmed' OR (selected_code IS NOT NULL AND selected_at IS NOT NULL)", name="ck_holding_import_candidates_confirmed_selection"),
        sa.CheckConstraint("status <> 'rejected' OR (selected_code IS NULL AND selected_at IS NULL)", name="ck_holding_import_candidates_rejected_selection"),
        _etf_code_check("ts_code", "ck_holding_import_candidates_code_bounded"),
        sa.CheckConstraint("name IS NULL OR (" + _safe_text_check("name", "tmp", 128).sqltext.text + ")", name="ck_holding_import_candidates_name_bounded"),
        _etf_code_check("selected_code", "ck_holding_import_candidates_selected_code_bounded"),
        sa.CheckConstraint("user_note IS NULL OR (" + _safe_text_check("user_note", "tmp", 2000).sqltext.text + " AND lower(user_note) NOT LIKE '%account%' AND lower(user_note) NOT LIKE '%identity%' AND lower(user_note) NOT LIKE '%raw_ocr%')", name="ck_holding_import_candidates_user_note_bounded"),
        _no_backslash_check("name", "ck_holding_import_candidates_name_no_backslash"),
        _no_backslash_check("user_note", "ck_holding_import_candidates_user_note_no_backslash"),
        sa.CheckConstraint("lower(safe_alternatives_json) NOT LIKE '%password%' AND lower(safe_alternatives_json) NOT LIKE '%account%' AND lower(safe_alternatives_json) NOT LIKE '%identity%' AND lower(safe_alternatives_json) NOT LIKE '%raw_ocr%' AND lower(safe_alternatives_json) NOT LIKE '%raw_text%' AND lower(safe_alternatives_json) NOT LIKE '%ocr_text%' AND lower(safe_alternatives_json) NOT LIKE '%pixels%' AND lower(safe_alternatives_json) NOT LIKE '%cookie%' AND lower(safe_alternatives_json) NOT LIKE '%secret%' AND lower(safe_alternatives_json) NOT LIKE '%token%' AND lower(field_confidence_json) NOT LIKE '%password%' AND lower(field_confidence_json) NOT LIKE '%account%' AND lower(field_confidence_json) NOT LIKE '%identity%' AND lower(field_confidence_json) NOT LIKE '%raw_ocr%' AND lower(field_confidence_json) NOT LIKE '%raw_text%' AND lower(field_confidence_json) NOT LIKE '%ocr_text%' AND lower(field_confidence_json) NOT LIKE '%pixels%' AND lower(field_confidence_json) NOT LIKE '%cookie%' AND lower(field_confidence_json) NOT LIKE '%secret%' AND lower(field_confidence_json) NOT LIKE '%token%'", name="ck_holding_import_candidates_json_sensitive_keys"),
        sa.CheckConstraint("shares IS NULL OR shares BETWEEN 0 AND 1000000000", name="ck_holding_import_candidates_shares_bounded"),
        sa.CheckConstraint("cost_price IS NULL OR cost_price BETWEEN 0 AND 1000000000", name="ck_holding_import_candidates_cost_bounded"),
        sa.CheckConstraint("target_weight IS NULL OR target_weight BETWEEN 0 AND 1", name="ck_holding_import_candidates_target_weight_bounded"),
        _hex_check("normalized_ocr_text_hash", "ck_holding_import_candidates_text_hash"),
    )
    op.create_index("ix_holding_import_candidates_session_id", "holding_import_candidates", ["session_id"], unique=False)
    op.create_index("ix_holding_import_candidates_match_status", "holding_import_candidates", ["match_status"], unique=False)
    op.create_index("ix_holding_import_candidates_status", "holding_import_candidates", ["status"], unique=False)
    op.create_index("ix_holding_import_candidates_session_status", "holding_import_candidates", ["session_id", "status"], unique=False)
    op.create_index("ix_holding_import_candidates_normalized_ocr_text_hash", "holding_import_candidates", ["normalized_ocr_text_hash"], unique=False)
    if op.get_bind().dialect.name == "sqlite":
        op.execute("""CREATE TRIGGER IF NOT EXISTS trg_holding_import_candidates_no_nul_insert
        BEFORE INSERT ON holding_import_candidates
        WHEN instr(COALESCE(NEW.name, ''), char(0)) > 0 OR instr(COALESCE(NEW.user_note, ''), char(0)) > 0
        BEGIN SELECT RAISE(ABORT, 'holding import text contains NUL'); END""")
        op.execute("""CREATE TRIGGER IF NOT EXISTS trg_holding_import_candidates_no_nul_update
        BEFORE UPDATE OF name, user_note ON holding_import_candidates
        WHEN instr(COALESCE(NEW.name, ''), char(0)) > 0 OR instr(COALESCE(NEW.user_note, ''), char(0)) > 0
        BEGIN SELECT RAISE(ABORT, 'holding import text contains NUL'); END""")


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_holding_import_candidates_no_nul_update")
        op.execute("DROP TRIGGER IF EXISTS trg_holding_import_candidates_no_nul_insert")
    for index_name in (
        "ix_holding_import_candidates_normalized_ocr_text_hash",
        "ix_holding_import_candidates_session_status",
        "ix_holding_import_candidates_status",
        "ix_holding_import_candidates_match_status",
        "ix_holding_import_candidates_session_id",
    ):
        op.drop_index(index_name, table_name="holding_import_candidates")
    op.drop_table("holding_import_candidates")
    for index_name in (
        "ix_holding_import_sessions_image_sha256",
        "ix_holding_import_sessions_status_expires",
        "ix_holding_import_sessions_expires_at",
        "ix_holding_import_sessions_status",
    ):
        op.drop_index(index_name, table_name="holding_import_sessions")
    op.drop_table("holding_import_sessions")
