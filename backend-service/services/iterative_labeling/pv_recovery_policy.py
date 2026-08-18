# @AI_GENERATED
# -*- coding: utf-8 -*-
"""PV 模型退化恢复优先级纯决策器。

该模块只返回下一步动作，不执行 Registry 晋升或跨路径切换。存在合格同路径 Challenger 时必须
先换将；只有整条路径不可用且无同路径替代时，才允许进入 CrossPathSwitchGate 九项预检。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class PathHealth:
    """当前生产路径健康信号。"""

    champion_loadable: bool = True
    production_contract_valid: bool = True
    no_coverage_cycles: int = 0
    consecutive_failed_cycles: int = 0


@dataclass(frozen=True)
class RecoveryDecision:
    """退化恢复决策，不包含任何写副作用。"""

    action: str
    reason: str
    challenger_evaluation_id: Optional[str] = None
    fallback_gate_required: bool = False
    whole_path_unavailable: bool = False


class PVRecoveryPolicy:
    """实现“同路径换将优先，整路径不可用才评估 fallback”的固定顺序。"""

    def __init__(
        self,
        *,
        no_coverage_failure_cycles: int = 24,
        path_failed_cycles: int = 3,
    ) -> None:
        if no_coverage_failure_cycles < 1 or path_failed_cycles < 1:
            raise ValueError("退化周期阈值必须大于 0")
        self._no_coverage_limit = int(no_coverage_failure_cycles)
        self._failed_limit = int(path_failed_cycles)

    def decide(
        self,
        health: PathHealth,
        *,
        qualified_challenger_evaluation_ids: Optional[List[str]] = None,
    ) -> RecoveryDecision:
        """返回 promote_within_path / evaluate_fallback_gate / hold 三种动作之一。"""

        challengers = sorted(
            {
                str(item).strip()
                for item in (qualified_challenger_evaluation_ids or [])
                if str(item).strip()
            }
        )
        if challengers:
            return RecoveryDecision(
                action="promote_within_path",
                reason="qualified_same_path_challenger_available",
                challenger_evaluation_id=challengers[0],
                fallback_gate_required=False,
                whole_path_unavailable=False,
            )

        unavailable_reasons: List[str] = []
        if health.champion_loadable is not True:
            unavailable_reasons.append("champion_unloadable")
        if health.production_contract_valid is not True:
            unavailable_reasons.append("production_contract_failed")
        if int(health.no_coverage_cycles) >= self._no_coverage_limit:
            unavailable_reasons.append("no_coverage_threshold_reached")
        if int(health.consecutive_failed_cycles) >= self._failed_limit:
            unavailable_reasons.append("path_failed_threshold_reached")

        if unavailable_reasons:
            return RecoveryDecision(
                action="evaluate_fallback_gate",
                reason=";".join(unavailable_reasons),
                fallback_gate_required=True,
                whole_path_unavailable=True,
            )
        return RecoveryDecision(
            action="hold",
            reason="same_path_recovery_not_available_and_path_still_usable",
            fallback_gate_required=False,
            whole_path_unavailable=False,
        )


__all__ = ["PVRecoveryPolicy", "PathHealth", "RecoveryDecision"]
# @AI_GENERATED: end
