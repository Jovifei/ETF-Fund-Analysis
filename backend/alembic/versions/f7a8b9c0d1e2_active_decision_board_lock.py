"""enforce one active decision-board refresh

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_index(
        "uq_task_runs_active_decision_board_refresh", "task_runs", ["task_name"], unique=True,
        sqlite_where=sa.text("task_name = 'refresh_decision_board' AND status IN ('queued', 'running')"),
        postgresql_where=sa.text("task_name = 'refresh_decision_board' AND status IN ('queued', 'running')"),
    )

def downgrade() -> None:
    op.drop_index("uq_task_runs_active_decision_board_refresh", table_name="task_runs")
