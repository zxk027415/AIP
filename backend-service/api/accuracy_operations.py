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
# @AI_GENERATED: end
