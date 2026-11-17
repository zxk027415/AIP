# @AI_GENERATED
# -*- coding: utf-8 -*-
"""独立历史回放执行器：只消费已认领的 historical_backfill 日期范围。

``BackfillRunner`` 与标签回流 ``BackfillLoop`` 职责不同：这里回放历史检测，
使用独立任务命名空间，不写生产 Seq Ledger、不推进生产 frontier、不计入
生产责任统计。容量令牌只向 ``BackfillCapacityArbiter`` 申请历史车道余量。
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from sqlalchemy import select

from services.db.models.pv_fault import PathActivationEpoch, PathActivationLaneClaim
from services.scheduler.pv_dual_path.backfill_capacity import BackfillCapacityArbiter
from services.scheduler.pv_dual_path.path_activation import (
    DeviceActivationScope,
    DeviceScope,
    HISTORICAL_BACKFILL_LANE,
)
from services.scheduler.pv_dual_path.persistence_utils import atomic_write_json

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_DEFAULT_TASK_DIR = _BACKEND_DIR / "data" / "pv_dual_path" / "backfill_tasks"
NAMESPACE = "historical_backfill"
_TERMINAL_RELEASE_STATUSES = frozenset({"cancelled"})
HistoryDetector = Callable[[DeviceScope, date], Dict[str, Any]]


class BackfillRunnerError(ValueError):
    """历史回放提交/状态转换非法。"""


@dataclass
class BackfillDayResult:
    """单个历史设备日的独立命名空间结果，不是生产 Ledger 行。"""

    site_id: str
    device_id: str
    branch_id: str
    business_date: str
    status: str
    error: Optional[str] = None
    detector_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "device_id": self.device_id,
            "branch_id": self.branch_id,
            "business_date": self.business_date,
            "status": self.status,
            "error": self.error,
            "detector_payload": dict(self.detector_payload),
            "namespace": NAMESPACE,
        }


@dataclass
class BackfillTask:
    """历史回放任务快照；持久化在独立 JSON 命名空间。"""

    backfill_task_id: str
    activation_epoch_id: str
    slot: str
    modeling_path: str
    status: str
    claimed_ranges: List[Dict[str, Any]]
    results: List[Dict[str, Any]] = field(default_factory=list)
    last_error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    namespace: str = NAMESPACE
    writes_production_ledger: bool = False
    advances_production_frontier: bool = False
    counts_as_production_responsibility: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backfill_task_id": self.backfill_task_id,
            "activation_epoch_id": self.activation_epoch_id,
            "slot": self.slot,
            "modeling_path": self.modeling_path,
            "status": self.status,
            "claimed_ranges": list(self.claimed_ranges),
            "results": list(self.results),
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "namespace": self.namespace,
            "writes_production_ledger": False,
            "advances_production_frontier": False,
            "counts_as_production_responsibility": False,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "BackfillTask":
        return cls(
            backfill_task_id=str(payload["backfill_task_id"]),
            activation_epoch_id=str(payload["activation_epoch_id"]),
            slot=str(payload.get("slot") or "pv_fault"),
            modeling_path=str(payload.get("modeling_path") or ""),
            status=str(payload.get("status") or "queued"),
            claimed_ranges=[dict(item) for item in payload.get("claimed_ranges") or []],
            results=[dict(item) for item in payload.get("results") or []],
            last_error=payload.get("last_error"),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )


class BackfillRunner:
    """只消费 historical_backfill LaneClaim 的独立历史检测通道。"""

    def __init__(
        self,
        adapter: Any,
        *,
        arbiter: Optional[BackfillCapacityArbiter] = None,
        detector: Optional[HistoryDetector] = None,
        task_dir: Optional[Path] = None,
        now_factory: Optional[Callable[[], datetime]] = None,
        task_id_factory: Optional[Callable[[], str]] = None,
    ) -> None:
        self._adapter = adapter
        self._arbiter = arbiter
        self._detector = detector
        self._task_dir = Path(task_dir) if task_dir is not None else _DEFAULT_TASK_DIR
        self._now_factory = now_factory or datetime.utcnow
        self._task_id_factory = task_id_factory or (lambda: f"bft-{uuid.uuid4().hex[:16]}")
        self._lock = threading.RLock()

    def submit_full_backfill(
        self,
        epoch_id: str,
        device_scopes: Optional[Sequence[DeviceActivationScope]] = None,
    ) -> str:
        """为已存在的 historical_backfill claim 创建独立任务；不新建生产责任。"""
        epoch_id = str(epoch_id or "").strip()
        if not epoch_id:
            raise BackfillRunnerError("activation_epoch_id 不能为空")
        with self._adapter.get_sync_session() as session:
            epoch = session.get(PathActivationEpoch, epoch_id)
            if epoch is None:
                raise BackfillRunnerError(f"启用周期不存在：{epoch_id}")
            claims = self._load_historical_claims(session, epoch_id, device_scopes)
            if not claims:
                raise BackfillRunnerError("没有可消费的 historical_backfill 认领范围")
            task_id = self._task_id_factory()
            accepted: List[PathActivationLaneClaim] = []
            for claim in claims:
                if claim.claim_status in {"running", "succeeded"}:
                    raise BackfillRunnerError(
                        f"历史范围已被任务 {claim.backfill_task_id or 'unknown'} 认领"
                    )
                if claim.claim_status == "failed":
                    raise BackfillRunnerError(
                        f"历史范围失败中，请对任务 {claim.backfill_task_id} retry，或 cancel 后 release"
                    )
                claim.backfill_task_id = task_id
                claim.claim_status = "claimed"
                accepted.append(claim)
            claimed_ranges = [_claim_payload(item) for item in accepted]
            slot = epoch.slot
            modeling_path = epoch.modeling_path

        now = self._now_iso()
        task = BackfillTask(
            backfill_task_id=task_id,
            activation_epoch_id=epoch_id,
            slot=slot,
            modeling_path=modeling_path,
            status="queued",
            claimed_ranges=claimed_ranges,
            created_at=now,
            updated_at=now,
        )
        self._save_task(task)
        return task_id

    def get_status(self, task_id: str) -> Optional[BackfillTask]:
        path = self._task_path(task_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return BackfillTask.from_dict(json.load(handle))

    def run(self, task_id: str) -> BackfillTask:
        """同步执行一个已排队任务；容量不足时保持 queued，无生产副作用。"""
        with self._lock:
            task = self._require_task(task_id)
            if task.status == "cancelled":
                return task
            if task.status not in {"queued"}:
                raise BackfillRunnerError(f"任务 {task_id} 当前状态 {task.status} 不可执行")
            lease_id = self._acquire_history_token()
            if lease_id is None:
                task.status = "queued"
                task.last_error = "historical_capacity_unavailable"
                task.updated_at = self._now_iso()
                self._save_task(task)
                return task
            try:
                return self._execute_locked(task)
            finally:
                if self._arbiter is not None:
                    self._arbiter.release(lease_id)

    def retry(self, task_id: str) -> str:
        """失败任务重试：保留原认领范围，不把日期交还生产积压。"""
        with self._lock:
            task = self._require_task(task_id)
            if task.status != "failed":
                raise BackfillRunnerError("只有 failed 任务可以 retry")
            self._set_claim_status(task, "claimed")
            task.status = "queued"
            task.last_error = None
            task.updated_at = self._now_iso()
            self._save_task(task)
            return task.backfill_task_id

    def cancel(self, task_id: str) -> BackfillTask:
        """人工取消：任务停止，认领仍保留直到显式 release。"""
        with self._lock:
            task = self._require_task(task_id)
            if task.status == "succeeded":
                raise BackfillRunnerError("已成功任务不能取消")
            task.status = "cancelled"
            task.updated_at = self._now_iso()
            self._save_task(task)
            return task

    def release(self, task_id: str) -> BackfillTask:
        """显式释放已取消任务的历史认领。"""
        with self._lock:
            task = self._require_task(task_id)
            if task.status not in _TERMINAL_RELEASE_STATUSES:
                raise BackfillRunnerError("只有 cancelled 任务可以显式释放认领")
            self._set_claim_status(task, "cancelled")
            task.updated_at = self._now_iso()
            self._save_task(task)
            return task

    def cancel_and_release(
        self,
        task_id: str,
        *,
        confirm: Any,
        operator: str,
        reason: str,
    ) -> BackfillTask:
        """先取消再显式释放历史范围；confirm 必须是 JSON boolean true。"""
        if confirm is not True:
            raise BackfillRunnerError("confirm 必须为 JSON boolean true")
        if not str(operator or "").strip() or not str(reason or "").strip():
            raise BackfillRunnerError("operator 与 reason 必填")
        self.cancel(task_id)
        return self.release(task_id)

    def _execute_locked(self, task: BackfillTask) -> BackfillTask:
        task.status = "running"
        task.results = []
        task.updated_at = self._now_iso()
        self._save_task(task)
        self._set_claim_status(task, "running")
        results: List[Dict[str, Any]] = []
        try:
            for claim in task.claimed_ranges:
                scope = DeviceScope(claim["site_id"], claim["device_id"], claim["branch_id"])
                for business_date in _iter_claimed_dates(claim):
                    latest = self._require_task(task.backfill_task_id)
                    if latest.status == "cancelled":
                        return latest
                    payload = self._detect(scope, business_date)
                    results.append(
                        BackfillDayResult(
                            site_id=scope.site_id,
                            device_id=scope.device_id,
                            branch_id=scope.branch_id,
                            business_date=business_date.isoformat(),
                            status="succeeded",
                            detector_payload=payload,
                        ).to_dict()
                    )
            task.results = results
            task.status = "succeeded"
            task.last_error = None
            self._set_claim_status(task, "succeeded")
        except Exception as exc:
            results.append(
                {
                    "status": "failed",
                    "error": str(exc),
                    "namespace": NAMESPACE,
                }
            )
            task.results = results
            task.status = "failed"
            task.last_error = str(exc)
            self._set_claim_status(task, "failed")
        task.updated_at = self._now_iso()
        self._save_task(task)
        return task

    def _detect(self, scope: DeviceScope, business_date: date) -> Dict[str, Any]:
        if self._detector is None:
            raise BackfillRunnerError("未注入历史检测器，拒绝猜测生产策略")
        payload = self._detector(scope, business_date)
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise BackfillRunnerError("历史检测器必须返回 dict")
        return dict(payload)

    def _acquire_history_token(self) -> Optional[str]:
        if self._arbiter is None:
            return f"unbounded-{uuid.uuid4().hex[:8]}"
        decision = self._arbiter.acquire(HISTORICAL_BACKFILL_LANE, 1)
        if not decision.granted:
            return None
        return decision.lease_id

    def _load_historical_claims(
        self,
        session: Any,
        epoch_id: str,
        device_scopes: Optional[Sequence[DeviceActivationScope]],
    ) -> List[PathActivationLaneClaim]:
        rows = list(
            session.execute(
                select(PathActivationLaneClaim).where(
                    PathActivationLaneClaim.activation_epoch_id == epoch_id,
                    PathActivationLaneClaim.lane == HISTORICAL_BACKFILL_LANE,
                )
            ).scalars().all()
        )
        allowed = None
        if device_scopes is not None:
            allowed = {
                (item.scope.site_id, item.scope.device_id, item.scope.branch_id)
                for item in device_scopes
            }
        filtered = []
        for row in rows:
            if row.range_end is None:
                raise BackfillRunnerError("historical_backfill 认领必须有 range_end")
            if allowed is not None and (row.site_id, row.device_id, row.branch_id) not in allowed:
                continue
            filtered.append(row)
        return filtered

    def _set_claim_status(self, task: BackfillTask, status: str) -> None:
        with self._adapter.get_sync_session() as session:
            rows = session.execute(
                select(PathActivationLaneClaim).where(
                    PathActivationLaneClaim.activation_epoch_id == task.activation_epoch_id,
                    PathActivationLaneClaim.lane == HISTORICAL_BACKFILL_LANE,
                    PathActivationLaneClaim.backfill_task_id == task.backfill_task_id,
                )
            ).scalars().all()
            for row in rows:
                row.claim_status = status

    def _require_task(self, task_id: str) -> BackfillTask:
        task = self.get_status(task_id)
        if task is None:
            raise BackfillRunnerError(f"历史任务不存在：{task_id}")
        return task

    def _task_path(self, task_id: str) -> Path:
        safe_id = str(task_id).replace("/", "_").replace("\\", "_")
        return self._task_dir / f"{safe_id}.json"

    def _save_task(self, task: BackfillTask) -> None:
        atomic_write_json(
            self._task_path(task.backfill_task_id),
            task.to_dict(),
            base_dir=self._task_dir,
        )

    def _now_iso(self) -> str:
        return self._now_factory().isoformat()


def _claim_payload(row: PathActivationLaneClaim) -> Dict[str, Any]:
    return {
        "site_id": row.site_id,
        "device_id": row.device_id,
        "branch_id": row.branch_id,
        "lane": row.lane,
        "range_start": row.range_start.isoformat(),
        "range_end": row.range_end.isoformat() if row.range_end is not None else None,
        "claim_status": row.claim_status,
    }


def _iter_claimed_dates(claim: Dict[str, Any]):
    start = date.fromisoformat(str(claim["range_start"]))
    raw_end = claim.get("range_end")
    if not raw_end:
        raise BackfillRunnerError("historical_backfill 认领必须有 range_end")
    end = date.fromisoformat(str(raw_end))
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)
# @AI_GENERATED: end
