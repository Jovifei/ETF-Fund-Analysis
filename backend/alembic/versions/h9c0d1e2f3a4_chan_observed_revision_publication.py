"""persist immutable observed revisions and transactional stream heads

Revision ID: h9c0d1e2f3a4
Revises: g8b9c0d1e2f3
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h9c0d1e2f3a4"
down_revision: str | None = "g8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IMMUTABLE_TABLES = (
    "chan_research_observations",
    "chan_structure_revisions",
    "chan_observed_transitions",
)


def _create_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for table in _IMMUTABLE_TABLES:
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_{table}_no_update
                    BEFORE UPDATE ON {table}
                    BEGIN
                        SELECT RAISE(ABORT, '{table} are immutable');
                    END
                    """
                )
            )
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_{table}_no_delete
                    BEFORE DELETE ON {table}
                    BEGIN
                        SELECT RAISE(ABORT, '{table} are immutable');
                    END
                    """
                )
            )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_chan_research_stream_heads_no_delete
                BEFORE DELETE ON chan_research_stream_heads
                BEGIN
                    SELECT RAISE(ABORT, 'chan research stream heads cannot be deleted');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_chan_research_stream_heads_monotonic
                BEFORE UPDATE OF latest_sequence_number, latest_observation_id ON chan_research_stream_heads
                WHEN NEW.latest_sequence_number < OLD.latest_sequence_number
                BEGIN
                    SELECT RAISE(ABORT, 'chan research stream head cannot move backward');
                END
                """
            )
        )
    elif dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION reject_chan_immutable_write()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
                END;
                $$
                """
            )
        )
        for table in _IMMUTABLE_TABLES:
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_{table}_no_update
                    BEFORE UPDATE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION reject_chan_immutable_write()
                    """
                )
            )
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_{table}_no_delete
                    BEFORE DELETE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION reject_chan_immutable_write()
                    """
                )
            )
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION reject_chan_stream_head_delete()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'chan research stream heads cannot be deleted';
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_chan_research_stream_heads_no_delete
                BEFORE DELETE ON chan_research_stream_heads
                FOR EACH ROW EXECUTE FUNCTION reject_chan_stream_head_delete()
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION reject_chan_stream_head_rewind()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF NEW.latest_sequence_number < OLD.latest_sequence_number THEN
                        RAISE EXCEPTION 'chan research stream head cannot move backward';
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
                CREATE TRIGGER trg_chan_research_stream_heads_monotonic
                BEFORE UPDATE OF latest_sequence_number, latest_observation_id ON chan_research_stream_heads
                FOR EACH ROW EXECUTE FUNCTION reject_chan_stream_head_rewind()
                """
            )
        )
    else:
        raise RuntimeError(f"unsupported Chan persistence migration dialect: {dialect}")


def upgrade() -> None:
    op.create_table(
        "chan_research_observations",
        sa.Column("observation_id", sa.String(length=64), primary_key=True),
        sa.Column("stream_id", sa.String(length=64), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("instrument", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("series_id", sa.String(length=256), nullable=False),
        sa.Column("price_basis_id", sa.String(length=256), nullable=False),
        sa.Column("adjustment_version", sa.String(length=256), nullable=False),
        sa.Column("input_revision_id", sa.String(length=256), nullable=False),
        sa.Column("settlement_status", sa.String(length=16), nullable=False),
        sa.Column("config_id", sa.String(length=256), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("cutoff", sa.Integer(), nullable=False),
        sa.Column("cutoff_bar_id", sa.String(length=256), nullable=False),
        sa.Column("cutoff_at", sa.String(length=40), nullable=False),
        sa.Column("engine_id", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("dialect_id", sa.String(length=128), nullable=False),
        sa.Column("engine_confirmation", sa.String(length=16), nullable=False),
        sa.Column("application_observation_status", sa.String(length=16), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("cutoff > 0", name="ck_chan_observation_cutoff_positive"),
        sa.CheckConstraint("sequence_number > 0", name="ck_chan_observation_sequence_positive"),
        sa.CheckConstraint("engine_confirmation = 'unknown'", name="ck_chan_observation_unconfirmed"),
        sa.CheckConstraint("application_observation_status = 'observed'", name="ck_chan_observation_observed"),
        sa.UniqueConstraint("stream_id", "observation_id", name="uq_chan_observation_stream_id"),
        sa.UniqueConstraint("stream_id", "sequence_number", name="uq_chan_observation_stream_sequence"),
        sa.UniqueConstraint(
            "stream_id", "sequence_number", "observation_id", name="uq_chan_observation_stream_sequence_id"
        ),
    )
    op.create_index(
        "ix_chan_observations_stream_cutoff",
        "chan_research_observations",
        ["stream_id", "cutoff", "cutoff_at"],
    )
    op.create_table(
        "chan_structure_revisions",
        sa.Column("revision_id", sa.String(length=64), primary_key=True),
        sa.Column("stream_id", sa.String(length=64), nullable=False),
        sa.Column("observation_id", sa.String(length=64), nullable=False),
        sa.Column("structure_key", sa.String(length=64), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["stream_id", "observation_id"],
            ["chan_research_observations.stream_id", "chan_research_observations.observation_id"],
            name="fk_chan_revision_observation",
        ),
        sa.UniqueConstraint("stream_id", "observation_id", "structure_key", name="uq_chan_revision_observation_structure"),
    )
    op.create_index(
        "ix_chan_revisions_stream_observation",
        "chan_structure_revisions",
        ["stream_id", "observation_id"],
    )
    op.create_table(
        "chan_observed_transitions",
        sa.Column("stream_id", sa.String(length=64), primary_key=True),
        sa.Column("observation_id", sa.String(length=64), primary_key=True),
        sa.Column("structure_key", sa.String(length=64), primary_key=True),
        sa.Column("cutoff_bar_id", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revision_id", sa.String(length=64), nullable=True),
        sa.Column("prior_revision_id", sa.String(length=64), nullable=True),
        sa.Column("reappearance", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["stream_id", "observation_id"],
            ["chan_research_observations.stream_id", "chan_research_observations.observation_id"],
            name="fk_chan_transition_observation",
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["chan_structure_revisions.revision_id"], name="fk_chan_transition_revision"),
        sa.ForeignKeyConstraint(
            ["prior_revision_id"],
            ["chan_structure_revisions.revision_id"],
            name="fk_chan_transition_prior_revision",
        ),
        sa.CheckConstraint(
            "status IN ('OBSERVED_NEW', 'OBSERVED_CHANGED', 'OBSERVED_UNCHANGED', 'OBSERVED_ABSENT')",
            name="ck_chan_transition_status",
        ),
        sa.CheckConstraint("reappearance = false OR status = 'OBSERVED_NEW'", name="ck_chan_transition_reappearance"),
    )
    op.create_index(
        "ix_chan_transitions_stream_structure",
        "chan_observed_transitions",
        ["stream_id", "structure_key"],
    )
    op.create_table(
        "chan_research_stream_heads",
        sa.Column("stream_id", sa.String(length=64), primary_key=True),
        sa.Column("latest_sequence_number", sa.Integer(), nullable=False),
        sa.Column("instrument", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("series_id", sa.String(length=256), nullable=False),
        sa.Column("price_basis_id", sa.String(length=256), nullable=False),
        sa.Column("adjustment_version", sa.String(length=256), nullable=False),
        sa.Column("config_id", sa.String(length=256), nullable=False),
        sa.Column("engine_id", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("dialect_id", sa.String(length=128), nullable=False),
        sa.Column("latest_observation_id", sa.String(length=64), nullable=False),
        sa.CheckConstraint("latest_sequence_number > 0", name="ck_chan_stream_head_sequence_positive"),
        sa.ForeignKeyConstraint(
            ["stream_id", "latest_sequence_number", "latest_observation_id"],
            [
                "chan_research_observations.stream_id",
                "chan_research_observations.sequence_number",
                "chan_research_observations.observation_id",
            ],
            name="fk_chan_stream_head_observation",
        ),
    )
    _create_guards()


def downgrade() -> None:
    op.drop_table("chan_research_stream_heads")
    op.drop_index("ix_chan_transitions_stream_structure", table_name="chan_observed_transitions")
    op.drop_table("chan_observed_transitions")
    op.drop_index("ix_chan_revisions_stream_observation", table_name="chan_structure_revisions")
    op.drop_table("chan_structure_revisions")
    op.drop_index("ix_chan_observations_stream_cutoff", table_name="chan_research_observations")
    op.drop_table("chan_research_observations")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("DROP FUNCTION IF EXISTS reject_chan_immutable_write()"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS reject_chan_stream_head_delete()"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS reject_chan_stream_head_rewind()"))
