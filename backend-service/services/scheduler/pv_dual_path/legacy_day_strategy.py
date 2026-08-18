# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/scheduler/pv_dual_path/legacy_day_strategy.py — 传统按天检测策略（Legacy_Day_Strategy）

LegacyDayStrategy 是双路径中「传统按天路径（legacy_day）」的检测策略实现，实现
strategy_base.DetectionStrategy 协议（name / run_cycle(ctx)->CycleResult）。它由现有
`pv_fault_tasks._run_pv_prediction_cycle()` 的 legacy_day 点粒度分支**等价搬迁**而来，并在其上
叠加本 spec 要求的三处关键改造：

  1. 事件时间游标（Req2.1 / Req2.9，修复墙钟漏诊）：把原分支的 `cutoff = datetime.utcnow()`
     （墙钟/Processing_Time）替换为**每设备的 Data_Watermark 上界**（`ctx.watermark.device_watermark`），
     检测窗口改为事件时间半开区间 `(cursor, watermark]`。历史回放 mock（业务时间为 2020/2021）
     不再因游标被推到墙钟 now 而永久漏检。
  2. 按设备独立取点 + 自然日分组不跨日拼接（Req2.4 / Req2.5）：按 `(site_id, device_id, branch_id)`
     各自取窗口内的点，检测样本切分仍复用既有 InferenceSampleGenerator / 工作流 time_window_split，
     二者均按自然日切样本，绝不把相邻自然日的点并入同一检测样本。
  3. 事件时间游标推进语义（Req2.2 / Req2.6 / Req2.8）：把游标推进到「本轮实际参与检测的数据点
     集合中的最大 Event_Time」，且 `new_cursor >= old_cursor`；某设备无新点则跳过、游标不变；
     Event_Time 缺失/不可解析的点拒绝纳入、相关设备游标不变、并在 CycleResult.skipped_reason /
     日志中体现被跳过的错误标识。

不以 Completeness_Gate 为放行前置（Req4.4）：legacy 允许对未完整当天的已到达点做增量检测，
本策略不调用 CompletenessGate。

分区隔离（Req5.1 / Req5.2）：游标与预测记录按 `(slot, modeling_path=legacy_day)` 分区读写，
复用 PathIsolationRegistry（advance_cursor 命中含 modeling_path 的复合主键分区、
write_prediction_records 为每条记录盖非空 modeling_path 标记）。审核批次沿用既有
`_write_prediction_batch`（payload 内已带 modeling_path 标记），避免改动落盘位置破坏既有
审核/展示链路。

输入 / 输出（交接友好）：
  - 输入：CycleContext（slot / modeling_path / model_ref / watermark / started_at）。
  - 输出：CycleResult（window_start/window_end 为本轮实际参与检测点的 Event_Time 边界、
    points_detected / points_deferred / devices_processed / batch_ids / review_ids / status / skipped_reason）。
    运行状态落账（prediction_last_run）由 DualPathScheduler 依据本 CycleResult 完成，本策略不直接写。

对应设计：.kiro/specs/pv-fault-dual-path-serving/design.md §1「LegacyDayStrategy」、§3「两条检测策略要点」。
需求：2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 4.4。
运行环境：conda `cp_web`。
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd
from sqlalchemy import select

from services.db.models.pv_fault import DevicePredictionCursor
from services.scheduler.pv_dual_path.path_activation import DeviceScope, PathActivationService
from services.scheduler.pv_dual_path.path_isolation import PathIsolationRegistry
from services.scheduler.pv_dual_path.production_window import is_production_responsible_date
from services.scheduler.pv_dual_path.strategy_base import CycleContext, CycleResult

logger = logging.getLogger(__name__)

_LEGACY_DAY = "legacy_day"

DeviceKey = Tuple[Any, Any, Any]
RowWithTime = Tuple[Dict[str, Any], pd.Timestamp]


@dataclass(frozen=True)
class DeviceWindowSelection:
    """单设备本轮事件时间窗口的纯选择结果。

    `rows_by_day` — 按 Event_Time 自然日分区且日内升序的有效点；任何无效 Event_Time
    出现时为空，以保证该设备本轮游标不推进。`invalid_count` — 无效时间点数；
    `outside_window_count` — 不在 `(cursor, watermark]` 内、因此未纳入本轮的点数。
    """

    rows_by_day: Dict[str, Tuple[RowWithTime, ...]]
    invalid_count: int
    outside_window_count: int

    def flattened(self) -> List[RowWithTime]:
        """按自然日、日内 Event_Time 顺序展开，供既有推理输入链路消费。"""
        return [
            item
            for event_day in sorted(self.rows_by_day)
            for item in self.rows_by_day[event_day]
        ]


def _normalized_timestamp(value: Any) -> Optional[pd.Timestamp]:
    """把单个 Event_Time 转为可比较的无时区 Timestamp；无效/非标量返回 None。"""
    parsed = pd.to_datetime(value, errors="coerce")
    if parsed is None or not isinstance(parsed, (datetime, pd.Timestamp)) or pd.isna(parsed):
        return None
    timestamp = pd.Timestamp(parsed)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp


def select_device_event_window(
    rows: Sequence[Mapping[str, Any]],
    cursor: Optional[datetime],
    watermark: datetime,
) -> DeviceWindowSelection:
    """纯逻辑选择单设备 `(cursor, watermark]` 已到达点，并按自然日分组。

    仓储查询本应已应用同一半开区间；这里再次防御性过滤，确保任何上游误返回的
    未来点或已消费点都不会进入检测。若任一点 Event_Time 无效，则拒绝该设备本轮
    全部输入，使相关游标保持不变；有效点会在后续清理无效数据后的轮次重新评估。
    """
    cursor_ts = _normalized_timestamp(cursor) if cursor is not None else None
    watermark_ts = _normalized_timestamp(watermark)
    if watermark_ts is None:
        raise ValueError("watermark 必须是有效 Event_Time")

    grouped: Dict[str, List[RowWithTime]] = defaultdict(list)
    invalid_count = 0
    outside_window_count = 0
    for source_row in rows:
        row = dict(source_row)
        event_time = _normalized_timestamp(row.get("time"))
        if event_time is None:
            invalid_count += 1
            continue
        if (cursor_ts is not None and event_time <= cursor_ts) or event_time > watermark_ts:
            outside_window_count += 1
            continue
        grouped[event_time.date().isoformat()].append((row, event_time))

    if invalid_count:
        return DeviceWindowSelection(
            rows_by_day={},
            invalid_count=invalid_count,
            outside_window_count=outside_window_count,
        )

    rows_by_day = {
        event_day: tuple(sorted(day_rows, key=lambda item: item[1]))
        for event_day, day_rows in grouped.items()
    }
    return DeviceWindowSelection(
        rows_by_day=rows_by_day,
        invalid_count=0,
        outside_window_count=outside_window_count,
    )


def _default_adapter_factory():
    """默认 DBAdapter 工厂：新建连接（游标枚举与分区写入共用），dispatch 结束后由本策略释放。"""
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig

    return DBAdapter(DBConfig())


def _day_from_time_window(time_window: Any) -> Optional[str]:
    """从预测的 time_window 提取自然日（ISO `YYYY-MM-DD`）；无法解析返回 None。

    legacy 的 time_window 形如 `2021-01-05`、`2021-01-05#day`、`2021-01-05#day_night` 等，
    统一取前 10 个字符按日期解析。解析失败返回 None，调用方按「该设备全部输入点均已参与检测」
    的保守口径推进游标，避免因 time_window 变体导致游标停滞、下轮重复推理。
    """
    raw = str(time_window or "").strip()
    if len(raw) >= 10:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    return None


class LegacyDayStrategy:
    """传统按天检测策略 —— 事件时间游标 + 按设备独立取点 + 分区读写。

    构造参数：
      - pv_repo          — PVFaultRepository 实例，复用其未标注点查询与预测记录写入。
      - adapter_factory  — 可注入的 DBAdapter 工厂（测试隔离用）；缺省新建生产连接。
      - registry_factory — 可注入的 PathIsolationRegistry 工厂 `(adapter) -> registry`；
                           缺省用 PathIsolationRegistry(adapter)。
    """

    name = "LegacyDayStrategy"

    def __init__(
        self,
        pv_repo: Any,
        *,
        adapter_factory: Optional[Callable[[], Any]] = None,
        registry_factory: Optional[Callable[[Any], PathIsolationRegistry]] = None,
        activation_factory: Optional[Callable[[Any], PathActivationService]] = None,
    ) -> None:
        self._pv_repo = pv_repo
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._registry_factory = registry_factory or (lambda adapter: PathIsolationRegistry(adapter))
        self._activation_factory = activation_factory or (
            lambda adapter: PathActivationService(adapter)
        )

    # ------------------------------------------------------------------
    # 策略入口
    # ------------------------------------------------------------------

    def run_cycle(self, ctx: CycleContext) -> CycleResult:
        """执行一轮传统按天检测，返回可断言的 CycleResult。

        流程：解析模型工件 → 读 legacy_day 分区游标 → 按设备取 `(cursor, watermark]` 的点、
        拒收无效 Event_Time 点 → 汇总跑预测工作流 → 写记录/批次/审核会话 →
        按「本轮参与检测点集合的最大 Event_Time」分设备推进游标（>= 旧值）。
        """
        # 惰性 import 既有实现函数，避免与 pv_fault_tasks 形成模块级循环导入。
        from services.scheduler.tasks import pv_fault_tasks as legacy

        slot = ctx.slot
        modeling_path = ctx.modeling_path or _LEGACY_DAY

        # 1) 解析模型工件（model_ref 缺失回退生产指针；仍缺失或工件不存在 → 跳过）。
        model_ref = str(ctx.champion_model_ref or ctx.model_ref or "").strip()
        if not model_ref:
            return self._skipped(modeling_path, "missing_champion_model_ref")

        try:
            model_id, model_file, model_path, execution_model_path = legacy._resolve_model_artifact(model_ref)
        except FileNotFoundError:
            logger.info("LegacyDayStrategy: 模型工件不存在 model_ref=%s", model_ref)
            return self._skipped(modeling_path, "model_pending")

        feature_list, sample_strategy = legacy._load_model_contract(model_file)
        use_persisted_sample_strategy = bool(sample_strategy)
        query_by_time = (
            self._pv_repo.query_unlabeled_by_point_labels
            if use_persisted_sample_strategy
            else self._pv_repo.query_unlabeled_training_samples
        )

        adapter = self._adapter_factory()
        try:
            registry = self._registry_factory(adapter)

            # 2) 读 legacy_day 分区游标（Req5.1）；空分区 → 跳过（无设备可预测）。
            device_cursors = self._read_partition_cursors(adapter, modeling_path)
            if not device_cursors:
                return self._skipped(modeling_path, "no_device_cursors")

            # 3) 按设备取 (cursor, watermark] 的点，拒收无效 Event_Time 点（Req2.1/2.8/2.9）。
            all_rows: List[Dict[str, Any]] = []
            device_valid: Dict[DeviceKey, List[Tuple[Dict[str, Any], pd.Timestamp]]] = {}
            rejected_invalid = 0
            skipped_caught_up = 0

            for device_key, old_cursor in device_cursors.items():
                site_id, device_id, branch_id = device_key
                watermark = ctx.watermark.device_watermark(site_id, device_id, branch_id)
                if watermark is None:
                    # 该设备无已到达数据 → 无新点，跳过、游标不变（Req2.6）。
                    skipped_caught_up += 1
                    continue
                if old_cursor is not None and watermark <= old_cursor:
                    # 水位未越过游标 → 无新点，跳过、游标不变（Req2.6）。
                    skipped_caught_up += 1
                    continue

                rows = query_by_time(
                    after_time=old_cursor,
                    before_time=watermark,
                    site_id=site_id,
                    device_id=device_id,
                    branch_id=branch_id,
                )
                if not rows:
                    skipped_caught_up += 1
                    continue

                selection = select_device_event_window(rows, old_cursor, watermark)
                rejected_invalid += selection.invalid_count
                if selection.invalid_count:
                    # Req2.8：任一点 Event_Time 无效时，该设备本轮整体不推进游标。
                    skipped_caught_up += 1
                    continue

                valid = self._filter_production_days(ctx, adapter, device_key, selection)
                if not valid:
                    skipped_caught_up += 1
                    continue

                device_valid[device_key] = valid
                all_rows.extend(row for row, _ in valid)

            if rejected_invalid:
                logger.warning(
                    "LegacyDayStrategy: 拒收 %d 个 Event_Time 缺失/不可解析的点（不推进相关游标）",
                    rejected_invalid,
                )

            candidate_evaluated = sum(len(v) for v in device_valid.values())
            if candidate_evaluated == 0:
                # 无任何可评估的有效新点：全部设备追平 / 或全被无效点拒收。
                return self._skipped(
                    modeling_path,
                    "skipped_caught_up",
                    rejected_invalid=rejected_invalid,
                )

            # 4) 汇总跑预测工作流（切样本按自然日，不跨日拼接，Req2.5）。
            batch_id = f"pred-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
            source_dataset_path, split_audit = self._prepare_prediction_input(
                legacy, all_rows, batch_id, model_file, sample_strategy, use_persisted_sample_strategy
            )
            if source_dataset_path is None:
                # 未能切出推理样本（如数据未构成完整样本）：本轮不推进任何游标。
                return self._skipped(modeling_path, "no_inference_sample", rejected_invalid=rejected_invalid)

            raw_predictions, unit_features = self._execute_prediction_workflow(
                legacy,
                source_dataset_path=source_dataset_path,
                feature_list=feature_list,
                model_id=model_id,
                execution_model_path=execution_model_path,
                use_persisted_sample_strategy=use_persisted_sample_strategy,
            )
            predictions = legacy._normalize_predictions(raw_predictions)

            # 5) 写预测记录（分区打标，Req5.2）→ 批次 → 审核会话。
            model_version = self._pv_repo.get_model_version(model_id)
            record_payloads = [
                {
                    "model_version_id": model_id if model_version is not None else None,
                    "site_id": p["site_id"],
                    "device_id": p["device_id"],
                    "branch_id": p["branch_id"],
                    "predicted_label": p["predicted_label"],
                    "confidence": p["confidence"],
                    "input_feature_json": {
                        "prediction_batch_id": batch_id,
                        "time_window": p["time_window"],
                        "source_dataset_path": source_dataset_path,
                        "model_ref": model_ref,
                        "modeling_path": modeling_path,
                    },
                }
                for p in predictions
            ]
            registry.write_prediction_records(self._pv_repo, slot, modeling_path, record_payloads)

            legacy._write_prediction_batch(
                batch_id,
                source_dataset_path=source_dataset_path,
                model_ref=model_ref,
                model_path=model_path,
                predictions=predictions,
                unit_features=unit_features,
                feature_list=feature_list,
                modeling_path=modeling_path,
            )
            review_session = legacy._create_prediction_review_session(
                batch_id,
                source_dataset_path=source_dataset_path,
                model_ref=model_ref,
                predictions=predictions,
                modeling_path=modeling_path,
            )
            review_id = str(review_session["review_id"])

            # 6) 按「本轮参与检测点集合最大 Event_Time」分设备推进游标（>= 旧值，Req2.2）。
            detected_ts, devices_advanced = self._advance_cursors(
                registry=registry,
                slot=slot,
                modeling_path=modeling_path,
                device_valid=device_valid,
                device_cursors=device_cursors,
                predictions=predictions,
                model_id=model_id if model_version is not None else None,
                review_unit_id=legacy._review_unit_id,
            )

            points_detected = len(detected_ts)
            points_deferred = candidate_evaluated - points_detected
            window_start = min(detected_ts).isoformat() if detected_ts else None
            window_end = max(detected_ts).isoformat() if detected_ts else None

            logger.info(
                "LegacyDayStrategy: batch=%s review=%s predictions=%d detected=%d deferred=%d "
                "devices_advanced=%d rejected_invalid=%d caught_up=%d",
                batch_id, review_id, len(predictions), points_detected, points_deferred,
                devices_advanced, rejected_invalid, skipped_caught_up,
            )

            return CycleResult(
                modeling_path=modeling_path,
                strategy_name=self.name,
                window_start=window_start,
                window_end=window_end,
                points_detected=points_detected,
                points_deferred=points_deferred,
                devices_processed=devices_advanced,
                batch_ids=[batch_id],
                review_ids=[review_id],
                status="success",
                skipped_reason=(
                    f"rejected_invalid_event_time={rejected_invalid}" if rejected_invalid else None
                ),
            )
        finally:
            self._dispose(adapter)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _filter_production_days(
        self,
        ctx: CycleContext,
        adapter: Any,
        device_key: DeviceKey,
        selection: DeviceWindowSelection,
    ) -> List[Tuple[Dict[str, Any], pd.Timestamp]]:
        """保留当前 Epoch 生产车道内、未被 historical_backfill 认领的自然日。"""
        epoch_id = str(ctx.activation_epoch_id or "").strip()
        if not epoch_id:
            return selection.flattened()
        try:
            activation = self._activation_factory(adapter)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LegacyDayStrategy: 无法构造 PathActivationService: %s", exc)
            return []
        scope = DeviceScope(str(device_key[0]), str(device_key[1]), str(device_key[2]))
        kept: List[Tuple[Dict[str, Any], pd.Timestamp]] = []
        for event_day in sorted(selection.rows_by_day):
            business_date = date.fromisoformat(event_day)
            if is_production_responsible_date(activation, epoch_id, scope, business_date):
                kept.extend(selection.rows_by_day[event_day])
        return kept

    def _read_partition_cursors(
        self, adapter: Any, modeling_path: str,
    ) -> Dict[DeviceKey, Optional[datetime]]:
        """读某 modeling_path 分区下全部设备的游标水位（Req5.1）。

        只读本分区行（`modeling_path == 该路径`），不读取/复用其他分区（Req5.6 隔离）。
        返回 `{(site,device,branch): last_predicted_time}`；last_predicted_time 可能为 None。
        """
        with adapter.get_sync_session() as session:
            rows = session.execute(
                select(DevicePredictionCursor).where(
                    DevicePredictionCursor.modeling_path == modeling_path
                )
            ).scalars().all()
            return {
                (row.site_id, row.device_id, row.branch_id): row.last_predicted_time
                for row in rows
            }

    def _prepare_prediction_input(
        self,
        legacy: Any,
        all_rows: List[Dict[str, Any]],
        batch_id: str,
        model_file: Any,
        sample_strategy: Optional[Dict[str, Any]],
        use_persisted_sample_strategy: bool,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """把本轮汇总的原始观测写成预测输入 CSV（相对路径），返回 (source_dataset_path, split_audit)。

        - 持久化采样策略路径：复用 InferenceSampleGenerator 按策略切样本（自然日粒度），
          切不出样本返回 (None, None) 交由上层跳过。
        - 无持久化策略路径：直接把观测行写出，交由工作流 time_window_split 按自然日切样本。
        """
        if use_persisted_sample_strategy:
            from services.iterative_labeling.inference_sample import (
                INFERENCE_DERIVED_COLUMNS,
                InferenceSampleGenerator,
            )

            measurements = pd.DataFrame(all_rows)
            measurements["time"] = pd.to_datetime(measurements["time"])
            try:
                sample_frame, split_audit = InferenceSampleGenerator().generate_inference_samples(
                    measurements, str(model_file)
                )
            except ValueError as exc:
                logger.warning(
                    "LegacyDayStrategy: 待预测数据未能按策略 %s 切出推理样本：%s",
                    (sample_strategy or {}).get("split_mode"), exc,
                )
                return None, None
            extra_columns = ["time_window", "period_role", *INFERENCE_DERIVED_COLUMNS]
            _input_path, source_dataset_path = legacy._write_prediction_input(
                sample_frame, batch_id, extra_columns=extra_columns
            )
            return source_dataset_path, split_audit

        _input_path, source_dataset_path = legacy._write_prediction_input(all_rows, batch_id)
        return source_dataset_path, None

    def _execute_prediction_workflow(
        self,
        legacy: Any,
        *,
        source_dataset_path: str,
        feature_list: List[str],
        model_id: str,
        execution_model_path: str,
        use_persisted_sample_strategy: bool,
    ) -> Tuple[Any, Dict[str, Any]]:
        """加载并执行 quickval 预测工作流，返回 (raw_predictions, unit_features)。等价搬迁自原分支。"""
        from api.workflows_enhanced import _execute_pipeline_sync, load_workflow_from_file

        workflow = load_workflow_from_file("workflow-pv-fault-diag-quickval-predict-v1")
        if workflow is None:
            raise RuntimeError("预测工作流模板 workflow-pv-fault-diag-quickval-predict-v1 不存在")

        required_nodes = {"load_csv": False, "feature_select": False, "random_forest_classifier": False}
        for node in workflow.nodes:
            config = node.data.config
            function_id = (
                config.get("functionId")
                if isinstance(config, dict)
                else getattr(config, "functionId", None)
            )
            if function_id == "load_csv":
                legacy._workflow_config_set(config, "file_path", source_dataset_path)
                required_nodes[function_id] = True
            elif function_id == "feature_select":
                legacy._workflow_config_set(config, "feature_list", feature_list)
                legacy._workflow_config_set(config, "model_path", execution_model_path)
                required_nodes[function_id] = True
            elif function_id == "random_forest_classifier":
                legacy._workflow_config_set(config, "model_id", model_id)
                legacy._workflow_config_set(config, "model_path", execution_model_path)
                required_nodes[function_id] = True
            elif function_id == "time_window_split" and use_persisted_sample_strategy:
                legacy._workflow_config_set(config, "solar_mode", None)
                legacy._workflow_config_set(config, "attach_night_features", False)
        if not all(required_nodes.values()):
            missing = [n for n, found in required_nodes.items() if not found]
            raise RuntimeError(f"预测工作流缺少必要节点: {', '.join(missing)}")

        execution_result = _execute_pipeline_sync(workflow)
        if not execution_result.get("success", False):
            raise RuntimeError(f"预测工作流执行失败: {execution_result.get('error', '未知错误')}")
        raw_predictions = execution_result.get("fault_predictions")

        unit_features: Dict[str, Any] = {}
        for raw in raw_predictions or []:
            if not isinstance(raw, dict):
                continue
            feats = raw.get("_features")
            if not isinstance(feats, dict) or not feats:
                continue
            uk = (
                f"{legacy._review_unit_id(raw.get('site_id'))}|{legacy._review_unit_id(raw.get('device_id'))}|"
                f"{legacy._review_unit_id(raw.get('branch_id'))}|{raw.get('time_window')}"
            )
            unit_features[uk] = legacy._json_safe(feats)
        return raw_predictions, unit_features

    def _advance_cursors(
        self,
        *,
        registry: PathIsolationRegistry,
        slot: str,
        modeling_path: str,
        device_valid: Dict[DeviceKey, List[Tuple[Dict[str, Any], pd.Timestamp]]],
        device_cursors: Dict[DeviceKey, Optional[datetime]],
        predictions: List[Dict[str, Any]],
        model_id: Optional[str],
        review_unit_id: Callable[[Any], str],
    ) -> Tuple[List[pd.Timestamp], int]:
        """按「本轮参与检测点集合的最大 Event_Time」分设备推进游标（Req2.2）。

        参与检测的点 = 其自然日出现在该设备预测结果中的有效点。某设备无对应预测 →
        不推进该设备游标（其点顺延至后续轮次，Req2.6）；time_window 无法解析出日期时，
        保守认定该设备全部输入点均已参与检测（避免游标停滞导致重复推理）。

        Returns:
            (detected_ts, devices_advanced) —— 全部参与检测点的 Event_Time 列表、成功推进的设备数。
        """
        # 归集每个设备产出的自然日；含 None 表示存在无法解析日期的 time_window（保守全推进）。
        produced_days: Dict[Tuple[str, str, str], set] = defaultdict(set)
        for p in predictions:
            norm_key = (
                review_unit_id(p.get("site_id")),
                review_unit_id(p.get("device_id")),
                review_unit_id(p.get("branch_id")),
            )
            produced_days[norm_key].add(_day_from_time_window(p.get("time_window")))

        detected_ts: List[pd.Timestamp] = []
        devices_advanced = 0
        for device_key, valid in device_valid.items():
            site_id, device_id, branch_id = device_key
            norm_key = (
                review_unit_id(site_id),
                review_unit_id(device_id),
                review_unit_id(branch_id),
            )
            produced = produced_days.get(norm_key)
            if not produced:
                # 该设备本轮无预测产出 → 顺延，游标不变（Req2.6）。
                continue

            if None in produced:
                device_detected = [ts for _, ts in valid]
            else:
                device_detected = [
                    ts for _, ts in valid if ts.date().isoformat() in produced
                ]
            if not device_detected:
                continue

            detected_ts.extend(device_detected)
            new_cursor = max(device_detected).to_pydatetime()
            old_cursor = device_cursors.get(device_key)
            # 窗口为 (old_cursor, watermark] 且检测点均在窗口内，new_cursor 天然 >= old_cursor；
            # 仍显式守护单调不减（Req2.2）。
            if old_cursor is not None and new_cursor < old_cursor:
                continue
            registry.advance_cursor(
                slot,
                modeling_path,
                site_id,
                device_id,
                branch_id,
                new_cursor,
                model_version_id=model_id,
            )
            devices_advanced += 1

        return detected_ts, devices_advanced

    def _skipped(
        self,
        modeling_path: str,
        reason: str,
        *,
        rejected_invalid: int = 0,
    ) -> CycleResult:
        """构造一个 status=skipped 的空 CycleResult（不写记录、不推进游标）。"""
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
        """best-effort 释放本策略新建的 DB 资源；失败不影响主流程。"""
        if adapter is None:
            return
        dispose = getattr(adapter, "dispose", None)
        if callable(dispose):
            try:
                dispose()
            except Exception as exc:  # noqa: BLE001
                logger.debug("LegacyDayStrategy: 释放 DB 资源失败: %s", exc)
# @AI_GENERATED: end
