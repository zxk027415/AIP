# @AI_GENERATED
"""pv_daily_rolling_ingestion_tracking

Revision ID: b2e6a1c9d3f7
Revises: 9f3c1a7b2d4e
Create Date: 2026-08-04 20:00:00.000000

光伏故障"按日滚动预测"生产表结构：

1. 新增 measurement_ingestion_daily —— 设备-天数据完整性判定表。
2. 新增 device_prediction_cursor —— 按设备维度的预测游标（替代全局
   prediction_cursor.json）。
3. 新增 pv_mock_release_schedule —— mock 喂数据错峰释放计划（mock 专用）。
4. training_samples 新增 data_source 列（VARCHAR(16) NOT NULL DEFAULT 'mock'）
   —— 区分数据来源（mock / production），逻辑隔离而非物理隔离。历史遗留行
   在 upgrade() 中一次性显式 UPDATE 为 'mock'（server_default 只影响新插入行，
   不会自动回填已有行）。
5. prediction_records 新增 business_date（DATE，可空）与 sample_id
   （VARCHAR(128)，可空）两列，并加复合索引，支持按业务日审计与样本溯源。

本迁移只做新增表/新增列，不修改 training_samples 现有主键结构（自增 id 保留），
不涉及分区表改造——分区/复合主键是另一个更高风险的改动，需单独确认后再做。

对应设计讨论：.kiro/specs/pv-fault-timeseries-diagnosis/ 相关会话记录
（按日滚动预测生产表结构 + mock/生产数据来源隔离）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2e6a1c9d3f7'
down_revision: Union[str, None] = '9f3c1a7b2d4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. measurement_ingestion_daily
    # ------------------------------------------------------------------
    op.create_table(
        'measurement_ingestion_daily',
        sa.Column('site_id', sa.String(length=128), nullable=False),
        sa.Column('device_id', sa.String(length=128), nullable=False),
        sa.Column('branch_id', sa.String(length=128), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('point_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expected_point_count', sa.Integer(), nullable=False, server_default='288'),
        sa.Column('is_complete', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('first_seen_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.PrimaryKeyConstraint('site_id', 'device_id', 'branch_id', 'business_date'),
    )
    op.create_index(
        'ix_ingestion_daily_complete', 'measurement_ingestion_daily',
        ['site_id', 'is_complete', 'business_date'], unique=False,
    )

    # ------------------------------------------------------------------
    # 2. device_prediction_cursor
    # ------------------------------------------------------------------
    op.create_table(
        'device_prediction_cursor',
        sa.Column('site_id', sa.String(length=128), nullable=False),
        sa.Column('device_id', sa.String(length=128), nullable=False),
        sa.Column('branch_id', sa.String(length=128), nullable=False),
        sa.Column('last_predicted_business_date', sa.Date(), nullable=True),
        sa.Column('last_predicted_at', sa.DateTime(), nullable=True),
        sa.Column('model_version_id', sa.String(length=64), nullable=True),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.PrimaryKeyConstraint('site_id', 'device_id', 'branch_id'),
    )

    # ------------------------------------------------------------------
    # 3. pv_mock_release_schedule（mock 专用）
    # ------------------------------------------------------------------
    op.create_table(
        'pv_mock_release_schedule',
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('site_id', sa.String(length=128), nullable=False),
        sa.Column('device_id', sa.String(length=128), nullable=False),
        sa.Column('branch_id', sa.String(length=128), nullable=False),
        sa.Column('planned_batch_index', sa.Integer(), nullable=False),
        sa.Column('delay_ticks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_dropped', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('released_at', sa.DateTime(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.PrimaryKeyConstraint('business_date', 'site_id', 'device_id', 'branch_id'),
    )
    op.create_index(
        'ix_mock_release_date_batch', 'pv_mock_release_schedule',
        ['business_date', 'planned_batch_index'], unique=False,
    )

    # ------------------------------------------------------------------
    # 4. training_samples.data_source
    # ------------------------------------------------------------------
    op.add_column(
        'training_samples',
        sa.Column('data_source', sa.String(length=16), nullable=False, server_default='mock'),
    )
    # server_default 只影响本迁移之后的新插入行；历史遗留行需要显式回填，
    # 否则它们的 data_source 会是 NULL（列声明 NOT NULL，实际上 ADD COLUMN
    # 时 MySQL 会用 server_default 填充已有行，这里显式 UPDATE 是双重保险，
    # 幂等、无副作用）。
    op.execute("UPDATE training_samples SET data_source = 'mock' WHERE data_source IS NULL OR data_source = ''")

    # ------------------------------------------------------------------
    # 5. prediction_records.business_date / sample_id
    # ------------------------------------------------------------------
    op.add_column('prediction_records', sa.Column('business_date', sa.Date(), nullable=True))
    op.add_column('prediction_records', sa.Column('sample_id', sa.String(length=128), nullable=True))
    op.create_index(
        'ix_prediction_records_device_business_date', 'prediction_records',
        ['site_id', 'device_id', 'branch_id', 'business_date'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_prediction_records_device_business_date', table_name='prediction_records')
    op.drop_column('prediction_records', 'sample_id')
    op.drop_column('prediction_records', 'business_date')

    op.drop_column('training_samples', 'data_source')

    op.drop_index('ix_mock_release_date_batch', table_name='pv_mock_release_schedule')
    op.drop_table('pv_mock_release_schedule')

    op.drop_table('device_prediction_cursor')

    op.drop_index('ix_ingestion_daily_complete', table_name='measurement_ingestion_daily')
    op.drop_table('measurement_ingestion_daily')
# @AI_GENERATED: end
