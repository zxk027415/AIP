# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/scheduler/pv_dual_path/scheduler.py — 双路径分派器（Dual_Path_Scheduler）

DualPathScheduler 是双路径检测的**定时任务入口**：它只做「读生产路径指针 → 校验 →
按 modeling_path 分派到对应检测策略 → 把本轮结果落账」这条路由链路，本身不做任何检测
逻辑（检测逻辑归两条策略 LegacyDayStrategy / SeqDailyStrategy）。

输入 / 输出（交接友好）：
  - 输入：slot（槽位，默认 "pv_fault"），与 modeling_path 组合成分区键。
  - 输出：CycleResult（本轮可断言结果，见 strategy_base.py）；同时通过 status_writer
    （默认复用 pv_fault_tasks._save_prediction_last_run）把结果落到 prediction_last_run，
    供审计查询与前端展示（Req1.5）。

关键判定（对应 requirements.md Requirement 1）：
  - Req1.1：被触发后读取 Production_Path_Pointer 取得当前 modeling_path。
  - Req1.2/1.3：seq_annotation → SeqDailyStrategy 且不触发 Legacy；legacy_day → 反之。
  - Req1.4：指针读取失败或取值不在 {legacy_day, seq_annotation} → 跳过本轮、不分派任一策略，
    以 status=skipped / reason=invalid_modeling_path 记录运行状态。
  - Req1.5：完成分派后在运行状态记录实际 modeling_path 与目标策略名称。
  - Req1.8：两条策略共用 Data_Watermark 作为时间进度基准（由本类注入 DataWatermarkService），
    均按数据到达推进、不看墙钟。

依赖解耦（避免与未完成任务/循环导入耦合）：
  - 策略实例通过**可注入映射** strategies（modeling_path → DetectionStrategy）获得；默认空。
    LegacyDayStrategy / SeqDailyStrategy 由后续任务 5.1 / 6.1 注册；缺失时本类返回
    status=skipped / reason=strategy_not_registered，不 import 尚不存在的策略类。
  - 指针读取、model_ref 读取、状态落账、水位服务均可注入；默认实现用**惰性 import**
    从 pv_fault_tasks / CumulativeTrainingService / DB 层取得，避免 pv_fault_tasks 在
    任务 4.3 反向 import 本模块时形成模块级循环导入。

对应设计：.kiro/specs/pv-fault-dual-path-serving/design.md §1 DualPathScheduler。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from services.scheduler.pv_dual_path.strategy_base import (
    CycleContext,
    CycleResult,
    DetectionStrategy,
)
from services.scheduler.pv_dual_path.watermark import DataWatermarkService

logger = logging.getLogger(__name__)

#: 合法建模路径集合；不在此集合内（含空/None/任意字符串）一律按非法处理并跳过（Req1.4）。
_VALID_MODELING_PATHS: Tuple[str, ...] = ("legacy_day", "seq_annotation", "tsc")

#: 默认槽位，与 modeling_path 组合成分区键（Path_Isolation_Registry 的分区维度之一）。
_DEFAULT_SLOT = "pv_fault"
# 实验室简化切换写入的哨兵 Epoch：日滚按无边界窗口跑，不查生产 DeviceScope。
_LAB_UNBOUNDED_EPOCH_ID = "lab-unbounded"


def _utc_now_iso() -> str:
    """返回无歧义 UTC 时间戳（供落账 updated_at 使用）。"""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 默认可注入依赖（均惰性 import，避免模块级循环导入）
# ---------------------------------------------------------------------------

def _default_read_modeling_paths(slot: str) -> Dict[str, Any]:
    """默认从 PVModelRegistry 读取路径、Champion 与 active Epoch，不猜默认模型。"""
    from services.iterative_labeling.pv_model_registry import PVModelRegistry

    state = PVModelRegistry().get_slot(slot)
    path_models: Dict[str, Any] = {}
    for path, lifecycle in state.path_models.items():
        champion = lifecycle.champion
        path_models[path] = {
            **lifecycle.to_dict(),
            "model_ref": champion.model_ref if champion else None,
        }
    production = state.path_models.get(state.production_path)
    production_champion = production.champion if production else None
    return {
        "production_path": state.production_path,
        "fallback_path": state.fallback_path,
        "active_activation_epoch_id": state.active_activation_epoch_id,
        "path_models": path_models,
        "production_model_ref": (
            production_champion.model_ref if production_champion else None
        ),
        "registry_source": "pv_model_registry",
    }


def _default_status_writer(payload: Dict[str, Any]) -> None:
    """默认状态落账：复用 pv_fault_tasks._save_prediction_last_run（原子写相对路径 JSON）。"""
    from services.scheduler.tasks.pv_fault_tasks import _save_prediction_last_run

    _save_prediction_last_run(payload)


def _default_watermark_factory() -> Tuple[DataWatermarkService, Any]:
    """默认水位服务工厂：新建 DBAdapter 并包装成 DataWatermarkService。

    返回 (service, disposable)。disposable 为本工厂新建、需在 dispatch 结束后释放的
    DBAdapter；注入自定义 watermark/factory 时不由本类负责释放。
    """
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig

    adapter = DBAdapter(DBConfig())
    return DataWatermarkService(adapter), adapter


class DualPathScheduler:
    """双路径分派器 —— 读指针、校验、分派、落账；不含任何检测逻辑。

    构造参数（均可注入，默认惰性绑定生产实现）：
      - strategies            — Mapping[modeling_path, DetectionStrategy]，默认空 dict。
                                后续任务 5.1 / 6.1 注册 LegacyDayStrategy / SeqDailyStrategy。
      - read_modeling_paths   — Callable[[slot], dict]，读 modeling-paths 摘要；失败应抛异常。
      - status_writer         — Callable[[dict], None]，落账运行状态；默认写 prediction_last_run。
      - watermark             — 已构造的 DataWatermarkService（注入时其生命周期由调用方负责）。
      - watermark_factory     — Callable[[], DataWatermarkService | (service, disposable)]；
                                与 watermark 二选一；默认新建 DBAdapter 并在 dispatch 后释放。
    """

    def __init__(
        self,
        strategies: Optional[Dict[str, DetectionStrategy]] = None,
        *,
        read_modeling_paths: Optional[Callable[[str], Dict[str, Any]]] = None,
        status_writer: Optional[Callable[[Dict[str, Any]], None]] = None,
        watermark: Optional[DataWatermarkService] = None,
        watermark_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._strategies: Dict[str, DetectionStrategy] = dict(strategies or {})
        self._read_modeling_paths = read_modeling_paths or _default_read_modeling_paths
        self._status_writer = status_writer or _default_status_writer
        self._watermark = watermark
        self._watermark_factory = watermark_factory

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def dispatch(self, slot: str = _DEFAULT_SLOT) -> CycleResult:
        """读指针 → 校验 → 分派 → 落账，返回本轮 CycleResult。

        分派本身不做检测；检测逻辑在被分派策略的 run_cycle 内。指针读取失败/非法、
        策略未注册均返回 status=skipped 并落账，不抛未捕获异常影响调度框架（Req1.4）。
        """
        started_at = datetime.utcnow()

        # 1) 读取生产路径指针（Req1.1）。读取失败 → 归类为 invalid_modeling_path（Req1.4）。
        try:
            summary = self._read_modeling_paths(slot)
            modeling_path = str((summary or {}).get("production_path") or "").strip()
        except Exception as exc:  # noqa: BLE001 — 任何读取异常都不得冒泡到调度框架
            logger.warning(
                "pv_dual_path.dispatch: 读取生产路径指针失败 slot=%s: %s", slot, exc
            )
            return self._skip(
                slot,
                started_at,
                reason="invalid_modeling_path",
                modeling_path=None,
                message=f"读取生产路径指针失败：{exc}",
            )

        # 2) 校验取值（Req1.4）。
        if modeling_path not in _VALID_MODELING_PATHS:
            logger.warning(
                "pv_dual_path.dispatch: 非法 modeling_path=%r slot=%s，跳过本轮",
                modeling_path, slot,
            )
            return self._skip(
                slot,
                started_at,
                reason="invalid_modeling_path",
                modeling_path=modeling_path or None,
                message=f"生产路径指针取值非法：{modeling_path!r}",
            )

        # 3) 取对应策略（可注入映射；未注册 → 跳过，便于后续任务注册，Req1.2/1.3 的前置）。
        strategy = self._strategies.get(modeling_path)
        if strategy is None:
            logger.info(
                "pv_dual_path.dispatch: modeling_path=%s 尚未注册策略，跳过本轮", modeling_path
            )
            return self._skip(
                slot,
                started_at,
                reason="strategy_not_registered",
                modeling_path=modeling_path,
                message=f"路径 {modeling_path} 尚未注册检测策略",
            )

        champion_ref = self._resolve_champion_ref(summary, modeling_path)
        if not champion_ref:
            return self._skip(
                slot,
                started_at,
                reason="missing_champion_model_ref",
                modeling_path=modeling_path,
                message=f"路径 {modeling_path} 没有可用 Champion，拒绝猜测默认模型",
            )
        epoch_id = str((summary or {}).get("active_activation_epoch_id") or "").strip()
        if epoch_id == _LAB_UNBOUNDED_EPOCH_ID:
            logger.warning(
                "pv_dual_path.dispatch: 实验室无边界 Epoch，按旧窗口语义分派 slot=%s path=%s",
                slot,
                modeling_path,
            )
            epoch_id = ""
        elif not epoch_id:
            return self._skip(
                slot,
                started_at,
                reason="missing_activation_epoch",
                modeling_path=modeling_path,
                message="缺少 active_activation_epoch_id，拒绝在无启用周期时分派",
            )

        # 4) 构造 CycleContext 快照并分派。本轮只用启动时读到的路径/Champion/Epoch。
        watermark, disposable = self._resolve_watermark()
        try:
            ctx = CycleContext(
                slot=slot,
                modeling_path=modeling_path,
                champion_model_ref=champion_ref,
                activation_epoch_id=epoch_id,
                watermark=watermark,
                started_at=started_at,
            )
            result = strategy.run_cycle(ctx)
        finally:
            self._dispose(disposable)

        # 5) 落账运行状态（Req1.5：记录实际 modeling_path 与目标策略名称）。
        self._write_status(
            result,
            slot,
            started_at,
            champion_model_ref=champion_ref,
            activation_epoch_id=epoch_id,
        )
        return result

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _resolve_champion_ref(self, summary: Dict[str, Any], modeling_path: str) -> str:
        """只取当前路径 Champion；缺失返回空串，由 dispatch 跳过，不回退其它路径或旧生产指针。"""
        try:
            path_models = (summary or {}).get("path_models") or {}
            entry = path_models.get(modeling_path) or {}
            champion = entry.get("champion") if isinstance(entry, dict) else None
            if isinstance(champion, dict):
                ref = str(champion.get("model_ref") or "").strip()
                if ref:
                    return ref
            ref = str(entry.get("model_ref") or "").strip()
            if ref:
                return ref
            return ""
        except Exception as exc:  # noqa: BLE001
            logger.debug("pv_dual_path.dispatch: 解析 Champion 失败: %s", exc)
            return ""

    def _resolve_watermark(self) -> Tuple[DataWatermarkService, Any]:
        """解析本轮共用的 DataWatermarkService。

        返回 (service, disposable)。disposable 非 None 时由本类在 dispatch 结束后释放；
        注入的 watermark / 自定义 factory 的资源生命周期由调用方负责（disposable=None）。
        """
        if self._watermark is not None:
            return self._watermark, None
        if self._watermark_factory is not None:
            produced = self._watermark_factory()
            if isinstance(produced, tuple) and len(produced) == 2:
                return produced[0], produced[1]
            return produced, None
        return _default_watermark_factory()

    @staticmethod
    def _dispose(disposable: Any) -> None:
        """best-effort 释放本类新建的 DB 资源；失败不影响主流程。"""
        if disposable is None:
            return
        dispose = getattr(disposable, "dispose", None)
        if callable(dispose):
            try:
                dispose()
            except Exception as exc:  # noqa: BLE001
                logger.debug("pv_dual_path.dispatch: 释放水位 DB 资源失败: %s", exc)

    def _skip(
        self,
        slot: str,
        started_at: datetime,
        *,
        reason: str,
        modeling_path: Optional[str],
        message: str,
    ) -> CycleResult:
        """构造并落账一个 status=skipped 的 CycleResult（不分派任一策略）。"""
        result = CycleResult(
            modeling_path=modeling_path or "",
            strategy_name="",
            window_start=None,
            window_end=None,
            points_detected=0,
            points_deferred=0,
            devices_processed=0,
            batch_ids=[],
            review_ids=[],
            status="skipped",
            skipped_reason=reason,
        )
        self._write_status(result, slot, started_at, message=message)
        return result

    def _write_status(
        self,
        result: CycleResult,
        slot: str,
        started_at: datetime,
        *,
        message: Optional[str] = None,
        champion_model_ref: Optional[str] = None,
        activation_epoch_id: Optional[str] = None,
    ) -> None:
        """把 CycleResult 转成 prediction_last_run 落账 payload 并写入（Req1.5）。

        payload 沿用现有状态消费者约定的 status / reason 字段；并补充 modeling_path、
        strategy_name、时间边界与条数等可断言字段，供审计与前端展示。落账失败不冒泡。
        """
        payload: Dict[str, Any] = {
            "task_id": "pv_prediction",
            "slot": slot,
            "status": result.status,
            # 现有状态消费者读 reason；skipped_reason 为空时用状态名兜底。
            "reason": result.skipped_reason or result.status,
            "modeling_path": result.modeling_path or None,
            "strategy_name": result.strategy_name or None,
            "window_start": result.window_start,
            "window_end": result.window_end,
            "points_detected": result.points_detected,
            "points_deferred": result.points_deferred,
            "devices_processed": result.devices_processed,
            "batch_ids": list(result.batch_ids),
            "review_ids": list(result.review_ids),
            "champion_model_ref": champion_model_ref,
            "activation_epoch_id": activation_epoch_id,
            "backlog_remaining": int(result.backlog_remaining or 0),
            "batched_backlog": bool(result.batched_backlog),
            "started_at": started_at.replace(tzinfo=timezone.utc).isoformat(),
            "updated_at": _utc_now_iso(),
        }
        if message is not None:
            payload["message"] = message
        try:
            self._status_writer(payload)
        except Exception as exc:  # noqa: BLE001 — 落账失败不得影响分派返回
            logger.warning("pv_dual_path.dispatch: 运行状态落账失败: %s", exc)
# @AI_GENERATED: end
