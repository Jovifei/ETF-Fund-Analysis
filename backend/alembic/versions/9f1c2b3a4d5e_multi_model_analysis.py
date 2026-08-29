"""Persist validated multi-model analysis and review candidates.

Revision ID: 9f1c2b3a4d5e
Revises: 158ca7025305
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f1c2b3a4d5e"
down_revision: str | None = "158ca7025305"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _hash_check(column: str) -> sa.CheckConstraint:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        expression = f"length({column}) = 64 AND {column} NOT GLOB '*[^0-9A-Fa-f]*'"
    elif dialect == "postgresql":
        expression = f"{column} ~ '^[0-9A-Fa-f]{{64}}$'"
    else:
        raise RuntimeError(f"unsupported migration dialect: {dialect}")
    return sa.CheckConstraint(expression, name=f"ck_{column}_strict_sha256")


def _failure_class_check(column: str = "failure_class") -> sa.CheckConstraint:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        expression = (
            f"{column} IS NULL OR (length({column}) BETWEEN 1 AND 128 AND "
            f"{column} GLOB '[A-Za-z_]*' AND "
            f"{column} NOT GLOB '*[^A-Za-z0-9_.]*' AND "
            f"{column} NOT GLOB '*.' AND "
            f"{column} NOT GLOB '*..*' AND "
            f"{column} NOT GLOB '*.[^A-Za-z_]*')"
        )
    elif dialect == "postgresql":
        expression = f"{column} IS NULL OR {column} ~ '^[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z_][A-Za-z0-9_]*)*$'"
    else:
        raise RuntimeError(f"unsupported migration dialect: {dialect}")
    return sa.CheckConstraint(expression, name="ck_analysis_runs_failure_class_strict")


def _create_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_analysis_runs_append_only
                BEFORE UPDATE ON analysis_runs
                BEGIN
                    SELECT RAISE(ABORT, 'analysis_runs are append-only');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_analysis_runs_no_delete
                BEFORE DELETE ON analysis_runs
                BEGIN
                    SELECT RAISE(ABORT, 'analysis_runs are append-only');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_agent_review_candidates_immutable
                BEFORE UPDATE ON agent_review_candidates
                WHEN NEW.candidate_id IS NOT OLD.candidate_id
                  OR NEW.runner IS NOT OLD.runner
                  OR NEW.bundle_hash IS NOT OLD.bundle_hash
                  OR NEW.memo_hash IS NOT OLD.memo_hash
                  OR NEW.memo_json IS NOT OLD.memo_json
                  OR NEW.created_at IS NOT OLD.created_at
                BEGIN
                    SELECT RAISE(ABORT, 'review candidate identity and evidence are immutable');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_agent_review_candidates_no_delete
                BEFORE DELETE ON agent_review_candidates
                BEGIN
                    SELECT RAISE(ABORT, 'review candidates are append-only');
                END
                """
            )
        )
    elif dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION reject_analysis_runs_update()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'analysis_runs are append-only';
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_analysis_runs_append_only
                BEFORE UPDATE ON analysis_runs
                FOR EACH ROW EXECUTE FUNCTION reject_analysis_runs_update()
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION reject_analysis_runs_delete()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'analysis_runs are append-only';
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_analysis_runs_no_delete
                BEFORE DELETE ON analysis_runs
                FOR EACH ROW EXECUTE FUNCTION reject_analysis_runs_delete()
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION reject_agent_review_candidate_immutable()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF NEW.candidate_id IS DISTINCT FROM OLD.candidate_id
                       OR NEW.runner IS DISTINCT FROM OLD.runner
                       OR NEW.bundle_hash IS DISTINCT FROM OLD.bundle_hash
                       OR NEW.memo_hash IS DISTINCT FROM OLD.memo_hash
                       OR NEW.memo_json IS DISTINCT FROM OLD.memo_json
                       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                        RAISE EXCEPTION 'review candidate identity and evidence are immutable';
                    END IF;
                    RETURN NEW;
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION reject_agent_review_candidate_delete()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'review candidates are append-only';
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_agent_review_candidates_no_delete
                BEFORE DELETE ON agent_review_candidates
                FOR EACH ROW EXECUTE FUNCTION reject_agent_review_candidate_delete()
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_agent_review_candidates_immutable
                BEFORE UPDATE ON agent_review_candidates
                FOR EACH ROW EXECUTE FUNCTION reject_agent_review_candidate_immutable()
                """
            )
        )
    else:
        raise RuntimeError(f"unsupported migration dialect: {dialect}")


def _drop_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_agent_review_candidates_no_delete"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_agent_review_candidates_immutable"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_analysis_runs_no_delete"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_analysis_runs_append_only"))
    elif dialect == "postgresql":
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_agent_review_candidates_no_delete ON agent_review_candidates"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_agent_review_candidates_immutable ON agent_review_candidates"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_analysis_runs_no_delete ON analysis_runs"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_analysis_runs_append_only ON analysis_runs"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS reject_agent_review_candidate_delete()"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS reject_agent_review_candidate_immutable()"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS reject_analysis_runs_delete()"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS reject_analysis_runs_update()"))
    else:
        raise RuntimeError(f"unsupported migration dialect: {dialect}")


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=512), nullable=False),
        sa.Column("schema_version", sa.String(length=512), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("failure_class", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.CheckConstraint(
            "status IN ('completed', 'analysis_unavailable', 'invalid_response', 'failed')",
            name="ck_analysis_runs_status",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND output_json IS NOT NULL AND result_hash IS NOT NULL AND failure_class IS NULL) OR "
            "(status IN ('analysis_unavailable', 'invalid_response', 'failed') AND output_json IS NULL AND result_hash IS NULL AND failure_class IS NOT NULL)",
            name="ck_analysis_runs_status_payload_coherent",
        ),
        _hash_check("input_hash"),
        sa.CheckConstraint(
            "result_hash IS NULL OR " + _hash_check("result_hash").sqltext.text,
            name="ck_analysis_runs_result_hash",
        ),
        _failure_class_check(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_runs_provider", "analysis_runs", ["provider"], unique=False)
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"], unique=False)
    op.create_index("ix_analysis_runs_input_hash", "analysis_runs", ["input_hash"], unique=False)
    op.create_index("ix_analysis_runs_result_hash", "analysis_runs", ["result_hash"], unique=False)
    op.create_index("ix_analysis_runs_created_at", "analysis_runs", ["created_at"], unique=False)
    op.create_index("ix_analysis_runs_status_created", "analysis_runs", ["status", "created_at"], unique=False)
    op.create_index("ix_analysis_runs_provider_created", "analysis_runs", ["provider", "created_at"], unique=False)

    op.create_table(
        "agent_review_candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.String(length=128), nullable=False),
        sa.Column("runner", sa.String(length=64), nullable=False),
        sa.Column("bundle_hash", sa.String(length=64), nullable=False),
        sa.Column("memo_hash", sa.String(length=64), nullable=False),
        sa.Column("memo_json", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(length=2000), nullable=True),
        sa.CheckConstraint(
            "runner IN ('codex_review_runner', 'claude_code_review_runner')",
            name="ck_review_candidates_runner",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'accepted', 'rejected')",
            name="ck_review_candidates_status",
        ),
        sa.CheckConstraint(
            "(review_status = 'pending' AND accepted_at IS NULL AND rejected_at IS NULL) OR "
            "(review_status = 'accepted' AND accepted_at IS NOT NULL AND rejected_at IS NULL) OR "
            "(review_status = 'rejected' AND accepted_at IS NULL AND rejected_at IS NOT NULL)",
            name="ck_review_candidates_status_timestamps_coherent",
        ),
        _hash_check("bundle_hash"),
        _hash_check("memo_hash"),
        sa.CheckConstraint(
            "memo_json IS NOT NULL AND length(memo_json) BETWEEN 1 AND 12000",
            name="ck_review_candidates_memo_json_bounded",
        ),
        sa.CheckConstraint(
            "review_note IS NULL OR length(review_note) <= 2000",
            name="ck_review_candidates_review_note_bounded",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id"),
    )
    op.create_index("ix_agent_review_candidates_runner", "agent_review_candidates", ["runner"], unique=False)
    op.create_index("ix_agent_review_candidates_bundle_hash", "agent_review_candidates", ["bundle_hash"], unique=False)
    op.create_index("ix_agent_review_candidates_memo_hash", "agent_review_candidates", ["memo_hash"], unique=False)
    op.create_index("ix_agent_review_candidates_review_status", "agent_review_candidates", ["review_status"], unique=False)
    op.create_index("ix_agent_review_candidates_created_at", "agent_review_candidates", ["created_at"], unique=False)
    op.create_index("ix_review_candidates_status_created", "agent_review_candidates", ["review_status", "created_at"], unique=False)
    op.create_index("ix_review_candidates_runner_created", "agent_review_candidates", ["runner", "created_at"], unique=False)

    with op.batch_alter_table("news_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("analysis_run_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("analysis_source", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("analysis_status", sa.String(length=32), nullable=True))
        batch_op.create_foreign_key(
            "fk_news_items_analysis_run_id", "analysis_runs", ["analysis_run_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_check_constraint(
            "ck_news_analysis_provenance_coherent",
            "(analysis_run_id IS NULL AND analysis_source IS NULL AND analysis_status IS NULL) OR "
            "(analysis_run_id IS NULL AND analysis_source = 'heuristic' AND analysis_status = 'disabled') OR "
            "(analysis_run_id IS NOT NULL AND analysis_source IS NOT NULL AND analysis_status IN ('completed', 'analysis_unavailable', 'invalid_response', 'failed'))",
        )
    op.create_index("ix_news_items_analysis_run_id", "news_items", ["analysis_run_id"], unique=False)
    op.create_index("ix_news_items_analysis_source", "news_items", ["analysis_source"], unique=False)
    op.create_index("ix_news_items_analysis_status", "news_items", ["analysis_status"], unique=False)
    _create_immutability_triggers()


def downgrade() -> None:
    _drop_immutability_triggers()
    op.drop_index("ix_news_items_analysis_status", table_name="news_items")
    op.drop_index("ix_news_items_analysis_source", table_name="news_items")
    op.drop_index("ix_news_items_analysis_run_id", table_name="news_items")
    with op.batch_alter_table("news_items", schema=None) as batch_op:
        batch_op.drop_constraint("fk_news_items_analysis_run_id", type_="foreignkey")
        # SQLite batch mode reconstructs the table.  Remove the provenance
        # CHECK before dropping the columns it references, otherwise the temp
        # CREATE TABLE contains dangling analysis_* identifiers.
        batch_op.drop_constraint("ck_news_analysis_provenance_coherent", type_="check")
        batch_op.drop_column("analysis_status")
        batch_op.drop_column("analysis_source")
        batch_op.drop_column("analysis_run_id")

    for index_name in (
        "ix_review_candidates_runner_created",
        "ix_review_candidates_status_created",
        "ix_agent_review_candidates_created_at",
        "ix_agent_review_candidates_review_status",
        "ix_agent_review_candidates_memo_hash",
        "ix_agent_review_candidates_bundle_hash",
        "ix_agent_review_candidates_runner",
    ):
        op.drop_index(index_name, table_name="agent_review_candidates")
    op.drop_table("agent_review_candidates")

    for index_name in (
        "ix_analysis_runs_provider_created",
        "ix_analysis_runs_status_created",
        "ix_analysis_runs_created_at",
        "ix_analysis_runs_result_hash",
        "ix_analysis_runs_input_hash",
        "ix_analysis_runs_status",
        "ix_analysis_runs_provider",
    ):
        op.drop_index(index_name, table_name="analysis_runs")
    op.drop_table("analysis_runs")
