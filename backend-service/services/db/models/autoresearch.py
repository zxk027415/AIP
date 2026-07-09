# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/db/models/autoresearch.py — AutoResearch 明细表 ORM 模型

定义 AutoResearch 主循环的运行时明细存储，替代原本散落的 JSON/JSONL/SQLite 文件：

  - ExperimentTrial           ← 替代 runs/{run_id}/trials.jsonl
  - ExperimentDecision        ← 替代 runs/{run_id}/decisions.jsonl
  - AutoResearchJob           ← 替代 data/autoresearch/jobs.sqlite
  - CandidateVerification     ← 替代 candidate_pool/candidate_verification_queue.json
  - CandidatePromotionLog     ← 替代 candidate_pool/baseline_comparison_promotions_log.json

现有 `experiment_run` / `candidate_pool` / `knowledge_claim` 三张表在 load_forecast.py 中定义，
本文件仅补充新增的明细表。所有表统一在 aip_algo_platform 库下（不使用独立 schema）。

关联规约：
  - 关联规划文档：docs/specs/autoresearch-mysql-migration/plan.md
  - 关联 schema 设计：docs/specs/autoresearch-mysql-migration/design.md
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


class ExperimentTrial(Base):
    """AutoResearch 单轮试验明细 — 一个 run 里每一次 iteration 一行。

    字段职责：
      - run_id            — 关联到 experiment_run.id
      - iteration_no      — run 内的轮次序号（从 1 开始）
      - status            — pending/running/success/failed/skipped/cancelled
      - override_json     — 该轮应用的 override（train_days / node_param_patches 等）
      - evidence_json     — 该轮产出的证据（windows_total, windows_challenger_better, failure_reason）
      - mape_improvement  — 相对 baseline 的 MAPE 变化（负值表示更好）
      - baseline_mape     — baseline 侧 MAPE
      - challenger_mape   — challenger 侧 MAPE
    """

    __tablename__ = "experiment_trial"
    __table_args__ = (
        Index("ix_trial_run_iter", "run_id", "iteration_no"),
        Index("ix_trial_run_status", "run_id", "status"),
        UniqueConstraint("run_id", "iteration_no", name="uq_trial_run_iter"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    iteration_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    override_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    mape_improvement: Mapped[float] = mapped_column(Float, nullable=True)
    baseline_mape: Mapped[float] = mapped_column(Float, nullable=True)
    challenger_mape: Mapped[float] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ExperimentDecision(Base):
    """AutoResearch 决策事件流 — 一条决策/事件一行（append-only）。

    字段职责：
      - run_id          — 关联到 experiment_run.id
      - seq             — run 内的递增序号（保证事件顺序）
      - decision_type   — run_started / cancel_requested / proposal_applied /
                          proposal_rejected / manual_continue / run_resumed / run_finished / run_failed
      - actor           — user / system
      - payload_json    — 事件详细内容（自由结构）
    """

    __tablename__ = "experiment_decision"
    __table_args__ = (
        Index("ix_decision_run_seq", "run_id", "seq"),
        Index("ix_decision_run_type", "run_id", "decision_type"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AutoResearchJob(Base):
    """AutoResearch Job Queue — 跨机器可用的任务队列，替代 jobs.sqlite。

    字段职责：
      - run_id            — 主键（也是 experiment_run.id）
      - status            — pending/running/success/failed/cancelled/interrupted
      - pid               — worker 进程 PID（诊断用）
      - host              — worker 所在机器 hostname（跨机器关键）
      - payload_json      — 任务参数（baseline_workflow_id / total_iterations / resume 等）
      - heartbeat_at      — worker 最后一次心跳时间
      - cancel_requested  — 是否被请求取消
    """

    __tablename__ = "autoresearch_job"
    __table_args__ = (
        Index("ix_job_status_hb", "status", "heartbeat_at"),
        Index("ix_job_created", "created_at"),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    pid: Mapped[int] = mapped_column(Integer, nullable=True)
    host: Mapped[str] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CandidateVerification(Base):
    """候选复验队列 — 候选池 → 多窗口复验 → prelaunch 的中间态。

    字段职责：
      - id                — 复验项 ID
      - candidate_id      — 关联 candidate_pool.id
      - slot              — 分区键
      - source_run_id     — 候选来自哪个 run
      - source_iteration  — 候选来自 run 的哪一轮
      - status            — queued/running/passed/failed/cancelled
      - config_json       — 复验参数（windows / aggregation / min_wins 等）
      - evidence_json     — 复验产出（multi_window_confirmed / windows_challenger_better）
    """

    __tablename__ = "candidate_verification"
    __table_args__ = (
        Index("ix_ver_slot_status", "slot", "status"),
        Index("ix_ver_candidate", "candidate_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    source_run_id: Mapped[str] = mapped_column(String(64), nullable=True)
    source_iteration: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class CandidatePromotionLog(Base):
    """候选晋升审计日志 — 每次 Promote/Reject 一行（append-only）。

    字段职责：
      - slot           — 分区键
      - candidate_id   — 关联 candidate_pool.id
      - action         — promoted / rejected / force_promoted
      - actor          — user / system
      - reason         — 文本原因
      - payload_json   — 完整上下文（触发时的 evidence、diff 等）
    """

    __tablename__ = "candidate_promotion_log"
    __table_args__ = (
        Index("ix_promo_slot_created", "slot", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(String(2048), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

# @AI_GENERATED: end
