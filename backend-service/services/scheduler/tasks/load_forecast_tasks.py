# -*- coding: utf-8 -*-
"""
services/scheduler/tasks/load_forecast_tasks.py — 负荷预测调度任务工厂

提供三个任务工厂函数，每个返回一个可注册到 SchedulerEngine 的 Callable：

- make_data_pull_task:        拉取站点实测数据并写入 lf_repo（高水位增量拉取）
- make_prediction_task:       预测任务占位（Stub，待与 precision_ops 集成）
- make_accuracy_backfill_task: 回填精度指标（MAPE 计算并 upsert AccuracyMetric）

Requirements: 4.2, 4.3, 4.4, 4.5
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable, Optional, Sequence, Tuple

from services.db.datasources.base import DataSourceError
from services.db.models.load_forecast import PredictionResult, StationData
from services.db.repositories.load_forecast import StationDataRecord

if TYPE_CHECKING:
    from services.db.datasources.base import StationDataSource
    from services.db.repositories.load_forecast import LoadForecastRepository

logger = logging.getLogger(__name__)

DEFAULT_MOCK_WORKFLOW_ID = "mock-load-naive-v1"
DEFAULT_MOCK_VERSION_TAG = "mock-naive-v1"
DEFAULT_MOCK_STATION_ID = "mock_load_station"
DEFAULT_MOCK_FEATURE_NAME = "load"


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _get_high_watermark(lf_repo: "LoadForecastRepository", slot: str, station_id: str) -> datetime:
    """
    查询指定槽位和站点的最新 timestamp_utc（高水位）。

    若无历史数据则返回 epoch（1970-01-01），确保首次拉取获取全量。
    """
    from services.db.models.load_forecast import StationData
    from sqlalchemy import func

    with lf_repo._adapter.get_sync_session() as session:
        result = (
            session.query(func.max(StationData.timestamp_utc))
            .filter(
                StationData.slot == slot,
                StationData.station_id == station_id,
            )
            .scalar()
        )
    return result if result is not None else datetime(1970, 1, 1)


def _build_naive_forecast_point(records: Sequence[object]) -> Optional[Tuple[datetime, float]]:
    """
    Build a one-step-ahead forecast from already ingested history only.

    The prediction target is the next timestamp after the latest observed point.
    The predicted value is the latest observed value. This is intentionally
    simple; its purpose is to validate the online data flow without leakage.
    """
    if len(records) < 2:
        return None

    ordered = sorted(records, key=lambda r: getattr(r, "timestamp_utc"))
    prev = ordered[-2]
    latest = ordered[-1]
    prev_ts = getattr(prev, "timestamp_utc")
    latest_ts = getattr(latest, "timestamp_utc")
    interval = latest_ts - prev_ts
    if interval <= timedelta(0):
        return None
    return latest_ts + interval, float(getattr(latest, "value"))


# ---------------------------------------------------------------------------
# Task 1: 数据拉取任务
# ---------------------------------------------------------------------------

def make_data_pull_task(
    station_source: "StationDataSource",
    lf_repo: "LoadForecastRepository",
    slot: str,
    before_pull: Optional[Callable[[], int]] = None,
) -> Callable:
    """
    返回 data_pull_task() — 增量拉取所有站点数据并写入 lf_repo。

    对每个可用站点：
      1. 从 lf_repo 查询该站点的最新 timestamp_utc（高水位）作为 since_timestamp
      2. 调用 station_source.pull_latest() 拉取新记录
      3. 将 StationRecord 列表转换为 StationDataRecord 并批量写入

    超时/数据源错误通过 DataSourceError 捕获，记录警告后继续处理下一站点。
    """

    def data_pull_task() -> None:
        if before_pull is not None:
            fed = before_pull()
            logger.info("data_pull_task: mock company feeder inserted %d row(s)", fed)

        stations = station_source.get_available_stations()
        total_inserted = 0

        for station_info in stations:
            station_id = station_info.station_id
            since_ts = _get_high_watermark(lf_repo, slot, station_id)

            try:
                records = station_source.pull_latest(station_id, since_ts)
            except DataSourceError as exc:
                logger.warning(
                    "data_pull_task: slot=%s station=%s DataSourceError: %s",
                    slot, station_id, exc,
                )
                continue

            if not records:
                continue

            station_data_records = [
                StationDataRecord(
                    station_id=r.station_id,
                    timestamp_utc=r.timestamp,
                    feature_name=r.feature_name,
                    value=r.value,
                    slot=slot,
                )
                for r in records
            ]

            inserted = lf_repo.insert_station_data(station_data_records)
            total_inserted += inserted

        logger.info(
            "data_pull_task: slot=%s pulled and inserted %d rows across %d stations",
            slot, total_inserted, len(stations),
        )

    return data_pull_task


# ---------------------------------------------------------------------------
# Task 2: 预测任务（真实 workflow pipeline 执行）
# ---------------------------------------------------------------------------

# @AI_GENERATED: 旧常量保留作向后兼容 alias；新代码从 slot config 读 max_shadow_slots
MAX_SHADOW_PREDICTIONS = 3  # 已废弃，仅向后兼容；实际上限由 slot.max_shadow_slots 决定
# @AI_GENERATED: end


# @AI_GENERATED: 重写 make_daily_rolling_task — 严格 gap-1-day + 从 slot 读训练窗口
def make_daily_rolling_task(
    lf_repo: "LoadForecastRepository",
    slot: str,
    station_id: str = DEFAULT_MOCK_STATION_ID,
    feature_name: str = DEFAULT_MOCK_FEATURE_NAME,
    slot_store=None,
    production_registry=None,
    version_registry=None,
) -> Callable:
    """
    返回 daily_rolling_task() — 每日滚动训练+预测主任务。

    严格 gap-1-day 语义：
      - 触发日 T：训练数据硬截止 T-1 23:59:59.999，绝不使用 T 日任何数据
      - 预测目标：T+1 全天（用最后两条记录的时间间隔推算 T+1 的时间点列表）
      - 训练窗口：最近 `slot.training_window_days` 天（默认 30）

    执行顺序（生产优先）：
      1. 生产模型（production_model）—— 失败则告警，其余模型仍继续
      2. 影子模型（shadow_models）—— 限 slot.max_shadow_slots 个，排精度降序
      3. 预上线模型（prelaunch_models）—— 限 slot.max_prelaunch_slots 个，排入池时间升序

    工作流内的 train_test_split_ts 节点通过 params 覆盖 mode="all_train"，
    确保全部窗口数据都用于训练（不再内部切测试集）。

    依赖注入（均可为 None，None 时对应功能静默跳过）：
      slot_store          — services.deployment.store.DeploymentSlotStore 实例，
                            读 slot config（training_window_days / max_shadow_slots 等）
      production_registry — precision_ops.ProductionRegistry 实例（精度运营侧生产登记）
      version_registry    — precision_ops.VersionRegistry 实例（精度运营侧影子列表）

    向后兼容说明：
      如果 slot_store 为 None（未迁移完成的老路径），自动回退到
      production_registry + version_registry + 默认 7 天窗口（旧行为）。
    """

    def daily_rolling_task() -> Optional[str]:
        import pandas as pd
        from datetime import date, timezone

        from services.deployment.rolling_window import compute_training_window

        trigger_date = date.today()  # 触发日 T

        # ---- Step 1: 从 slot store 读取配置 ----
        training_window_days = 30      # 默认值
        max_shadow = MAX_SHADOW_PREDICTIONS  # 默认 3
        max_prelaunch = 2              # 默认 2
        prelaunch_workflow_ids: list = []

        if slot_store is not None:
            try:
                slot_obj = slot_store.get(slot)
                if slot_obj is not None:
                    training_window_days = slot_obj.training_window_days
                    max_shadow = slot_obj.max_shadow_slots
                    max_prelaunch = slot_obj.max_prelaunch_slots
                    # 预上线模型：按入池时间升序，限 max_prelaunch 个
                    active_prelaunches = sorted(
                        [m for m in slot_obj.prelaunch_models if m.status == "prelaunch"],
                        key=lambda m: (
                            m.prelaunch_meta.started_at if m.prelaunch_meta else ""
                        ),
                    )[:max_prelaunch]
                    prelaunch_workflow_ids = [
                        (m.workflow_id, m.version_tag) for m in active_prelaunches
                    ]
            except Exception as exc:
                logger.warning("daily_rolling_task: slot_store 读取失败，使用默认配置: %s", exc)

        # ---- Step 2: 获取可用数据日期集合（用于窗口计算）----
        try:
            with lf_repo._adapter.get_sync_session() as session:
                date_rows = (
                    session.query(StationData.timestamp_utc)
                    .filter(
                        StationData.slot == slot,
                        StationData.station_id == station_id,
                        StationData.feature_name == feature_name,
                    )
                    .all()
                )
            available_dates = [r[0].date() for r in date_rows if r[0] is not None]
        except Exception as exc:
            logger.warning("daily_rolling_task: 获取可用日期失败: %s", exc)
            available_dates = []

        # ---- Step 3: 严格 gap-1-day 窗口计算 ----
        window = compute_training_window(
            trigger_date=trigger_date,
            max_window_days=training_window_days,
            available_data=available_dates,
        )

        if window.training_end is None:
            logger.info(
                "daily_rolling_task: slot=%s 无可用训练数据（训练窗口为空），跳过",
                slot,
            )
            return None

        # ---- Step 4: 从 DB 拉取训练+推理数据（窗口内数据 + T 日数据供推理特征）----
        # 训练数据：[training_start, T-1 23:59:59.999]（gap-1-day 约束）
        # 推理数据：需要 T 日数据构造特征（滞后等），但不作为训练标签
        import numpy as np
        from datetime import datetime as dt_cls

        train_end_dt = dt_cls.combine(
            window.training_end,
            dt_cls.max.time(),
        ).replace(microsecond=999999)

        # 从 DB 中拉取 [training_start - 14天 lag热身, T-1末] 的数据
        # 热身 14 天供 lag_feature 等算子用，不改变"不使用 T 日数据"的约束
        import pandas as pd
        from datetime import timedelta

        lag_warmup_start = dt_cls.combine(
            window.training_start - timedelta(days=14),
            dt_cls.min.time(),
        ) if window.training_start else None

        try:
            with lf_repo._adapter.get_sync_session() as session:
                q = (
                    session.query(StationData)
                    .filter(
                        StationData.slot == slot,
                        StationData.station_id == station_id,
                        StationData.feature_name == feature_name,
                        StationData.timestamp_utc <= train_end_dt,  # 严格 ≤ T-1 末
                    )
                    .order_by(StationData.timestamp_utc.asc())
                )
                if lag_warmup_start is not None:
                    q = q.filter(StationData.timestamp_utc >= lag_warmup_start)
                rows = q.all()
        except Exception as exc:
            logger.error("daily_rolling_task: 拉取训练数据失败: %s", exc)
            return None

        if len(rows) < 2:
            logger.info(
                "daily_rolling_task: slot=%s station=%s 数据不足 (%d rows)，跳过",
                slot, station_id, len(rows),
            )
            return None

        # 构建 DataFrame
        input_data = pd.DataFrame([
            {
                "record_time": r.timestamp_utc,
                "value": r.value,
                "station_id": r.station_id,
                "feature_name": r.feature_name,
            }
            for r in rows
        ])

        # ---- Step 5: 推算预测目标时间戳（T+1 全天）----
        # forecast_ts = T+1 的第一个点位（基于最后两条记录的时间间隔）
        last_ts = rows[-1].timestamp_utc
        if len(rows) >= 2:
            interval = rows[-1].timestamp_utc - rows[-2].timestamp_utc
            if interval <= timedelta(0):
                interval = timedelta(minutes=15)
        else:
            interval = timedelta(minutes=15)

        # T+1 第一个预测点（绕开 T 日，直接跳到 T+1）
        from datetime import datetime as dt_cls2, date as date_cls
        t_plus_1_start = dt_cls2.combine(
            trigger_date + timedelta(days=1),
            dt_cls2.min.time(),
        ) + interval  # 第一个点在 T+1 00:00 + interval
        forecast_ts = t_plus_1_start

        # ---- Step 6: 逐个 workflow 执行 ----
        # 先收集所有需要跑的 workflow 列表（production + shadow + prelaunch）
        workflows_to_run: list = []

        # production
        if production_registry is not None:
            prod_entry = production_registry.get(slot)
        else:
            prod_entry = None

        if slot_store is not None:
            try:
                slot_obj = slot_store.get(slot)
                if slot_obj is not None and slot_obj.production_model is not None:
                    prod_wf_id = slot_obj.production_model.workflow_id
                    prod_tag = slot_obj.production_model.version_tag
                    if prod_wf_id:
                        workflows_to_run.append({
                            "workflow_id": prod_wf_id,
                            "version_tag": prod_tag,
                            "is_shadow": False,
                            "role": "production",
                        })
            except Exception:
                pass

        # 若 slot_store 无数据，降级到 production_registry（旧路径向后兼容）
        if not workflows_to_run and prod_entry is not None and prod_entry.get("workflow_id"):
            workflows_to_run.append({
                "workflow_id": prod_entry["workflow_id"],
                "version_tag": prod_entry.get("version_tag", "production"),
                "is_shadow": False,
                "role": "production",
            })

        if not workflows_to_run:
            logger.info(
                "daily_rolling_task: slot=%s 无生产模型登记，跳过",
                slot,
            )
            return None

        # shadow（优先从 slot_store，降级到 version_registry）
        if slot_store is not None:
            try:
                slot_obj = slot_store.get(slot)
                if slot_obj is not None:
                    active_shadows = sorted(
                        [m for m in slot_obj.shadow_models if m.status == "shadow"],
                        key=lambda m: m.accuracy_score if m.accuracy_score is not None else float("inf"),
                    )[:max_shadow]
                    for m in active_shadows:
                        workflows_to_run.append({
                            "workflow_id": m.workflow_id,
                            "version_tag": m.version_tag,
                            "is_shadow": True,
                            "role": "shadow",
                        })
            except Exception as exc:
                logger.warning("daily_rolling_task: 读取 shadow_models 失败: %s", exc)
        elif version_registry is not None:
            shadows = version_registry.list_shadows(slot)
            shadows.sort(key=lambda v: v.get("registered_at", ""), reverse=True)
            for s in shadows[:max_shadow]:
                if s.get("workflow_id"):
                    workflows_to_run.append({
                        "workflow_id": s["workflow_id"],
                        "version_tag": f"shadow-{s['workflow_id'][:20]}",
                        "is_shadow": True,
                        "role": "shadow",
                    })

        # prelaunch
        for wf_id, vtag in prelaunch_workflow_ids:
            workflows_to_run.append({
                "workflow_id": wf_id,
                "version_tag": vtag,
                "is_shadow": True,
                "role": "prelaunch",
            })

        # ---- Step 7: 执行每个 workflow ----
        first_cycle_id = None
        for wf in workflows_to_run:
            try:
                cid = _run_single_prediction(
                    lf_repo=lf_repo,
                    slot=slot,
                    workflow_id=wf["workflow_id"],
                    version_tag=wf["version_tag"],
                    input_data=input_data,
                    forecast_ts=forecast_ts,
                    is_shadow=wf["is_shadow"],
                    # 覆盖 train_test_split_ts 使用 all_train 模式
                    operator_param_overrides={"train_test_split_ts": {"mode": "all_train"}},
                )
                if first_cycle_id is None and not wf["is_shadow"]:
                    first_cycle_id = cid
                logger.info(
                    "daily_rolling_task: slot=%s role=%s workflow=%s forecast_ts=%s OK",
                    slot, wf["role"], wf["workflow_id"], forecast_ts,
                )
            except Exception as exc:
                logger.warning(
                    "daily_rolling_task: slot=%s role=%s workflow=%s 失败: %s",
                    slot, wf["role"], wf["workflow_id"], exc,
                )
                if wf["role"] == "production":
                    logger.error(
                        "daily_rolling_task: 生产模型预测失败！slot=%s workflow=%s",
                        slot, wf["workflow_id"],
                    )

        return first_cycle_id

    return daily_rolling_task


# 向后兼容 alias：旧代码或 main.py 里如果直接用 make_prediction_task 仍然有效
def make_prediction_task(
    lf_repo,
    slot: str,
    station_id: str = DEFAULT_MOCK_STATION_ID,
    feature_name: str = DEFAULT_MOCK_FEATURE_NAME,
    production_registry=None,
    version_registry=None,
    config_manager=None,
) -> Callable:
    """
    向后兼容 alias — 内部调用新版 make_daily_rolling_task。

    config_manager 参数已忽略（training_window_days 现在从 slot_store 读取）。
    如需完整功能，请直接使用 make_daily_rolling_task 并传入 slot_store。
    """
    return make_daily_rolling_task(
        lf_repo=lf_repo,
        slot=slot,
        station_id=station_id,
        feature_name=feature_name,
        slot_store=None,  # 降级到老路径（production_registry + version_registry）
        production_registry=production_registry,
        version_registry=version_registry,
    )
# @AI_GENERATED: end


# @AI_GENERATED: 新增 operator_param_overrides 参数
def _run_single_prediction(
    lf_repo: "LoadForecastRepository",
    slot: str,
    workflow_id: str,
    version_tag: str,
    input_data,
    forecast_ts: datetime,
    is_shadow: bool,
    operator_param_overrides: Optional[dict] = None,
) -> Optional[str]:
    """
    Run one workflow prediction and write PredictionResult. Returns cycle_id.

    operator_param_overrides — 按 functionId 覆盖算子参数的字典，例如：
      {"train_test_split_ts": {"mode": "all_train"}}
    传入 workflow_predictor.run_prediction 后，该 functionId 的节点 params
    会被 merge 覆盖，优先级高于工作流 JSON 里的节点 config。
    """
    from services.scheduler.tasks.workflow_predictor import run_prediction
# @AI_GENERATED: end

    cycle_id = f"{workflow_id}:{forecast_ts.strftime('%Y%m%d%H%M%S')}"

    # Check if already predicted for this cycle
    with lf_repo._adapter.get_sync_session() as session:
        existing = (
            session.query(PredictionResult.id)
            .filter(
                PredictionResult.slot == slot,
                PredictionResult.workflow_id == workflow_id,
                PredictionResult.prediction_cycle_id == cycle_id,
            )
            .first()
        )
        if existing is not None:
            logger.info("prediction_task: cycle already exists: %s", cycle_id)
            return cycle_id

    # Execute workflow pipeline
    # @AI_GENERATED: 传入 operator_param_overrides 覆盖节点参数（如 mode="all_train"）
    result = run_prediction(workflow_id, input_data, slot,
                            operator_param_overrides=operator_param_overrides)
    # @AI_GENERATED: end

    if not result["success"] or result["predicted_value"] is None:
        # Write a failed prediction record
        with lf_repo._adapter.get_sync_session() as session:
            session.add(
                PredictionResult(
                    slot=slot,
                    workflow_id=workflow_id,
                    version_tag=version_tag,
                    prediction_cycle_id=cycle_id,
                    forecast_timestamp=forecast_ts,
                    predicted_value=0.0,
                    actual_value=None,
                    status="failed",
                    is_shadow=is_shadow,
                    created_at=datetime.utcnow(),
                )
            )
        logger.warning(
            "prediction_task: workflow %s prediction failed: %s",
            workflow_id, result.get("error"),
        )
        return cycle_id

    # Write successful prediction
    predicted_value = result["predicted_value"]
    with lf_repo._adapter.get_sync_session() as session:
        session.add(
            PredictionResult(
                slot=slot,
                workflow_id=workflow_id,
                version_tag=version_tag,
                prediction_cycle_id=cycle_id,
                forecast_timestamp=forecast_ts,
                predicted_value=predicted_value,
                actual_value=None,
                status="predicted",
                is_shadow=is_shadow,
                created_at=datetime.utcnow(),
            )
        )

    logger.info(
        "prediction_task: slot=%s workflow=%s forecast_ts=%s predicted=%.4f is_shadow=%s",
        slot, workflow_id, forecast_ts, predicted_value, is_shadow,
    )
    return cycle_id


# ---------------------------------------------------------------------------
# Task 3: 精度回填任务
# ---------------------------------------------------------------------------

def make_accuracy_backfill_task(
    lf_repo: "LoadForecastRepository",
    slot: str,
    station_id: str = DEFAULT_MOCK_STATION_ID,
    feature_name: str = DEFAULT_MOCK_FEATURE_NAME,
    workflow_id: str = DEFAULT_MOCK_WORKFLOW_ID,
    slot_store=None,
) -> Callable:
    """
    返回 accuracy_backfill_task() — 计算 MAPE 并 upsert AccuracyMetric。

    步骤：
    1. 只对 forecast_timestamp 已进入 station_data 的预测记录回填 actual_value
    2. 按 workflow_id 分组计算 rolling MAPE
    3. upsert AccuracyMetric（原有逻辑不变）

    新增步骤（阶段 2，需传入 slot_store）：
    4. 更新 shadow.consecutive_better_days（每天跑的 shadow 是否今天优于生产）
    5. 用最新 MAPE 更新 prelaunch_meta.current_rolling_mape
    6. 对每个 prelaunch 调 check_graduation，执行毕业/失败状态转换

    Args:
        slot_store — DeploymentSlotStore 实例（可选，传入时启用步骤 4~6）

    Returns:
        更新的 workflow_id 数量
    """

    def accuracy_backfill_task() -> int:
        # 回填只能使用已经进入平台库的 actual，避免从 source CSV 读未来值。
        with lf_repo._adapter.get_sync_session() as session:
            latest_actual_ts = (
                session.query(StationData.timestamp_utc)
                .filter(
                    StationData.slot == slot,
                    StationData.station_id == station_id,
                    StationData.feature_name == feature_name,
                )
                .order_by(StationData.timestamp_utc.desc())
                .limit(1)
                .scalar()
            )
            if latest_actual_ts is not None:
                pending = (
                    session.query(PredictionResult)
                    .filter(
                        PredictionResult.slot == slot,
                        PredictionResult.workflow_id == workflow_id,
                        PredictionResult.actual_value.is_(None),
                        PredictionResult.forecast_timestamp <= latest_actual_ts,
                    )
                    .all()
                )
                for pred in pending:
                    actual = (
                        session.query(StationData.value)
                        .filter(
                            StationData.slot == slot,
                            StationData.station_id == station_id,
                            StationData.feature_name == feature_name,
                            StationData.timestamp_utc == pred.forecast_timestamp,
                        )
                        .order_by(StationData.ingested_at.desc())
                        .limit(1)
                        .scalar()
                    )
                    if actual is None:
                        continue
                    pred.actual_value = float(actual)
                    pred.status = "evaluated"
                    pred.evaluated_at = datetime.utcnow()

        # 查询该 slot 下所有有实际值的预测记录
        with lf_repo._adapter.get_sync_session() as session:
            rows = (
                session.query(PredictionResult)
                .filter(
                    PredictionResult.slot == slot,
                    PredictionResult.actual_value.isnot(None),
                )
                .all()
            )
            session.expunge_all()

        # 按 workflow_id 分组
        groups: dict = defaultdict(list)
        for row in rows:
            groups[row.workflow_id].append(row)

        updated = 0
        # @AI_GENERATED: 记录本轮计算出的各 workflow rolling MAPE，供步骤 4~6 使用
        latest_mapes: dict = {}
        # @AI_GENERATED: end

        for wf_id, preds in groups.items():
            total_count = len(preds)

            # 过滤 actual=0 的记录，避免除零
            valid_pairs = [
                (p.predicted_value, p.actual_value)
                for p in preds
                if p.actual_value != 0
            ]

            if not valid_pairs:
                logger.debug(
                    "accuracy_backfill_task: slot=%s workflow_id=%s no valid pairs (all actual=0), skipping",
                    slot, wf_id,
                )
                continue

            mape = statistics.mean(
                abs(predicted - actual) / abs(actual) * 100
                for predicted, actual in valid_pairs
            )

            lf_repo.upsert_accuracy_metrics(
                slot,
                wf_id,
                {
                    "rolling_mape": mape,
                    "valid_cycle_count": len(valid_pairs),
                    "total_cycle_count": total_count,
                    "status": "active",
                    "last_evaluated_at": datetime.utcnow(),
                },
            )
            updated += 1
            # @AI_GENERATED
            latest_mapes[wf_id] = mape
            # @AI_GENERATED: end

        logger.info(
            "accuracy_backfill_task: slot=%s updated accuracy for %d workflow(s)",
            slot, updated,
        )

        # @AI_GENERATED: 步骤 4~6 — 需要 slot_store 才执行
        if slot_store is not None and latest_mapes:
            try:
                _post_backfill_slot_update(slot, slot_store, latest_mapes)
            except Exception as exc:
                # 后置操作失败不影响精度回填主流程
                logger.warning(
                    "accuracy_backfill_task: slot=%s 后置操作失败（不影响回填）: %s",
                    slot, exc,
                )
        # @AI_GENERATED: end

        return updated

    return accuracy_backfill_task


# @AI_GENERATED: 阶段 2 — backfill 后置操作：更新 shadow consecutive_better_days + prelaunch 毕业判定
def _post_backfill_slot_update(
    slot: str,
    slot_store,
    latest_mapes: dict,
) -> None:
    """
    accuracy_backfill 完成后的 slot 状态更新。

    步骤：
      1. 用最新 MAPE 更新 slot 内 production / shadow 的 accuracy_score
      2. 更新每个 shadow 的 consecutive_better_days（今天优于生产则 +1，否则清零）
      3. 更新每个 prelaunch 的 prelaunch_meta 精度字段
      4. 对每个 prelaunch 执行毕业判定，graduate → shadow，fail → retired
      5. 如果 auto_switch_enabled，检查 shadow 切换资格并自动执行

    所有操作最终调一次 slot_store.upsert(slot_obj) 原子写入。

    Args:
        slot:         槽位名称
        slot_store:   DeploymentSlotStore 实例
        latest_mapes: {workflow_id → rolling_mape}（本轮刚算出的）
    """
    from services.deployment.prelaunch_lifecycle import evaluate_all_prelaunches

    slot_obj = slot_store.get(slot)
    if slot_obj is None:
        logger.info("_post_backfill_slot_update: slot=%s 无 slot 数据，跳过", slot)
        return

    # ---- Step 1: 更新 production accuracy_score ----
    prod_mape: Optional[float] = None
    if slot_obj.production_model is not None:
        prod_wf = slot_obj.production_model.workflow_id
        new_mape = latest_mapes.get(prod_wf)
        if new_mape is not None:
            slot_obj.production_model.accuracy_score = new_mape
            prod_mape = new_mape
        else:
            prod_mape = slot_obj.production_model.accuracy_score  # 用旧值兜底

    # ---- Step 1.5: 同步更新 precision_ops accuracy_metrics.json（精度运营页面读此文件）----
    # @AI_GENERATED: 精度运营与模型部署精度同步
    try:
        from services.precision_ops.accuracy_tracker import AccuracyTracker
        from datetime import datetime as _dt2
        tracker = AccuracyTracker()
        for wf_id, mape in latest_mapes.items():
            existing = tracker.get_rolling_metrics(slot, wf_id) or {}
            tracker.update_metrics(slot, wf_id, {
                "rolling_mape": mape,
                "valid_cycle_count": int(existing.get("valid_cycle_count", 0)) + 1,
                "total_cycle_count": int(existing.get("total_cycle_count", 0)) + 1,
                "last_evaluated_at": _dt2.now().isoformat(),
                "status": "active",
            })
        logger.info(
            "_post_backfill_slot_update: synced %d workflow MAPE(s) to accuracy_metrics.json",
            len(latest_mapes),
        )
    except Exception as _sync_exc:
        logger.warning("_post_backfill_slot_update: 同步 accuracy_metrics.json 失败（非阻塞）: %s", _sync_exc)
    # @AI_GENERATED: end

    # ---- Step 2: 更新 shadow accuracy_score + consecutive_better_days ----
    for shadow in slot_obj.shadow_models:
        if shadow.status != "shadow":
            continue
        new_mape = latest_mapes.get(shadow.workflow_id)
        if new_mape is not None:
            shadow.accuracy_score = new_mape
        # 连续优于天数计算（MAPE 越低越好）
        if shadow.accuracy_score is not None and prod_mape is not None:
            if shadow.accuracy_score < prod_mape:
                shadow.consecutive_better_days += 1
            else:
                shadow.consecutive_better_days = 0
        else:
            # 无可比数据：不重置（保留旧值，保守处理）
            pass

    # ---- Step 3~4: Prelaunch 精度更新 + 毕业判定 ----
    decisions = evaluate_all_prelaunches(slot_obj, accuracy_by_workflow_id=latest_mapes)
    from datetime import datetime as _dt
    slot_obj.updated_at = _dt.now().isoformat()

    # 先写回 slot_obj（含精度更新），再做状态转换（防止中间状态丢失）
    slot_store.upsert(slot_obj)

    for decision in decisions:
        if decision.decision == "graduate":
            success = slot_store.promote_prelaunch_to_shadow(slot, decision.workflow_id)
            if success:
                logger.info(
                    "_post_backfill_slot_update: slot=%s prelaunch %s 毕业为 shadow | %s",
                    slot, decision.workflow_id, decision.reason,
                )
        elif decision.decision == "fail":
            success = slot_store.fail_prelaunch(slot, decision.workflow_id, decision.reason)
            if success:
                logger.info(
                    "_post_backfill_slot_update: slot=%s prelaunch %s 失败 → retired | %s",
                    slot, decision.workflow_id, decision.reason,
                )

    # ---- Step 5: Shadow 锦标赛切换资格检查 ----
    # 重新读一次（状态转换后可能有新 shadow）
    slot_obj = slot_store.get(slot)
    if slot_obj is None or not slot_obj.auto_switch_enabled:
        return

    try:
        from services.deployment.switch_decision import SwitchDecisionEngine
        from services.deployment.store import SwitchEventLog
        engine = SwitchDecisionEngine(
            slot_store=slot_store,
            event_log=SwitchEventLog(),
        )
        eligibility = engine.check_switch_eligibility(slot)
        if eligibility.eligible and eligibility.target_workflow_id:
            logger.info(
                "_post_backfill_slot_update: slot=%s 自动切换触发 → target=%s",
                slot, eligibility.target_workflow_id,
            )
            engine.execute_switch(
                slot=slot,
                target_workflow_id=eligibility.target_workflow_id,
                trigger_type="auto",
                reason=(
                    f"shadow 连续 {eligibility.consecutive_better_days} 天优于生产，"
                    "满足自动切换条件"
                ),
            )
        else:
            logger.debug(
                "_post_backfill_slot_update: slot=%s switch not eligible: %s",
                slot, eligibility.reason,
            )
    except Exception as exc:
        logger.warning(
            "_post_backfill_slot_update: slot=%s 切换检查失败（不影响精度回填）: %s",
            slot, exc,
        )
# @AI_GENERATED: end
