# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/db/repositories/autoresearch.py — AutoResearch 相关 CRUD Repository

覆盖 AutoResearch 主循环所需的所有 DB 操作，供 Phase 1 双写和 Phase 2 读切换调用。

包含的表：
  - experiment_run          — 主状态 + snapshot_state 断点快照
  - experiment_trial        — 每轮明细
  - experiment_decision     — 决策事件流
  - autoresearch_job        — 跨机器 job 队列（替代 jobs.sqlite）
  - candidate_pool          — 候选池（复用已有表）
  - candidate_verification  — 复验队列
  - candidate_promotion_log — 候选晋升审计
  - knowledge_claim         — 知识层（复用已有表）

所有写操作走 DBAdapter.get_sync_session 管理事务，失败自动 rollback。

关联文档：docs/specs/autoresearch-mysql-migration/design.md 第八节
"""

from __future__ import annotations

import socket
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError

from ..adapter import DBAdapter
from ..models.load_forecast import CandidatePool, ExperimentRun, KnowledgeClaim
from ..models.autoresearch import (
    AutoResearchJob,
    CandidatePromotionLog,
    CandidateVerification,
    ExperimentDecision,
    ExperimentTrial,
)


# 心跳超时阈值：worker 超过这个时间没心跳视为死亡（与旧 jobs.sqlite 保持一致 120s）
HEARTBEAT_TIMEOUT_SECONDS = 120

# 可恢复状态集合（服务重启时会被标记为 interrupted）
INTERRUPTIBLE_STATUSES = {"pending", "running", "waiting_review", "cancelling"}


class AutoResearchRepository:
    """AutoResearch 数据 CRUD 集合。"""

    def __init__(self, adapter: DBAdapter) -> None:
        self._adapter = adapter

    # ==================================================================
    # experiment_run — 主状态记录
    # ==================================================================

    def upsert_run(self, run_data: Dict[str, Any]) -> ExperimentRun:
        """Upsert 一条 run 记录（按 id 判重）。

        run_data 里至少要有 id / slot / status；其他字段可选。
        更新时会自动刷新 updated_at 为当前时间。
        """
        if "id" not in run_data:
            raise ValueError("run_data must contain 'id'")

        with self._adapter.get_sync_session() as session:
            obj = session.get(ExperimentRun, run_data["id"])
            if obj is None:
                obj = ExperimentRun(**run_data)
                session.add(obj)
            else:
                for k, v in run_data.items():
                    setattr(obj, k, v)
            obj.updated_at = datetime.utcnow()
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def get_run(self, run_id: str) -> Optional[ExperimentRun]:
        """按 run_id 查询单条 run。"""
        with self._adapter.get_sync_session() as session:
            obj = session.get(ExperimentRun, run_id)
            if obj is not None:
                session.expunge(obj)
            return obj

    def list_runs(
        self,
        slot: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ExperimentRun]:
        """列出 run，按 updated_at 倒序。可按 slot / status 过滤。"""
        with self._adapter.get_sync_session() as session:
            q = session.query(ExperimentRun)
            if slot is not None:
                q = q.filter(ExperimentRun.slot == slot)
            if status is not None:
                q = q.filter(ExperimentRun.status == status)
            rows = (
                q.order_by(ExperimentRun.updated_at.desc()).limit(max(1, limit)).all()
            )
            session.expunge_all()
            return rows

    def mark_interrupted_running_runs(self) -> List[str]:
        """服务启动时调用：把仍处于 running/pending/waiting_review/cancelling 的 run
        标记为 interrupted，返回被标记的 run_id 列表。
        对应旧代码 `AutoResearchRunStore.scan_and_mark_interrupted()`。
        """
        now = datetime.utcnow()
        marked: List[str] = []
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(ExperimentRun)
                .filter(ExperimentRun.status.in_(INTERRUPTIBLE_STATUSES))
                .all()
            )
            for row in rows:
                row.previous_status = row.status
                row.status = "interrupted"
                row.recoverable = True
                row.interrupted_at = now
                row.updated_at = now
                if not row.error_message:
                    row.error_message = "服务重启或内存状态丢失，运行已中断"
                marked.append(row.id)
            return marked

    # ==================================================================
    # experiment_trial — 每轮明细
    # ==================================================================

    def append_trial(self, run_id: str, trial: Dict[str, Any]) -> ExperimentTrial:
        """追加一条 trial 记录。若同 run_id + iteration_no 已存在则更新（upsert）。"""
        if "iteration_no" not in trial or "status" not in trial:
            raise ValueError("trial must contain 'iteration_no' and 'status'")

        with self._adapter.get_sync_session() as session:
            obj = (
                session.query(ExperimentTrial)
                .filter_by(run_id=run_id, iteration_no=trial["iteration_no"])
                .first()
            )
            payload = {**trial, "run_id": run_id}
            if obj is None:
                obj = ExperimentTrial(**payload)
                session.add(obj)
            else:
                for k, v in payload.items():
                    setattr(obj, k, v)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def list_trials(self, run_id: str, limit: int = 500) -> List[ExperimentTrial]:
        """列出某 run 的所有 trial，按 iteration_no 升序。"""
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(ExperimentTrial)
                .filter(ExperimentTrial.run_id == run_id)
                .order_by(ExperimentTrial.iteration_no.asc())
                .limit(max(1, limit))
                .all()
            )
            session.expunge_all()
            return rows

    def get_completed_iterations(self, run_id: str) -> Set[int]:
        """断点恢复用：返回已 success 完成的 iteration_no 集合。"""
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(ExperimentTrial.iteration_no)
                .filter(
                    ExperimentTrial.run_id == run_id,
                    ExperimentTrial.status == "success",
                )
                .all()
            )
            return {r[0] for r in rows}

    # ==================================================================
    # experiment_decision — 决策事件流
    # ==================================================================

    def _next_decision_seq(self, session, run_id: str) -> int:
        """在同一 session 内取下一个 seq（保证递增）。"""
        max_seq = (
            session.query(func.max(ExperimentDecision.seq))
            .filter(ExperimentDecision.run_id == run_id)
            .scalar()
        )
        return (max_seq or 0) + 1

    def append_decision(
        self, run_id: str, decision_type: str, payload: Dict[str, Any], actor: str = "system"
    ) -> ExperimentDecision:
        """追加一条决策事件。seq 自动递增。"""
        with self._adapter.get_sync_session() as session:
            seq = self._next_decision_seq(session, run_id)
            obj = ExperimentDecision(
                run_id=run_id,
                seq=seq,
                decision_type=decision_type,
                actor=actor,
                payload_json=payload or {},
            )
            session.add(obj)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def list_decisions(
        self, run_id: str, decision_type: Optional[str] = None, limit: int = 500
    ) -> List[ExperimentDecision]:
        """列出某 run 的决策事件，按 seq 升序。"""
        with self._adapter.get_sync_session() as session:
            q = session.query(ExperimentDecision).filter(ExperimentDecision.run_id == run_id)
            if decision_type is not None:
                q = q.filter(ExperimentDecision.decision_type == decision_type)
            rows = q.order_by(ExperimentDecision.seq.asc()).limit(max(1, limit)).all()
            session.expunge_all()
            return rows

    # ==================================================================
    # autoresearch_job — 跨机器 Job 队列
    # ==================================================================

    def submit_job(self, run_id: str, payload: Dict[str, Any]) -> AutoResearchJob:
        """提交一个 pending job。如果同 run_id 已有 job，重置为 pending。"""
        now = datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            obj = session.get(AutoResearchJob, run_id)
            if obj is None:
                obj = AutoResearchJob(
                    run_id=run_id,
                    status="pending",
                    payload_json=payload or {},
                    created_at=now,
                    cancel_requested=False,
                )
                session.add(obj)
            else:
                obj.status = "pending"
                obj.payload_json = payload or {}
                obj.created_at = now
                obj.pid = None
                obj.host = None
                obj.started_at = None
                obj.finished_at = None
                obj.heartbeat_at = None
                obj.cancel_requested = False
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def claim_job(self, pid: int, host: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Worker 领取一个 pending job。使用 SELECT ... FOR UPDATE SKIP LOCKED 支持多 worker 并行。

        返回：{"run_id": str, "payload": dict}，无可领任务时返回 None。
        """
        hostname = host or socket.gethostname()
        now = datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            # SKIP LOCKED 允许多 worker 并行抢占，不互相阻塞
            stmt = (
                select(AutoResearchJob)
                .where(AutoResearchJob.status == "pending")
                .order_by(AutoResearchJob.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return None
            row.status = "running"
            row.pid = pid
            row.host = hostname
            row.started_at = now
            row.heartbeat_at = now
            session.flush()
            return {"run_id": row.run_id, "payload": row.payload_json or {}}

    def heartbeat(self, run_id: str) -> None:
        """Worker 心跳。"""
        now = datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            session.execute(
                update(AutoResearchJob)
                .where(AutoResearchJob.run_id == run_id)
                .values(heartbeat_at=now)
            )

    def is_cancel_requested(self, run_id: str) -> bool:
        """Worker 定期检查是否被请求取消。"""
        with self._adapter.get_sync_session() as session:
            obj = session.get(AutoResearchJob, run_id)
            return bool(obj and obj.cancel_requested)

    def request_cancel(self, run_id: str) -> bool:
        """FastAPI 端标记取消。返回是否成功（找到并更新了记录）。"""
        with self._adapter.get_sync_session() as session:
            result = session.execute(
                update(AutoResearchJob)
                .where(AutoResearchJob.run_id == run_id)
                .values(cancel_requested=True)
            )
            return result.rowcount > 0

    def finish_job(self, run_id: str, status: str) -> None:
        """Worker 完成 job（status: success/failed/cancelled）。"""
        now = datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            session.execute(
                update(AutoResearchJob)
                .where(AutoResearchJob.run_id == run_id)
                .values(status=status, finished_at=now, heartbeat_at=now)
            )

    def get_job(self, run_id: str) -> Optional[AutoResearchJob]:
        """按 run_id 查询单个 job。"""
        with self._adapter.get_sync_session() as session:
            obj = session.get(AutoResearchJob, run_id)
            if obj is not None:
                session.expunge(obj)
            return obj

    def list_jobs(self, limit: int = 50) -> List[AutoResearchJob]:
        """列出最近 job，按 created_at 倒序。"""
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(AutoResearchJob)
                .order_by(AutoResearchJob.created_at.desc())
                .limit(max(1, limit))
                .all()
            )
            session.expunge_all()
            return rows

    def mark_dead_workers(
        self, timeout_seconds: int = HEARTBEAT_TIMEOUT_SECONDS
    ) -> List[str]:
        """服务启动时调用：标记心跳超时的 running job 为 interrupted。
        返回被标记的 run_id 列表。
        """
        cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
        now = datetime.utcnow()
        marked: List[str] = []
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(AutoResearchJob)
                .filter(
                    AutoResearchJob.status == "running",
                    (AutoResearchJob.heartbeat_at.is_(None))
                    | (AutoResearchJob.heartbeat_at < cutoff),
                )
                .all()
            )
            for row in rows:
                row.status = "interrupted"
                row.finished_at = now
                marked.append(row.run_id)
            return marked

    # ==================================================================
    # candidate_pool — 候选池（复用现有表）
    # ==================================================================

    def upsert_candidate(self, candidate_data: Dict[str, Any]) -> CandidatePool:
        """Upsert 候选池记录（按 id 判重）。"""
        if "id" not in candidate_data:
            raise ValueError("candidate_data must contain 'id'")

        with self._adapter.get_sync_session() as session:
            obj = session.get(CandidatePool, candidate_data["id"])
            if obj is None:
                obj = CandidatePool(**candidate_data)
                session.add(obj)
            else:
                for k, v in candidate_data.items():
                    setattr(obj, k, v)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def list_candidates(
        self, slot: str, status: Optional[str] = None, limit: int = 200
    ) -> List[CandidatePool]:
        """按 slot / status 查询候选池，按 best_mape 升序（更好的排前面）。"""
        with self._adapter.get_sync_session() as session:
            q = session.query(CandidatePool).filter(CandidatePool.slot == slot)
            if status is not None:
                q = q.filter(CandidatePool.status == status)
            # MySQL 不支持 NULLS LAST，用 CASE 表达式替代
            rows = (
                q.order_by(
                    CandidatePool.best_mape.is_(None),  # NULL → True(1) 排后面
                    CandidatePool.best_mape.asc(),
                )
                .limit(max(1, limit))
                .all()
            )
            session.expunge_all()
            return rows

    def get_candidate(self, candidate_id: str) -> Optional[CandidatePool]:
        """按 id 查询单条候选。"""
        with self._adapter.get_sync_session() as session:
            obj = session.get(CandidatePool, candidate_id)
            if obj is not None:
                session.expunge(obj)
            return obj

    # ==================================================================
    # candidate_verification — 复验队列
    # ==================================================================

    def upsert_verification(self, verification_data: Dict[str, Any]) -> CandidateVerification:
        """Upsert 复验记录（按 id 判重）。"""
        if "id" not in verification_data:
            raise ValueError("verification_data must contain 'id'")

        with self._adapter.get_sync_session() as session:
            obj = session.get(CandidateVerification, verification_data["id"])
            if obj is None:
                obj = CandidateVerification(**verification_data)
                session.add(obj)
            else:
                for k, v in verification_data.items():
                    setattr(obj, k, v)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def list_verifications(
        self, slot: str, status: Optional[str] = None, limit: int = 200
    ) -> List[CandidateVerification]:
        """列出复验队列，按 created_at 倒序。"""
        with self._adapter.get_sync_session() as session:
            q = session.query(CandidateVerification).filter(CandidateVerification.slot == slot)
            if status is not None:
                q = q.filter(CandidateVerification.status == status)
            rows = (
                q.order_by(CandidateVerification.created_at.desc())
                .limit(max(1, limit))
                .all()
            )
            session.expunge_all()
            return rows

    def get_verification(self, verification_id: str) -> Optional[CandidateVerification]:
        with self._adapter.get_sync_session() as session:
            obj = session.get(CandidateVerification, verification_id)
            if obj is not None:
                session.expunge(obj)
            return obj

    # ==================================================================
    # candidate_promotion_log — 候选晋升审计
    # ==================================================================

    def append_promotion(
        self,
        slot: str,
        candidate_id: str,
        action: str,
        actor: str = "system",
        reason: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> CandidatePromotionLog:
        """追加一条晋升审计日志。"""
        with self._adapter.get_sync_session() as session:
            obj = CandidatePromotionLog(
                slot=slot,
                candidate_id=candidate_id,
                action=action,
                actor=actor,
                reason=reason or "",
                payload_json=payload or {},
            )
            session.add(obj)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def list_promotions(
        self, slot: str, limit: int = 200
    ) -> List[CandidatePromotionLog]:
        """按 slot 列出晋升日志，按时间倒序。"""
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(CandidatePromotionLog)
                .filter(CandidatePromotionLog.slot == slot)
                .order_by(CandidatePromotionLog.created_at.desc())
                .limit(max(1, limit))
                .all()
            )
            session.expunge_all()
            return rows

    # ==================================================================
    # knowledge_claim — 知识层（复用现有表）
    # ==================================================================

    def upsert_claim(self, claim_data: Dict[str, Any]) -> KnowledgeClaim:
        """Upsert 知识声明（按 id 判重）。"""
        if "id" not in claim_data:
            raise ValueError("claim_data must contain 'id'")

        with self._adapter.get_sync_session() as session:
            obj = session.get(KnowledgeClaim, claim_data["id"])
            if obj is None:
                obj = KnowledgeClaim(**claim_data)
                session.add(obj)
            else:
                for k, v in claim_data.items():
                    setattr(obj, k, v)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def query_claims_by_scenario(
        self,
        scenario_fingerprint: str,
        claim_type: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> List[KnowledgeClaim]:
        """按场景指纹检索知识声明，按 confidence 降序。可选按 claim_type 过滤。"""
        with self._adapter.get_sync_session() as session:
            q = session.query(KnowledgeClaim).filter(
                KnowledgeClaim.scenario_fingerprint == scenario_fingerprint,
                KnowledgeClaim.decayed_at.is_(None),
            )
            if claim_type is not None:
                q = q.filter(KnowledgeClaim.claim_type == claim_type)
            if min_confidence > 0:
                q = q.filter(KnowledgeClaim.confidence >= min_confidence)
            rows = (
                q.order_by(KnowledgeClaim.confidence.desc())
                .limit(max(1, limit))
                .all()
            )
            session.expunge_all()
            return rows

    def list_active_claims(
        self, slot: Optional[str] = None, limit: int = 200
    ) -> List[KnowledgeClaim]:
        """列出未衰减（decayed_at is null）的 claim。"""
        with self._adapter.get_sync_session() as session:
            q = session.query(KnowledgeClaim).filter(KnowledgeClaim.decayed_at.is_(None))
            if slot is not None:
                q = q.filter(KnowledgeClaim.slot == slot)
            rows = (
                q.order_by(KnowledgeClaim.confidence.desc())
                .limit(max(1, limit))
                .all()
            )
            session.expunge_all()
            return rows

# @AI_GENERATED: end
