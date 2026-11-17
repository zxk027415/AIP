# @AI_GENERATED
# -*- coding: utf-8 -*-
"""PV 双路径 REST：Ledger/Epoch/Shadow/Backfill 与治理事件。

写接口保留 P0 鉴权 TODO，本任务不实施鉴权。
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.iterative_labeling.pv_governance_events import (
    PathSwitchEventStore,
    PromotionEventStore,
)
from services.iterative_labeling.pv_model_registry import PVModelRegistry
from services.scheduler.pv_dual_path.backfill_runner import BackfillRunner, BackfillRunnerError
from services.scheduler.pv_dual_path.config import load_dual_path_config
from services.scheduler.pv_dual_path.cross_path_switch_coordinator import (
    CrossPathSwitchCoordinator,
    PathSwitchRequest,
)
from services.scheduler.pv_dual_path.path_activation import PathActivationService
from services.scheduler.pv_dual_path.seq_device_day_ledger import (
    LedgerOperationError,
    SeqDeviceDayLedgerRepository,
)
from services.scheduler.pv_dual_path.shadow_compare import (
    ShadowCompareRunner,
    ShadowReportNotFoundError,
    ShadowReportStore,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduler/pv-dual-path", tags=["pv-dual-path"])

# TODO P0 鉴权：Ledger/Epoch/Shadow/Backfill 写入口上线前必须鉴权（Req10.9/10.10）。本任务不实施。


def _db_adapter():
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig

    return DBAdapter(DBConfig())


def _activation_service(adapter) -> PathActivationService:
    return PathActivationService(adapter, load_dual_path_config())


def _parse_date(raw: Optional[str], field: str) -> Optional[date]:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field} 非法日期") from exc


class ActivationPreviewBody(BaseModel):
    slot: str = "pv_fault"
    modeling_path: str
    activation_mode: str
    backfill_days: Optional[int] = None
    device_scope: List[Dict[str, Any]] = Field(default_factory=list)


class ShadowCompareBody(BaseModel):
    slot: str = "pv_fault"
    start_date: str
    end_date: str
    device_scope: Optional[List[Dict[str, Any]]] = None


class BackfillControlBody(BaseModel):
    confirm: Any = None
    operator: str = ""
    reason: str = ""


@router.get("/ledger")
async def get_ledger(
    slot: str = "pv_fault",
    modeling_path: str = "seq_annotation",
    site_id: Optional[str] = None,
    device_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    """Console 查询 Seq 设备日权威状态；GET 无写副作用。"""
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")
    if start and end and end < start:
        raise HTTPException(status_code=422, detail="end_date 不能早于 start_date")
    adapter = _db_adapter()
    try:
        repo = SeqDeviceDayLedgerRepository(adapter)
        payload = repo.list(
            page=page,
            page_size=page_size,
            slot=slot,
            modeling_path=modeling_path,
            site_id=site_id,
            device_id=device_id,
            branch_id=branch_id,
            start_date=start,
            end_date=end,
            status=status,
        )
        items = []
        frontiers: Dict[str, Optional[str]] = {}
        for record in payload["items"]:
            key = record.key
            items.append(
                {
                    "slot": key.slot,
                    "modeling_path": key.modeling_path,
                    "site_id": key.site_id,
                    "device_id": key.device_id,
                    "branch_id": key.branch_id,
                    "business_date": key.business_date.isoformat(),
                    "status": record.status,
                    "input_fingerprint": record.input_fingerprint,
                    "batch_id": record.batch_id,
                    "supersedes_batch_id": record.supersedes_batch_id,
                    "attempt_count": record.attempt_count,
                    "last_error": record.last_error,
                    "processed_at": record.processed_at.isoformat() if record.processed_at else None,
                    "activation_epoch_id": record.activation_epoch_id,
                }
            )
            device_key = f"{key.site_id}|{key.device_id}|{key.branch_id}"
            if device_key not in frontiers:
                from services.scheduler.pv_dual_path.seq_device_day_ledger import DeviceKey

                frontier = repo.compute_frontier(
                    DeviceKey(key.slot, key.modeling_path, key.site_id, key.device_id, key.branch_id),
                    record.activation_epoch_id,
                )
                frontiers[device_key] = frontier.isoformat() if frontier else None
        return {
            "page": payload["page"],
            "page_size": payload["page_size"],
            "total": payload["total"],
            "items": items,
            "frontier_summary": frontiers,
            "cursor_semantics": "continuous_completion_frontier",
        }
    except LedgerOperationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        dispose = getattr(adapter, "dispose", None)
        if callable(dispose):
            dispose()


@router.get("/activation-epochs")
async def get_activation_epochs(
    slot: str = "pv_fault",
    modeling_path: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    adapter = _db_adapter()
    try:
        return _activation_service(adapter).list_epochs(
            slot=slot,
            modeling_path=modeling_path,
            page=page,
            page_size=page_size,
        )
    finally:
        dispose = getattr(adapter, "dispose", None)
        if callable(dispose):
            dispose()


@router.post("/activation-preview")
async def post_activation_preview(body: ActivationPreviewBody):
    """只计算逐设备边界与九项可预检条件，不建立 Epoch。"""
    # TODO P0 鉴权：activation preview 后续切换入口上线前必须鉴权。
    adapter = _db_adapter()
    try:
        coordinator = CrossPathSwitchCoordinator(
            activation=_activation_service(adapter),
        )
        preview = coordinator.preview(
            PathSwitchRequest(
                modeling_path=body.modeling_path,
                slot=body.slot,
                activation_mode=body.activation_mode,
                backfill_days=body.backfill_days,
                device_scope=body.device_scope,
            )
        )
        from services.scheduler.pv_dual_path.cross_path_switch_coordinator import _preview_to_dict

        return {"preview": _preview_to_dict(preview), "side_effects": False}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        dispose = getattr(adapter, "dispose", None)
        if callable(dispose):
            dispose()


@router.post("/shadow-compare")
async def post_shadow_compare(body: ShadowCompareBody):
    """创建双 Champion 只读比对；不得接受任意模型引用。"""
    # TODO P0 鉴权：Shadow 创建入口上线前必须鉴权。
    start = _parse_date(body.start_date, "start_date")
    end = _parse_date(body.end_date, "end_date")
    if start is None or end is None:
        raise HTTPException(status_code=422, detail="start_date/end_date 必填")
    try:
        runner = ShadowCompareRunner(
            model_registry=PVModelRegistry(),
            slot=body.slot,
        )
        report = runner.run_compare(start, end, device_scope=body.device_scope)
        return {
            "comparison_id": report.comparison_id,
            "status": "completed",
            "legacy_model_ref": report.legacy_model_ref,
            "seq_model_ref": report.seq_model_ref,
            "queued": False,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/shadow-compare/{comparison_id}")
async def get_shadow_compare(comparison_id: str, slot: str = "pv_fault"):
    try:
        report = ShadowReportStore(slot=slot).load_or_raise(comparison_id)
    except ShadowReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return report.to_dict()


@router.get("/backfill/{backfill_task_id}")
async def get_backfill(backfill_task_id: str):
    adapter = _db_adapter()
    try:
        task = BackfillRunner(adapter, detector=lambda *_args, **_kwargs: {"status": "skipped"}).get_status(
            backfill_task_id
        )
        if task is None:
            raise HTTPException(status_code=404, detail="未知 backfill_task_id")
        return task.to_dict()
    finally:
        dispose = getattr(adapter, "dispose", None)
        if callable(dispose):
            dispose()


@router.post("/backfill/{backfill_task_id}/retry")
async def retry_backfill(backfill_task_id: str):
    # TODO P0 鉴权：Backfill 控制入口上线前必须鉴权。
    adapter = _db_adapter()
    try:
        runner = BackfillRunner(adapter, detector=lambda *_a, **_k: {"status": "skipped"})
        return {"backfill_task_id": runner.retry(backfill_task_id), "status": "queued"}
    except BackfillRunnerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        dispose = getattr(adapter, "dispose", None)
        if callable(dispose):
            dispose()


@router.post("/backfill/{backfill_task_id}/cancel-release")
async def cancel_release_backfill(backfill_task_id: str, body: BackfillControlBody):
    # TODO P0 鉴权：Backfill 控制入口上线前必须鉴权。
    adapter = _db_adapter()
    try:
        runner = BackfillRunner(adapter, detector=lambda *_a, **_k: {"status": "skipped"})
        task = runner.cancel_and_release(
            backfill_task_id,
            confirm=body.confirm,
            operator=body.operator,
            reason=body.reason,
        )
        return task.to_dict()
    except BackfillRunnerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        dispose = getattr(adapter, "dispose", None)
        if callable(dispose):
            dispose()
# @AI_GENERATED: end
