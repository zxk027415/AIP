# @AI_GENERATED
"""create_day_and_point_label_isolation_tables

Revision ID: e7b9c2d4f6a8
Revises: c4f2e8a1d5b9
Create Date: 2026-08-21 10:50:00.000000

光伏故障实时点路径 redesign Phase 2：
新增 day_label_ops / day_labels / point_label_ops。
不修改、不删除现有 point_labels 与 label_ops，旧表保留作双写和回滚窗口。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7b9c2d4f6a8"
down_revision: Union[str, None] = "c4f2e8a1d5b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "day_label_ops",
        sa.Column("op_id", sa.String(length=16), nullable=False),
        sa.Column("site_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("branch_id", sa.String(length=128), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("t_start", sa.DateTime(), nullable=False),
        sa.Column("t_end", sa.DateTime(), nullable=False),
        sa.Column("label_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("reviewer", sa.String(length=128), nullable=True),
        sa.Column("source_ref", sa.String(length=256), nullable=True),
        sa.Column("rest_of_day_policy", sa.String(length=16), nullable=True),
        sa.Column("parent_op_id", sa.String(length=16), nullable=True),
        sa.Column("label_space_version", sa.String(length=64), nullable=False),
        sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("op_id"),
    )
    op.create_index(
        "ix_day_label_ops_device_date",
        "day_label_ops",
        ["site_id", "device_id", "branch_id", "business_date"],
        unique=False,
    )
    op.create_index("ix_day_label_ops_source_status", "day_label_ops", ["source", "status"], unique=False)

    op.create_table(
        "day_labels",
        sa.Column("site_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("branch_id", sa.String(length=128), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("label_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("op_id", sa.String(length=16), nullable=False),
        sa.Column("reviewer", sa.String(length=128), nullable=True),
        sa.Column("label_space_version", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("site_id", "device_id", "branch_id", "business_date"),
    )
    op.create_index("ix_day_labels_op_id", "day_labels", ["op_id"], unique=False)

    op.create_table(
        "point_label_ops",
        sa.Column("op_id", sa.String(length=16), nullable=False),
        sa.Column("site_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("branch_id", sa.String(length=128), nullable=False),
        sa.Column("t_start", sa.DateTime(), nullable=False),
        sa.Column("t_end", sa.DateTime(), nullable=False),
        sa.Column("label_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("reviewer", sa.String(length=128), nullable=True),
        sa.Column("source_ref", sa.String(length=256), nullable=True),
        sa.Column("rest_of_day_policy", sa.String(length=16), nullable=True),
        sa.Column("parent_op_id", sa.String(length=16), nullable=True),
        sa.Column("label_space_version", sa.String(length=64), nullable=False),
        sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("op_id"),
    )
    op.create_index(
        "ix_point_label_ops_device_range",
        "point_label_ops",
        ["site_id", "device_id", "branch_id", "t_start", "t_end"],
        unique=False,
    )
    op.create_index("ix_point_label_ops_source_status", "point_label_ops", ["source", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_point_label_ops_source_status", table_name="point_label_ops")
    op.drop_index("ix_point_label_ops_device_range", table_name="point_label_ops")
    op.drop_table("point_label_ops")
    op.drop_index("ix_day_labels_op_id", table_name="day_labels")
    op.drop_table("day_labels")
    op.drop_index("ix_day_label_ops_source_status", table_name="day_label_ops")
    op.drop_index("ix_day_label_ops_device_date", table_name="day_label_ops")
    op.drop_table("day_label_ops")
# @AI_GENERATED: end
