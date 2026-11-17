# @AI_GENERATED
"""
负荷预测 REST API 路由模块

提供训练、预测、回测、场景查询和任务状态查询端点。
内部通过 import 直接调用现有负荷预测核心代码，数据以 Python 原生对象在进程内传递。
"""
import sys
import os
import time
import uuid
import pickle
import traceback
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytz
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

# @AI_GENERATED
# pandas 2.x 兼容性补丁：closed 参数在 2.x 中改名为 inclusive
# 必须在 import features/engine.py 之前执行
_original_date_range = pd.date_range

def _patched_date_range(*args, **kwargs):
    if "closed" in kwargs:
        closed_val = kwargs.pop("closed")
        mapping = {"left": "left", "right": "right", None: "both"}
        kwargs["inclusive"] = mapping.get(closed_val, closed_val)
    return _original_date_range(*args, **kwargs)

pd.date_range = _patched_date_range
# @AI_GENERATED: end

# ---------------------------------------------------------------------------
# 确保 backend-service 根目录在 sys.path 中，仅加载后端目录内模块
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from common.constants import SCENARIO_CONFIGS
from data_process import (
    get_completed_timestamp,
    chebyshev_detector,
    get_completed_df,
    get_train_status,
    get_timestamp_freq,
)
from db_data_fetch import offline_load_data
from features.engine import add_more_features
from models_pkg.trainer import model_prefer_trainer
from models_pkg.wrapper import LoadForecastWrapper
from forecast_utils import predict_format_transform, capture_df_delay_info, df_recovery_by_self_defined

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/api/load-forecast", tags=["load-forecast"])

# ---------------------------------------------------------------------------
# 内存任务状态存储
# ---------------------------------------------------------------------------
task_store: Dict[str, Dict[str, Any]] = {}

# 内存模型缓存 (task_id -> pickled model bytes)
_model_cache: Dict[str, bytes] = {}

VALID_TASK_TYPES = set(SCENARIO_CONFIGS.keys())  # {"DI", "D", "WI", "W", "MI", "M"}


def _new_task_id(prefix: str = "task") -> str:
    """生成唯一任务 ID"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _parse_app_lang(request: Request) -> str:
    """根据请求头解析界面语言：zh 或 en"""
    raw = (request.headers.get("x-app-lang") or request.headers.get("X-App-Lang") or "").strip().lower()
    if raw.startswith("en"):
        return "en"
    return "zh"


def _create_task(task_id: str, task_type: str, locale: str = "zh") -> Dict[str, Any]:
    """创建并注册一个新的任务状态条目"""
    now = datetime.now().isoformat()
    loc = "en" if (locale or "").lower().startswith("en") else "zh"
    entry = {
        "task_id": task_id,
        "status": "pending",
        "task_type": task_type,
        "locale": loc,
        "current_step": None,
        "completed_steps": [],
        "step_durations": {},
        "total_duration": 0.0,
        "error_message": None,
        "error_step": None,
        "created_at": now,
        "updated_at": now,
        "result": None,
        "logs": [],
    }
    task_store[task_id] = entry
    return entry


# @AI_GENERATED
def _append_log(task_id: str, message: str, log_type: str = "info"):
    """追加日志到任务状态"""
    entry = task_store.get(task_id)
    if not entry:
        return
    ts = datetime.now().strftime("%H:%M:%S")
    entry["logs"].append({"timestamp": ts, "message": message, "type": log_type})
# @AI_GENERATED: end


# @AI_GENERATED
# 步骤名称 i18n（与前端 loadForecast.steps.* 语义对齐）
_STEP_LABELS_I18N: Dict[str, Dict[str, str]] = {
    "data_fetch": {"zh": "数据获取", "en": "Data fetching"},
    "anomaly_detection": {"zh": "异常检测", "en": "Anomaly detection"},
    "feature_engineering": {"zh": "特征工程", "en": "Feature engineering"},
    "model_train": {"zh": "模型训练", "en": "Model training"},
    "model_predict": {"zh": "模型推理", "en": "Model inference"},
    "post_processing": {"zh": "结果后处理", "en": "Post-processing"},
    "backtest_loop": {"zh": "回测循环", "en": "Backtest loop"},
}


def _task_lang(task_id: str) -> str:
    entry = task_store.get(task_id)
    if not entry:
        return "zh"
    return entry.get("locale") or "zh"


def _step_label(step_name: str, lang: str) -> str:
    row = _STEP_LABELS_I18N.get(step_name)
    if not row:
        return step_name
    return row.get(lang) or row["zh"]


def _update_step(task_id: str, step_name: str, *, started: bool = False, duration: float = 0.0):
    """更新任务的当前步骤信息，同时自动追加日志"""
    entry = task_store.get(task_id)
    if not entry:
        return
    entry["updated_at"] = datetime.now().isoformat()
    lang = _task_lang(task_id)
    label = _step_label(step_name, lang)
    if started:
        entry["status"] = "running"
        entry["current_step"] = step_name
        if lang == "en":
            _append_log(task_id, f"▶ {label} starting...", "start")
        else:
            _append_log(task_id, f"▶ {label} 开始执行...", "start")
    else:
        entry["completed_steps"].append(step_name)
        entry["step_durations"][step_name] = round(duration, 3)
        entry["current_step"] = None
        if lang == "en":
            _append_log(task_id, f"✓ {label} completed ({duration:.2f}s)", "success")
        else:
            _append_log(task_id, f"✓ {label} 完成 (耗时 {duration:.2f}s)", "success")


def _mark_success(task_id: str, result: Any = None, total_duration: float = 0.0):
    entry = task_store.get(task_id)
    if not entry:
        return
    entry["status"] = "success"
    entry["total_duration"] = round(total_duration, 3)
    entry["result"] = result
    entry["updated_at"] = datetime.now().isoformat()
    lang = _task_lang(task_id)
    ttype = entry.get("task_type") or "train"
    if ttype == "backtest":
        msg = (
            f"✓ Backtest finished, total {total_duration:.2f}s"
            if lang == "en"
            else f"✓ 回测完成，总耗时 {total_duration:.2f}s"
        )
    elif ttype == "predict":
        msg = (
            f"✓ Inference finished, total {total_duration:.2f}s"
            if lang == "en"
            else f"✓ 推理完成，总耗时 {total_duration:.2f}s"
        )
    else:
        msg = (
            f"✓ Training finished, total {total_duration:.2f}s"
            if lang == "en"
            else f"✓ 训练完成，总耗时 {total_duration:.2f}s"
        )
    _append_log(task_id, msg, "success")


def _mark_failed(task_id: str, step_name: str, error: Exception, total_duration: float = 0.0):
    entry = task_store.get(task_id)
    if not entry:
        return
    entry["status"] = "failed"
    entry["error_step"] = step_name
    entry["error_message"] = str(error)
    entry["total_duration"] = round(total_duration, 3)
    entry["updated_at"] = datetime.now().isoformat()
    lang = _task_lang(task_id)
    label = _step_label(step_name, lang)
    if lang == "en":
        _append_log(task_id, f"✗ {label} failed: {error}", "error")
    else:
        _append_log(task_id, f"✗ {label} 失败: {error}", "error")


def _error_response(task_id: str, error: Exception, failed_step: str) -> JSONResponse:
    """构建统一错误响应"""
    return JSONResponse(
        status_code=500,
        content={
            "task_id": task_id,
            "status": "failed",
            "error_type": type(error).__name__,
            "error_message": str(error),
            "failed_step": failed_step,
            "traceback": traceback.format_exc(),
        },
    )


def _build_delay_info(str_d: str, forecast_horizon: int, load_field: str, weather_cols: list) -> dict:
    """动态生成 that_time_latest 延迟信息字典（复用 run.py 逻辑）"""
    base_time = pd.to_datetime(str_d) + timedelta(days=1) - timedelta(minutes=15)
    end_time = pd.to_datetime(str_d) + timedelta(days=forecast_horizon + 1) - timedelta(minutes=15)
    info = {load_field: base_time.strftime("%Y-%m-%d %H:%M:%S")}
    for col in weather_cols:
        info[col] = end_time.strftime("%Y-%m-%d %H:%M:%S")
    return info


# ---------------------------------------------------------------------------
# 从请求体提取通用参数的辅助函数
# ---------------------------------------------------------------------------

def _extract_common_params(body: dict) -> dict:
    """从请求 JSON 中提取数据源和预测相关的通用参数"""
    task_type = body.get("task_type", "D")
    if task_type not in VALID_TASK_TYPES:
        raise ValueError(f"无效的 task_type: {task_type}，有效值为 {sorted(VALID_TASK_TYPES)}")

    return {
        "task_type": task_type,
        "table_name": body.get("table_name", "sgms_hbuilding_load_quarter3"),
        "parent_field": body.get("parent_field", "parent_id"),
        "child_field": body.get("child_field", "child_id"),
        "time_field": body.get("time_field", "record_time"),
        "load_field": body.get("load_field", "load"),
        "parent_id": body.get("parent_id") or "park_01",
        "child_id": body.get("child_id") or "yARGkDuq",
        "time_granularity": body.get("time_granularity", "15min"),
        "time_zone": body.get("time_zone", "Asia/Shanghai"),
        "forecast_horizon": int(body.get("forecast_horizon", 1)),
        "forecast_start_time": body.get("forecast_start_time", "00:15"),
        "separate_modeling": body.get("separate_modeling", "false"),
        "operate_status": body.get("operate_status", "offline"),
        "other_cols": body.get("other_cols", []),
        "data_source": body.get("data_source", "offline"),
        "csv_path": body.get("csv_path") or os.path.join(_BACKEND_DIR, "datasets", "load_true_weihai_260415.csv"),
        "specify_model": body.get("specify_model", "xgb"),
        "nowtime": body.get("nowtime", None),
    }


# ===========================================================================
# POST /api/load-forecast/train
# ===========================================================================

@router.post("/train")
async def train(request: Request):
    """
    触发负荷预测模型训练（异步）。

    立即返回 task_id，训练在后台线程执行。
    前端通过 GET /status/{task_id} 轮询进度。
    """
    body = await request.json()
    task_id = _new_task_id("train")

    # --- 参数校验 ---
    try:
        params = _extract_common_params(body)
    except ValueError as e:
        return JSONResponse(status_code=400, content={
            "task_id": task_id, "status": "failed",
            "error_type": "ConfigError", "error_message": str(e), "failed_step": "validation",
        })

    _create_task(task_id, "train", _parse_app_lang(request))

    # @AI_GENERATED
    # 在后台线程中执行训练，API 立即返回 task_id
    def _run_training():
        _train_sync(task_id, params)

    thread = threading.Thread(target=_run_training, daemon=True)
    thread.start()
    # @AI_GENERATED: end

    return {
        "task_id": task_id,
        "status": "pending",
    }


# @AI_GENERATED
def _train_sync(task_id: str, params: dict):
    """同步执行训练流程（在后台线程中调用）"""

    # @AI_GENERATED
    # 添加 loguru sink，将训练日志实时捕获到 task_store
    def _log_sink(message):
        record = message.record
        text = record["message"]
        # 过滤掉过长的 DataFrame 输出，只保留摘要
        if len(text) > 500:
            text = text[:500] + "..."
        level = record["level"].name.lower()
        log_type = "error" if level in ("error", "critical") else "info"
        _append_log(task_id, text, log_type)

    sink_id = logger.add(_log_sink, format="{message}", level="INFO")
    # @AI_GENERATED: end

    overall_start = time.time()
    scenario = SCENARIO_CONFIGS[params["task_type"]]
    step = "data_fetch"

    try:
        # ---- Step 1: 数据获取 ----
        _update_step(task_id, step, started=True)
        logger.info(f"[{task_id}] Step {step} started")
        t0 = time.time()

        is_training = "true"
        train_trigger_time = params["nowtime"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        logger.info(f"[{task_id}] csv_path={params['csv_path']}, exists={os.path.exists(params['csv_path'])}")

        _result = offline_load_data(
            params["task_type"], params["table_name"],
            params["parent_field"], params["child_field"],
            params["time_field"], params["load_field"],
            params["parent_id"], params["child_id"],
            params["time_granularity"], is_training,
            params["time_zone"],
            nowtime=train_trigger_time,
            other_cols=params["other_cols"],
            csv_path=params["csv_path"],
        )
        if _result is None:
            raise RuntimeError(f"数据加载失败: offline_load_data 返回 None。csv_path={params['csv_path']}, "
                               f"parent_id={params['parent_id']}, child_id={params['child_id']}")
        load_df, his_min_max = _result

        str_d = pd.to_datetime(train_trigger_time).strftime("%Y-%m-%d")
        that_time_latest = _build_delay_info(
            str_d, params["forecast_horizon"], params["load_field"], params["other_cols"])
        load_df, his_min_max = df_recovery_by_self_defined(
            load_df, that_time_latest, params["time_granularity"],
            time_field=params["time_field"], load_field=params["load_field"])

        dur = time.time() - t0
        _update_step(task_id, step, duration=dur)
        logger.info(f"[{task_id}] Step {step} completed in {dur:.2f}s, rows={len(load_df)}")

        # ---- 训练状态检查 ----
        train_status = get_train_status(
            load_df, params["task_type"], params["forecast_horizon"],
            time_field=params["time_field"], load_field=params["load_field"])
        if train_status != "true":
            raise RuntimeError(
                f"训练数据不满足最低要求 (task_type={params['task_type']}, "
                f"forecast_horizon={params['forecast_horizon']})")

        # ---- Step 2: 异常检测与数据补全 ----
        step = "anomaly_detection"
        _update_step(task_id, step, started=True)
        logger.info(f"[{task_id}] Step {step} started")
        t0 = time.time()

        original_time_freq, daily_horizon = get_timestamp_freq(
            load_df, time_field=params["time_field"])

        timestamp_completed_df = get_completed_timestamp(
            load_df, original_time_freq, daily_horizon, is_training,
            time_field=params["time_field"])

        train_delay_info = capture_df_delay_info(
            timestamp_completed_df, is_training, train_trigger_time,
            time_field=params["time_field"])

        anomaly_detected_df = chebyshev_detector(
            timestamp_completed_df, load_field=params["load_field"])

        completed_df = get_completed_df(
            anomaly_detected_df, delay_info=train_delay_info,
            time_field=params["time_field"], load_field=params["load_field"])

        dur = time.time() - t0
        _update_step(task_id, step, duration=dur)
        logger.info(f"[{task_id}] Step {step} completed in {dur:.2f}s, rows={len(completed_df)}")

        # ---- Step 3: 特征工程 ----
        step = "feature_engineering"
        _update_step(task_id, step, started=True)
        logger.info(f"[{task_id}] Step {step} started")
        t0 = time.time()

        forecast_timestamps, feat_df, train_shift_info = add_more_features(
            scenario,
            task_id=task_id,
            parent_id=params["parent_id"],
            child_id=params["child_id"],
            operate_status=params["operate_status"],
            completed_df=completed_df,
            original_time_freq=original_time_freq,
            daily_horizon=daily_horizon,
            forecast_horizon=params["forecast_horizon"],
            forecast_start_time=params["forecast_start_time"],
            is_training=is_training,
            time_zone=params["time_zone"],
            nowtime=train_trigger_time,
            separate_modeling=params["separate_modeling"],
            gaps_defined=None,
            time_field=params["time_field"],
            load_field=params["load_field"],
        )

        dur = time.time() - t0
        _update_step(task_id, step, duration=dur)
        logger.info(f"[{task_id}] Step {step} completed in {dur:.2f}s")

        # ---- Step 4: 模型训练 ----
        step = "model_train"
        _update_step(task_id, step, started=True)
        logger.info(f"[{task_id}] Step {step} started")
        t0 = time.time()

        total_model, total_feature_list, total_auto_model_tag, _daily_horizon = model_prefer_trainer(
            feat_df, daily_horizon, params["forecast_horizon"],
            scenario=scenario,
            separate_modeling=params["separate_modeling"],
            time_field=params["time_field"],
            load_field=params["load_field"],
        )

        dur = time.time() - t0
        _update_step(task_id, step, duration=dur)
        logger.info(f"[{task_id}] Step {step} completed in {dur:.2f}s")

        # ---- 包装并缓存模型 ----
        custom_model = LoadForecastWrapper(
            train_shift_info, train_delay_info, feat_df, forecast_timestamps,
            total_model, total_feature_list, total_auto_model_tag, daily_horizon,
            params["forecast_horizon"], params["forecast_start_time"],
            params["time_granularity"],
            scenario=scenario,
            time_field=params["time_field"],
            load_field=params["load_field"],
        )

        model_id = f"model-{params['parent_id']}-{params['child_id']}-{params['task_type']}-{task_id}"
        _model_cache[model_id] = pickle.dumps(custom_model)

        total_duration = time.time() - overall_start
        result = {
            "model_id": model_id,
            "daily_horizon": daily_horizon,
            "original_time_freq": original_time_freq,
        }
        _mark_success(task_id, result=result, total_duration=total_duration)
        logger.info(f"[{task_id}] Training completed in {total_duration:.2f}s, model_id={model_id}")

    except Exception as e:
        total_duration = time.time() - overall_start
        logger.error(f"[{task_id}] Step {step} failed: {e}")
        logger.error(traceback.format_exc())
        _mark_failed(task_id, step, e, total_duration)
    finally:
        # 清理 loguru sink
        try:
            logger.remove(sink_id)
        except Exception:
            pass
# @AI_GENERATED: end



# ===========================================================================
# POST /api/load-forecast/predict
# ===========================================================================

@router.post("/predict")
async def predict(request: Request):
    """
    触发负荷预测推理。

    内部调用: 数据获取 → 异常检测 → 特征工程 → LoadForecastWrapper.predict()
    """
    body = await request.json()
    task_id = _new_task_id("pred")

    # --- 参数校验 ---
    try:
        params = _extract_common_params(body)
    except ValueError as e:
        return JSONResponse(status_code=400, content={
            "task_id": task_id, "status": "failed",
            "error_type": "ConfigError", "error_message": str(e), "failed_step": "validation",
        })

    model_id = body.get("model_id")
    lang_pf = _parse_app_lang(request)
    if not model_id or model_id not in _model_cache:
        err_msg = (
            f"model_id '{model_id}' not found or model not trained"
            if lang_pf == "en"
            else f"model_id '{model_id}' 不存在或未训练"
        )
        return JSONResponse(status_code=400, content={
            "task_id": task_id, "status": "failed",
            "error_type": "ConfigError",
            "error_message": err_msg,
            "failed_step": "validation",
        })

    _create_task(task_id, "predict", lang_pf)
    overall_start = time.time()
    scenario = SCENARIO_CONFIGS[params["task_type"]]
    step = "data_fetch"

    try:
        # ---- Step 1: 数据获取 ----
        _update_step(task_id, step, started=True)
        logger.info(f"[{task_id}] Step {step} started")
        t0 = time.time()

        is_training = "false"
        pred_trigger_time = params["nowtime"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        load_df, his_min_max = offline_load_data(
            params["task_type"], params["table_name"],
            params["parent_field"], params["child_field"],
            params["time_field"], params["load_field"],
            params["parent_id"], params["child_id"],
            params["time_granularity"], is_training,
            params["time_zone"],
            nowtime=pred_trigger_time,
            other_cols=params["other_cols"],
            csv_path=params["csv_path"],
        )

        str_d = pd.to_datetime(pred_trigger_time).strftime("%Y-%m-%d")
        that_time_latest = _build_delay_info(
            str_d, params["forecast_horizon"], params["load_field"], params["other_cols"])
        load_df, his_min_max = df_recovery_by_self_defined(
            load_df, that_time_latest, params["time_granularity"],
            time_field=params["time_field"], load_field=params["load_field"])

        dur = time.time() - t0
        _update_step(task_id, step, duration=dur)
        logger.info(f"[{task_id}] Step {step} completed in {dur:.2f}s, rows={len(load_df)}")

        # ---- Step 2: 异常检测与数据补全 ----
        step = "anomaly_detection"
        _update_step(task_id, step, started=True)
        logger.info(f"[{task_id}] Step {step} started")
        t0 = time.time()

        original_time_freq, daily_horizon = get_timestamp_freq(
            load_df, time_field=params["time_field"])

        timestamp_completed_df = get_completed_timestamp(
            load_df, original_time_freq, daily_horizon, is_training,
            time_field=params["time_field"])

        pred_delay_info = capture_df_delay_info(
            timestamp_completed_df, is_training, pred_trigger_time,
            time_field=params["time_field"])

        anomaly_detected_df = chebyshev_detector(
            timestamp_completed_df, load_field=params["load_field"])

        completed_df = get_completed_df(
            anomaly_detected_df, pred_delay_info,
            time_field=params["time_field"], load_field=params["load_field"])

        dur = time.time() - t0
        _update_step(task_id, step, duration=dur)
        logger.info(f"[{task_id}] Step {step} completed in {dur:.2f}s, rows={len(completed_df)}")

        # ---- Step 3: 特征工程 ----
        step = "feature_engineering"
        _update_step(task_id, step, started=True)
        logger.info(f"[{task_id}] Step {step} started")
        t0 = time.time()

        forecast_timestamps, feat_df, pred_shift_info = add_more_features(
            scenario,
            task_id=task_id,
            parent_id=params["parent_id"],
            child_id=params["child_id"],
            operate_status=params["operate_status"],
            completed_df=completed_df,
            original_time_freq=original_time_freq,
            daily_horizon=daily_horizon,
            forecast_horizon=params["forecast_horizon"],
            forecast_start_time=params["forecast_start_time"],
            is_training=is_training,
            time_zone=params["time_zone"],
            nowtime=pred_trigger_time,
            separate_modeling=params["separate_modeling"],
            gaps_defined=None,
            time_field=params["time_field"],
            load_field=params["load_field"],
        )

        dur = time.time() - t0
        _update_step(task_id, step, duration=dur)
        logger.info(f"[{task_id}] Step {step} completed in {dur:.2f}s")

        # ---- Step 4: 模型推理 ----
        step = "model_predict"
        _update_step(task_id, step, started=True)
        logger.info(f"[{task_id}] Step {step} started")
        t0 = time.time()

        custom_model = pickle.loads(_model_cache[model_id])

        # 构造 MLflow predict 输入（复用 run.py 逻辑）
        first_layer_keys = list(feat_df.keys())
        feat_df_dict = {}
        for tmp_key in first_layer_keys:
            if isinstance(feat_df[tmp_key], pd.DataFrame):
                tmp_dict = {}
                for c in feat_df[tmp_key].columns:
                    tmp_dict[c] = feat_df[tmp_key][c].values
                feat_df_dict[tmp_key] = tmp_dict
            else:
                feat_df_dict[tmp_key] = feat_df[tmp_key]

        inputs = pd.DataFrame()
        inputs["feat_df"] = [feat_df_dict]
        inputs["other_params"] = [{
            "pred_start_time": pred_trigger_time,
            "specify_model": params["specify_model"],
            "separate_modeling": params["separate_modeling"],
        }]

        predict_output = custom_model.predict(None, inputs)

        # 如果 predict 返回字符串，说明内部出错
        if isinstance(predict_output, str):
            raise RuntimeError(predict_output)

        dur = time.time() - t0
        _update_step(task_id, step, duration=dur)
        logger.info(f"[{task_id}] Step {step} completed in {dur:.2f}s")

        # ---- Step 5: 结果后处理 ----
        step = "post_processing"
        _update_step(task_id, step, started=True)
        logger.info(f"[{task_id}] Step {step} started")
        t0 = time.time()

        pred_values = predict_output.get("pred", [])
        pred_re = list(np.array(pred_values).flatten())
        json_list = predict_format_transform(
            pred_re, forecast_timestamps, his_min_max,
            time_field=params["time_field"], load_field=params["load_field"])

        # 提取时间戳和预测值
        timestamps_out = []
        values_out = []
        tz_obj = pytz.timezone(params["time_zone"])
        for item in json_list:
            ts = item["time"]
            dt = pytz.datetime.datetime.fromtimestamp(ts, tz_obj)
            timestamps_out.append(dt.strftime("%Y-%m-%d %H:%M:%S"))
            values_out.append(item[params["load_field"]])

        dur = time.time() - t0
        _update_step(task_id, step, duration=dur)
        logger.info(f"[{task_id}] Step {step} completed in {dur:.2f}s")

        total_duration = time.time() - overall_start
        _mark_success(task_id, result={"count": len(values_out)}, total_duration=total_duration)

        return {
            "task_id": task_id,
            "status": "success",
            "duration_seconds": round(total_duration, 2),
            "steps_completed": task_store[task_id]["completed_steps"],
            "forecast_timestamps": timestamps_out,
            "forecast_values": values_out,
        }

    except Exception as e:
        total_duration = time.time() - overall_start
        logger.error(f"[{task_id}] Step {step} failed: {e}")
        logger.error(traceback.format_exc())
        _mark_failed(task_id, step, e, total_duration)
        return _error_response(task_id, e, step)


# ===========================================================================
# POST /api/load-forecast/backtest
# ===========================================================================

# @AI_GENERATED
@router.post("/backtest")
async def backtest(request: Request):
    """
    触发负荷预测回测评估。

    按日期循环调用训练和预测流程（复用 run.py 中 run_backtest() 的逻辑），
    返回每日预测结果和评估指标。
    """
    body = await request.json()
    task_id = _new_task_id("bt")

    # --- 参数校验 ---
    try:
        params = _extract_common_params(body)
    except ValueError as e:
        return JSONResponse(status_code=400, content={
            "task_id": task_id, "status": "failed",
            "error_type": "ConfigError", "error_message": str(e), "failed_step": "validation",
        })

    start_date = body.get("start_date")
    end_date = body.get("end_date")
    lang_bt = _parse_app_lang(request)
    if not start_date or not end_date:
        return JSONResponse(status_code=400, content={
            "task_id": task_id, "status": "failed",
            "error_type": "ConfigError",
            "error_message": "start_date and end_date are required" if lang_bt == "en" else "start_date 和 end_date 为必填参数",
            "failed_step": "validation",
        })

    try:
        date_range = pd.date_range(start_date, end_date, freq="D")
    except Exception as e:
        return JSONResponse(status_code=400, content={
            "task_id": task_id, "status": "failed",
            "error_type": "ConfigError",
            "error_message": (f"Invalid date range: {e}" if lang_bt == "en" else f"日期范围无效: {e}"),
            "failed_step": "validation",
        })

    if len(date_range) == 0:
        return JSONResponse(status_code=400, content={
            "task_id": task_id, "status": "failed",
            "error_type": "ConfigError",
            "error_message": (
                "Empty date range; check start_date and end_date"
                if lang_bt == "en"
                else "日期范围为空，请检查 start_date 和 end_date"
            ),
            "failed_step": "validation",
        })

    _create_task(task_id, "backtest", lang_bt)

    # @AI_GENERATED
    # 异步执行回测，立即返回 task_id
    _date_range_list = list(date_range)

    def _run_backtest():
        _backtest_sync(task_id, params, _date_range_list, start_date, end_date)

    thread = threading.Thread(target=_run_backtest, daemon=True)
    thread.start()

    return {
        "task_id": task_id,
        "status": "pending",
    }
    # @AI_GENERATED: end


# @AI_GENERATED
def _backtest_sync(task_id: str, params: dict, date_range_list: list, start_date: str, end_date: str):
    """同步执行回测流程（在后台线程中调用）"""
    overall_start = time.time()
    scenario = SCENARIO_CONFIGS[params["task_type"]]
    daily_results: List[Dict[str, Any]] = []
    step = "backtest_loop"

    try:
        _update_step(task_id, step, started=True)
        _append_log(task_id, f"回测开始: {start_date} → {end_date}, {len(date_range_list)} 天", "info")
        logger.info(f"[{task_id}] Backtest started: {start_date} → {end_date}, "
                     f"{len(date_range_list)} days, task_type={params['task_type']}")

        for day_idx, start_d in enumerate(date_range_list):
            str_d = start_d.strftime("%Y-%m-%d")
            train_trigger_time = str_d + " 00:00:00"
            pred_trigger_time = str_d + " 00:00:00"
            day_start = time.time()

            logger.info(f"[{task_id}] Day {day_idx + 1}/{len(date_range_list)}: {str_d}")

            # ==================== 训练阶段 ====================
            is_training = "true"

            load_df, his_min_max = offline_load_data(
                params["task_type"], params["table_name"],
                params["parent_field"], params["child_field"],
                params["time_field"], params["load_field"],
                params["parent_id"], params["child_id"],
                params["time_granularity"], is_training,
                params["time_zone"],
                nowtime=train_trigger_time,
                other_cols=params["other_cols"],
                csv_path=params["csv_path"],
            )

            that_time_latest = _build_delay_info(
                str_d, params["forecast_horizon"], params["load_field"], params["other_cols"])
            load_df, his_min_max = df_recovery_by_self_defined(
                load_df, that_time_latest, params["time_granularity"],
                time_field=params["time_field"], load_field=params["load_field"])

            train_status = get_train_status(
                load_df, params["task_type"], params["forecast_horizon"],
                time_field=params["time_field"], load_field=params["load_field"])

            if train_status != "true":
                logger.warning(f"[{task_id}] Day {str_d}: 训练数据不满足要求，跳过")
                daily_results.append({
                    "date": str_d,
                    "status": "skipped",
                    "reason": "训练数据不满足最低要求",
                })
                continue

            original_time_freq, daily_horizon = get_timestamp_freq(
                load_df, time_field=params["time_field"])

            timestamp_completed_df = get_completed_timestamp(
                load_df, original_time_freq, daily_horizon, is_training,
                time_field=params["time_field"])

            train_delay_info = capture_df_delay_info(
                timestamp_completed_df, is_training, train_trigger_time,
                time_field=params["time_field"])

            anomaly_detected_df = chebyshev_detector(
                timestamp_completed_df, load_field=params["load_field"])

            completed_df = get_completed_df(
                anomaly_detected_df, delay_info=train_delay_info,
                time_field=params["time_field"], load_field=params["load_field"])

            forecast_timestamps, feat_df, train_shift_info = add_more_features(
                scenario,
                task_id=task_id,
                parent_id=params["parent_id"],
                child_id=params["child_id"],
                operate_status=params["operate_status"],
                completed_df=completed_df,
                original_time_freq=original_time_freq,
                daily_horizon=daily_horizon,
                forecast_horizon=params["forecast_horizon"],
                forecast_start_time=params["forecast_start_time"],
                is_training=is_training,
                time_zone=params["time_zone"],
                nowtime=train_trigger_time,
                separate_modeling=params["separate_modeling"],
                gaps_defined=None,
                time_field=params["time_field"],
                load_field=params["load_field"],
            )

            total_model, total_feature_list, total_auto_model_tag, _daily_horizon = model_prefer_trainer(
                feat_df, daily_horizon, params["forecast_horizon"],
                scenario=scenario,
                separate_modeling=params["separate_modeling"],
                time_field=params["time_field"],
                load_field=params["load_field"],
            )

            custom_model = LoadForecastWrapper(
                train_shift_info, train_delay_info, feat_df, forecast_timestamps,
                total_model, total_feature_list, total_auto_model_tag, daily_horizon,
                params["forecast_horizon"], params["forecast_start_time"],
                params["time_granularity"],
                scenario=scenario,
                time_field=params["time_field"],
                load_field=params["load_field"],
            )

            # ==================== 预测阶段 ====================
            is_training = "false"

            load_df_pred, his_min_max_pred = offline_load_data(
                params["task_type"], params["table_name"],
                params["parent_field"], params["child_field"],
                params["time_field"], params["load_field"],
                params["parent_id"], params["child_id"],
                params["time_granularity"], is_training,
                params["time_zone"],
                nowtime=pred_trigger_time,
                other_cols=params["other_cols"],
                csv_path=params["csv_path"],
            )

            that_time_latest_pred = _build_delay_info(
                str_d, params["forecast_horizon"], params["load_field"], params["other_cols"])
            load_df_pred, his_min_max_pred = df_recovery_by_self_defined(
                load_df_pred, that_time_latest_pred, params["time_granularity"],
                time_field=params["time_field"], load_field=params["load_field"])

            original_time_freq_pred, daily_horizon_pred = get_timestamp_freq(
                load_df_pred, time_field=params["time_field"])

            timestamp_completed_df_pred = get_completed_timestamp(
                load_df_pred, original_time_freq_pred, daily_horizon_pred, is_training,
                time_field=params["time_field"])

            pred_delay_info = capture_df_delay_info(
                timestamp_completed_df_pred, is_training, pred_trigger_time,
                time_field=params["time_field"])

            anomaly_detected_df_pred = chebyshev_detector(
                timestamp_completed_df_pred, load_field=params["load_field"])

            completed_df_pred = get_completed_df(
                anomaly_detected_df_pred, pred_delay_info,
                time_field=params["time_field"], load_field=params["load_field"])

            forecast_timestamps_pred, feat_df_pred, pred_shift_info = add_more_features(
                scenario,
                task_id=task_id,
                parent_id=params["parent_id"],
                child_id=params["child_id"],
                operate_status=params["operate_status"],
                completed_df=completed_df_pred,
                original_time_freq=original_time_freq_pred,
                daily_horizon=daily_horizon_pred,
                forecast_horizon=params["forecast_horizon"],
                forecast_start_time=params["forecast_start_time"],
                is_training=is_training,
                time_zone=params["time_zone"],
                nowtime=pred_trigger_time,
                separate_modeling=params["separate_modeling"],
                gaps_defined=None,
                time_field=params["time_field"],
                load_field=params["load_field"],
            )

            # 构造 MLflow predict 输入
            first_layer_keys = list(feat_df_pred.keys())
            feat_df_dict = {}
            for tmp_key in first_layer_keys:
                if isinstance(feat_df_pred[tmp_key], pd.DataFrame):
                    tmp_dict = {}
                    for c in feat_df_pred[tmp_key].columns:
                        tmp_dict[c] = feat_df_pred[tmp_key][c].values
                    feat_df_dict[tmp_key] = tmp_dict
                else:
                    feat_df_dict[tmp_key] = feat_df_pred[tmp_key]

            inputs = pd.DataFrame()
            inputs["feat_df"] = [feat_df_dict]
            inputs["other_params"] = [{
                "pred_start_time": pred_trigger_time,
                "specify_model": params["specify_model"],
                "separate_modeling": params["separate_modeling"],
            }]

            predict_output = custom_model.predict(None, inputs)

            if isinstance(predict_output, str):
                logger.warning(f"[{task_id}] Day {str_d}: predict returned error string: {predict_output}")
                daily_results.append({
                    "date": str_d,
                    "status": "failed",
                    "reason": predict_output,
                })
                continue

            # 结果后处理
            pred_values = predict_output.get("pred", [])
            pred_re = list(np.array(pred_values).flatten())
            json_list = predict_format_transform(
                pred_re, forecast_timestamps_pred, his_min_max_pred,
                time_field=params["time_field"], load_field=params["load_field"])

            timestamps_out = []
            values_out = []
            tz_obj = pytz.timezone(params["time_zone"])
            for item in json_list:
                ts = item["time"]
                dt = pytz.datetime.datetime.fromtimestamp(ts, tz_obj)
                timestamps_out.append(dt.strftime("%Y-%m-%d %H:%M:%S"))
                values_out.append(item[params["load_field"]])

            day_duration = time.time() - day_start
            daily_results.append({
                "date": str_d,
                "status": "success",
                "duration_seconds": round(day_duration, 2),
                "forecast_timestamps": timestamps_out,
                "forecast_values": values_out,
                "point_count": len(values_out),
            })

            logger.info(f"[{task_id}] Day {str_d} completed in {day_duration:.2f}s, "
                         f"points={len(values_out)}")

        dur = time.time() - overall_start
        _update_step(task_id, step, duration=dur)

        total_duration = time.time() - overall_start
        success_count = sum(1 for r in daily_results if r.get("status") == "success")
        _mark_success(task_id, result={
            "total_days": len(date_range_list),
            "success_days": success_count,
            "skipped_days": sum(1 for r in daily_results if r.get("status") == "skipped"),
            "failed_days": sum(1 for r in daily_results if r.get("status") == "failed"),
            "duration_seconds": round(total_duration, 2),
            "daily_results": daily_results,
        }, total_duration=total_duration)
        logger.info(f"[{task_id}] Backtest completed in {total_duration:.2f}s")

    except Exception as e:
        total_duration = time.time() - overall_start
        logger.error(f"[{task_id}] Backtest failed at step {step}: {e}")
        logger.error(traceback.format_exc())
        _mark_failed(task_id, step, e, total_duration)
# @AI_GENERATED: end


# ===========================================================================
# GET /api/load-forecast/scenarios
# ===========================================================================

# @AI_GENERATED
@router.get("/scenarios")
async def get_scenarios():
    """
    获取六种预测场景（DI/D/WI/W/MI/M）的配置信息。

    直接读取 SCENARIO_CONFIGS 返回场景列表。
    """
    logger.info("Fetching load forecast scenario configurations")
    scenarios = []
    for key, sc in SCENARIO_CONFIGS.items():
        scenarios.append({
            "task_type": key,
            "name": getattr(sc, "name", key),
            "description": getattr(sc, "description", ""),
            "rounding_unit": getattr(sc, "rounding_unit", None),
            "default_retrain": getattr(sc, "default_retrain", None),
            "forecast_horizon_range": getattr(sc, "forecast_horizon_range", None),
        })
    return {"scenarios": scenarios}
# @AI_GENERATED: end


# ===========================================================================
# GET /api/load-forecast/status/{task_id}
# ===========================================================================

# @AI_GENERATED
@router.get("/status/{task_id}")
async def get_task_status(request: Request, task_id: str):
    """
    查询负荷预测任务的执行状态。

    从内存任务状态存储中查询。
    """
    entry = task_store.get(task_id)
    if not entry:
        lang = _parse_app_lang(request)
        detail = "Task not found" if lang == "en" else f"任务 {task_id} 不存在"
        raise HTTPException(status_code=404, detail=detail)
    return entry
# @AI_GENERATED: end
