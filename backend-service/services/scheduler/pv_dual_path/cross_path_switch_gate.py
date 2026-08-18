# @AI_GENERATED
# -*- coding: utf-8 -*-
"""九项跨路径切换纯准入判定器与 ActivationPreview 设备范围摘要。

只做判定和预览，不执行实际切换。原子切换由任务 10.3 的协调器驱动。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence

_ALLOWED_ACTIVATION_MODES = frozenset({"cutover_only", "recent_window", "full_backfill"})
_DEFAULT_REPORT_VALID_DAYS = 14
_DEFAULT_MIN_COMPARABLE = 200
_DEFAULT_MIN_COVERAGE = 0.9


@dataclass(frozen=True)
class GateCondition:
    """单项准入条件的判定结果。"""

    number: int
    name: str
    passed: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class GateResult:
    """九项准入的聚合结果。"""

    all_passed: bool
    conditions: List[GateCondition] = field(default_factory=list)
    failed_conditions: List[GateCondition] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "conditions": [
                {"number": c.number, "name": c.name, "passed": c.passed, "reason": c.reason}
                for c in self.conditions
            ],
            "failed_conditions": [
                {"number": c.number, "name": c.name, "reason": c.reason}
                for c in self.failed_conditions
            ],
        }


@dataclass(frozen=True)
class ActivationPreview:
    """切换前的不可变设备范围预览（10.2）。"""

    activation_mode: str
    device_scope: List[Dict[str, Any]]
    device_scope_count: int
    device_scope_digest: str
    effective_from_date: Optional[str]
    lane_claims: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activation_mode": self.activation_mode,
            "device_scope": self.device_scope,
            "device_scope_count": self.device_scope_count,
            "device_scope_digest": self.device_scope_digest,
            "effective_from_date": self.effective_from_date,
            "lane_claims": self.lane_claims,
        }


class CrossPathSwitchGate:
    """九项跨路径切换纯准入判定器。

    逐项验证全部条件并返回所有失败编号/名称；字符串真值一律拒绝。
    缺三层证据或仅 Seq 宏 F1 更高一律判证据不足。
    """

    def __init__(
        self,
        *,
        report_valid_days: int = _DEFAULT_REPORT_VALID_DAYS,
        min_comparable_device_days: int = _DEFAULT_MIN_COMPARABLE,
        min_coverage_rate: float = _DEFAULT_MIN_COVERAGE,
        artifact_validator: Optional[Callable[[str], bool]] = None,
        contract_validator: Optional[Callable[[str], bool]] = None,
        boundary_calculator: Optional[Callable[[str, Any], List[Dict[str, Any]]]] = None,
    ) -> None:
        self._report_valid_days = max(1, int(report_valid_days))
        self._min_comparable = max(1, int(min_comparable_device_days))
        self._min_coverage = float(min_coverage_rate)
        self._artifact_validator = artifact_validator
        self._contract_validator = contract_validator
        self._boundary_calculator = boundary_calculator

    def evaluate(
        self,
        *,
        target_champion_model_ref: Optional[str],
        report: Optional[Dict[str, Any]],
        current_legacy_champion_ref: Optional[str],
        current_seq_champion_ref: Optional[str],
        activation_mode: Optional[str],
        device_scope: Optional[List[Dict[str, Any]]] = None,
        confirm: Any = None,
        now: Optional[datetime] = None,
    ) -> GateResult:
        """逐项评估九项准入条件，返回全部结果。"""

        current = now or datetime.utcnow()
        conditions: List[GateCondition] = []

        # 1. 目标 Champion 可加载
        ref = str(target_champion_model_ref or "").strip()
        if not ref:
            conditions.append(GateCondition(1, "target_champion_loadable", False, "no_champion"))
        elif self._artifact_validator and not self._artifact_validator(ref):
            conditions.append(GateCondition(1, "target_champion_loadable", False, "artifact_unloadable"))
        else:
            conditions.append(GateCondition(1, "target_champion_loadable", True))

        # 2. 目标契约通过
        if not ref:
            conditions.append(GateCondition(2, "target_contract_valid", False, "no_champion"))
        elif self._contract_validator and not self._contract_validator(ref):
            conditions.append(GateCondition(2, "target_contract_valid", False, "contract_failed"))
        else:
            conditions.append(GateCondition(2, "target_contract_valid", True))

        # 3. 报告双 model_ref 匹配当前 Champion
        report_data = report or {}
        report_legacy = str(report_data.get("legacy_model_ref") or "").strip()
        report_seq = str(report_data.get("seq_model_ref") or "").strip()
        expected_legacy = str(current_legacy_champion_ref or "").strip()
        expected_seq = str(current_seq_champion_ref or "").strip()
        refs_match = (
            bool(report_data)
            and report_legacy == expected_legacy
            and report_seq == expected_seq
            and expected_legacy
            and expected_seq
        )
        if refs_match:
            conditions.append(GateCondition(3, "report_model_refs_match", True))
        else:
            conditions.append(GateCondition(
                3, "report_model_refs_match", False,
                f"expected legacy={expected_legacy!r} seq={expected_seq!r}, "
                f"got legacy={report_legacy!r} seq={report_seq!r}",
            ))

        # 4. 报告未超过有效期
        generated_at_raw = report_data.get("generated_at")
        if not generated_at_raw:
            conditions.append(GateCondition(4, "report_not_expired", False, "no_generated_at"))
        else:
            try:
                generated_at = datetime.fromisoformat(str(generated_at_raw))
                expired = (current - generated_at) > timedelta(days=self._report_valid_days)
                if expired:
                    conditions.append(GateCondition(
                        4, "report_not_expired", False,
                        f"report_age_exceeds_{self._report_valid_days}_days",
                    ))
                else:
                    conditions.append(GateCondition(4, "report_not_expired", True))
            except (ValueError, TypeError):
                conditions.append(GateCondition(4, "report_not_expired", False, "invalid_generated_at"))

        # 5. 可比设备日数量、覆盖率，以及三层证据齐全且 Seq 原生不伪造横向结论
        comparable = int(report_data.get("comparable_total") or 0)
        coverage = float(report_data.get("coverage_rate") or 0.0)
        layers_ok = all(
            isinstance(report_data.get(name), dict) and bool(report_data.get(name))
            for name in ("common_metrics", "seq_native_metrics", "runtime_metrics")
        )
        seq_native = (
            report_data.get("seq_native_metrics")
            if isinstance(report_data.get("seq_native_metrics"), dict)
            else {}
        )
        forged_seq_cross = bool(
            seq_native.get("legacy_counterpart") in (None, "", "无 Legacy 对应值")
            and seq_native.get("cross_path_conclusion") not in (None, "")
        )
        sample_ok = (
            comparable >= self._min_comparable
            and coverage >= self._min_coverage
            and layers_ok
            and not forged_seq_cross
        )
        if sample_ok:
            conditions.append(GateCondition(5, "sample_and_coverage_sufficient", True))
        else:
            reason = (
                f"comparable={comparable} (min {self._min_comparable}), "
                f"coverage={coverage:.4f} (min {self._min_coverage})"
            )
            if not layers_ok:
                reason += "; evidence_layers_incomplete"
            if forged_seq_cross:
                reason += "; seq_native_cross_path_conclusion_forged"
            conditions.append(GateCondition(
                5, "sample_and_coverage_sufficient", False, reason,
            ))

        # 6. 无 blocking 项
        uncomparable = list(report_data.get("uncomparable_items") or [])
        blocking = [item for item in uncomparable if item.get("severity") == "blocking"]
        if blocking:
            conditions.append(GateCondition(
                6, "no_blocking_items", False,
                f"{len(blocking)}_blocking_items",
            ))
        else:
            conditions.append(GateCondition(6, "no_blocking_items", True))

        # 7. activation_mode 合法
        mode = str(activation_mode or "").strip()
        if mode in _ALLOWED_ACTIVATION_MODES:
            conditions.append(GateCondition(7, "activation_mode_valid", True))
        else:
            conditions.append(GateCondition(
                7, "activation_mode_valid", False,
                f"invalid_mode={mode!r}, allowed={sorted(_ALLOWED_ACTIVATION_MODES)}",
            ))

        # 8. 可计算设备边界
        boundaries = self._compute_boundaries(mode, device_scope)
        non_empty = [b for b in boundaries if b.get("effective_from_date") is not None]
        if non_empty:
            conditions.append(GateCondition(8, "device_boundaries_computable", True))
        else:
            conditions.append(GateCondition(
                8, "device_boundaries_computable", False,
                "all_device_boundaries_empty",
            ))

        # 9. confirm 为 JSON boolean true
        if confirm is True:
            conditions.append(GateCondition(9, "confirm_true", True))
        elif confirm is False:
            conditions.append(GateCondition(9, "confirm_true", False, "confirm_is_false"))
        elif isinstance(confirm, str):
            conditions.append(GateCondition(
                9, "confirm_true", False,
                "string_truthy_not_accepted",
            ))
        else:
            conditions.append(GateCondition(
                9, "confirm_true", False,
                f"confirm_not_boolean: {type(confirm).__name__}",
            ))

        failed = [c for c in conditions if not c.passed]
        return GateResult(
            all_passed=len(failed) == 0,
            conditions=conditions,
            failed_conditions=failed,
        )

    def _compute_boundaries(
        self,
        activation_mode: str,
        device_scope: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """尝试计算逐设备边界；无注入 calculator 时只返回 scope 本身。"""
        if not device_scope:
            return []
        if self._boundary_calculator:
            return list(self._boundary_calculator(activation_mode, device_scope))
        return [
            {**device, "effective_from_date": device.get("effective_from_date")}
            for device in device_scope
        ]


def compute_activation_preview(
    *,
    activation_mode: str,
    device_scope: List[Dict[str, Any]],
    boundary_calculator: Optional[Callable[[str, Any], List[Dict[str, Any]]]] = None,
) -> ActivationPreview:
    """10.2 生成不可变 ActivationPreview；全设备边界为空时第 8 项失败。"""

    mode = str(activation_mode or "").strip()
    if mode not in _ALLOWED_ACTIVATION_MODES:
        raise ValueError(f"非法 activation_mode: {mode!r}")

    if boundary_calculator:
        boundaries = list(boundary_calculator(mode, device_scope))
    else:
        boundaries = [
            {**device, "effective_from_date": device.get("effective_from_date")}
            for device in device_scope
        ]

    # 排序：按 (site_id, device_id, branch_id, lane, range_start, range_end)
    sorted_scope = sorted(
        boundaries,
        key=lambda d: (
            str(d.get("site_id") or ""),
            str(d.get("device_id") or ""),
            str(d.get("branch_id") or ""),
            str(d.get("lane") or ""),
            str(d.get("range_start") or ""),
            str(d.get("range_end") or ""),
        ),
    )

    # device_scope_digest: SHA-256 of canonical JSON
    digest_payload = json.dumps(
        sorted_scope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    device_scope_digest = hashlib.sha256(digest_payload).hexdigest()

    # effective_from_date: 所有非空设备边界中的最早日期
    effective_dates: List[date] = []
    for item in sorted_scope:
        raw = item.get("effective_from_date")
        if raw is None:
            continue
        if isinstance(raw, date) and not isinstance(raw, datetime):
            effective_dates.append(raw)
        elif isinstance(raw, datetime):
            effective_dates.append(raw.date())
        else:
            try:
                effective_dates.append(date.fromisoformat(str(raw)[:10]))
            except (ValueError, TypeError):
                pass

    min_date = min(effective_dates).isoformat() if effective_dates else None

    # lane_claims placeholder (populated by 10.3 coordinator)
    lane_claims: List[Dict[str, Any]] = []
    for item in sorted_scope:
        if item.get("lane") and item.get("range_start"):
            lane_claims.append({
                "site_id": item.get("site_id"),
                "device_id": item.get("device_id"),
                "branch_id": item.get("branch_id"),
                "lane": item.get("lane"),
                "range_start": str(item.get("range_start")),
                "range_end": str(item.get("range_end") or ""),
            })

    return ActivationPreview(
        activation_mode=mode,
        device_scope=sorted_scope,
        device_scope_count=len(sorted_scope),
        device_scope_digest=device_scope_digest,
        effective_from_date=min_date,
        lane_claims=lane_claims,
    )


__all__ = [
    "ActivationPreview",
    "CrossPathSwitchGate",
    "GateCondition",
    "GateResult",
    "compute_activation_preview",
]
# @AI_GENERATED: end
