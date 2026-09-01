"""sector snapshots: add board_type (industry/concept/market)

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-09-01

SQLite 不支持 ALTER 修改/删除约束，故使用 batch_alter_table（复制-重建表）策略。
存量 sector_snapshots 行在重建时以 server_default="industry" 填充，符合历史语义。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sector_snapshots") as batch_op:
        # 新增 board_type 列（行业/概念/全市场），存量行默认 industry
        batch_op.add_column(
            sa.Column("board_type", sa.String(length=16), nullable=False, server_default="industry")
        )
        # 旧唯一约束未含 board_type，先删后建（含 board_type），避免行业/概念同名冲突
        batch_op.drop_constraint("uq_sector_name_date_source", type_="unique")
        batch_op.create_unique_constraint(
            "uq_sector_name_date_source",
            ["sector_name", "trade_date", "source", "board_type"],
        )
        # 新复合索引：按 board_type + 板块 + 日期查询
        batch_op.create_index(
            "ix_sector_board_date",
            ["board_type", "sector_name", "trade_date"],
        )


def downgrade() -> None:
    with op.batch_alter_table("sector_snapshots") as batch_op:
        batch_op.drop_index("ix_sector_board_date")
        batch_op.drop_constraint("uq_sector_name_date_source", type_="unique")
        batch_op.create_unique_constraint(
            "uq_sector_name_date_source",
            ["sector_name", "trade_date", "source"],
        )
        batch_op.drop_column("board_type")
