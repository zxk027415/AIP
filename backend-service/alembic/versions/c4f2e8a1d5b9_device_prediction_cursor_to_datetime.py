# @AI_GENERATED
"""device_prediction_cursor: last_predicted_business_date → last_predicted_time

Revision ID: c4f2e8a1d5b9
Revises: b2e6a1c9d3f7
Create Date: 2026-08-11 20:00:00.000000

device_prediction_cursor 表从"按天游标"改为"精确时刻游标"：

- 删除 last_predicted_business_date（DATE）
- 新增 last_predicted_time（DATETIME，可空）

表当前为空表（从未被生产代码写入），无历史数据需要转换。
对应设计：pv_prediction 任务改造为点粒度时间窗口查询——每次 cron 触发时
取 (last_predicted_time, cutoff] 窗口内所有未预测的测量点，不依赖"设备-天数据是否到齐"。

初始值由 scripts/init_device_prediction_cursors.py 单独写入，
不在本迁移里硬编码（迁移应只改结构，不写业务数据）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4f2e8a1d5b9"
down_revision: Union[str, None] = "b2e6a1c9d3f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 删旧的 DATE 游标列
    op.drop_column("device_prediction_cursor", "last_predicted_business_date")
    # 新增精确时刻游标列（可空；NULL 表示该设备从未被预测过，从头取所有数据）
    op.add_column(
        "device_prediction_cursor",
        sa.Column("last_predicted_time", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("device_prediction_cursor", "last_predicted_time")
    op.add_column(
        "device_prediction_cursor",
        sa.Column("last_predicted_business_date", sa.Date(), nullable=True),
    )
# @AI_GENERATED: end
