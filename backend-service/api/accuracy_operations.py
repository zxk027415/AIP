# @AI_GENERATED
"""
api/accuracy_operations.py — 精度运营 HTTP 路由模块

挂载前缀：/api/accuracy-operations

端点列表：
  GET  /overview                  — 运营总览（生产/影子精度 + 告警/恢复计数）
  GET  /alerts                    — 告警列表（可按 status 过滤）
  POST /alerts/{alert_id}/rca     — 触发或幂等获取 RCA 报告
  GET  /rca/{rca_report_id}       — 获取指定 RCA 报告详情
  POST /recovery/decide           — 仲裁触发（基于 RCA 结论决策恢复通道）
  POST /recovery/shadow-switch    — 执行通道A 影子切换
  GET  /monitoring/snapshot       — 精度监控快照（只读）
  GET  /models/lifecycle          — 四形态模型生命周期视图
  POST /alerts/{alert_id}/close   — 手动关闭告警

依赖注入：使用 lru_cache(maxsize=1) 延迟初始化所有组件（单例）。
错误处理：ValueError → 400，FileNotFoundError/None → 404，TimeoutExpired → 504。
"""
from __future__ import annotations

import logging
import subprocess
from functools import lru_cache
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 服务层延迟导入
# ---------------------------------------------------------------------------
from services.accuracy_operations.store import AccuracyOperationsStore
from services.accuracy_operations.monitor import AccuracyMonitor
from services.accuracy_operations.rca_orchestrator import RCAOrchestrator
from services.accuracy_operations.arbitrator import RecoveryArbitrator
from services.accuracy_operations.rca_skill_client import RCASkillClient
from services.precision_ops.accuracy_tracker import AccuracyTracker
from services.precision_ops.version_registry import VersionRegistry
from services.precision_ops.config_manager import ConfigManager
from services.deployment import DeploymentSlotStore, SwitchDecisionEngine, SwitchEventLog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 懒加载单例工厂（lru_cache 保证进程内唯一实例）
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_store() -> AccuracyOperationsStore:
    """返回 AccuracyOperationsStore 单例。"""
    return AccuracyOperationsStore()


@lru_cache(maxsize=1)
def _get_components() -> Dict[str, Any]:
    """
    返回精度运营核心组件字典（进程内单例）。

    包含：
      store        — AccuracyOperationsStore 持久化实例
      monitor      — AccuracyMonitor 精度退化监控
      rca_orchestrator — RCAOrchestrator 根因分析编排
      arbitrator   — RecoveryArbitrator 恢复仲裁器
    """
    store = _get_store()
    tracker = AccuracyTracker()
    vr = VersionRegistry()  # 仅供旧槽位只读兼容；部署槽位是发布真源
    cm = ConfigManager()
    skill_client = RCASkillClient()
    slot_store = DeploymentSlotStore()
    deployment_switch_engine = SwitchDecisionEngine(
        slot_store=slot_store,
        event_log=SwitchEventLog(),
    )

    monitor = AccuracyMonitor(
        tracker, vr, cm, store, deployment_slot_store=slot_store
    )
    rca_orch = RCAOrchestrator(skill_client, store)
    arbitrator = RecoveryArbitrator(
        vr, tracker, cm, deployment_switch_engine, store,
        deployment_slot_store=slot_store,
    )

    return {
        "store": store,
        "monitor": monitor,
        "rca_orchestrator": rca_orch,
        "arbitrator": arbitrator,
        "slot_store": slot_store,
        "tracker": tracker,
    }


# ---------------------------------------------------------------------------
# APIRouter
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/accuracy-operations", tags=["accuracy-operations"])


# ---------------------------------------------------------------------------
# 请求体模型
# ---------------------------------------------------------------------------


class TriggerRCARequest(BaseModel):
    """POST /alerts/{alert_id}/rca 请求体"""
    trigger_type: str  # "alert" | "scheduled" | "manual"


class RecoveryDecideRequest(BaseModel):
    """POST /recovery/decide 请求体"""
    slot: str            # 槽位名称
    rca_report_id: str   # RCA 报告 ID — 格式 rca-{8hex}


class ShadowSwitchRequest(BaseModel):
    """POST /recovery/shadow-switch 请求体"""
    slot: str               # 槽位名称
    shadow_workflow_id: str  # 目标影子 workflow_id
    decision_id: str         # 关联恢复决策 ID — 格式 rec-{8hex}


class CloseAlertRequest(BaseModel):
    """POST /alerts/{alert_id}/close 请求体"""
    slot: str                          # 槽位名称
    recovery_evidence: Dict[str, Any]  # 恢复证据，必须含 type="manual_close"


class InjectDegradationRequest(BaseModel):
    """POST /experiments/inject-degradation — 默认数据层劣化，可选 metric_rewrite"""
    slot: str = "load_forecast"
    target_degradation_pct: float = 20.0
    model_form: str = "production"  # production | shadow
    workflow_id: Optional[str] = None
    version_tag: Optional[str] = None
    note: str = ""
    run_monitor: bool = True
    # noise|missing|zero_spike|metric_rewrite；默认 noise（改 StationData）
    mode: str = "noise"
    days: int = 5
    fraction: float = 0.6
    noise_pct: float = 45.0
    station_id: Optional[str] = None
    feature_name: Optional[str] = None
    rerun_pipeline: bool = True


class RestoreDegradationRequest(BaseModel):
    """POST /experiments/restore-degradation — 按快照恢复指标/StationData

    rerun_pipeline — 是否在还原 StationData 后同步跑 gap-1 日滚 + 精度回填。
    默认 False：仅还原数据与指标，接口快速返回；日滚可单独通过
    POST /experiments/retrigger-pipeline 触发，避免超时卡住。
    """
    slot: str = "load_forecast"
    close_open_alerts: bool = True
    # @AI_GENERATED: 默认 False，避免日滚同步执行导致接口超时卡住
    rerun_pipeline: bool = False
    # @AI_GENERATED: end


class ActivateMetricsRequest(BaseModel):
    """POST /experiments/activate-metrics — 把部署版本指标写成 active（演示前置）"""
    slot: str = "load_forecast"
    min_valid_cycles: int = 3


# ---------------------------------------------------------------------------
# 端点实现
# ---------------------------------------------------------------------------


@router.get("/overview")
def get_overview(slot: str = Query(..., description="槽位名称 — 分区键，如 default")) -> Dict[str, Any]:
    """
    GET /overview — 精度运营总览

    返回：
      slot                  — 查询的槽位名称
      production            — 生产版本精度快照（含 rolling_mape/mae/status 等）
      shadows               — 影子版本精度快照列表
      open_alert_count      — 当前 open 状态告警数量
      active_recovery_count — 当前活跃恢复决策数量（pending/executing）
    """
    try:
        comps = _get_components()
        store: AccuracyOperationsStore = comps["store"]
        monitor: AccuracyMonitor = comps["monitor"]

        # 精度快照
        snapshot = monitor.get_monitoring_snapshot(slot)

        # open 告警计数
        open_alerts = store.list_alerts(slot, status="open")
        open_alert_count = len(open_alerts)

        # 活跃恢复计数（pending/executing 的 recovery 决策）
        active_recovery_count = _count_active_recoveries(store, slot)

        return {
            "slot": slot,
            "production": snapshot.get("production"),
            "shadows": snapshot.get("shadows", []),
            "open_alert_count": open_alert_count,
            "active_recovery_count": active_recovery_count,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.exception("GET /overview 异常 slot=%s", slot)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
def list_alerts(
    slot: str = Query(..., description="槽位名称 — 分区键"),
    status: Optional[str] = Query(None, description="告警状态过滤 — open/rca_running/recovering/observing/closed"),
) -> Dict[str, Any]:
    """
    GET /alerts — 告警列表

    返回：
      alerts  — AccuracyAlert 列表（每项含告警完整字段）
      total   — 返回条数
    """
    try:
        store: AccuracyOperationsStore = _get_components()["store"]
        alerts = store.list_alerts(slot, status=status, limit=200)
        return {
            "alerts": [a.dict() for a in alerts],
            "total": len(alerts),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.exception("GET /alerts 异常 slot=%s status=%s", slot, status)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/rca")
def trigger_rca(alert_id: str, body: TriggerRCARequest) -> Dict[str, Any]:
    """
    POST /alerts/{alert_id}/rca — 触发 RCA 分析

    流程：
      1. 从 store 加载 alert（404 若不存在）
      2. 校验 alert.model_form ∈ {production, shadow}（400 否则）
      3. 调用 rca_orchestrator.trigger() 执行 RCA
      4. 超时 → 504；其他异常 → 500

    请求体字段：
      trigger_type — 触发方式（alert/scheduled/manual）

    返回：RCAReport 完整 dict（含 error_profile/data_quality_diagnosis/actionable_insights）
    """
    comps = _get_components()
    store: AccuracyOperationsStore = comps["store"]
    rca_orch: RCAOrchestrator = comps["rca_orchestrator"]

    # 加载告警（需要先从 slot 参数获取，但 alert_id 路由未携带 slot）
    # 通过扫描所有已知 slot 找到该 alert，或直接从 alert 内容获取 slot
    alert = _find_alert_any_slot(store, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"告警不存在: alert_id={alert_id}")

    # 校验 model_form
    model_form_val = alert.model_form if isinstance(alert.model_form, str) else alert.model_form.value
    if model_form_val not in ("production", "shadow"):
        raise HTTPException(
            status_code=400,
            detail=f"model_form 必须为 production 或 shadow，当前值: {model_form_val!r}",
        )

    slot = alert.slot

    try:
        rca = rca_orch.trigger(slot, alert, trigger_type=body.trigger_type)
        return rca.dict()
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail=f"RCA 执行超时: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("POST /alerts/%s/rca 异常", alert_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rca/{rca_report_id}")
def get_rca_report(
    rca_report_id: str,
    slot: str = Query(..., description="槽位名称 — RCA 文件按 slot 分区存储"),
) -> Dict[str, Any]:
    """
    GET /rca/{rca_report_id} — 获取 RCA 报告详情

    注意：slot 为必填 query param，因为 RCA 文件按槽位分区。

    返回：RCAReport 完整 dict（含 error_profile/data_quality_diagnosis/actionable_insights）
    """
    try:
        store: AccuracyOperationsStore = _get_components()["store"]
        rca = store.get_rca(slot, rca_report_id)
        if rca is None:
            raise HTTPException(status_code=404, detail=f"RCA 报告不存在: rca_report_id={rca_report_id}")
        return rca.dict()
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.exception("GET /rca/%s 异常 slot=%s", rca_report_id, slot)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recovery/decide")
def recovery_decide(body: RecoveryDecideRequest) -> Dict[str, Any]:
    """
    POST /recovery/decide — 仲裁触发

    流程：
      1. 从 store 加载 RCA 报告（404 若不存在）
      2. 校验 rca.status == succeeded（400 否则）
      3. 调用 arbitrator.decide(slot, rca_report_id)

    请求体字段：
      slot          — 槽位名称
      rca_report_id — RCA 报告 ID — 格式 rca-{8hex}

    返回：RecoveryDecision 完整 dict
    """
    comps = _get_components()
    store: AccuracyOperationsStore = comps["store"]
    arbitrator: RecoveryArbitrator = comps["arbitrator"]

    rca = store.get_rca(body.slot, body.rca_report_id)
    if rca is None:
        raise HTTPException(
            status_code=404,
            detail=f"RCA 报告不存在: slot={body.slot}, rca_report_id={body.rca_report_id}",
        )

    rca_status = rca.status if isinstance(rca.status, str) else rca.status.value
    if rca_status != "succeeded":
        raise HTTPException(
            status_code=400,
            detail=f"RCA 报告状态不为 succeeded（当前={rca_status!r}），无法触发仲裁",
        )

    try:
        decision = arbitrator.decide(body.slot, body.rca_report_id)
        return decision.dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.exception("POST /recovery/decide 异常 slot=%s rca=%s", body.slot, body.rca_report_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recovery/shadow-switch")
def recovery_shadow_switch(body: ShadowSwitchRequest) -> Dict[str, Any]:
    """
    POST /recovery/shadow-switch — 手动执行通道A 影子切换

    流程：
      1. 从 store 加载 RecoveryDecision（404 若不存在）
      2. 从 store 加载关联 AccuracyAlert（404 若不存在）
      3. 调用 arbitrator.execute_switch(slot, decision, alert)

    请求体字段：
      slot               — 槽位名称
      shadow_workflow_id — 目标影子版本 workflow_id（供参考，实际目标由 arbitrator 重定位）
      decision_id        — 关联恢复决策 ID — 格式 rec-{8hex}

    返回：更新后的 RecoveryDecision dict
    """
    comps = _get_components()
    store: AccuracyOperationsStore = comps["store"]
    arbitrator: RecoveryArbitrator = comps["arbitrator"]

    decision = store.get_decision(body.slot, body.decision_id)
    if decision is None:
        raise HTTPException(
            status_code=404,
            detail=f"恢复决策不存在: slot={body.slot}, decision_id={body.decision_id}",
        )

    alert = store.get_alert(body.slot, decision.alert_id)
    if alert is None:
        raise HTTPException(
            status_code=404,
            detail=f"关联告警不存在: slot={body.slot}, alert_id={decision.alert_id}",
        )

    try:
        updated_decision = arbitrator.execute_switch(body.slot, decision, alert)
        return updated_decision.dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.exception(
            "POST /recovery/shadow-switch 异常 slot=%s decision_id=%s",
            body.slot,
            body.decision_id,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recovery/decisions/{decision_id}")
def get_recovery_decision(
    decision_id: str,
    slot: str = Query(..., description="槽位名称 — RecoveryDecision 文件按 slot 分区存储"),
) -> Dict[str, Any]:
    """获取一条已持久化的恢复决策，供 UI 回显通道 A/观察状态。"""
    try:
        store: AccuracyOperationsStore = _get_components()["store"]
        decision = store.get_decision(slot, decision_id)
        if decision is None:
            raise HTTPException(
                status_code=404,
                detail=f"恢复决策不存在: slot={slot}, decision_id={decision_id}",
            )
        return decision.dict()
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.exception(
            "GET /recovery/decisions/%s 异常 slot=%s", decision_id, slot
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitoring/snapshot")
def get_monitoring_snapshot(
    slot: str = Query(..., description="槽位名称 — 分区键"),
) -> Dict[str, Any]:
    """
    GET /monitoring/snapshot — 精度监控快照（只读）

    返回 AccuracyMonitor.get_monitoring_snapshot(slot) 的完整结果：
      production        — 生产版本精度指标 dict | None
      shadows           — 影子版本精度指标列表
      prelaunches       — prelaunch 版本精度指标列表
      autoresearch_score — 暂不实现，返回 None
    """
    try:
        monitor: AccuracyMonitor = _get_components()["monitor"]
        return monitor.get_monitoring_snapshot(slot)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.exception("GET /monitoring/snapshot 异常 slot=%s", slot)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/lifecycle")
def get_models_lifecycle(
    slot: str = Query(..., description="槽位名称 — 分区键"),
) -> Dict[str, Any]:
    """
    GET /models/lifecycle — 四形态模型生命周期视图

    返回：
      nodes — 所有版本节点列表（production/shadow/retired），每项含：
                workflow_id  — 工作流模板 ID
                version_tag  — 版本标签
                model_form   — 形态（production/shadow/retired）
                status       — 版本状态字符串
      edges — 生命周期有向边列表（当前返回 []，历史追踪能力待实现）
    """
    try:
        comps = _get_components()
        slot_obj = comps["slot_store"].get(slot)
        if slot_obj is None:
            return {"nodes": [], "edges": []}
        all_versions: List[Dict[str, Any]] = []
        if slot_obj.production_model is not None:
            all_versions.append({**slot_obj.production_model.model_dump(), "role": "production"})
        all_versions.extend({**model.model_dump(), "role": model.status} for model in slot_obj.shadow_models)
        all_versions.extend({**model.model_dump(), "role": model.status} for model in slot_obj.prelaunch_models)

        nodes: List[Dict[str, Any]] = []
        for v in all_versions:
            raw_status = v.get("status", "")
            # 映射 version_registry status → model_form 展示字段
            if raw_status == "production":
                model_form = "production"
            elif raw_status == "shadow":
                model_form = "shadow"
            else:
                model_form = "retired"

            nodes.append({
                "workflow_id": v.get("workflow_id", ""),
                "version_tag": v.get("version_tag", ""),
                "model_form": model_form,
                "status": raw_status,
            })

        # edges 需要历史追踪能力，当前版本返回空列表
        return {"nodes": nodes, "edges": []}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.exception("GET /models/lifecycle 异常 slot=%s", slot)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/close")
def close_alert(alert_id: str, body: CloseAlertRequest) -> Dict[str, Any]:
    """
    POST /alerts/{alert_id}/close — 手动关闭告警

    流程：
      调用 store.transition_alert_status(slot, alert_id, "closed", recovery_evidence)

    请求体字段：
      slot               — 槽位名称
      recovery_evidence  — 恢复证据 dict，格式：
                           { "type": "manual_close", "ref": str, "at": str }

    返回：更新后的 AccuracyAlert dict
    """
    try:
        store: AccuracyOperationsStore = _get_components()["store"]
        updated_alert = store.transition_alert_status(
            body.slot,
            alert_id,
            "closed",
            recovery_evidence=body.recovery_evidence,
        )
        return updated_alert.dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.exception("POST /alerts/%s/close 异常 slot=%s", alert_id, body.slot)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _count_active_recoveries(store: AccuracyOperationsStore, slot: str) -> int:
    """
    统计 slot 下 status ∈ {pending, executing} 的 RecoveryDecision 数量。

    用于 /overview 端点中的 active_recovery_count 字段。
    若 recovery 目录不存在，返回 0。

    :param store: AccuracyOperationsStore 实例
    :param slot: 槽位名称
    :return: 活跃恢复决策数量
    """
    from services.accuracy_operations.store import _accuracy_ops_dir
    from services.precision_ops.utils import load_json_safe
    from services.accuracy_operations.models import RecoveryDecision

    active_statuses = {"pending", "executing"}
    recovery_dir = _accuracy_ops_dir(slot) / "recovery"
    if not recovery_dir.exists():
        return 0

    count = 0
    for json_file in recovery_dir.glob("*.json"):
        data = load_json_safe(json_file)
        if data is None:
            continue
        try:
            decision = RecoveryDecision.parse_obj(data)
            decision_status = (
                decision.status if isinstance(decision.status, str)
                else decision.status.value
            )
            if decision_status in active_statuses:
                count += 1
        except Exception:
            continue
    return count


def _find_alert_any_slot(
    store: AccuracyOperationsStore,
    alert_id: str,
) -> Optional[Any]:
    """
    在所有已知 slot 目录下查找 alert_id 对应的 AccuracyAlert。

    由于 POST /alerts/{alert_id}/rca 路由未携带 slot 参数，
    需要通过扫描目录找到该告警所在的槽位。

    :param store: AccuracyOperationsStore 实例
    :param alert_id: 告警 ID — 格式 alert-{8hex}
    :return: AccuracyAlert，未找到返回 None
    """
    from services.precision_ops.utils import BASE_DATA_DIR
    from pathlib import Path

    base = BASE_DATA_DIR
    if not base.exists():
        return None

    for slot_dir in base.iterdir():
        if not slot_dir.is_dir():
            continue
        slot = slot_dir.name
        # 仅扫描 accuracy_ops/alerts/ 子目录存在的 slot
        alerts_dir = slot_dir / "accuracy_ops" / "alerts"
        if not alerts_dir.exists():
            continue
        alert = store.get_alert(slot, alert_id)
        if alert is not None:
            return alert

    return None


# @AI_GENERATED: 槽位运营总览端点 — pv_fault 使用分类精度，load_forecast 复用现有 MAPE
@router.get("/slot-overview")
def get_slot_overview(
    slot: str = Query(..., description="槽位名称 — pv_fault 返回分类精度，load_forecast 返回 MAPE 总览"),
) -> Dict[str, Any]:
    """
    GET /slot-overview — 按槽位聚合运营总览

    pv_fault: 分类精度、标签分布、置信度、审核进度、模型溯源。
    load_forecast/default: 在现有 overview 基础上增加 domain 字段。
    """
    try:
        if slot == "pv_fault":
            from services.iterative_labeling.pv_training_workspace import PVTrainingWorkspaceService
            workspace = PVTrainingWorkspaceService()
            return workspace.build_slot_overview("pv_fault")
        else:
            # 复用现有 overview 逻辑
            comps = _get_components()
            store_inst: AccuracyOperationsStore = comps["store"]
            monitor_inst: AccuracyMonitor = comps["monitor"]
            snapshot = monitor_inst.get_monitoring_snapshot(slot)
            open_alerts = store_inst.list_alerts(slot, status="open")
            return {
                "domain": "load_forecast" if "load" in slot else slot,
                "production": snapshot.get("production"),
                "shadows": snapshot.get("shadows", []),
                "open_alert_count": len(open_alerts),
                "active_recovery_count": _count_active_recoveries(store_inst, slot),
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("GET /slot-overview 异常 slot=%s", slot)
        raise HTTPException(status_code=500, detail=str(e))
# @AI_GENERATED: end


# @AI_GENERATED: 劣化实验 + 预测曲线
@router.get("/experiments/degradation-status")
def get_degradation_experiment_status(
    slot: str = Query("load_forecast", description="槽位名称"),
) -> Dict[str, Any]:
    """查询是否处于人工注入劣化态，以及生产版本当前劣化%。"""
    try:
        from services.accuracy_operations.degradation_experiment import get_degradation_status
        comps = _get_components()
        return get_degradation_status(slot, comps["tracker"], comps["slot_store"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("GET /experiments/degradation-status 异常 slot=%s", slot)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/experiments/inject-degradation")
def post_inject_degradation(body: InjectDegradationRequest) -> Dict[str, Any]:
    """默认改 StationData（noise/missing/zero_spike），再回填指标并走真实监控。"""
    try:
        from services.accuracy_operations.degradation_experiment import inject_degradation
        comps = _get_components()
        kwargs = {
            "slot": body.slot,
            "tracker": comps["tracker"],
            "monitor": comps["monitor"],
            "slot_store": comps["slot_store"],
            "target_degradation_pct": body.target_degradation_pct,
            "model_form": body.model_form,
            "workflow_id": body.workflow_id,
            "version_tag": body.version_tag,
            "note": body.note,
            "run_monitor": body.run_monitor,
            "mode": body.mode,
            "days": body.days,
            "fraction": body.fraction,
            "noise_pct": body.noise_pct,
            "rerun_pipeline": body.rerun_pipeline,
        }
        if body.station_id:
            kwargs["station_id"] = body.station_id
        if body.feature_name:
            kwargs["feature_name"] = body.feature_name
        return inject_degradation(**kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("POST /experiments/inject-degradation 异常")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/experiments/restore-degradation")
def post_restore_degradation(body: RestoreDegradationRequest) -> Dict[str, Any]:
    """按快照恢复 StationData / 滚动指标，可选关闭实验相关 open 告警。

    默认 rerun_pipeline=False：仅还原数据，接口立即返回；
    若需要用还原后数据重训，请单独调用 POST /experiments/retrigger-pipeline。
    """
    try:
        from services.accuracy_operations.degradation_experiment import restore_degradation
        comps = _get_components()
        return restore_degradation(
            slot=body.slot,
            tracker=comps["tracker"],
            store=comps["store"],
            close_open_alerts=body.close_open_alerts,
            slot_store=comps.get("slot_store"),
            rerun_pipeline=body.rerun_pipeline,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("POST /experiments/restore-degradation 异常")
        raise HTTPException(status_code=500, detail=str(e))


# @AI_GENERATED: 实验 pipeline 单独触发接口（从 restore 解耦，避免超时）
class ReriggerPipelineRequest(BaseModel):
    """POST /experiments/retrigger-pipeline — 对当前 slot 手动触发 gap-1 日滚 + 精度回填

    用途：在 restore-degradation（rerun_pipeline=False）完成后，
    按需触发重训，刷新指标与曲线。前端可在用户主动点击时调用，
    不阻塞恢复操作本身。
    station_id / feature_name — 可选，缺省自动从库中取最高水位站点。
    """
    slot: str = "load_forecast"
    station_id: Optional[str] = None
    feature_name: Optional[str] = None


@router.post("/experiments/retrigger-pipeline")
def post_retrigger_pipeline(body: ReriggerPipelineRequest) -> Dict[str, Any]:
    """手动触发 gap-1 日滚 + 精度回填，刷新恢复后的指标与曲线。

    通常在 restore-degradation（rerun_pipeline=False）完成后调用。
    该接口同步执行，可能需要数分钟；前端建议按钮配合 loading 状态使用。
    """
    try:
        from services.accuracy_operations.degradation_experiment import (
            _resolve_station_feature,
            _run_load_forecast_pipeline_after_data_change,
        )
        comps = _get_components()
        station_id = body.station_id or None
        feature_name = body.feature_name or None
        # 自动解析站点（若未指定）
        resolved_station, resolved_feature = _resolve_station_feature(
            body.slot, station_id, feature_name
        )
        result = _run_load_forecast_pipeline_after_data_change(
            slot=body.slot,
            station_id=resolved_station,
            feature_name=resolved_feature,
            slot_store=comps.get("slot_store"),
        )
        return {
            "slot": body.slot,
            "station_id": resolved_station,
            "feature_name": resolved_feature,
            "pipeline": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("POST /experiments/retrigger-pipeline 异常")
        raise HTTPException(status_code=500, detail=str(e))
# @AI_GENERATED: end


@router.post("/experiments/activate-metrics")
def post_activate_metrics(body: ActivateMetricsRequest) -> Dict[str, Any]:
    """把 slots.json 中 production/shadow 指标写成 active（演示前置，不伪造预测点）。"""
    try:
        from services.accuracy_operations.degradation_experiment import activate_slot_metrics_from_deployment
        comps = _get_components()
        return activate_slot_metrics_from_deployment(
            slot=body.slot,
            tracker=comps["tracker"],
            slot_store=comps["slot_store"],
            min_valid_cycles=body.min_valid_cycles,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("POST /experiments/activate-metrics 异常")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prediction-series")
def get_prediction_series(
    slot: str = Query("load_forecast", description="槽位名称"),
    workflow_id: Optional[str] = Query(None, description="工作流 ID；缺省取 production"),
    version_tag: Optional[str] = Query(None, description="版本标签；缺省取 production"),
    days: int = Query(1, ge=1, le=90, description="回溯天数；未指定 business_day 时使用，默认 1 天≈96 点"),
    business_day: Optional[str] = Query(
        None,
        description="业务日 YYYY-MM-DD；指定后只返回该自然日的点（优先于 days 窗口）",
    ),
) -> Dict[str, Any]:
    """返回 pred/actual 时序点，供精度运营曲线图使用。

    默认按单日展示（约 96 个 15 分钟点）。可传 business_day 翻看历史日；
    available_days 列出该版本已有预测的业务日，供前端翻页。
    时间窗锚定该版本预测水位（forecast_timestamp），不用墙钟 now()。
    """
    from datetime import datetime, timedelta

    # 直接当 Python 函数调用时，Query() 默认值会漏进来；只接受真正的 str/int。
    if not isinstance(workflow_id, str):
        workflow_id = None
    if not isinstance(version_tag, str):
        version_tag = None
    if not isinstance(business_day, str):
        business_day = None
    if isinstance(business_day, str):
        business_day = business_day.strip() or None
    if not isinstance(days, int):
        try:
            days = int(days)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            days = 1
    if not isinstance(slot, str):
        slot = "load_forecast"

    day_start: Optional[datetime] = None
    if business_day:
        try:
            day_start = datetime.strptime(business_day[:10], "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"business_day 格式须为 YYYY-MM-DD，收到: {business_day!r}",
            ) from exc

    try:
        comps = _get_components()
        slot_store = comps["slot_store"]
        slot_obj = slot_store.get(slot)
        if slot_obj is None:
            raise HTTPException(status_code=404, detail=f"槽位不存在: {slot}")

        wf_id = workflow_id
        v_tag = version_tag
        if not wf_id or not v_tag:
            if slot_obj.production_model is None:
                raise HTTPException(status_code=400, detail="未指定版本且槽位无 production")
            wf_id = wf_id or slot_obj.production_model.workflow_id
            v_tag = v_tag or slot_obj.production_model.version_tag

        points: List[Dict[str, Any]] = []
        window_end: Optional[datetime] = None
        window_start: Optional[datetime] = None
        resolved_version = v_tag
        fallback_used = False
        available_days: List[str] = []
        resolved_business_day: Optional[str] = business_day

        try:
            from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled
            from sqlalchemy import func
            from services.db.models.load_forecast import PredictionResult

            if _is_db_enabled():
                repo = _get_lf_repo()
                if repo is not None:
                    with repo._adapter.get_sync_session() as session:
                        # 水位排除 failed（墙钟脏点会把业务日 2025 预测裁空）
                        def _max_ts(version: Optional[str], statuses: Optional[tuple] = None):
                            q = session.query(func.max(PredictionResult.forecast_timestamp)).filter(
                                PredictionResult.slot == slot,
                                PredictionResult.workflow_id == wf_id,
                            )
                            if version:
                                q = q.filter(PredictionResult.version_tag == version)
                            if statuses:
                                q = q.filter(PredictionResult.status.in_(list(statuses)))
                            return q.scalar()

                        pred_end = _max_ts(v_tag, ("evaluated", "predicted", "pending"))
                        if pred_end is None:
                            pred_end = _max_ts(v_tag, None)
                        if pred_end is None:
                            pred_end = _max_ts(None, ("evaluated", "predicted", "pending"))
                            if pred_end is not None:
                                fallback_used = True
                        if pred_end is None:
                            pred_end = _max_ts(None, None)
                            if pred_end is not None:
                                fallback_used = True
                        if pred_end is None:
                            return {
                                "slot": slot,
                                "workflow_id": wf_id,
                                "version_tag": v_tag,
                                "days": days,
                                "business_day": business_day,
                                "available_days": [],
                                "point_count": 0,
                                "points": [],
                                "window_anchor": "empty",
                            }
                        window_end = pred_end
                        if getattr(window_end, "tzinfo", None) is not None:
                            window_end = window_end.replace(tzinfo=None)

                        # 先解析版本（可能 fallback），再算 available_days / 单日窗
                        version_for_days = None if fallback_used else v_tag
                        day_rows = (
                            session.query(PredictionResult.forecast_timestamp)
                            .filter(
                                PredictionResult.slot == slot,
                                PredictionResult.workflow_id == wf_id,
                                PredictionResult.status != "failed",
                            )
                        )
                        if version_for_days:
                            day_rows = day_rows.filter(
                                PredictionResult.version_tag == version_for_days
                            )
                        day_ts_list = [r[0] for r in day_rows.all() if r[0] is not None]
                        day_set = set()
                        for ts in day_ts_list:
                            ts_naive = ts.replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts
                            day_set.add(ts_naive.strftime("%Y-%m-%d"))
                        available_days = sorted(day_set)

                        if day_start is not None:
                            window_start = day_start
                            window_end = day_start + timedelta(days=1) - timedelta(seconds=1)
                            resolved_business_day = day_start.strftime("%Y-%m-%d")
                        else:
                            # 默认单日：取水位所在业务日（不是 days 天跨度）
                            if days <= 1 and available_days:
                                resolved_business_day = available_days[-1]
                                window_start = datetime.strptime(resolved_business_day, "%Y-%m-%d")
                                window_end = window_start + timedelta(days=1) - timedelta(seconds=1)
                            else:
                                window_start = window_end - timedelta(days=days)
                                resolved_business_day = (
                                    window_end.strftime("%Y-%m-%d") if window_end else None
                                )

                        q = session.query(PredictionResult).filter(
                            PredictionResult.slot == slot,
                            PredictionResult.workflow_id == wf_id,
                            PredictionResult.forecast_timestamp >= window_start,
                            PredictionResult.forecast_timestamp <= window_end,
                            PredictionResult.status != "failed",
                        )
                        if not fallback_used:
                            q = q.filter(PredictionResult.version_tag == v_tag)
                        rows = q.order_by(PredictionResult.forecast_timestamp.asc()).all()

                        if not rows:
                            fallback_used = True
                            all_rows = (
                                session.query(PredictionResult)
                                .filter(
                                    PredictionResult.slot == slot,
                                    PredictionResult.workflow_id == wf_id,
                                    PredictionResult.forecast_timestamp >= window_start,
                                    PredictionResult.forecast_timestamp <= window_end,
                                    PredictionResult.status != "failed",
                                )
                                .order_by(PredictionResult.forecast_timestamp.asc())
                                .all()
                            )
                            counts: Dict[str, int] = {}
                            for r in all_rows:
                                counts[r.version_tag] = counts.get(r.version_tag, 0) + 1
                            if counts:
                                resolved_version = max(counts.items(), key=lambda kv: kv[1])[0]
                                rows = [r for r in all_rows if r.version_tag == resolved_version]
                            else:
                                rows = []
                        else:
                            resolved_version = rows[0].version_tag if rows else v_tag

                        session.expunge_all()
                    for row in rows:
                        points.append({
                            "timestamp": row.forecast_timestamp.isoformat() if row.forecast_timestamp else None,
                            "predicted": float(row.predicted_value) if row.predicted_value is not None else None,
                            "actual": float(row.actual_value) if row.actual_value is not None else None,
                            "prediction_cycle_id": row.prediction_cycle_id,
                            "status": row.status,
                        })
        except Exception as db_exc:
            logger.warning("prediction-series DB 查询失败 slot=%s: %s", slot, db_exc)

        return {
            "slot": slot,
            "workflow_id": wf_id,
            "version_tag": resolved_version,
            "requested_version_tag": v_tag,
            "version_fallback": fallback_used and resolved_version != v_tag,
            "days": days,
            "business_day": resolved_business_day,
            "available_days": available_days,
            "point_count": len(points),
            "points": points,
            "window_start": window_start.isoformat() if window_start else None,
            "window_end": window_end.isoformat() if window_end else None,
            "window_anchor": "business_day" if (business_day or days <= 1) else "prediction_watermark",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("GET /prediction-series 异常 slot=%s", slot)
        raise HTTPException(status_code=500, detail=str(e))
# @AI_GENERATED: end
