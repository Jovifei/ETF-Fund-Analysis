"""Replay receipts for signed device requests (no credential material)."""
from alembic import op
import sqlalchemy as sa

revision = "d40609090002"
down_revision = "d40609090001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("workspace_bridge_receipts",
        sa.Column("receipt_id", sa.String(65), primary_key=True),
        sa.Column("device_id", sa.String(32), sa.ForeignKey("workspace_bridge_devices.device_id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workspace_bridge_receipts_device_id", "workspace_bridge_receipts", ["device_id"])
    op.create_index("ix_workspace_bridge_receipts_created_at", "workspace_bridge_receipts", ["created_at"])


def downgrade():
    op.drop_table("workspace_bridge_receipts")
