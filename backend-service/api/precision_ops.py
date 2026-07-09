"""
api/precision_ops.py — 精度运营 REST API 路由

挂载前缀：/api/precision-ops

提供 11 个端点，覆盖版本管理、精度监控、切换操作、配置管理四个分组。
所有端点按槽位（slot）分区，默认槽位名为 "default"。

依赖注入：文件顶部初始化单例服务（lazy import 避免循环依赖）。
错误响应：统一使用 error_response() 工具函数，格式见设计文档 §错误处理。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

# ---------------------------------------------------------------------------
# 延迟导入服务层（lazy import，避免循环依赖）
# ---------------------------------------------------------------------------
from services.precision_ops.version_registry import VersionRegistry
from services.precision_ops.accuracy_tracker import AccuracyTracker
from services.precision_ops.switch_engine import SwitchDecisionEngine
from services.precision_ops.switch_log import SwitchLog
from services.precision_ops.production_registry import ProductionRegistry
from services.precision_ops.config_manager import ConfigManager
from services.precision_ops.prelaunch_manager import PrelaunchManager
from services.precision_ops.utils import BASE_DATA_DIR, load_json_safe

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 单例服务初始化
# ---------------------------------------------------------------------------
_config_manager = ConfigManager()
_version_registry = VersionRegistry()
_accuracy_tracker = AccuracyTracker()
_switch_log = SwitchLog()
_production_registry = ProductionRegistry()
_prelaunch_manager = PrelaunchManager()
_switch_engine = SwitchDecisionEngine(
    version_registry=_version_registry,
    accuracy_tracker=_accuracy_tracker,
    switch_log=_switch_log,
    production_registry=_production_registry,
    config_manager=_config_manager,
)

# ---------------------------------------------------------------------------
# APIRouter
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/api/precision-ops", tags=["precision-ops"])


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def error_response(
    code: str,
    message: str,
    details: dict = None,
    status_code: int = 400,
) -> JSONResponse:
    """
    统一错误响应工厂。

    :param code:        机器可读错误码（如 "invalid_state_transition"）
    :param message:     人类可读错误描述（中文）
    :param details:     附加结构化信息（可选），用于前端展示字段级错误
    :param status_code: HTTP 状态码，默认 400
    :return: JSONResponse
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "error": True,
            "code": code,
            "message": message,
            "details": details or {},
        },
    )


# ---------------------------------------------------------------------------
# Pydantic 请求体模型
# ---------------------------------------------------------------------------

class RegisterVersionBody(BaseModel):
    """注册版本请求体"""
    workflow_id: str
    version_tag: str
    status: str
    slot: str = "default"
    source_run_id: Optional[str] = None
    source_candidate_id: Optional[str] = None
    baseline_mape: Optional[float] = None
    registered_at: Optional[str] = None


class TransitionStatusBody(BaseModel):
    """变更版本状态请求体"""
    workflow_id: str
    new_status: str


class ManualSwitchBody(BaseModel):
    """手动切换请求体"""
    target_workflow_id: str
    reason: str = ""


# ---------------------------------------------------------------------------
# 版本管理
# ---------------------------------------------------------------------------

@router.post("/{slot}/versions", summary="注册新版本")
def register_version(slot: str, body: RegisterVersionBody):
    """
    注册新工作流版本到指定槽位（slot）。

    - **slot** — 槽位名称（分区键），如 "default"
    - Body: `workflow_id`（工作流 ID）、`version_tag`（版本标签）、
      `status`（初始状态：production / shadow / retired）等字段。
    - 成功返回完整的版本条目（含 `registered_at`、可选字段默认值）。
    - 字段校验失败（缺必填字段、重复注册等）→ 400。
    """
    entry = body.model_dump(exclude_none=False)
    # 确保 slot 路径参数覆盖 body 中的 slot 字段
    entry["slot"] = slot

    try:
        result = _version_registry.register(entry)
    except ValueError as exc:
        return error_response(
            code="invalid_version_entry",
            message=str(exc),
        )
    except ValidationError as exc:
        return error_response(
            code="validation_error",
            message="版本条目字段校验失败",
            details={"errors": exc.errors()},
        )

    return result


@router.get("/{slot}/versions", summary="列出槽位所有版本")
def list_versions(slot: str):
    """
    列出指定槽位下全部版本（含 production / shadow / retired）。

    - **slot** — 槽位名称（分区键）
    - 返回版本条目列表。
    """
    versions = _version_registry.list_all(slot)
    return {"slot": slot, "versions": versions}


@router.patch(
    "/{slot}/versions/{version_tag}/status",
    summary="变更版本状态",
)
def transition_version_status(
    slot: str,
    version_tag: str,
    body: TransitionStatusBody,
):
    """
    变更指定版本的状态（合法转换集合见设计文档 §状态转换规则）。

    - **slot** — 槽位名称（分区键）
    - **version_tag** — 版本标签（路径参数）
    - Body: `workflow_id`（工作流 ID）+ `new_status`（目标状态）
    - 非法转换（如 retired → production）→ 400。
    """
    try:
        result = _version_registry.transition_status(
            workflow_id=body.workflow_id,
            version_tag=version_tag,
            new_status=body.new_status,
        )
    except ValueError as exc:
        return error_response(
            code="invalid_state_transition",
            message=str(exc),
        )

    return result


# ---------------------------------------------------------------------------
# 精度监控
# ---------------------------------------------------------------------------

@router.get("/{slot}/leaderboard", summary="精度排行榜")
def get_leaderboard(slot: str):
    """
    返回指定槽位的精度排行榜。

    - 排除 `status=insufficient_data` 的版本
    - 按 `rolling_mape`（滚动 MAPE）升序排列
    - MAPE 差异 < 0.0001 时按 `valid_cycle_count`（有效周期数）降序
    """
    board = _accuracy_tracker.get_leaderboard(slot)
    return {"slot": slot, "leaderboard": board}


@router.get("/{slot}/metrics-history", summary="多版本 MAPE 时序数据")
def get_metrics_history(
    slot: str,
    workflow_ids: Optional[str] = Query(
        default=None,
        description="逗号分隔的 workflow_id 列表，不传则返回全部版本",
    ),
    window_days: int = Query(
        default=7,
        ge=1,
        le=30,
        description="评估窗口天数（[1, 30]），用于说明数据有效期",
    ),
):
    """
    返回多版本每日 MAPE 时序数据（简化实现：直接返回 accuracy_metrics.json 内容）。

    - **workflow_ids** — 逗号分隔，如 `wf-v1,wf-v2`；不传则返回全部版本
    - **window_days** — 评估窗口天数（默认 7），用于请求说明，不做服务端过滤
    - 简化实现：直接返回槽位 `accuracy_metrics.json` 中已有的指标快照，暂不按天聚合
    """
    metrics_path = BASE_DATA_DIR / slot / "accuracy_metrics.json"
    data = load_json_safe(metrics_path, default={})
    metrics_dict: dict = data.get("metrics", {})

    # 按 workflow_ids 过滤
    if workflow_ids:
        requested_ids = {wid.strip() for wid in workflow_ids.split(",") if wid.strip()}
        metrics_dict = {k: v for k, v in metrics_dict.items() if k in requested_ids}

    return {
        "slot": slot,
        "window_days": window_days,
        "evaluation_window_days": data.get("evaluation_window_days", window_days),
        "updated_at": data.get("updated_at"),
        "metrics": metrics_dict,
    }


@router.get("/{slot}/production", summary="当前生产登记条目")
def get_production(slot: str):
    """
    获取指定槽位当前认定的生产登记条目。

    返回 `workflow_id`（当前生产工作流 ID）、`version_tag`（版本标签）、
    `updated_at`（最后更新时间）、`source_event_id`（来源切换事件 ID）。

    登记条目不存在或已损坏时返回 `{"production": null}`。
    """
    entry = _production_registry.get(slot)
    return {"slot": slot, "production": entry}


# ---------------------------------------------------------------------------
# 切换操作
# ---------------------------------------------------------------------------

@router.post("/{slot}/switch", summary="手动触发切换")
def manual_switch(slot: str, body: ManualSwitchBody):
    """
    手动触发工作流版本切换。

    - **target_workflow_id** — 必填，目标工作流 ID（必须已在注册表中存在）
    - **reason** — 可选，手动切换原因（最多 500 字符）
    - 目标版本不存在 → 400。
    """
    try:
        event = _switch_engine.execute_switch(
            slot=slot,
            target_workflow_id=body.target_workflow_id,
            trigger_type="manual",
            reason=body.reason,
        )
    except ValueError as exc:
        return error_response(
            code="invalid_switch_target",
            message=str(exc),
        )

    return event


@router.post("/{slot}/rollback", summary="回滚最近一次切换")
def rollback(slot: str):
    """
    回滚指定槽位最近一次切换操作。

    - 从切换日志获取最近事件，检查回滚窗口（`rollback_window_hours`）
    - 超出回滚窗口或无切换历史 → 400
    """
    try:
        event = _switch_engine.rollback(slot)
    except ValueError as exc:
        return error_response(
            code="rollback_failed",
            message=str(exc),
        )

    return event


@router.get("/{slot}/switch-log", summary="切换日志分页查询")
def get_switch_log(
    slot: str,
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数，最大 100"),
    trigger_type: Optional[str] = Query(
        default=None,
        description="触发类型过滤（精确匹配）：automatic / manual / rollback",
    ),
    start_time: Optional[str] = Query(
        default=None,
        description="起始时间（ISO 8601 字符串，含），如 2026-06-01T00:00:00+00:00",
    ),
    end_time: Optional[str] = Query(
        default=None,
        description="结束时间（ISO 8601 字符串，含）",
    ),
):
    """
    分页查询切换审计日志（最新在前）。

    支持按 `trigger_type`（触发类型）和时间范围过滤。
    返回 `total`（总条数）、`page`（当前页码）、`page_size`（每页条数）、`events`（事件列表）。
    """
    result = _switch_log.query(
        slot=slot,
        page=page,
        page_size=page_size,
        trigger_type=trigger_type,
        start_time=start_time,
        end_time=end_time,
    )
    return result


# ---------------------------------------------------------------------------
# 配置管理
# ---------------------------------------------------------------------------

@router.get("/{slot}/config", summary="获取槽位配置")
def get_config(slot: str):
    """
    获取指定槽位的精度运营配置。

    返回 `SlotConfig` 的完整字段（含默认值）。
    配置文件不存在时静默返回默认配置，不报错。
    """
    config = _config_manager.load_config(slot)
    return _config_manager.to_dict(config)


@router.put("/{slot}/config", summary="更新槽位配置")
def update_config(slot: str, updates: dict):
    """
    更新指定槽位的精度运营配置（支持部分更新）。

    - Body: 部分或全量 `SlotConfig` 字段（JSON 对象）
    - 任一参数越界（如 `evaluation_window_days` 超出 [1, 30]）→ 400，整体拒绝，存储不变
    - 成功返回更新后的完整配置
    """
    try:
        new_config = _config_manager.update_config(slot, updates)
    except ValueError as exc:
        return error_response(
            code="invalid_config_value",
            message=str(exc),
        )

    return _config_manager.to_dict(new_config)


# ---------------------------------------------------------------------------
# 预上线管理
# ---------------------------------------------------------------------------

class PrelaunchEnqueueBody(BaseModel):
    """预上线入队请求体"""
    candidate_id: str                    # 来源候选 ID（复验通过的候选）
    workflow_id: str                      # 工作流模板 ID
    version_tag: Optional[str] = None    # 版本标签（不传则自动生成）
    source_run_id: Optional[str] = None  # 来源 AutoResearch run ID
    observation_days: int = 7            # 观察天数，默认 7
    graduate_tolerance_pct: float = 5.0  # 毕业容差百分比，默认 5
    note: str = ""                       # 备注


@router.get("/{slot}/prelaunch", summary="获取预上线队列")
def get_prelaunch_queue(
    slot: str,
    status: Optional[str] = Query(
        default=None,
        description="按状态过滤：observing / graduated / failed / cancelled",
    ),
):
    """
    获取指定槽位的预上线队列。

    - 不传 status 返回全部（含历史）
    - 传 status=observing 只返回当前观察中的项
    - 返回列表按 started_at 降序（最新在前）
    """
    queue = _prelaunch_manager.get_queue(slot)
    if status:
        queue = [item for item in queue if item.get("status") == status]
    # 按 started_at 降序
    queue.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return {"slot": slot, "queue": queue, "total": len(queue)}


@router.post("/{slot}/prelaunch", summary="候选入预上线")
def enqueue_prelaunch(slot: str, body: PrelaunchEnqueueBody):
    """
    将复验通过的候选加入预上线队列。

    入队后自动注册到 VersionRegistry 为 shadow 状态，
    开始跟随真实预测运行积累精度数据。

    前置条件：
    - 当前观察中的预上线项 < 2（并发上限）
    - 同一 candidate_id 不可重复入队

    字段说明：
    - `candidate_id`（候选 ID）— 复验通过的候选记录 ID
    - `workflow_id`（工作流 ID）— 要预上线的模板 ID
    - `observation_days`（观察天数）— 默认 7 天
    - `graduate_tolerance_pct`（毕业容差%）— 预上线 MAPE 比生产高不超过此百分比仍可毕业
    """
    version_tag = body.version_tag or f"prelaunch-{body.candidate_id[:12]}"

    # 获取当前生产版本的 baseline_mape
    prod_entry = _production_registry.get(slot)
    baseline_mape = None
    if prod_entry:
        prod_metrics = _accuracy_tracker.get_rolling_metrics(
            slot, prod_entry.get("workflow_id", "")
        )
        if prod_metrics:
            baseline_mape = prod_metrics.get("rolling_mape")

    try:
        item = _prelaunch_manager.enqueue(
            slot=slot,
            candidate_id=body.candidate_id,
            workflow_id=body.workflow_id,
            version_tag=version_tag,
            source_run_id=body.source_run_id,
            observation_days=body.observation_days,
            graduate_tolerance_pct=body.graduate_tolerance_pct,
            baseline_mape_at_entry=baseline_mape,
            note=body.note,
        )
    except ValueError as exc:
        return error_response(
            code="prelaunch_enqueue_failed",
            message=str(exc),
        )

    # 注册到 VersionRegistry 为 shadow
    try:
        _version_registry.register({
            "workflow_id": body.workflow_id,
            "version_tag": version_tag,
            "status": "shadow",
            "slot": slot,
            "source_candidate_id": body.candidate_id,
            "source_run_id": body.source_run_id,
            "baseline_mape": baseline_mape,
        })
    except (ValueError, Exception) as exc:
        # 注册失败不阻塞入队（可能已存在），记录 warning
        logger.warning(
            "prelaunch: VersionRegistry 注册 shadow 失败（非阻塞）: %s", exc
        )

    return {"success": True, "item": item}


@router.post("/{slot}/prelaunch/{prelaunch_id}/graduate", summary="手动毕业（提前上线）")
def graduate_prelaunch(slot: str, prelaunch_id: str):
    """
    手动将预上线项标记为毕业，触发正式上线。

    毕业后自动将该版本从 shadow 切换为 production（通过 SwitchDecisionEngine）。
    原有 production 降级为 shadow。
    """
    try:
        item = _prelaunch_manager.graduate(slot, prelaunch_id, reason="manual")
    except ValueError as exc:
        return error_response(
            code="prelaunch_graduate_failed",
            message=str(exc),
        )

    # 执行正式上线：调用 switch_engine 将该版本切换为 production
    promote_event = None
    try:
        promote_event = _switch_engine.execute_switch(
            slot=slot,
            target_workflow_id=item["workflow_id"],
            trigger_type="manual",
            reason=f"预上线毕业上线: prelaunch_id={prelaunch_id}, candidate={item.get('candidate_id')}",
        )
    except (ValueError, Exception) as exc:
        logger.warning(
            "prelaunch graduate → switch failed: %s (prelaunch status already graduated)", exc
        )

    return {
        "success": True,
        "item": item,
        "switch_event": promote_event,
    }


@router.post("/{slot}/prelaunch/{prelaunch_id}/cancel", summary="取消预上线")
def cancel_prelaunch(slot: str, prelaunch_id: str, reason: str = ""):
    """
    取消预上线观察。

    取消后该版本仍保留在 VersionRegistry 中作为 shadow，
    但不再参与自动毕业评估。用户可后续手动退役或重新入预上线。
    """
    try:
        item = _prelaunch_manager.cancel(slot, prelaunch_id, reason=reason)
    except ValueError as exc:
        return error_response(
            code="prelaunch_cancel_failed",
            message=str(exc),
        )

    return {"success": True, "item": item}


# ---------------------------------------------------------------------------
# 预上线模拟实验（真实 XGBoost 滚动预测，严格无数据穿越）
# ---------------------------------------------------------------------------

class RunSimulationBody(BaseModel):
    """模拟实验请求体"""
    start_date: str = "2026-04-01"       # 观察起始日（假设"今天"）
    observation_days: int = 7            # 观察天数
    train_days: int = 60                 # 每日训练窗口天数
    graduate_tolerance_pct: float = 5.0  # 毕业容差%


@router.post("/{slot}/prelaunch-simulation", summary="运行预上线滚动预测实验")
def run_prelaunch_simulation(slot: str, body: RunSimulationBody):
    """
    用威海负荷真实数据运行滚动预测实验（真实 XGBoost 模型）。

    严格无数据穿越：
      Day T: train(截止 T-1 全部数据) → predict(T 日 96 个点) → 对比 T 日真值

    两个模型：
      - 生产模型: XGBoost 200 棵树 + 基础特征（lag_1/96/672, rolling_mean_96）
      - 预上线候选: XGBoost 500 棵树 + 扩展特征（额外 lag_288/384, 同时刻2周均值, 24h趋势）

    流程：
    1. 重置精度运营状态（生产模型 = production）
    2. 注册预上线候选为 shadow + 创建预上线队列项
    3. 逐天滚动训练+预测（每天完全独立训练）
    4. 写入 accuracy_metrics + 更新预上线队列
    5. 判断毕业条件

    预计运行时间: 2-5 分钟（14 次 XGBoost 训练+预测）。
    """
    from pathlib import Path
    from datetime import timedelta, timezone as tz
    from services.precision_ops.rolling_forecast_experiment import run_rolling_forecast_experiment
    from services.precision_ops.utils import (
        BASE_DATA_DIR, _atomic_write_json, ensure_data_dir, now_iso,
    )

    # --- 定位数据文件 ---
    csv_path = Path(__file__).resolve().parent.parent / "datasets" / "load_true_weihai_260415.csv"
    if not csv_path.exists():
        return error_response("csv_not_found", f"数据文件不存在: {csv_path.name}")

    # --- 运行滚动预测 ---
    try:
        result = run_rolling_forecast_experiment(
            csv_path=str(csv_path),
            start_date=body.start_date,
            observation_days=body.observation_days,
            train_days=body.train_days,
            production_n_estimators=200,
            prelaunch_n_estimators=500,
        )
    except Exception as exc:
        logger.error("prelaunch-simulation failed: %s", exc, exc_info=True)
        return error_response("simulation_failed", f"实验运行失败: {exc}")

    # --- 更新 precision_ops 状态 ---
    ensure_data_dir(slot)

    PROD_WF = "xgboost-200-baseline"
    PROD_TAG = "production-xgb200"
    PRE_WF = "xgboost-500-extended"
    PRE_TAG = "prelaunch-xgb500-ext"
    CAND_ID = "sim-rolling-forecast-001"

    try:
        start_dt_obj = __import__("datetime").datetime.fromisoformat(body.start_date)
    except Exception:
        start_dt_obj = __import__("datetime").datetime(2026, 4, 1)

    # 重写 version_registry
    _atomic_write_json(BASE_DATA_DIR / slot / "version_registry.json", {
        "slot": slot,
        "versions": [
            {
                "workflow_id": PROD_WF,
                "version_tag": PROD_TAG,
                "status": "production",
                "slot": slot,
                "baseline_mape": None,
                "registered_at": (start_dt_obj - timedelta(days=7)).isoformat(),
                "source_run_id": None,
                "source_candidate_id": None,
            },
            {
                "workflow_id": PRE_WF,
                "version_tag": PRE_TAG,
                "status": "shadow",
                "slot": slot,
                "baseline_mape": None,
                "registered_at": start_dt_obj.isoformat(),
                "source_run_id": None,
                "source_candidate_id": CAND_ID,
            },
        ],
        "max_shadow_versions": 5,
    })

    # 写入 accuracy_metrics
    summary = result["summary"]
    eval_end = (start_dt_obj + timedelta(days=body.observation_days)).isoformat()
    _atomic_write_json(BASE_DATA_DIR / slot / "accuracy_metrics.json", {
        "slot": slot,
        "evaluation_window_days": body.observation_days,
        "metrics": {
            PROD_WF: {
                "rolling_mape": summary["production_avg_mape"],
                "rolling_mae": 0,
                "valid_cycle_count": body.observation_days,
                "total_cycle_count": body.observation_days,
                "last_evaluated_at": eval_end,
                "status": "active",
            },
            PRE_WF: {
                "rolling_mape": summary["prelaunch_avg_mape"],
                "rolling_mae": 0,
                "valid_cycle_count": body.observation_days,
                "total_cycle_count": body.observation_days,
                "last_evaluated_at": eval_end,
                "status": "active",
            },
        },
        "updated_at": eval_end,
    })

    # 创建预上线队列项
    _atomic_write_json(BASE_DATA_DIR / slot / "prelaunch_queue.json", [{
        "id": f"prelaunch-sim-{CAND_ID[:8]}",
        "candidate_id": CAND_ID,
        "workflow_id": PRE_WF,
        "version_tag": PRE_TAG,
        "slot": slot,
        "status": "observing",
        "started_at": start_dt_obj.isoformat(),
        "observation_days": body.observation_days,
        "graduate_tolerance_pct": body.graduate_tolerance_pct,
        "source_run_id": None,
        "baseline_mape_at_entry": summary["production_avg_mape"],
        "current_rolling_mape": summary["prelaunch_avg_mape"],
        "production_rolling_mape": summary["production_avg_mape"],
        "evaluated_cycles": body.observation_days,
        "graduated_at": None,
        "failed_at": None,
        "cancelled_at": None,
        "note": (
            f"滚动预测实验: {body.start_date} 起 {body.observation_days} 天, "
            f"每日 train(截止T-1)+predict(T), XGBoost 真实训练"
        ),
    }])

    # 毕业判断
    tolerance = body.graduate_tolerance_pct
    avg_prod = summary["production_avg_mape"] or 0
    avg_pre = summary["prelaunch_avg_mape"] or 0
    threshold = avg_prod * (1 + tolerance / 100)
    graduated = avg_pre <= threshold

    return {
        "success": True,
        "slot": slot,
        "experiment": result["config"],
        "daily_results": result["daily_results"],
        "summary": {
            **summary,
            "threshold": round(threshold, 4),
            "graduate_tolerance_pct": tolerance,
            "graduated": graduated,
            "conclusion": (
                f"预上线通过: MAPE {avg_pre:.4f}% ≤ 阈值 {threshold:.4f}%，推荐正式上线"
                if graduated else
                f"预上线未通过: MAPE {avg_pre:.4f}% > 阈值 {threshold:.4f}%"
            ),
        },
    }



# ---------------------------------------------------------------------------
# 定时预测 Worker 控制 API
# ---------------------------------------------------------------------------

class StartWorkerBody(BaseModel):
    """启动 worker 请求体"""
    start_date: str = "2026-04-01"
    observation_days: int = 7
    train_days: int = 60
    interval_seconds: float = 30.0
    graduate_tolerance_pct: float = 5.0


@router.post("/{slot}/prediction-worker/start", summary="启动每日预测模拟 Worker")
def start_prediction_worker(slot: str, body: StartWorkerBody):
    """
    启动后台定时 Worker，模拟每日滚动预测。

    每隔 interval_seconds 推进一天:
      1. 生产模型 + 预上线模型同时训练+预测
      2. 对比真值计算 MAPE
      3. 更新精度运营指标
      4. 观察期满自动判定毕业/失败

    默认 30s 一天，7 天 ≈ 3.5 分钟跑完。
    前端 60s 自动刷新可看到 MAPE 逐天变化。
    """
    from services.precision_ops.daily_prediction_worker import (
        DailyPredictionWorker, get_worker,
    )

    existing = get_worker()
    if existing and existing.running:
        return {"status": "already_running", **existing.get_status()}

    worker = DailyPredictionWorker(
        slot=slot,
        start_date=body.start_date,
        observation_days=body.observation_days,
        train_days=body.train_days,
        interval_seconds=body.interval_seconds,
        graduate_tolerance_pct=body.graduate_tolerance_pct,
    )
    result = worker.start()
    return result


@router.post("/{slot}/prediction-worker/stop", summary="停止每日预测模拟 Worker")
def stop_prediction_worker(slot: str):
    """停止后台 Worker"""
    from services.precision_ops.daily_prediction_worker import get_worker

    worker = get_worker()
    if worker is None or not worker.running:
        return {"status": "not_running"}
    return worker.stop()


@router.get("/{slot}/prediction-worker/status", summary="获取 Worker 状态")
def get_prediction_worker_status(slot: str):
    """
    获取当前 Worker 运行状态。

    返回: running, current_day, total_days, daily_results, completed 等。
    前端可定时轮询此接口展示进度。
    """
    from services.precision_ops.daily_prediction_worker import get_worker

    worker = get_worker()
    if worker is None:
        return {"running": False, "current_day": 0, "total_days": 0, "completed": False}
    return worker.get_status()
