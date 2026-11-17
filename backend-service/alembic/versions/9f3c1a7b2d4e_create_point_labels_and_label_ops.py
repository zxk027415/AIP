# @AI_GENERATED
"""create_point_labels_and_label_ops

Revision ID: 9f3c1a7b2d4e
Revises: 2a240e0c2ce6
Create Date: 2026-07-30 18:00:00.000000

光伏故障逐点标签重构（pv-fault-label-segment-redesign）的存储层：
新增 point_labels（逐点标签，标签唯一事实来源）与 label_ops（标注操作日志）两张表。
两表均建在 aip_algo_platform 库（无 schema= 参数），与现有 training_samples 同库。
本迁移只做「新增」，不动任何现有表。

对应设计文档 `.kiro/specs/pv-fault-label-segment-redesign/design.md` 数据模型章节，
任务清单 `.kiro/specs/pv-fault-label-segment-redesign/tasks.md` 任务 3。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f3c1a7b2d4e'
down_revision: Union[str, None] = '2a240e0c2ce6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'point_labels',
        sa.Column('site_id', sa.String(length=128), nullable=False),
        sa.Column('device_id', sa.String(length=128), nullable=False),
        sa.Column('branch_id', sa.String(length=128), nullable=False),
        sa.Column('time', sa.DateTime(), nullable=False),
        sa.Column('label_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('op_id', sa.String(length=16), nullable=False),
        sa.Column('label_space_version', sa.String(length=64), nullable=False),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.PrimaryKeyConstraint('site_id', 'device_id', 'branch_id', 'time'),
    )
    op.create_index('ix_point_labels_op_id', 'point_labels', ['op_id'], unique=False)

    op.create_table(
        'label_ops',
        sa.Column('op_id', sa.String(length=16), nullable=False),
        sa.Column('site_id', sa.String(length=128), nullable=False),
        sa.Column('device_id', sa.String(length=128), nullable=False),
        sa.Column('branch_id', sa.String(length=128), nullable=False),
        sa.Column('t_start', sa.DateTime(), nullable=False),
        sa.Column('t_end', sa.DateTime(), nullable=False),
        sa.Column('label_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='active'),
        sa.Column('reviewer', sa.String(length=128), nullable=True),
        sa.Column('source_ref', sa.String(length=256), nullable=True),
        sa.Column('rest_of_day_policy', sa.String(length=16), nullable=True),
        sa.Column('parent_op_id', sa.String(length=16), nullable=True),
        sa.Column('label_space_version', sa.String(length=64), nullable=False),
        sa.Column('migration_batch_id', sa.String(length=64), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.PrimaryKeyConstraint('op_id'),
    )
    op.create_index(
        'ix_label_ops_device_range', 'label_ops',
        ['site_id', 'device_id', 'branch_id', 't_start', 't_end'], unique=False,
    )
    op.create_index('ix_label_ops_source_status', 'label_ops', ['source', 'status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_label_ops_source_status', table_name='label_ops')
    op.drop_index('ix_label_ops_device_range', table_name='label_ops')
    op.drop_table('label_ops')
    op.drop_index('ix_point_labels_op_id', table_name='point_labels')
    op.drop_table('point_labels')
# @AI_GENERATED: end
