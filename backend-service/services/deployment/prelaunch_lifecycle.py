# @AI_GENERATED
"""
services/deployment/prelaunch_lifecycle.py — 预上线毕业判定逻辑

职责（Responsibilities）：
  - `check_graduation(prelaunch, production)` — 判断预上线模型是否满足毕业/失败条件
    · 观察期未满  → decision="continue"
    · 观察期满 + MAPE 达标 → decision="graduate"
    · 观察期满 + MAPE 未达标 → decision="fail"
  - `update_prelaunch_accuracy(slot_obj, accuracy_by_workflow_id)` — 把最新精度回填到
    prelaunch_models 里的 prelaunch_meta.current_rolling_mape / production_rolling_mape

对应计划文档：
  `docs/specs/algorithm-deployment-refactor/deployment-cron-prelaunch-plan.md`
  → 阶段 2：Prelaunch 毕业 + Shadow 切换判定接进 backfill cron

关联模块：
  - `services/deployment/models.py` — ModelVersion、PrelaunchMeta
  - `services/deployment/store.py`  — DeploymentSlotStore（promote/fail 操作）
  - `services/scheduler/tasks/load_forecast_tasks.py` — make_accuracy_backfill_task 调用

字段说明（英文 — 中文）：
  - `observation_days`          — 观察期天数（每条 prelaunch 独立）
  - `graduate_tolerance_pct`    — 毕业容差百分比（MAPE 比生产高不超过此值仍可毕业）
  - `evaluated_cycles`          — 已评估天数（每日 backfill 后 +1）
  - `current_rolling_mape`      — 当前预上线滚动 MAPE
  - `production_rolling_mape`   — 当前生产滚动 MAPE（参照基准）
  - `baseline_mape_at_entry`    — 入池时的生产 MAPE 快照（审计用，不参与毕业判定）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.deployment.models import DeploymentSlot, ModelVersion

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GraduationDecision — 毕业判定结果
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GraduationDecision:
    """
    预上线毕业判定结果（不可变数据类）。

    字段说明：
      - decision          — 判定结论：
                            "continue"  — 观察期未满，继续
                            "graduate"  — 观察期满 + MAPE 达标，毕业为 shadow
                            "fail"      — 观察期满 + MAPE 未达标，降级为 retired
      - workflow_id       — 被判定的预上线模型 workflow_id
      - reason            — 人类可读说明
      - threshold_used    — 实际使用的 MAPE 门槛（= production_mape × (1 + tolerance_pct/100)）
      - prelaunch_mape    — 预上线当前 MAPE（可能为 None）
      - production_mape   — 生产当前 MAPE（可能为 None）
      - elapsed_days      — 已观察天数
    """

    decision: str  # "continue" | "graduate" | "fail"
    workflow_id: str
    reason: str
    threshold_used: Optional[float] = None
    prelaunch_mape: Optional[float] = None
    production_mape: Optional[float] = None
    elapsed_days: int = 0


# ---------------------------------------------------------------------------
# 核心判定函数
# ---------------------------------------------------------------------------

def check_graduation(
    prelaunch: ModelVersion,
    production: Optional[ModelVersion],
) -> GraduationDecision:
    """
    判断单个预上线模型是否满足毕业/失败条件。

    毕业条件（AND）：
      a) elapsed_days >= observation_days（观察期满）
      b) current_rolling_mape <= production_mape * (1 + graduate_tolerance_pct / 100)

    失败条件：
      a) elapsed_days >= observation_days（观察期满）
      b) 不满足毕业条件 b）（MAPE 超标）

    特殊情况（保守处理，返回 "continue"）：
      - prelaunch 没有 prelaunch_meta
      - current_rolling_mape 或 production_rolling_mape 为 None（数据尚未积累）
      - production 为 None

    Args:
        prelaunch:  status="prelaunch" 的 ModelVersion（含 prelaunch_meta）
        production: 当前生产模型（可为 None，此时返回 "continue"）

    Returns:
        GraduationDecision
    """
    meta = prelaunch.prelaunch_meta
    if meta is None:
        return GraduationDecision(
            decision="continue",
            workflow_id=prelaunch.workflow_id,
            reason="prelaunch_meta 为空，跳过判定",
        )

    # 计算已观察天数
    try:
        started_dt = datetime.fromisoformat(meta.started_at)
        if started_dt.tzinfo is None:
            started_dt = started_dt.replace(tzinfo=timezone.utc)
        now_dt = datetime.now(tz=timezone.utc)
        elapsed_days = max(0, (now_dt - started_dt).days)
    except (ValueError, TypeError):
        elapsed_days = meta.evaluated_cycles  # 降级：用评估周期数代替

    # 观察期未满 → continue
    if elapsed_days < meta.observation_days:
        return GraduationDecision(
            decision="continue",
            workflow_id=prelaunch.workflow_id,
            reason=(
                f"观察期未满：已 {elapsed_days} 天 / 需 {meta.observation_days} 天"
            ),
            prelaunch_mape=meta.current_rolling_mape,
            production_mape=meta.production_rolling_mape,
            elapsed_days=elapsed_days,
        )

    # 观察期满 —— 检查精度
    pre_mape = meta.current_rolling_mape
    prod_mape = (
        meta.production_rolling_mape
        or (production.accuracy_score if production is not None else None)
    )

    # 数据不足时保守处理（不强制失败）
    if pre_mape is None or prod_mape is None:
        return GraduationDecision(
            decision="continue",
            workflow_id=prelaunch.workflow_id,
            reason=(
                f"观察期满（{elapsed_days} 天）但精度数据不足："
                f"prelaunch_mape={pre_mape}, production_mape={prod_mape}，继续等待"
            ),
            prelaunch_mape=pre_mape,
            production_mape=prod_mape,
            elapsed_days=elapsed_days,
        )

    threshold = prod_mape * (1.0 + meta.graduate_tolerance_pct / 100.0)

    if pre_mape <= threshold:
        return GraduationDecision(
            decision="graduate",
            workflow_id=prelaunch.workflow_id,
            reason=(
                f"观察期满（{elapsed_days} 天），MAPE 达标："
                f"prelaunch={pre_mape:.4f}% ≤ threshold={threshold:.4f}%"
                f"（production={prod_mape:.4f}% × {1 + meta.graduate_tolerance_pct/100:.2f}）"
            ),
            threshold_used=threshold,
            prelaunch_mape=pre_mape,
            production_mape=prod_mape,
            elapsed_days=elapsed_days,
        )
    else:
        return GraduationDecision(
            decision="fail",
            workflow_id=prelaunch.workflow_id,
            reason=(
                f"观察期满（{elapsed_days} 天），MAPE 未达标："
                f"prelaunch={pre_mape:.4f}% > threshold={threshold:.4f}%"
                f"（production={prod_mape:.4f}% × {1 + meta.graduate_tolerance_pct/100:.2f}）"
            ),
            threshold_used=threshold,
            prelaunch_mape=pre_mape,
            production_mape=prod_mape,
            elapsed_days=elapsed_days,
        )


# ---------------------------------------------------------------------------
# 批量判定：遍历 slot 内所有 prelaunch，返回变化列表
# ---------------------------------------------------------------------------

def evaluate_all_prelaunches(
    slot_obj: DeploymentSlot,
    accuracy_by_workflow_id: Optional[Dict[str, float]] = None,
) -> List[GraduationDecision]:
    """
    遍历 slot_obj.prelaunch_models 中所有 status="prelaunch" 的模型，
    对每个执行 check_graduation，返回所有「非 continue」的判定结果。

    如果提供 accuracy_by_workflow_id，会先用最新精度更新 prelaunch_meta.current_rolling_mape
    和 production_rolling_mape（更新是在内存对象上，调用方负责持久化 slot_obj）。

    Args:
        slot_obj:               DeploymentSlot（内存对象）
        accuracy_by_workflow_id: {workflow_id → rolling_mape}（可选）
                                 来自 accuracy_backfill 步骤计算出的最新 MAPE

    Returns:
        判定结果列表（只含 graduate 或 fail 的条目，continue 不返回）
    """
    if accuracy_by_workflow_id:
        _update_prelaunch_accuracy(slot_obj, accuracy_by_workflow_id)

    results: List[GraduationDecision] = []
    active = [m for m in slot_obj.prelaunch_models if m.status == "prelaunch"]

    if not active:
        return results

    prod = slot_obj.production_model

    for model in active:
        decision = check_graduation(model, prod)
        logger.info(
            "prelaunch_lifecycle.check: slot=%s workflow=%s → %s | %s",
            slot_obj.slot, model.workflow_id, decision.decision, decision.reason,
        )
        if decision.decision != "continue":
            results.append(decision)

    return results


# ---------------------------------------------------------------------------
# 精度更新辅助（内存操作）
# ---------------------------------------------------------------------------

def _update_prelaunch_accuracy(
    slot_obj: DeploymentSlot,
    accuracy_by_workflow_id: Dict[str, float],
) -> None:
    """
    用最新精度更新 prelaunch_models 里每条 prelaunch_meta 的精度字段。

    同时同步生产 rolling_mape（production_rolling_mape），保证判定时参照基准最新。

    Args:
        slot_obj:               DeploymentSlot（内存对象，直接修改）
        accuracy_by_workflow_id: {workflow_id → rolling_mape}
    """
    prod_mape: Optional[float] = None
    if slot_obj.production_model is not None:
        prod_wf = slot_obj.production_model.workflow_id
        prod_mape = accuracy_by_workflow_id.get(prod_wf, slot_obj.production_model.accuracy_score)
        # 同步更新生产模型的 accuracy_score
        if prod_mape is not None:
            slot_obj.production_model.accuracy_score = prod_mape

    for model in slot_obj.prelaunch_models:
        if model.status != "prelaunch" or model.prelaunch_meta is None:
            continue
        new_mape = accuracy_by_workflow_id.get(model.workflow_id)
        if new_mape is not None:
            model.prelaunch_meta.current_rolling_mape = new_mape
            model.prelaunch_meta.evaluated_cycles = (
                model.prelaunch_meta.evaluated_cycles + 1
            )
        if prod_mape is not None:
            model.prelaunch_meta.production_rolling_mape = prod_mape
# @AI_GENERATED: end
