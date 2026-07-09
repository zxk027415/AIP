# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/db/models/deployment.py — 部署链路 ORM 模型

替代原本散落在 data/deployment/ 和 data/scheduler/ 下的 JSON 文件：

  - DeploymentSlot           ← 替代 slots.json（槽位级）
  - DeploymentModelVersion   ← 替代 slots.json 中的 production_model/shadow_models/prelaunch_models
  - SwitchEvent              ← 替代 data/deployment/switch_log.json
  - SchedulerTask            ← 替代 data/scheduler/tasks.json

`prelaunch_queue` 表已在 load_forecast.py 定义，本文件不重复。
`version_registry` 表已在 load_forecast.py 定义（历史版本注册），本文件不重复。

关联文档：docs/specs/autoresearch-mysql-migration/design.md
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BIGINT,
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeploymentSlot(Base):
    """部署槽位 — 一个 slot 一行，记录生产 workflow 和资源上限。

    字段职责：
      - slot                     — 主键（load_forecast/default 等）
      - production_workflow_id   — 当前生产模型指向的 workflow_id
      - cooldown_days            — 切换冷却期（天）
      - max_shadow_slots         — 影子池上限
      - max_prelaunch_slots      — 预上线池上限
      - training_window_days     — 训练窗口天数（结构参数，人工运营决策）
      - switch_observation_days  — 切换观察窗口
    """

    __tablename__ = "deployment_slot"

    slot: Mapped[str] = mapped_column(String(64), primary_key=True)
    production_workflow_id: Mapped[str] = mapped_column(String(128), nullable=True)
    cooldown_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_shadow_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_prelaunch_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    training_window_days: Mapped[int] = mapped_column(Integer, nullable=True)
    switch_observation_days: Mapped[int] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DeploymentModelVersion(Base):
    """部署模型版本 — 每个 workflow_id 在某个 slot 下的状态记录。

    一个 slot 对应多行：
      - status='production'（唯一）
      - status='shadow'（0-N，锦标赛）
      - status='prelaunch'（0-M，独立闸门）
      - status='retired'（历史归档）

    字段职责：
      - slot / workflow_id       — 联合唯一
      - status                   — production/shadow/prelaunch/retired
      - accuracy_score           — 精度评分（MAPE 或复合指标）
      - consecutive_better_days  — 连续跑赢生产的天数（切换判定用）
      - source_run_id            — 来自哪个 AutoResearch run
      - source_candidate_id      — 来自哪个候选
      - prelaunch_meta_json      — 预上线元数据（observation_days / graduate_tolerance_pct /
                                    current_rolling_mape / production_rolling_mape /
                                    evaluated_cycles / note），status='prelaunch' 时才有值
    """

    __tablename__ = "deployment_model_version"
    __table_args__ = (
        UniqueConstraint("slot", "workflow_id", name="uq_dmv_slot_wf"),
        Index("ix_dmv_slot_status", "slot", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version_tag: Mapped[str] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    accuracy_score: Mapped[float] = mapped_column(Float, nullable=True)
    consecutive_better_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_run_id: Mapped[str] = mapped_column(String(64), nullable=True)
    source_candidate_id: Mapped[str] = mapped_column(String(64), nullable=True)
    prelaunch_meta_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SwitchEvent(Base):
    """切换事件 — append-only 审计日志，替代 switch_log.json。

    字段职责：
      - event_id          — 事件唯一 ID
      - slot              — 分区键
      - trigger_type      — auto/manual/rollback
      - from_workflow_id  — 切换前的生产 workflow
      - to_workflow_id    — 切换后的生产 workflow
      - from_mape         — 切换前的 MAPE
      - to_mape           — 切换后的 MAPE
      - actor             — 触发者（system/user 名）
      - reason            — 切换原因文本
    """

    __tablename__ = "switch_event"
    __table_args__ = (
        Index("ix_switch_slot_ts", "slot", "ts"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_workflow_id: Mapped[str] = mapped_column(String(128), nullable=True)
    to_workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    from_mape: Mapped[float] = mapped_column(Float, nullable=True)
    to_mape: Mapped[float] = mapped_column(Float, nullable=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(String(2048), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SchedulerTask(Base):
    """Cron 定时任务 — 替代 data/scheduler/tasks.json。

    字段职责：
      - task_id              — 任务 ID
      - name                 — 显示名称
      - task_type            — lf_data_pull / lf_train / lf_predict / lf_accuracy_backfill /
                                mock_data_feed 等
      - slot                 — 关联的部署槽位
      - cron_expression      — 5-段 cron 表达式
      - enabled              — 是否启用
      - payload_json         — 任务参数
      - last_execution_time  — 最近一次执行时间（trigger-now 或 cron）
      - last_result_json     — 最近一次执行结果（status/output/error）
    """

    __tablename__ = "scheduler_task"
    __table_args__ = (
        Index("ix_task_slot_enabled", "slot", "enabled"),
    )

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    slot: Mapped[str] = mapped_column(String(64), nullable=True)
    cron_expression: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    last_execution_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_result_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

# @AI_GENERATED: end
