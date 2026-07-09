# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/db/repositories/deployment.py — 部署链路 CRUD Repository

覆盖部署链路所需的所有 DB 操作，供 Phase 1 双写替代 slots.json / switch_log.json /
tasks.json 的读写。

包含的表：
  - deployment_slot           — 槽位配置（生产 workflow、冷却期、上限）
  - deployment_model_version  — 每个 slot 下所有版本（含 prelaunch/shadow/production/retired）
  - switch_event              — 切换事件 append-only 审计
  - scheduler_task            — Cron 定时任务

关联文档：docs/specs/autoresearch-mysql-migration/design.md 第 7-10 节
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import update

from ..adapter import DBAdapter
from ..models.deployment import (
    DeploymentModelVersion,
    DeploymentSlot,
    SchedulerTask,
    SwitchEvent,
)


class DeploymentRepository:
    """部署链路数据 CRUD 集合。"""

    def __init__(self, adapter: DBAdapter) -> None:
        self._adapter = adapter

    # ==================================================================
    # deployment_slot — 槽位配置
    # ==================================================================

    def upsert_slot(self, slot_data: Dict[str, Any]) -> DeploymentSlot:
        """Upsert 槽位配置（按 slot 判重）。"""
        if "slot" not in slot_data:
            raise ValueError("slot_data must contain 'slot'")

        with self._adapter.get_sync_session() as session:
            obj = session.get(DeploymentSlot, slot_data["slot"])
            if obj is None:
                obj = DeploymentSlot(**slot_data)
                session.add(obj)
            else:
                for k, v in slot_data.items():
                    setattr(obj, k, v)
            obj.updated_at = datetime.utcnow()
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def get_slot(self, slot: str) -> Optional[DeploymentSlot]:
        """按 slot 名查询单个槽位配置。"""
        with self._adapter.get_sync_session() as session:
            obj = session.get(DeploymentSlot, slot)
            if obj is not None:
                session.expunge(obj)
            return obj

    def list_slots(self) -> List[DeploymentSlot]:
        """列出所有槽位。"""
        with self._adapter.get_sync_session() as session:
            rows = session.query(DeploymentSlot).all()
            session.expunge_all()
            return rows

    def update_production_workflow(self, slot: str, workflow_id: str) -> None:
        """更新指定槽位的生产 workflow_id（切换后调用）。"""
        now = datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            session.execute(
                update(DeploymentSlot)
                .where(DeploymentSlot.slot == slot)
                .values(production_workflow_id=workflow_id, updated_at=now)
            )

    # ==================================================================
    # deployment_model_version — 每个 slot 下所有版本
    # ==================================================================

    def upsert_model_version(self, version_data: Dict[str, Any]) -> DeploymentModelVersion:
        """Upsert 部署版本记录（按 slot + workflow_id 唯一约束判重）。"""
        if "slot" not in version_data or "workflow_id" not in version_data:
            raise ValueError("version_data must contain 'slot' and 'workflow_id'")

        with self._adapter.get_sync_session() as session:
            obj = (
                session.query(DeploymentModelVersion)
                .filter_by(
                    slot=version_data["slot"],
                    workflow_id=version_data["workflow_id"],
                )
                .first()
            )
            if obj is None:
                obj = DeploymentModelVersion(**version_data)
                session.add(obj)
            else:
                for k, v in version_data.items():
                    setattr(obj, k, v)
            obj.updated_at = datetime.utcnow()
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def list_versions_by_slot(self, slot: str) -> List[DeploymentModelVersion]:
        """列出某 slot 下的所有版本。"""
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(DeploymentModelVersion)
                .filter(DeploymentModelVersion.slot == slot)
                .order_by(DeploymentModelVersion.updated_at.desc())
                .all()
            )
            session.expunge_all()
            return rows

    def list_versions_by_status(
        self, slot: str, status: str
    ) -> List[DeploymentModelVersion]:
        """按 slot + status 列出版本（用于取生产/影子/预上线池）。

        影子池按 accuracy_score 降序（精度好的在前，None 排最后）。
        """
        with self._adapter.get_sync_session() as session:
            q = session.query(DeploymentModelVersion).filter(
                DeploymentModelVersion.slot == slot,
                DeploymentModelVersion.status == status,
            )
            # accuracy_score IS NULL 排最后
            rows = q.order_by(
                DeploymentModelVersion.accuracy_score.is_(None),
                DeploymentModelVersion.accuracy_score.asc(),
            ).all()
            session.expunge_all()
            return rows

    def get_production_version(self, slot: str) -> Optional[DeploymentModelVersion]:
        """取某 slot 的生产版本（唯一）。"""
        with self._adapter.get_sync_session() as session:
            obj = (
                session.query(DeploymentModelVersion)
                .filter(
                    DeploymentModelVersion.slot == slot,
                    DeploymentModelVersion.status == "production",
                )
                .first()
            )
            if obj is not None:
                session.expunge(obj)
            return obj

    def update_version_status(
        self, slot: str, workflow_id: str, new_status: str
    ) -> None:
        """切换某个 workflow 的状态（比如 shadow → production, prelaunch → shadow）。"""
        now = datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            session.execute(
                update(DeploymentModelVersion)
                .where(
                    DeploymentModelVersion.slot == slot,
                    DeploymentModelVersion.workflow_id == workflow_id,
                )
                .values(status=new_status, updated_at=now)
            )

    def update_prelaunch_meta(
        self, slot: str, workflow_id: str, meta: Dict[str, Any]
    ) -> None:
        """更新预上线元数据（每天精度回填后调用）。"""
        now = datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            session.execute(
                update(DeploymentModelVersion)
                .where(
                    DeploymentModelVersion.slot == slot,
                    DeploymentModelVersion.workflow_id == workflow_id,
                )
                .values(prelaunch_meta_json=meta, updated_at=now)
            )

    def update_accuracy_and_streak(
        self,
        slot: str,
        workflow_id: str,
        accuracy_score: Optional[float],
        consecutive_better_days: Optional[int] = None,
    ) -> None:
        """更新版本精度和连续跑赢天数（cron 精度回填后调用）。"""
        now = datetime.utcnow()
        values: Dict[str, Any] = {"updated_at": now}
        if accuracy_score is not None:
            values["accuracy_score"] = accuracy_score
        if consecutive_better_days is not None:
            values["consecutive_better_days"] = consecutive_better_days
        with self._adapter.get_sync_session() as session:
            session.execute(
                update(DeploymentModelVersion)
                .where(
                    DeploymentModelVersion.slot == slot,
                    DeploymentModelVersion.workflow_id == workflow_id,
                )
                .values(**values)
            )

    # ==================================================================
    # switch_event — 切换事件 append-only
    # ==================================================================

    def append_switch_event(self, event_data: Dict[str, Any]) -> SwitchEvent:
        """追加一条切换事件。event_id 必须由调用方生成（唯一）。"""
        required = ("event_id", "slot", "trigger_type", "to_workflow_id")
        for k in required:
            if k not in event_data:
                raise ValueError(f"event_data must contain '{k}'")

        with self._adapter.get_sync_session() as session:
            obj = SwitchEvent(**event_data)
            session.add(obj)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def list_switch_events(
        self, slot: Optional[str] = None, limit: int = 200
    ) -> List[SwitchEvent]:
        """列出切换事件，按 ts 倒序。"""
        with self._adapter.get_sync_session() as session:
            q = session.query(SwitchEvent)
            if slot is not None:
                q = q.filter(SwitchEvent.slot == slot)
            rows = q.order_by(SwitchEvent.ts.desc()).limit(max(1, limit)).all()
            session.expunge_all()
            return rows

    # ==================================================================
    # scheduler_task — Cron 定时任务
    # ==================================================================

    def upsert_task(self, task_data: Dict[str, Any]) -> SchedulerTask:
        """Upsert Cron 任务（按 task_id 判重）。"""
        if "task_id" not in task_data:
            raise ValueError("task_data must contain 'task_id'")

        with self._adapter.get_sync_session() as session:
            obj = session.get(SchedulerTask, task_data["task_id"])
            if obj is None:
                obj = SchedulerTask(**task_data)
                session.add(obj)
            else:
                for k, v in task_data.items():
                    setattr(obj, k, v)
            obj.updated_at = datetime.utcnow()
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def get_task(self, task_id: str) -> Optional[SchedulerTask]:
        """按 task_id 查询单个任务。"""
        with self._adapter.get_sync_session() as session:
            obj = session.get(SchedulerTask, task_id)
            if obj is not None:
                session.expunge(obj)
            return obj

    def list_tasks(
        self, slot: Optional[str] = None, enabled_only: bool = False
    ) -> List[SchedulerTask]:
        """列出所有 Cron 任务，可按 slot / enabled 过滤。"""
        with self._adapter.get_sync_session() as session:
            q = session.query(SchedulerTask)
            if slot is not None:
                q = q.filter(SchedulerTask.slot == slot)
            if enabled_only:
                q = q.filter(SchedulerTask.enabled == True)  # noqa: E712
            rows = q.order_by(SchedulerTask.task_id.asc()).all()
            session.expunge_all()
            return rows

    def update_last_execution(
        self, task_id: str, execution_time: datetime, result: Dict[str, Any]
    ) -> None:
        """任务执行后更新 last_execution_time 和 last_result_json。"""
        now = datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            session.execute(
                update(SchedulerTask)
                .where(SchedulerTask.task_id == task_id)
                .values(
                    last_execution_time=execution_time,
                    last_result_json=result or {},
                    updated_at=now,
                )
            )

    def set_task_enabled(self, task_id: str, enabled: bool) -> None:
        """启用/禁用一个任务。"""
        now = datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            session.execute(
                update(SchedulerTask)
                .where(SchedulerTask.task_id == task_id)
                .values(enabled=enabled, updated_at=now)
            )

# @AI_GENERATED: end
