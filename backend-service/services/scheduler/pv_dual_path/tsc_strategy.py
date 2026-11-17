# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/scheduler/pv_dual_path/tsc_strategy.py — TSC 时序分类诊断检测策略

TscDailyStrategy 是「时序分类诊断（tsc）」路径的检测策略实现，与 LegacyDayStrategy
（天级聚合特征 + RF）和 SeqDailyStrategy（全天 288 点序列标注）并列，作为第三条
生产检测路径接入 DualPathScheduler。

核心区别：
  - 天路径把一天时序聚合成统计特征向量，喂 RandomForest 做日级分类。
  - 点路径（CausalTCN）实时逐点判定，每来一个点立即输出。
  - TSC 路径把目标设备日组织为 288×3 clock-grid（value/i_cal/is_measured），
    由冻结预测画布加载模型训练时的窗口合同，执行多窗口分类并按多数投票聚合为日级诊断。

slot = ``pv_tsc``（独立），modeling_path = ``tsc``。
游标语义和天路径一致（event_time_watermark），不需要 SeqDeviceDayLedger。

首轮运行时如果 ``device_prediction_cursor`` 中无 ``slot="pv_tsc"`` 的行，
会从 DataWatermarkService 读取全部设备列表，以当前水位为起始游标建行（lazy 初始化，
只检测新数据，历史回补通过 BackfillRunner 按需进行）。

运行环境：conda ``cp_web``。
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import select

from services.db.models.pv_fault import DevicePredictionCursor
from services.scheduler.pv_dual_path.path_activation import DeviceScope, PathActivationService
from services.scheduler.pv_dual_path.path_isolation import PathIsolationRegistry
from services.scheduler.pv_dual_path.production_window import is_production_responsible_date
from services.scheduler.pv_dual_path.strategy_base import CycleContext, CycleResult

logger = logging.getLogger(__name__)

_TSC = "tsc"
_TSC_SLOT = "pv_tsc"

DeviceKey = Tuple[Any, Any, Any]


def _default_adapter_factory():
    """默认 DBAdapter 工厂。"""
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig

    return DBAdapter(DBConfig())


def _default_workflow_runner(**kwargs: Any) -> Dict[str, Any]:
    """延迟导入持久化画布执行器，避免策略模块加载时反向初始化 API。"""
    from services.scheduler.slot_workflow_runner import run_slot_workflow_sync

    return run_slot_workflow_sync(**kwargs)


def _normalized_timestamp(value: Any) -> Optional[pd.Timestamp]:
    """把单个 Event_Time 转为无时区 Timestamp；无效返回 None。"""
    parsed = pd.to_datetime(value, errors="coerce")
    if parsed is None or not isinstance(parsed, (datetime, pd.Timestamp)) or pd.isna(parsed):
        return None
    ts = pd.Timestamp(parsed)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


class TscDailyStrategy:
    """TSC 时序分类检测策略 — 滑动窗口 MultiRocket + 多窗口投票 → 日级诊断。

    构造参数：
      - pv_repo            — PVFaultRepository 实例，复用其查询与写入接口。
      - adapter_factory    — 可注入的 DBAdapter 工厂（测试隔离用）。
      - registry_factory   — 可注入的 PathIsolationRegistry 工厂。
      - activation_factory — 可注入的 PathActivationService 工厂。
    """

    name = "TscDailyStrategy"

    def __init__(
        self,
        pv_repo: Any,
        *,
        adapter_factory: Optional[Callable[[], Any]] = None,
        registry_factory: Optional[Callable[[Any], PathIsolationRegistry]] = None,
        activation_factory: Optional[Callable[[Any], PathActivationService]] = None,
        workflow_runner: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> None:
        self._pv_repo = pv_repo
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._registry_factory = registry_factory or (lambda adapter: PathIsolationRegistry(adapter))
        self._activation_factory = activation_factory or (
            lambda adapter: PathActivationService(adapter)
        )
        self._workflow_runner = workflow_runner or _default_workflow_runner

    # ------------------------------------------------------------------
    # 策略入口
    # ------------------------------------------------------------------

    def run_cycle(self, ctx: CycleContext) -> CycleResult:
        """执行一轮 TSC 检测。

        新点只用于确定待检测目标日；真正推理数据始终从原始测量表读取“前一日 +
        目标日”完整上下文，避免被 ``pv_point`` 标签状态截断。只有已成功产生日级
        预测的连续目标日才允许推进 ``pv_tsc/tsc`` 独立游标。
        """
        from services.scheduler.tasks import pv_fault_tasks as legacy

        slot = ctx.slot or _TSC_SLOT
        modeling_path = ctx.modeling_path or _TSC

        model_ref = str(ctx.champion_model_ref or "").strip()
        if not model_ref:
            return self._skipped(modeling_path, "missing_champion_model_ref")
        if not self._model_artifact_available(model_ref):
            return self._skipped(modeling_path, "model_pending")

        from services.operator_execution.slot_workflows import resolve_predict_workflow_id

        workflow_id = resolve_predict_workflow_id(slot)

        adapter = self._adapter_factory()
        try:
            registry = self._registry_factory(adapter)
            device_cursors = self._read_partition_cursors(adapter, slot, modeling_path)
            if not device_cursors:
                device_cursors = self._lazy_init_cursors(
                    adapter, ctx.watermark, slot, modeling_path,
                )
            if not device_cursors:
                return self._skipped(modeling_path, "no_device_cursors")

            predictions: List[Dict[str, Any]] = []
            source_rows: List[Dict[str, Any]] = []
            window_config: Dict[str, Any] = {}
            cursor_advances: Dict[DeviceKey, datetime] = {}
            skipped_caught_up = 0
            rejected_invalid = 0

            for device_key, old_cursor in device_cursors.items():
                site_id, device_id, branch_id = device_key
                watermark = ctx.watermark.device_watermark(site_id, device_id, branch_id)
                if watermark is None or (old_cursor is not None and watermark <= old_cursor):
                    skipped_caught_up += 1
                    continue

                watermark_ts = pd.Timestamp(watermark)
                candidate_start = (
                    pd.Timestamp(old_cursor)
                    if old_cursor is not None
                    else watermark_ts.normalize() - pd.Timedelta(days=1)
                )
                candidate_rows = self._pv_repo.query_device_measurements(
                    site_id=str(site_id),
                    device_id=str(device_id),
                    branch_id=str(branch_id),
                    time_start=candidate_start.to_pydatetime(),
                    time_end=(watermark_ts + pd.Timedelta(microseconds=1)).to_pydatetime(),
                )
                if not candidate_rows:
                    skipped_caught_up += 1
                    continue

                days_data: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                has_invalid = False
                for row in candidate_rows:
                    row_dict = dict(row) if not isinstance(row, dict) else dict(row)
                    event_time = _normalized_timestamp(row_dict.get("time"))
                    if event_time is None:
                        has_invalid = True
                        rejected_invalid += 1
                        continue
                    if old_cursor is not None and event_time <= pd.Timestamp(old_cursor):
                        continue
                    if event_time > watermark_ts:
                        continue
                    days_data[event_time.date().isoformat()].append(row_dict)

                if has_invalid or not days_data:
                    skipped_caught_up += 1
                    continue

                epoch_id = str(ctx.activation_epoch_id or "").strip()
                if epoch_id:
                    try:
                        activation = self._activation_factory(adapter)
                        scope = DeviceScope(str(site_id), str(device_id), str(branch_id))
                        days_data = {
                            day: rows_list
                            for day, rows_list in days_data.items()
                            if is_production_responsible_date(
                                activation, epoch_id, scope, date.fromisoformat(day)
                            )
                        }
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("TscDailyStrategy: PathActivation 检查失败: %s", exc)
                        days_data = {}

                if not days_data:
                    skipped_caught_up += 1
                    continue

                successful_event_times: List[pd.Timestamp] = []
                for day_key in sorted(days_data):
                    target_date = date.fromisoformat(day_key)
                    context_start = datetime.combine(
                        target_date - timedelta(days=1), datetime.min.time()
                    )
                    context_end = datetime.combine(
                        target_date + timedelta(days=1), datetime.min.time()
                    )
                    context_rows = self._pv_repo.query_device_measurements(
                        site_id=str(site_id),
                        device_id=str(device_id),
                        branch_id=str(branch_id),
                        time_start=context_start,
                        time_end=context_end,
                    )
                    context_frame = pd.DataFrame(context_rows)
                    if "time" in context_frame.columns:
                        context_frame["time"] = pd.to_datetime(
                            context_frame["time"], errors="coerce"
                        )

                    canvas_input_id = (
                        f"tsc-canvas-{target_date.strftime('%Y%m%d')}-"
                        f"{uuid.uuid4().hex[:10]}"
                    )
                    try:
                        _, canvas_input_path = legacy._write_prediction_input(
                            context_frame,
                            canvas_input_id,
                            slot=slot,
                        )
                        canvas_result = self._workflow_runner(
                            slot=slot,
                            workflow_id=workflow_id,
                            execution_purpose="product_workflow",
                            model_artifact_ref=model_ref,
                            extra_global_config={
                                "input_file_path": canvas_input_path,
                                "operate_status": "predict",
                                "run_mode": "predict",
                            },
                            operator_param_overrides={
                                "tsc_predict": {
                                    "target_day": day_key,
                                    "aggregation": "majority",
                                }
                            },
                            execution_metadata={
                                "target_day": day_key,
                                "site_id": str(site_id),
                                "device_id": str(device_id),
                                "branch_id": str(branch_id),
                                "input_file_path": canvas_input_path,
                            },
                            require_persisted_execution=True,
                        )
                        result = self._extract_workflow_prediction(
                            canvas_result,
                            device_key=device_key,
                            target_day=day_key,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.info(
                            "TscDailyStrategy: 设备 %s 日期 %s 画布执行延后，"
                            "未推进游标: %s",
                            device_key,
                            day_key,
                            exc,
                        )
                        # 不允许越过失败日期，否则该设备日将永久失去重试机会。
                        break

                    current_window_config = dict(
                        result.get("model_window_config") or {}
                    )
                    if (
                        window_config
                        and current_window_config
                        and current_window_config != window_config
                    ):
                        logger.error(
                            "TscDailyStrategy: 同批模型窗口合同不一致，设备 %s 日期 %s 不落账",
                            device_key,
                            day_key,
                        )
                        break
                    if current_window_config:
                        window_config = current_window_config

                    predictions.append({
                        "site_id": site_id,
                        "device_id": device_id,
                        "branch_id": branch_id,
                        "time_window": day_key,
                        "target_day": result.get("target_day") or day_key,
                        "predicted_label": int(result["predicted_label"]),
                        "confidence": float(result.get("confidence") or 0.0),
                        "n_windows": int(result.get("n_windows") or 0),
                        "per_window_predictions": result.get("per_window_predictions") or [],
                        "per_window_details": result.get("per_window_details") or [],
                        "aggregation": result.get("aggregation") or "majority",
                        "model_name": result.get("model_name"),
                        "model_window_config": current_window_config,
                        "source_workflow_id": canvas_result.get("workflow_id"),
                        "source_execution_id": canvas_result.get("execution_id"),
                        "source_workflow_version": canvas_result.get(
                            "source_workflow_version"
                        ),
                    })
                    source_rows.extend(
                        {**dict(row), "tsc_target_day": day_key}
                        for row in context_rows
                    )
                    for row in days_data[day_key]:
                        event_time = _normalized_timestamp(row.get("time"))
                        if event_time is not None:
                            successful_event_times.append(event_time)

                if successful_event_times:
                    new_cursor = max(successful_event_times).to_pydatetime()
                    if old_cursor is None or new_cursor > old_cursor:
                        cursor_advances[device_key] = new_cursor

            if not predictions:
                return self._skipped(
                    modeling_path,
                    "no_inference_sample",
                    rejected_invalid=rejected_invalid,
                )

            batch_id = (
                f"tsc-pred-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-"
                f"{uuid.uuid4().hex[:8]}"
            )
            _, source_dataset_path = legacy._write_prediction_input(
                source_rows,
                batch_id,
                extra_columns=["tsc_target_day"],
                slot=slot,
            )
            record_payloads = [
                {
                    "model_version_id": None,
                    "site_id": prediction["site_id"],
                    "device_id": prediction["device_id"],
                    "branch_id": prediction["branch_id"],
                    "predicted_label": prediction["predicted_label"],
                    "confidence": prediction["confidence"],
                    "input_feature_json": {
                        "prediction_batch_id": batch_id,
                        "time_window": prediction["time_window"],
                        "source_dataset_path": source_dataset_path,
                        "model_ref": model_ref,
                        "modeling_path": modeling_path,
                        "n_windows": prediction.get("n_windows"),
                        "per_window_predictions": prediction.get("per_window_predictions"),
                        "per_window_details": prediction.get("per_window_details"),
                        "aggregation": prediction.get("aggregation"),
                        "window_config": window_config,
                        "source_workflow_id": prediction.get("source_workflow_id"),
                        "source_execution_id": prediction.get("source_execution_id"),
                        "source_workflow_version": prediction.get(
                            "source_workflow_version"
                        ),
                    },
                }
                for prediction in predictions
            ]
            registry.write_prediction_records(
                self._pv_repo, slot, modeling_path, record_payloads
            )

            legacy._write_prediction_batch(
                batch_id,
                source_dataset_path=source_dataset_path,
                model_ref=model_ref,
                model_path=model_ref,
                predictions=predictions,
                modeling_path=modeling_path,
                cursor_advance_times=cursor_advances,
                slot=slot,
            )
            review_session = legacy._create_prediction_review_session(
                batch_id,
                source_dataset_path=source_dataset_path,
                model_ref=model_ref,
                predictions=predictions,
                modeling_path=modeling_path,
                slot=slot,
                window_config=window_config,
            )
            review_id = str(review_session["review_id"])

            for device_key, new_time in cursor_advances.items():
                registry.advance_cursor(
                    slot=slot,
                    modeling_path=modeling_path,
                    site_id=str(device_key[0]),
                    device_id=str(device_key[1]),
                    branch_id=str(device_key[2]),
                    event_time=new_time,
                )

            all_event_times = [
                prediction["time_window"]
                for prediction in predictions
                if prediction.get("time_window")
            ]
            devices_advanced = len(cursor_advances)
            logger.info(
                "TscDailyStrategy: batch=%s review=%s predictions=%d devices=%d "
                "rejected_invalid=%d caught_up=%d",
                batch_id,
                review_id,
                len(predictions),
                devices_advanced,
                rejected_invalid,
                skipped_caught_up,
            )
            return CycleResult(
                modeling_path=modeling_path,
                strategy_name=self.name,
                window_start=min(all_event_times) if all_event_times else None,
                window_end=max(all_event_times) if all_event_times else None,
                points_detected=len(predictions),
                points_deferred=0,
                devices_processed=devices_advanced,
                batch_ids=[batch_id],
                review_ids=[review_id],
                status="success",
                skipped_reason=(
                    f"rejected_invalid_event_time={rejected_invalid}"
                    if rejected_invalid
                    else None
                ),
            )
        finally:
            self._dispose(adapter)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _model_artifact_available(model_ref: str) -> bool:
        """只做模型目录存在性预检；真正加载必须由画布内 ``tsc_predict`` 完成。"""
        from pathlib import Path

        backend_dir = Path(__file__).resolve().parents[3]
        reference = Path(model_ref)
        candidates = (
            [reference]
            if reference.is_absolute()
            else [backend_dir / reference, backend_dir.parent / reference, Path.cwd() / reference]
        )
        available = any(candidate.is_dir() for candidate in candidates)
        if not available:
            logger.info("TscDailyStrategy: 模型路径不存在 model_ref=%s", model_ref)
        return available

    @staticmethod
    def _extract_workflow_prediction(
        canvas_result: Dict[str, Any],
        *,
        device_key: DeviceKey,
        target_day: str,
    ) -> Dict[str, Any]:
        """从画布结果中选出唯一设备日；缺失、冲突或算子错误均 fail-closed。"""
        rows = canvas_result.get("fault_predictions")
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("TSC 预测画布未返回 fault_predictions")

        expected_ids = tuple(str(value) for value in device_key)
        matches: List[Dict[str, Any]] = []
        for value in rows:
            if not isinstance(value, dict):
                continue
            row_ids = tuple(
                str(value.get(name))
                for name in ("site_id", "device_id", "branch_id")
            )
            row_day = str(value.get("target_day") or value.get("time_window") or "")[:10]
            if row_ids == expected_ids and row_day == target_day:
                matches.append(value)

        if len(matches) != 1:
            raise RuntimeError(
                f"TSC 预测画布期望唯一设备日结果，实际匹配 {len(matches)} 条"
            )
        selected = dict(matches[0])
        if selected.get("error"):
            raise RuntimeError(str(selected["error"]))
        if selected.get("predicted_label") is None:
            raise RuntimeError("TSC 预测画布结果缺少 predicted_label")
        return selected

    def _read_partition_cursors(
        self, adapter: Any, slot: str, modeling_path: str,
    ) -> Dict[DeviceKey, Optional[datetime]]:
        """读 (slot, modeling_path) 分区下全部设备的游标水位。"""
        with adapter.get_sync_session() as session:
            rows = session.execute(
                select(DevicePredictionCursor).where(
                    DevicePredictionCursor.slot == slot,
                    DevicePredictionCursor.modeling_path == modeling_path,
                )
            ).scalars().all()
            return {
                (row.site_id, row.device_id, row.branch_id): row.last_predicted_time
                for row in rows
            }

    def _lazy_init_cursors(
        self,
        adapter: Any,
        watermark_service: Any,
        slot: str,
        modeling_path: str,
    ) -> Dict[DeviceKey, Optional[datetime]]:
        """Lazy 游标初始化：首轮无 pv_tsc 游标行时，从已有设备列表建行。

        从 pv_fault/legacy_day 分区读取全部设备三元组（该分区一定存在且最全），
        为每台设备在 (slot=pv_tsc, modeling_path=tsc) 下创建游标行，
        ``last_predicted_time`` 设为当前水位（只检测新数据）。
        """
        logger.info(
            "TscDailyStrategy: slot=%s 无游标行，开始 lazy 初始化（从当前水位开始）",
            slot,
        )
        # 从 pv_fault/legacy_day 读设备列表（最全的来源）
        with adapter.get_sync_session() as session:
            existing_rows = session.execute(
                select(DevicePredictionCursor).where(
                    DevicePredictionCursor.slot == "pv_fault",
                    DevicePredictionCursor.modeling_path == "legacy_day",
                )
            ).scalars().all()

        if not existing_rows:
            logger.warning("TscDailyStrategy: pv_fault/legacy_day 也无游标行，无法初始化")
            return {}

        cursors: Dict[DeviceKey, Optional[datetime]] = {}
        with adapter.get_sync_session() as session:
            for row in existing_rows:
                device_key = (row.site_id, row.device_id, row.branch_id)
                # 以设备当前水位为起始游标（只检测新数据）
                current_watermark = watermark_service.device_watermark(
                    row.site_id, row.device_id, row.branch_id,
                )
                new_row = DevicePredictionCursor(
                    slot=slot,
                    modeling_path=modeling_path,
                    site_id=row.site_id,
                    device_id=row.device_id,
                    branch_id=row.branch_id,
                    last_predicted_time=current_watermark,
                )
                session.merge(new_row)
                cursors[device_key] = current_watermark
            session.commit()

        logger.info(
            "TscDailyStrategy: lazy 初始化完成，建立 %d 台设备的游标行",
            len(cursors),
        )
        return cursors

    def _skipped(
        self,
        modeling_path: str,
        reason: str,
        *,
        rejected_invalid: int = 0,
    ) -> CycleResult:
        """构造 status=skipped 的空 CycleResult。"""
        skipped_reason = reason
        if rejected_invalid:
            skipped_reason = f"{reason};rejected_invalid_event_time={rejected_invalid}"
        return CycleResult(
            modeling_path=modeling_path,
            strategy_name=self.name,
            window_start=None,
            window_end=None,
            points_detected=0,
            points_deferred=0,
            devices_processed=0,
            batch_ids=[],
            review_ids=[],
            status="skipped",
            skipped_reason=skipped_reason,
        )

    @staticmethod
    def _dispose(adapter: Any) -> None:
        """Best-effort 释放 DB 资源。"""
        dispose = getattr(adapter, "dispose", None)
        if callable(dispose):
            try:
                dispose()
            except Exception:  # noqa: BLE001
                pass
# @AI_GENERATED: end
