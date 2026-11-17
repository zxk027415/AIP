# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/scheduler/pv_dual_path/seq_daily_strategy.py — 全天序列检测策略（Seq_Daily_Strategy）

SeqDailyStrategy 是双路径调度里 `modeling_path=seq_annotation`（全天序列路径）的检测策略实现，
实现 strategy_base.DetectionStrategy 协议（`name` + `run_cycle(ctx)->CycleResult`）。它由
DualPathScheduler 在指针命中 seq_annotation 时分派执行，语义是「只对（近）完整的历史整天
做 288 点时钟网格检测」。

本模块由现有 `services/scheduler/tasks/pv_fault_tasks.py::_run_seq_annotation_prediction_cycle()`
**等价搬迁**而来，并在其上**叠加**以下三处改造（对应 tasks.md 6.1）：

  1. 数据水位判定「历史整天」（Req3.1 / Req3.2）：
     把原「墙钟当天」判据 `_date < cutoff.date()` 替换为按设备数据水位的
     `event_date < ctx.watermark.device_watermark_date(...)`；两条策略共用 Data_Watermark、
     都不看墙钟，历史回放与实时生产口径一致。
  2. 显式完整性闸门（Req4.3 / Req3.3）：
     每个候选天先用 `PVFaultRepository.query_device_measurements` 拉整天全量，再经
     CompletenessGate（seq 严格：`admissible_for_path(decision, "seq_annotation")`）放行，
     未达标的设备-天不检测、保留至后续轮次；288 网格/掩码/占用率-间隔-覆盖门控与跨日拒绝
     仍由 SeqAnnotationPredictor.predict_device_day(include_night=True) **原样裁决、不放宽**
     （Req3.4 / Req3.5 / Req3.6）。
  3. 按 (slot, modeling_path=seq_annotation) 分区读写（Req5.1 / Req5.2）：
     游标（device_prediction_cursor）按 `modeling_path == "seq_annotation"` 读、写时带该分区键；
     预测记录（prediction_records）写入带 `modeling_path=seq_annotation` 标记。晚到点仍走
     Immutable_Batch_Recovery（复用 pv_fault_tasks 的 `_load_seq_recovery_batch` /
     `_partition_seq_predictions_for_recovery`），保留首次批次审核事实不被覆盖（Req3.7）。

行为等价与复用：批次落盘、审核会话创建、预测归一化、seq 幂等键、不可变批次恢复等既有能力
**直接复用** pv_fault_tasks 中的对应函数（惰性 import，避免与任务 4.3 反向 import 形成
模块级循环导入），不重写恢复语义。

状态落账不在本策略内进行：策略只返回可断言的 CycleResult，由 DualPathScheduler 统一写
prediction_last_run（Req1.5）；这样 ShadowCompareRunner 以只读方式复用本策略时不会污染生产
运行状态。

对应设计：.kiro/specs/pv-fault-dual-path-serving/design.md §3「SeqDailyStrategy」。
需求：3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.3。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from services.db.repositories.pv_fault import PVFaultRepository
from services.scheduler.pv_dual_path.completeness_gate import CompletenessGate
from services.scheduler.pv_dual_path.config import DualPathConfig, load_dual_path_config
from services.scheduler.pv_dual_path.path_activation import DeviceScope, PathActivationService
from services.scheduler.pv_dual_path.path_isolation import PathIsolationRegistry
from services.scheduler.pv_dual_path.production_window import is_production_responsible_date
from services.scheduler.pv_dual_path.seq_device_day_ledger import (
    DeviceDayKey,
    DeviceKey as LedgerDeviceKey,
    SeqDeviceDayLedgerRepository,
    stable_input_fingerprint,
)
from services.scheduler.pv_dual_path.strategy_base import CycleContext, CycleResult

logger = logging.getLogger(__name__)

#: 本策略负责的建模路径分区键（与 modeling_path 分区维度一致）。
_SEQ_ANNOTATION = "seq_annotation"

#: 设备三元组类型别名。
_DeviceKey = Tuple[Any, Any, Any]


class SeqDailyStrategy:
    """全天序列检测策略 —— 只检测数据水位之前的完整历史整天（288 点时钟网格）。

    构造参数（均可注入，便于测试与旁路复用）：
      - pv_repo             — PVFaultRepository，测量/预测记录读写入口。
      - config              — DualPathConfig，完整性阈值/期望点数；缺省经 load_dual_path_config()。
      - gate                — CompletenessGate，缺省时按 config + 内部 DB 适配器构造。
      - db_adapter_factory  — Callable[[], DBAdapter]，游标读写与闸门查询共用的 DB 适配器工厂；
                              缺省惰性新建 DBAdapter(DBConfig())，并在本轮结束后释放。
    """

    #: DetectionStrategy 协议要求的策略名称（审计/日志/CycleResult.strategy_name）。
    name = "SeqDailyStrategy"

    def __init__(
        self,
        pv_repo: PVFaultRepository,
        *,
        config: Optional[DualPathConfig] = None,
        gate: Optional[CompletenessGate] = None,
        db_adapter_factory: Optional[Callable[[], Any]] = None,
        ledger_factory: Optional[Callable[[Any, str], SeqDeviceDayLedgerRepository]] = None,
        activation_factory: Optional[Callable[[Any], PathActivationService]] = None,
        isolation_factory: Optional[Callable[[Any], PathIsolationRegistry]] = None,
    ) -> None:
        self._pv_repo = pv_repo
        self._config = config
        self._gate = gate
        self._db_adapter_factory = db_adapter_factory
        self._ledger_factory = ledger_factory
        self._activation_factory = activation_factory
        self._isolation_factory = isolation_factory

    # ------------------------------------------------------------------
    # DetectionStrategy 协议入口
    # ------------------------------------------------------------------

    def run_cycle(self, ctx: CycleContext) -> CycleResult:
        """执行一轮全天序列检测，返回可断言的 CycleResult（不落账运行状态）。"""
        model_ref = str(ctx.model_ref or "").strip()
        if not model_ref:
            return self._skipped(reason="model_pending", message="seq_annotation 尚无可用模型工件引用")

        # 1) 解析序列标注工件并加载 predictor（含生产契约校验）。失败 → 跳过（Req 前置）。
        predictor, model_id, model_path, invalid = self._load_predictor(model_ref)
        if invalid is not None:
            return invalid

        # 2) 准备 DB 适配器、完整性闸门。适配器由本类新建时在结束后释放。
        adapter, disposable = self._resolve_adapter()
        try:
            gate = self._resolve_gate(adapter)
            return self._run_with_resources(ctx, predictor, model_id, model_path, adapter, gate)
        finally:
            self._dispose(disposable)

    # ------------------------------------------------------------------
    # 主检测流程（持有 DB 适配器与闸门后执行）
    # ------------------------------------------------------------------

    def _run_with_resources(
        self,
        ctx: CycleContext,
        predictor: Any,
        model_id: str,
        model_path: str,
        adapter: Any,
        gate: CompletenessGate,
    ) -> CycleResult:
        from services.scheduler.tasks.pv_fault_tasks import (
            _create_prediction_review_session,
            _load_seq_recovery_batch,
            _normalize_predictions,
            _partition_seq_predictions_for_recovery,
            _seq_prediction_batch_id,
            _seq_sample_key,
            _write_prediction_batch,
            _write_prediction_input,
        )

        if self._should_use_ledger(ctx, adapter):
            return self._run_ledger_driven(
                ctx,
                predictor,
                model_id,
                model_path,
                adapter,
                gate,
                _create_prediction_review_session=_create_prediction_review_session,
                _normalize_predictions=_normalize_predictions,
                _seq_prediction_batch_id=_seq_prediction_batch_id,
                _seq_sample_key=_seq_sample_key,
                _write_prediction_batch=_write_prediction_batch,
                _write_prediction_input=_write_prediction_input,
            )

        pv_repo = self._pv_repo
        model_ref = str(ctx.model_ref or "").strip()

        # 3) 读取 seq_annotation 分区游标 + 设备三元组全集（缺分区视为初始水位，不复用其他分区值）。
        device_universe, seq_cursors = self._read_partition_cursors(adapter)
        if not device_universe:
            return self._skipped(
                reason="no_device_cursors",
                message="device_prediction_cursor 与到达表都为空，请先喂数据。",
            )

        # 4) 按设备用「数据水位」判定历史整天，收集每设备待检测的未标注点。
        rows_by_device: Dict[_DeviceKey, List[Dict[str, Any]]] = {}
        watermark_date_by_device: Dict[_DeviceKey, Any] = {}
        for device_key in device_universe:
            last_time = seq_cursors.get(device_key)
            # 游标已停在远处哨兵时不再对百万行 training_samples 逐设备打 MAX(time)。
            if last_time is not None and last_time >= datetime(2090, 1, 1):
                continue
            watermark_dt = ctx.watermark.device_watermark(
                device_key[0], device_key[1], device_key[2]
            )
            if watermark_dt is None:
                # 该设备尚无任何已到达数据 → 无「数据今天」基准，跳过（不推进游标）。
                continue
            watermark_date_by_device[device_key] = watermark_dt.date()
            # 缺分区游标视为固定初始水位 None（从初始位置起，Req5.6），不读其他 modeling_path 分区值。
            rows = pv_repo.query_unlabeled_by_point_labels(
                after_time=last_time,
                before_time=watermark_dt,
                site_id=device_key[0],
                device_id=device_key[1],
                branch_id=device_key[2],
            )
            if rows:
                rows_by_device[device_key] = rows

        if not rows_by_device:
            return self._skipped(
                reason="skipped_caught_up",
                message="所有设备均无新增待预测数据。",
            )

        # 5) 逐设备逐天：水位前完整整天 → 完整性闸门（seq 严格）→ predictor 检测。
        raw_predictions: List[Dict[str, Any]] = []
        prediction_input_rows: List[Dict[str, Any]] = []
        recovery_candidates: List[Dict[str, Any]] = []
        skipped_incomplete_days = 0
        # 条数守恒（Req1.7）：以游标治理的未标注候选点为统一计数单位。
        detected_points = 0
        deferred_points = 0
        detected_min_time: Optional[pd.Timestamp] = None
        detected_max_time: Optional[pd.Timestamp] = None

        for device_key, rows in rows_by_device.items():
            watermark_date = watermark_date_by_device[device_key]
            frame = pd.DataFrame(rows)
            frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
            frame = frame.dropna(subset=["time"]).sort_values("time")
            frame["_date"] = frame["time"].dt.date

            # 数据水位判定：仅自然日「严格早于」设备数据水位所在自然日的整天可进入检测。
            completed = frame[frame["_date"] < watermark_date]
            # 水位当天（及之后）的点顺延到后续轮次（Req3.2）。
            deferred_points += int(len(frame) - len(completed))
            if completed.empty:
                skipped_incomplete_days += 1
                continue

            # Seq 每设备只有一个时间游标，必须按自然日升序维护「连续成功前沿」。
            # 一旦某日不能形成检测事实，该日及所有更晚候选日都顺延，严禁游标越洞（Req3.9）。
            completed_day_groups = list(completed.groupby("_date", sort=True))
            for day_index, (day, day_group) in enumerate(completed_day_groups):
                day_point_count = int(len(day_group))
                remaining_point_count = sum(
                    int(len(later_group))
                    for _, later_group in completed_day_groups[day_index:]
                )
                remaining_day_count = len(completed_day_groups) - day_index
                recovery_candidates.append(
                    {
                        "site_id": device_key[0],
                        "device_id": device_key[1],
                        "branch_id": device_key[2],
                        "time_window": str(day),
                    }
                )

                # 显式完整性闸门（seq 严格）：首个未达标日形成消费洞，本轮不再考察更晚日期。
                decision = gate.evaluate(device_key[0], device_key[1], device_key[2], day)
                if not gate.admissible_for_path(decision, _SEQ_ANNOTATION):
                    logger.info(
                        "seq_daily_strategy: 设备%s 业务日 %s 未过完整性闸门 "
                        "ratio=%.4f error=%s；连续前沿在此停止，顺延该日及其后 %s 天",
                        device_key,
                        day,
                        decision.ratio,
                        decision.error,
                        remaining_day_count,
                    )
                    skipped_incomplete_days += remaining_day_count
                    deferred_points += remaining_point_count
                    break

                day_start = datetime.combine(day, datetime.min.time())
                full_day_rows = pv_repo.query_device_measurements(
                    site_id=device_key[0],
                    device_id=device_key[1],
                    branch_id=device_key[2],
                    time_start=day_start,
                    time_end=day_start + timedelta(days=1),
                )
                if not full_day_rows:
                    logger.info(
                        "seq_daily_strategy: 设备%s 业务日 %s 整天全量查询为空；"
                        "连续前沿在此停止，顺延该日及其后 %s 天",
                        device_key,
                        day,
                        remaining_day_count,
                    )
                    skipped_incomplete_days += remaining_day_count
                    deferred_points += remaining_point_count
                    break

                day_frame = pd.DataFrame(full_day_rows)
                day_frame["time"] = pd.to_datetime(day_frame["time"], errors="coerce")
                day_frame = day_frame.dropna(subset=["time"]).sort_values("time")

                # 288 网格/掩码/门控与跨日拒绝由 predictor 原样裁决，不放宽（Req3.4/3.5/3.6）。
                result = predictor.predict_device_day(day_frame, include_night=True)
                if result.get("error"):
                    logger.warning(
                        "seq_daily_strategy: predictor 拒绝 %s %s: %s；"
                        "连续前沿在此停止，顺延该日及其后 %s 天",
                        device_key,
                        day,
                        result["error"],
                        remaining_day_count,
                    )
                    skipped_incomplete_days += remaining_day_count
                    deferred_points += remaining_point_count
                    break

                # 只有成功形成预测事实的整天才进入不可变输入批次与游标推进候选。
                prediction_input_rows.extend(full_day_rows)
                detected_points += day_point_count
                day_min = day_group["time"].min()
                day_max = day_group["time"].max()
                if detected_min_time is None or day_min < detected_min_time:
                    detected_min_time = day_min
                if detected_max_time is None or day_max > detected_max_time:
                    detected_max_time = day_max

                raw_predictions.append(
                    {
                        "site_id": device_key[0],
                        "device_id": device_key[1],
                        "branch_id": device_key[2],
                        "time_window": str(day),
                        "predicted_label": result["predicted_label"],
                        "confidence": result["confidence"],
                        "prediction_detail": {
                            "timestamps": result["timestamps"],
                            "point_predictions": result["point_predictions"],
                            "raw_point_predictions": result.get("raw_point_predictions") or [],
                            "point_confidences": result["point_confidences"],
                            "segment_predictions": result["segment_predictions"],
                            "postprocessing": result.get("postprocessing") or {},
                            "model_name": result["model_name"],
                            "seq_len_used": result["seq_len_used"],
                            "trained_full_day": result["trained_full_day"],
                        },
                    }
                )

        predictions = _normalize_predictions(raw_predictions) if raw_predictions else []
        model_version = pv_repo.get_model_version(model_id)
        new_predictions, recovery_batches = _partition_seq_predictions_for_recovery(
            pv_repo,
            model_ref,
            predictions,
            recovery_candidates=recovery_candidates,
        )
        if not predictions and not recovery_batches:
            return self._skipped(
                reason="no_complete_device_day",
                message="新增数据中没有满足质量门控的完整设备日，游标未推进。",
                points_deferred=deferred_points,
            )

        # 6) 组织批次：先从数据库引用的不可变批次补建审核（保留首次事实），再处理本轮新增设备日。
        batch_results: List[Dict[str, Any]] = []
        final_device_advance_times: Dict[_DeviceKey, datetime] = {}
        final_device_model_ids: Dict[_DeviceKey, Optional[str]] = {}

        def merge_advance_times(
            values: Dict[_DeviceKey, datetime], cursor_model_id: Optional[str]
        ) -> None:
            for key, value in values.items():
                current = final_device_advance_times.get(key)
                if current is None or value >= current:
                    final_device_advance_times[key] = value
                    final_device_model_ids[key] = cursor_model_id

        # 6a) 不可变批次恢复（Req3.7）：不覆盖首次 predictions/source/cursor 事实。
        for recovery_batch_id in sorted(recovery_batches):
            recovery_model_ref = recovery_batches[recovery_batch_id]
            recovered_predictions, recovered_source_path, recovered_advances = (
                _load_seq_recovery_batch(recovery_batch_id, recovery_model_ref)
            )
            recovered_session = _create_prediction_review_session(
                recovery_batch_id,
                source_dataset_path=recovered_source_path,
                model_ref=recovery_model_ref,
                predictions=recovered_predictions,
                modeling_path=_SEQ_ANNOTATION,
            )
            recovery_model_version = pv_repo.get_model_version(recovery_model_ref)
            recovery_model_id = (
                recovery_model_ref if recovery_model_version is not None else None
            )
            merge_advance_times(recovered_advances, recovery_model_id)
            batch_results.append(
                {
                    "batch_id": recovery_batch_id,
                    "review_id": recovered_session["review_id"],
                    "prediction_count": len(recovered_predictions),
                    "inserted_count": 0,
                    "recovered": True,
                }
            )

        # 6b) 本轮新增设备日：独立批次，身份/游标不混入旧批次；预测记录带 seq_annotation 分区标记。
        if new_predictions:
            inserted, new_result = self._persist_new_predictions(
                pv_repo=pv_repo,
                model_ref=model_ref,
                model_id=model_id,
                model_path=model_path,
                model_version=model_version,
                new_predictions=new_predictions,
                prediction_input_rows=prediction_input_rows,
                seq_sample_key=_seq_sample_key,
                seq_prediction_batch_id=_seq_prediction_batch_id,
                write_prediction_input=_write_prediction_input,
                write_prediction_batch=_write_prediction_batch,
                create_prediction_review_session=_create_prediction_review_session,
            )
            merge_advance_times(
                inserted["advance_times"],
                model_id if model_version is not None else None,
            )
            batch_results.append(new_result)

        if not batch_results:
            return self._skipped(
                reason="all_duplicate",
                message="本批设备日预测记录均已存在且无可恢复批次，游标未推进。",
                points_deferred=deferred_points,
            )

        if not final_device_advance_times:
            raise RuntimeError("seq 预测批次已送审但没有可推进的设备游标")

        # 7) 推进 seq_annotation 分区游标（带 modeling_path 分区键，不影响 legacy_day 分区）。
        self._advance_partition_cursors(
            adapter, final_device_advance_times, final_device_model_ids
        )

        batch_ids = [item["batch_id"] for item in batch_results]
        review_ids = [item["review_id"] for item in batch_results]

        return CycleResult(
            modeling_path=_SEQ_ANNOTATION,
            strategy_name=self.name,
            window_start=detected_min_time.isoformat() if detected_min_time is not None else None,
            window_end=detected_max_time.isoformat() if detected_max_time is not None else None,
            points_detected=detected_points,
            points_deferred=deferred_points,
            devices_processed=len(final_device_advance_times),
            batch_ids=batch_ids,
            review_ids=review_ids,
            status="success",
            skipped_reason=None,
        )

    def _should_use_ledger(self, ctx: CycleContext, adapter: Any) -> bool:
        """有启用周期且适配器可开会话时走 Ledger 权威路径；否则保留旧队头语义。"""
        if not str(ctx.activation_epoch_id or "").strip():
            return False
        if self._ledger_factory is not None:
            return True
        return hasattr(adapter, "get_sync_session")

    def _cycle_limit(self) -> Tuple[int, bool]:
        config = self._config or load_dual_path_config()
        raw_value = getattr(config, "max_device_days_per_cycle", 50)
        try:
            raw = int(raw_value)
        except (TypeError, ValueError):
            return 50, True
        if raw < 1 or raw > 1000:
            return 50, True
        return raw, False

    def _run_ledger_driven(
        self,
        ctx: CycleContext,
        predictor: Any,
        model_id: str,
        model_path: str,
        adapter: Any,
        gate: CompletenessGate,
        *,
        _create_prediction_review_session: Callable[..., Dict[str, Any]],
        _normalize_predictions: Callable[..., List[Dict[str, Any]]],
        _seq_prediction_batch_id: Callable[..., str],
        _seq_sample_key: Callable[[Any], Tuple[Any, str]],
        _write_prediction_batch: Callable[..., None],
        _write_prediction_input: Callable[..., Tuple[Any, str]],
    ) -> CycleResult:
        """Ledger 驱动：逐日独立过门禁，较早 waiting/failed 不阻塞较晚 ready。"""
        from services.scheduler.pv_dual_path.immutable_batch_recovery import (
            ImmutableBatchRecovery,
        )

        epoch_id = str(ctx.activation_epoch_id or "").strip()
        slot = ctx.slot or "pv_fault"
        model_ref = str(ctx.champion_model_ref or ctx.model_ref or "").strip()
        pv_repo = self._pv_repo
        ledger = (
            self._ledger_factory(adapter, epoch_id)
            if self._ledger_factory is not None
            else SeqDeviceDayLedgerRepository(adapter, activation_epoch_id=epoch_id)
        )
        activation = (
            self._activation_factory(adapter)
            if self._activation_factory is not None
            else PathActivationService(adapter)
        )
        isolation = (
            self._isolation_factory(adapter)
            if self._isolation_factory is not None
            else PathIsolationRegistry(adapter)
        )
        recovery = ImmutableBatchRecovery(
            ledger, isolation, slot=slot, modeling_path=_SEQ_ANNOTATION
        )
        cycle_limit, invalid_limit = self._cycle_limit()

        device_universe, seq_cursors = self._read_partition_cursors(adapter)
        if not device_universe:
            return self._skipped(
                reason="no_device_cursors",
                message="device_prediction_cursor 与到达表都为空，请先喂数据。",
            )

        detected_points = 0
        deferred_points = 0
        candidate_days = 0
        detected_min_time: Optional[pd.Timestamp] = None
        detected_max_time: Optional[pd.Timestamp] = None

        for device_key in device_universe:
            watermark_dt = ctx.watermark.device_watermark(
                device_key[0], device_key[1], device_key[2]
            )
            if watermark_dt is None:
                continue
            watermark_date = watermark_dt.date()
            scope = DeviceScope(str(device_key[0]), str(device_key[1]), str(device_key[2]))
            boundary = activation.current_device_boundary(epoch_id, scope)
            start_date = boundary.effective_from_date if boundary is not None else None
            if start_date is None:
                continue
            last_time = seq_cursors.get(device_key)
            if last_time is not None:
                cursor_date = last_time.date() if hasattr(last_time, "date") else last_time
                if isinstance(cursor_date, date):
                    start_date = max(start_date, cursor_date + timedelta(days=1))
            day = start_date
            while day < watermark_date:
                day_start = datetime.combine(day, time.min)
                full_day_rows = pv_repo.query_device_measurements(
                    site_id=device_key[0],
                    device_id=device_key[1],
                    branch_id=device_key[2],
                    time_start=day_start,
                    time_end=day_start + timedelta(days=1),
                )
                point_count = len(full_day_rows)
                if not is_production_responsible_date(activation, epoch_id, scope, day):
                    day += timedelta(days=1)
                    continue
                candidate_days += 1
                decision = gate.evaluate(device_key[0], device_key[1], device_key[2], day)
                is_ready = bool(full_day_rows) and gate.admissible_for_path(
                    decision, _SEQ_ANNOTATION
                )
                fingerprint = stable_input_fingerprint(full_day_rows or [{"time": day.isoformat(), "value": None}])
                key = DeviceDayKey(
                    slot=slot,
                    modeling_path=_SEQ_ANNOTATION,
                    site_id=str(device_key[0]),
                    device_id=str(device_key[1]),
                    branch_id=str(device_key[2]),
                    business_date=day,
                )
                ledger.upsert_candidate(
                    key,
                    fingerprint,
                    is_ready=is_ready,
                    activation_epoch_id=epoch_id,
                )
                if not is_ready:
                    deferred_points += point_count
                day += timedelta(days=1)

        runnable = ledger.list_runnable(slot, limit=1000)
        remaining = max(0, len(runnable) - cycle_limit)
        batch = runnable[:cycle_limit]
        raw_predictions: List[Dict[str, Any]] = []
        batch_results: List[Dict[str, Any]] = []
        processed_devices: Dict[_DeviceKey, datetime] = {}

        for record in batch:
            key = record.key
            device_key = (key.site_id, key.device_id, key.branch_id)
            day = key.business_date
            day_start = datetime.combine(day, time.min)
            full_day_rows = pv_repo.query_device_measurements(
                site_id=key.site_id,
                device_id=key.device_id,
                branch_id=key.branch_id,
                time_start=day_start,
                time_end=day_start + timedelta(days=1),
            )
            infer = recovery.prepare_for_inference(
                key, full_day_rows, activation_epoch_id=epoch_id
            )
            if infer.action == "skip":
                continue
            if not full_day_rows:
                recovery.record_failure(infer, "empty_device_day")
                deferred_points += 0
                continue
            day_frame = pd.DataFrame(full_day_rows)
            day_frame["time"] = pd.to_datetime(day_frame["time"], errors="coerce")
            day_frame = day_frame.dropna(subset=["time"]).sort_values("time")
            try:
                result = predictor.predict_device_day(day_frame, include_night=True)
            except Exception as exc:  # noqa: BLE001
                recovery.record_failure(infer, str(exc))
                deferred_points += int(len(day_frame))
                continue
            if result.get("error"):
                recovery.record_failure(infer, str(result["error"]))
                deferred_points += int(len(day_frame))
                continue
            prediction = {
                "site_id": key.site_id,
                "device_id": key.device_id,
                "branch_id": key.branch_id,
                "time_window": str(day),
                "predicted_label": result["predicted_label"],
                "confidence": result["confidence"],
                "prediction_detail": {
                    "timestamps": result["timestamps"],
                    "point_predictions": result["point_predictions"],
                    "raw_point_predictions": result.get("raw_point_predictions") or [],
                    "point_confidences": result["point_confidences"],
                    "segment_predictions": result["segment_predictions"],
                    "postprocessing": result.get("postprocessing") or {},
                    "model_name": result["model_name"],
                    "seq_len_used": result["seq_len_used"],
                    "trained_full_day": result["trained_full_day"],
                },
            }
            predictions = _normalize_predictions([prediction])
            new_batch_id = _seq_prediction_batch_id(model_ref, predictions)
            _, source_path = _write_prediction_input(full_day_rows, new_batch_id)
            payload = {
                "source_dataset_path": source_path,
                "model_ref": model_ref,
                "model_path": model_path,
                "predictions": predictions,
                "modeling_path": _SEQ_ANNOTATION,
            }
            try:
                recovery.persist_success(infer, batch_id=new_batch_id, payload=payload)
            except Exception as exc:  # noqa: BLE001
                recovery.record_failure(infer, str(exc))
                deferred_points += int(len(day_frame))
                continue
            _write_prediction_batch(
                new_batch_id,
                source_dataset_path=source_path,
                model_ref=model_ref,
                model_path=model_path,
                predictions=predictions,
                modeling_path=_SEQ_ANNOTATION,
            )
            model_version = pv_repo.get_model_version(model_id)
            business_date, sample_id = _seq_sample_key(prediction["time_window"])
            pv_repo.insert_prediction_records(
                [
                    {
                        "model_version_id": model_id if model_version is not None else None,
                        "site_id": prediction["site_id"],
                        "device_id": prediction["device_id"],
                        "branch_id": prediction["branch_id"],
                        "predicted_label": prediction["predicted_label"],
                        "confidence": prediction["confidence"],
                        "business_date": business_date,
                        "sample_id": sample_id,
                        "modeling_path": _SEQ_ANNOTATION,
                        "input_feature_json": {
                            "prediction_batch_id": new_batch_id,
                            "time_window": prediction["time_window"],
                            "source_dataset_path": source_path,
                            "model_ref": model_ref,
                            "modeling_path": _SEQ_ANNOTATION,
                            "prediction_granularity": "point",
                            "input_fingerprint": infer.fingerprint,
                            "supersedes_batch_id": infer.supersedes_batch_id,
                        },
                    }
                ]
            )
            session = _create_prediction_review_session(
                new_batch_id,
                source_dataset_path=source_path,
                model_ref=model_ref,
                predictions=predictions,
                modeling_path=_SEQ_ANNOTATION,
            )
            batch_results.append(
                {
                    "batch_id": new_batch_id,
                    "review_id": session["review_id"],
                    "prediction_count": 1,
                    "inserted_count": 1,
                    "recovered": False,
                }
            )
            raw_predictions.append(prediction)
            detected_points += int(len(day_frame))
            day_min = day_frame["time"].min()
            day_max = day_frame["time"].max()
            if detected_min_time is None or day_min < detected_min_time:
                detected_min_time = day_min
            if detected_max_time is None or day_max > detected_max_time:
                detected_max_time = day_max
            processed_devices[device_key] = datetime.combine(day, time(23, 55))

        frontier_times: Dict[_DeviceKey, datetime] = {}
        unique_devices = {
            (record.key.site_id, record.key.device_id, record.key.branch_id)
            for record in runnable
        }
        unique_devices.update(processed_devices.keys())
        for triple in unique_devices:
            frontier = ledger.compute_frontier(
                LedgerDeviceKey(
                    slot=slot,
                    modeling_path=_SEQ_ANNOTATION,
                    site_id=str(triple[0]),
                    device_id=str(triple[1]),
                    branch_id=str(triple[2]),
                ),
                epoch_id,
            )
            if frontier is None:
                continue
            frontier_times[triple] = datetime.combine(frontier, time(23, 55))
        if frontier_times:
            self._advance_partition_cursors(
                adapter,
                frontier_times,
                {key: model_id for key in frontier_times},
            )

        if not batch_results and detected_points == 0:
            return CycleResult(
                modeling_path=_SEQ_ANNOTATION,
                strategy_name=self.name,
                window_start=None,
                window_end=None,
                points_detected=0,
                points_deferred=deferred_points,
                devices_processed=0,
                batch_ids=[],
                review_ids=[],
                status="skipped" if not batch else "success",
                skipped_reason="no_complete_device_day" if not batch else None,
                backlog_remaining=remaining,
                batched_backlog=remaining > 0,
                invalid_max_device_days_per_cycle=invalid_limit,
            )

        return CycleResult(
            modeling_path=_SEQ_ANNOTATION,
            strategy_name=self.name,
            window_start=detected_min_time.isoformat() if detected_min_time is not None else None,
            window_end=detected_max_time.isoformat() if detected_max_time is not None else None,
            points_detected=detected_points,
            points_deferred=deferred_points,
            devices_processed=len(frontier_times or processed_devices),
            batch_ids=[item["batch_id"] for item in batch_results],
            review_ids=[item["review_id"] for item in batch_results],
            status="success",
            skipped_reason=None,
            backlog_remaining=remaining,
            batched_backlog=remaining > 0,
            invalid_max_device_days_per_cycle=invalid_limit,
        )

    # ------------------------------------------------------------------
    # 新增设备日的落盘 + 记录写入（带 seq_annotation 分区标记）
    # ------------------------------------------------------------------

    def _persist_new_predictions(
        self,
        *,
        pv_repo: PVFaultRepository,
        model_ref: str,
        model_id: str,
        model_path: str,
        model_version: Any,
        new_predictions: List[Dict[str, Any]],
        prediction_input_rows: List[Dict[str, Any]],
        seq_sample_key: Callable[[Any], Tuple[Any, str]],
        seq_prediction_batch_id: Callable[..., str],
        write_prediction_input: Callable[..., Tuple[Any, str]],
        write_prediction_batch: Callable[..., None],
        create_prediction_review_session: Callable[..., Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """把本轮新增设备日预测落盘为不可变批次并写入 prediction_records（带 modeling_path）。

        与 pv_fault_tasks 原实现等价，唯一叠加是 record_payloads / 批次带
        `modeling_path=seq_annotation` 分区标记（Req5.2）。返回 (inserted_info, batch_result)。
        """
        new_batch_id = seq_prediction_batch_id(model_ref, new_predictions)
        new_unit_keys = {
            (
                prediction["site_id"],
                prediction["device_id"],
                prediction["branch_id"],
                str(prediction["time_window"]),
            )
            for prediction in new_predictions
        }
        new_input_rows: List[Dict[str, Any]] = []
        new_advance_times: Dict[_DeviceKey, datetime] = {}
        for row in prediction_input_rows:
            try:
                row_timestamp = pd.Timestamp(row["time"])
                row_day = str(row_timestamp.date())
            except (KeyError, TypeError, ValueError):
                continue
            row_key = (row.get("site_id"), row.get("device_id"), row.get("branch_id"), row_day)
            if row_key in new_unit_keys:
                new_input_rows.append(row)
                device_key = row_key[:3]
                advance_time = row_timestamp.to_pydatetime()
                previous_time = new_advance_times.get(device_key)
                if previous_time is None or advance_time > previous_time:
                    new_advance_times[device_key] = advance_time
        if not new_input_rows or not new_advance_times:
            raise RuntimeError("新增 seq 预测没有对应的不可变输入测量和游标时间")

        _, new_source_dataset_path = write_prediction_input(new_input_rows, new_batch_id)
        write_prediction_batch(
            new_batch_id,
            source_dataset_path=new_source_dataset_path,
            model_ref=model_ref,
            model_path=model_path,
            predictions=new_predictions,
            modeling_path=_SEQ_ANNOTATION,
            cursor_advance_times=new_advance_times,
        )

        record_payloads: List[Dict[str, Any]] = []
        for prediction in new_predictions:
            detail = prediction.get("prediction_detail") or {}
            business_date, sample_id = seq_sample_key(prediction["time_window"])
            record_payloads.append(
                {
                    "model_version_id": model_id if model_version is not None else None,
                    "site_id": prediction["site_id"],
                    "device_id": prediction["device_id"],
                    "branch_id": prediction["branch_id"],
                    "predicted_label": prediction["predicted_label"],
                    "confidence": prediction["confidence"],
                    "business_date": business_date,
                    "sample_id": sample_id,
                    # 叠加分区：预测记录带 seq_annotation 标记，消费方据此唯一确定路径（Req5.2）。
                    "modeling_path": _SEQ_ANNOTATION,
                    "input_feature_json": {
                        "prediction_batch_id": new_batch_id,
                        "time_window": prediction["time_window"],
                        "source_dataset_path": new_source_dataset_path,
                        "model_ref": model_ref,
                        "modeling_path": _SEQ_ANNOTATION,
                        "prediction_granularity": "point",
                        "segment_predictions": detail.get("segment_predictions") or [],
                        "detail_ref": f"{new_batch_id}:{prediction['time_window']}",
                    },
                }
            )

        inserted_records = pv_repo.insert_prediction_records(record_payloads)
        new_review_session = create_prediction_review_session(
            new_batch_id,
            source_dataset_path=new_source_dataset_path,
            model_ref=model_ref,
            predictions=new_predictions,
            modeling_path=_SEQ_ANNOTATION,
        )
        batch_result = {
            "batch_id": new_batch_id,
            "review_id": new_review_session["review_id"],
            "prediction_count": len(new_predictions),
            "inserted_count": len(inserted_records),
            "recovered": False,
        }
        return {"advance_times": new_advance_times}, batch_result

    # ------------------------------------------------------------------
    # 工件解析 / 资源解析
    # ------------------------------------------------------------------

    def _load_predictor(
        self, model_ref: str
    ) -> Tuple[Any, str, str, Optional[CycleResult]]:
        """解析 seq_annotation 工件并加载 predictor，做生产契约与全天 288 点校验。

        返回 (predictor, model_id, model_path, invalid_result)。invalid_result 非 None 时
        表示工件不可用/非全天工件，应作为 skipped 结果直接返回。
        """
        from services.scheduler.tasks.pv_fault_tasks import _resolve_seq_annotation_artifact

        try:
            model_id, model_dir, model_path = _resolve_seq_annotation_artifact(model_ref)
            from services.iterative_labeling.seq_annotation.predictor import (
                SeqAnnotationPredictor,
            )
            from services.iterative_labeling.seq_annotation.production_contract import (
                assert_final_sequence_contract,
            )

            predictor = SeqAnnotationPredictor(str(model_dir))
            assert_final_sequence_contract(predictor.metadata)
        except (FileNotFoundError, TypeError, ValueError, RuntimeError) as exc:
            logger.error("seq_daily_strategy: seq_annotation 工件不可用: %s", exc)
            return None, "", "", self._skipped(
                reason="seq_annotation_model_invalid", message=str(exc)
            )

        if not predictor.supports_night or predictor.seq_len != 288:
            message = "序列标注模型不是全天 288 点工件，拒绝进入生产预测"
            logger.error("seq_daily_strategy: %s", message)
            return None, "", "", self._skipped(
                reason="seq_annotation_not_full_day", message=message
            )
        return predictor, model_id, model_path, None

    def _resolve_adapter(self) -> Tuple[Any, Any]:
        """解析本轮 DB 适配器；本类新建时返回 disposable 供结束后释放。"""
        if self._db_adapter_factory is not None:
            produced = self._db_adapter_factory()
            if isinstance(produced, tuple) and len(produced) == 2:
                return produced[0], produced[1]
            return produced, None
        from services.db.adapter import DBAdapter
        from services.db.config import DBConfig

        adapter = DBAdapter(DBConfig())
        return adapter, adapter

    def _resolve_gate(self, adapter: Any) -> CompletenessGate:
        """构造/复用完整性闸门；缺省时按 config + IngestionTrackerRepository(adapter)。"""
        if self._gate is not None:
            return self._gate
        from services.db.repositories.ingestion_tracker import IngestionTrackerRepository

        config = self._config or load_dual_path_config()
        tracker = IngestionTrackerRepository(
            adapter, completeness_ratio=config.completeness_ratio
        )
        return CompletenessGate(tracker, config)

    # ------------------------------------------------------------------
    # 分区游标读写（按 modeling_path=seq_annotation）
    # ------------------------------------------------------------------

    def _read_partition_cursors(
        self, adapter: Any
    ) -> Tuple[List[_DeviceKey], Dict[_DeviceKey, Optional[datetime]]]:
        """读设备三元组全集 + seq_annotation 分区游标。

        - device_universe：从 device_prediction_cursor 表取 DISTINCT 设备三元组，仅用于
          「设备身份发现」，不复用其他 modeling_path 分区的游标水位值（Req5.6）。
        - seq_cursors：仅 `modeling_path == "seq_annotation"` 分区的 last_predicted_time；
          缺该分区行的设备由调用方按固定初始水位（None）处理。
        """
        from sqlalchemy import select

        from services.db.models.pv_fault import DevicePredictionCursor

        with adapter.get_sync_session() as session:
            universe_rows = session.execute(
                select(
                    DevicePredictionCursor.site_id,
                    DevicePredictionCursor.device_id,
                    DevicePredictionCursor.branch_id,
                ).distinct()
            ).all()
            seq_rows = session.execute(
                select(DevicePredictionCursor).where(
                    DevicePredictionCursor.modeling_path == _SEQ_ANNOTATION
                )
            ).scalars().all()

        device_universe: List[_DeviceKey] = [
            (row[0], row[1], row[2]) for row in universe_rows
        ]
        if not device_universe:
            from services.db.models.pv_fault import MeasurementIngestionDaily

            with adapter.get_sync_session() as session:
                ingestion_rows = session.execute(
                    select(
                        MeasurementIngestionDaily.site_id,
                        MeasurementIngestionDaily.device_id,
                        MeasurementIngestionDaily.branch_id,
                    ).distinct()
                ).all()
            device_universe = [(row[0], row[1], row[2]) for row in ingestion_rows]
        seq_cursors: Dict[_DeviceKey, Optional[datetime]] = {
            (row.site_id, row.device_id, row.branch_id): row.last_predicted_time
            for row in seq_rows
        }
        return device_universe, seq_cursors

    def _advance_partition_cursors(
        self,
        adapter: Any,
        advance_times: Dict[_DeviceKey, datetime],
        model_ids: Dict[_DeviceKey, Optional[str]],
    ) -> None:
        """把 seq_annotation 分区游标推进到各设备本轮已检测的 max Event_Time。

        upsert 带 `modeling_path=seq_annotation` 分区键：同一设备 legacy_day 分区行不受影响
        （Req5.1 / Req5.5）。
        """
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        from services.db.models.pv_fault import DevicePredictionCursor

        now = datetime.utcnow()
        cursor_records = [
            {
                "slot": "pv_fault",
                "site_id": key[0],
                "device_id": key[1],
                "branch_id": key[2],
                "modeling_path": _SEQ_ANNOTATION,
                "last_predicted_time": advance_time,
                "last_predicted_at": now,
                "model_version_id": model_ids.get(key),
                "updated_at": now,
            }
            for key, advance_time in advance_times.items()
        ]
        with adapter.get_sync_session() as session:
            statement = mysql_insert(DevicePredictionCursor).values(cursor_records)
            statement = statement.on_duplicate_key_update(
                last_predicted_time=statement.inserted.last_predicted_time,
                last_predicted_at=statement.inserted.last_predicted_at,
                model_version_id=statement.inserted.model_version_id,
                updated_at=statement.inserted.updated_at,
            )
            session.execute(statement)

    # ------------------------------------------------------------------
    # 小工具
    # ------------------------------------------------------------------

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
                logger.debug("seq_daily_strategy: 释放 DB 资源失败: %s", exc)

    def _skipped(
        self,
        *,
        reason: str,
        message: str,
        points_deferred: int = 0,
    ) -> CycleResult:
        """构造一个 status=skipped 的 CycleResult（不落账，交由分派器处理）。"""
        logger.info("seq_daily_strategy: skipped reason=%s message=%s", reason, message)
        return CycleResult(
            modeling_path=_SEQ_ANNOTATION,
            strategy_name=self.name,
            window_start=None,
            window_end=None,
            points_detected=0,
            points_deferred=points_deferred,
            devices_processed=0,
            batch_ids=[],
            review_ids=[],
            status="skipped",
            skipped_reason=reason,
        )
# @AI_GENERATED: end
