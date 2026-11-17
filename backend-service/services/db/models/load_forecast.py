# -*- coding: utf-8 -*-
"""
services/db/models/load_forecast.py — 负荷预测 ORM 模型

定义 aip_algo_platform 库下的 8 张负荷预测相关表。
原设计使用独立 schema `load_forecast`；现统一迁入 aip_algo_platform，
去掉 schema= 参数，降低部署权限要求。

Requirements: 2.1, 2.2, 2.4, 2.5
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

# schema 统一到 aip_algo_platform，不再跨库
_SCHEMA = None


class StationData(Base):
    """站点实测数据 — 存储各站点按时间戳和特征名归档的测量值。"""

    __tablename__ = "station_data"
    __table_args__ = (
        Index("ix_station_data_slot_station_ts", "slot", "station_id", "timestamp_utc"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    feature_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ExperimentRun(Base):
    """AutoResearch 实验运行记录 — 记录每次自动实验的配置、状态、快照和洞察结论。

    字段职责（key fields）：
      - id                    — run_id，形如 `ares-xxxxxxxxxxxx`
      - slot                  — 部署槽位（分区键）
      - status                — 当前状态：pending/running/waiting_review/cancelling/
                                success/failed/cancelled/interrupted
      - previous_status       — 服务重启前的状态（interrupted 前的原状态）
      - recoverable           — 是否可从 snapshot 恢复
      - baseline_workflow_id  — 该 run 的 baseline 工作流 ID
      - current_iteration     — 当前已完成到第几轮
      - total_iterations      — 总轮数（compare_config.total_iterations）
      - config                — 完整 compare_config JSON（search_space / evaluation_contract 等）
      - runtime_patch         — 该 run 累计的运行时补丁
      - snapshot_state        — 完整 state JSON（用于断点恢复），替代 snapshot.json
      - run_insight           — run 结束时生成的 insight，替代 insights/{run_id}.json
      - terminal_status       — 结束状态标签
      - error_message         — 失败原因文本
      - started_at / finished_at / interrupted_at / resumed_at / updated_at — 时间戳
    """

    __tablename__ = "experiment_run"
    __table_args__ = (
        Index("ix_experiment_run_slot_status", "slot", "status"),
        Index("ix_experiment_run_updated_at", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # @AI_GENERATED: AutoResearch MySQL 迁移新增字段
    previous_status: Mapped[str] = mapped_column(String(32), nullable=True)
    recoverable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    baseline_workflow_id: Mapped[str] = mapped_column(String(128), nullable=True)
    current_iteration: Mapped[int] = mapped_column(Integer, nullable=True)
    total_iterations: Mapped[int] = mapped_column(Integer, nullable=True)
    # @AI_GENERATED: end
    config: Mapped[dict] = mapped_column(JSON, nullable=True)
    runtime_patch: Mapped[dict] = mapped_column(JSON, nullable=True)
    # @AI_GENERATED: 完整 state 快照（断点恢复用），替代 snapshot.json
    snapshot_state: Mapped[dict] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str] = mapped_column(String(2048), nullable=True)
    # @AI_GENERATED: end
    run_insight: Mapped[dict] = mapped_column(JSON, nullable=True)
    terminal_status: Mapped[str] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    # @AI_GENERATED: 时间戳字段
    interrupted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    resumed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    # @AI_GENERATED: end


class CandidatePool(Base):
    """候选池 — 记录每个实验轮次产出的候选配置及其评估结果。"""

    __tablename__ = "candidate_pool"
    __table_args__ = (
        Index("ix_candidate_pool_slot_patch_sig", "slot", "patch_signature"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    patch_signature: Mapped[str] = mapped_column(String(256), nullable=False)
    best_mape: Mapped[float] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class KnowledgeClaim(Base):
    """知识声明 — 存储从实验中沉淀的可复用场景经验和置信度评分。"""

    __tablename__ = "knowledge_claim"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario_fingerprint: Mapped[str] = mapped_column(String(256), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_data: Mapped[dict] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    source_run_id: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    decayed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class PredictionResult(Base):
    """预测结果 — 保存每次预测周期的预测值、实际值及评估状态。"""

    __tablename__ = "prediction_result"
    __table_args__ = (
        Index("ix_pred_result_slot_wf_ts", "slot", "workflow_id", "forecast_timestamp"),
        Index("ix_pred_result_slot_cycle", "slot", "prediction_cycle_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    prediction_cycle_id: Mapped[str] = mapped_column(String(128), nullable=False)
    forecast_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    is_shadow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class AccuracyMetric(Base):
    """精度指标 — 按槽位和工作流聚合的滚动 MAPE/MAE 及周期统计。"""

    __tablename__ = "accuracy_metric"
    __table_args__ = (
        UniqueConstraint("slot", "workflow_id", name="uq_accuracy_metric_slot_wf"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rolling_mape: Mapped[float] = mapped_column(Float, nullable=True)
    rolling_mae: Mapped[float] = mapped_column(Float, nullable=True)
    valid_cycle_count: Mapped[int] = mapped_column(Integer, nullable=True)
    total_cycle_count: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class VersionRegistry(Base):
    """版本注册表 — 登记各槽位下工作流模板的历史版本及其基线精度。"""

    __tablename__ = "version_registry"
    __table_args__ = (
        UniqueConstraint("slot", "workflow_id", "version_tag", name="uq_version_registry_slot_wf_tag"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_run_id: Mapped[str] = mapped_column(String(64), nullable=True)
    source_candidate_id: Mapped[str] = mapped_column(String(64), nullable=True)
    baseline_mape: Mapped[float] = mapped_column(Float, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PrelaunchQueue(Base):
    """预上线队列 — 追踪候选配置灰度上线期间的精度监控和毕业判断。"""

    __tablename__ = "prelaunch_queue"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    observation_days: Mapped[int] = mapped_column(Integer, nullable=False)
    graduate_tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False)
    current_rolling_mape: Mapped[float] = mapped_column(Float, nullable=True)
    production_rolling_mape: Mapped[float] = mapped_column(Float, nullable=True)
    evaluated_cycles: Mapped[int] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    graduated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
