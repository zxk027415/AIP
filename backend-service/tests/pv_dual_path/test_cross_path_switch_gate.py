# @AI_GENERATED
# -*- coding: utf-8 -*-
"""CrossPathSwitchGate 九项准入与 ActivationPreview 设备范围摘要测试。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from services.scheduler.pv_dual_path.cross_path_switch_gate import (
    ActivationPreview,
    CrossPathSwitchGate,
    GateResult,
    compute_activation_preview,
)


def _valid_report(generated_at: str = "2026-01-10T00:00:00") -> dict:
    return {
        "legacy_model_ref": "models/legacy-v1.pkl",
        "seq_model_ref": "models/seq-v1",
        "comparable_total": 250,
        "coverage_rate": 0.95,
        "uncomparable_items": [],
        "generated_at": generated_at,
        "common_metrics": {"agreement_rate": 0.8},
        "seq_native_metrics": {"legacy_counterpart": None},
        "runtime_metrics": {"blocking_count": 0},
    }


def _scope() -> list:
    return [
        {
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": "1",
            "effective_from_date": "2026-01-05",
            "lane": "production",
            "range_start": "2026-01-05",
            "range_end": "",
        },
    ]


def test_all_nine_conditions_pass_when_valid() -> None:
    gate = CrossPathSwitchGate(
        artifact_validator=lambda ref: True,
        contract_validator=lambda ref: True,
    )
    result = gate.evaluate(
        target_champion_model_ref="models/seq-v1",
        report=_valid_report(),
        current_legacy_champion_ref="models/legacy-v1.pkl",
        current_seq_champion_ref="models/seq-v1",
        activation_mode="cutover_only",
        device_scope=_scope(),
        confirm=True,
        now=datetime(2026, 1, 12),
    )
    assert result.all_passed is True
    assert len(result.conditions) == 9
    assert result.failed_conditions == []


def test_string_confirm_is_rejected() -> None:
    gate = CrossPathSwitchGate()
    result = gate.evaluate(
        target_champion_model_ref="x",
        report=_valid_report(),
        current_legacy_champion_ref="models/legacy-v1.pkl",
        current_seq_champion_ref="models/seq-v1",
        activation_mode="cutover_only",
        device_scope=_scope(),
        confirm="true",
        now=datetime(2026, 1, 12),
    )
    failed_names = [c.name for c in result.failed_conditions]
    assert "confirm_true" in failed_names
    assert result.all_passed is False


def test_expired_report_fails_condition_4() -> None:
    gate = CrossPathSwitchGate(report_valid_days=14)
    old_report = _valid_report(generated_at="2025-12-01T00:00:00")
    result = gate.evaluate(
        target_champion_model_ref="x",
        report=old_report,
        current_legacy_champion_ref="models/legacy-v1.pkl",
        current_seq_champion_ref="models/seq-v1",
        activation_mode="cutover_only",
        device_scope=_scope(),
        confirm=True,
        now=datetime(2026, 1, 12),
    )
    cond4 = next(c for c in result.conditions if c.number == 4)
    assert cond4.passed is False


def test_insufficient_sample_fails_condition_5() -> None:
    gate = CrossPathSwitchGate(min_comparable_device_days=300)
    result = gate.evaluate(
        target_champion_model_ref="x",
        report=_valid_report(),
        current_legacy_champion_ref="models/legacy-v1.pkl",
        current_seq_champion_ref="models/seq-v1",
        activation_mode="cutover_only",
        device_scope=_scope(),
        confirm=True,
        now=datetime(2026, 1, 12),
    )
    cond5 = next(c for c in result.conditions if c.number == 5)
    assert cond5.passed is False


def test_blocking_items_fail_condition_6() -> None:
    report = _valid_report()
    report["uncomparable_items"] = [{"severity": "blocking", "reason": "artifact_load_failed"}]
    gate = CrossPathSwitchGate()
    result = gate.evaluate(
        target_champion_model_ref="x",
        report=report,
        current_legacy_champion_ref="models/legacy-v1.pkl",
        current_seq_champion_ref="models/seq-v1",
        activation_mode="cutover_only",
        device_scope=_scope(),
        confirm=True,
        now=datetime(2026, 1, 12),
    )
    cond6 = next(c for c in result.conditions if c.number == 6)
    assert cond6.passed is False


def test_invalid_activation_mode_fails_condition_7() -> None:
    gate = CrossPathSwitchGate()
    result = gate.evaluate(
        target_champion_model_ref="x",
        report=_valid_report(),
        current_legacy_champion_ref="models/legacy-v1.pkl",
        current_seq_champion_ref="models/seq-v1",
        activation_mode="invalid_mode",
        device_scope=_scope(),
        confirm=True,
        now=datetime(2026, 1, 12),
    )
    cond7 = next(c for c in result.conditions if c.number == 7)
    assert cond7.passed is False


def test_empty_device_scope_fails_condition_8() -> None:
    gate = CrossPathSwitchGate()
    result = gate.evaluate(
        target_champion_model_ref="x",
        report=_valid_report(),
        current_legacy_champion_ref="models/legacy-v1.pkl",
        current_seq_champion_ref="models/seq-v1",
        activation_mode="cutover_only",
        device_scope=[],
        confirm=True,
        now=datetime(2026, 1, 12),
    )
    cond8 = next(c for c in result.conditions if c.number == 8)
    assert cond8.passed is False


def test_activation_preview_computes_digest_and_min_date() -> None:
    scope = [
        {"site_id": "s1", "device_id": "d1", "branch_id": "1", "effective_from_date": "2026-01-10"},
        {"site_id": "s1", "device_id": "d2", "branch_id": "1", "effective_from_date": "2026-01-05"},
    ]
    preview = compute_activation_preview(
        activation_mode="cutover_only",
        device_scope=scope,
    )
    assert isinstance(preview, ActivationPreview)
    assert preview.device_scope_count == 2
    assert preview.effective_from_date == "2026-01-05"
    assert len(preview.device_scope_digest) == 64  # SHA-256 hex


def test_activation_preview_all_empty_boundaries() -> None:
    scope = [
        {"site_id": "s1", "device_id": "d1", "branch_id": "1", "effective_from_date": None},
    ]
    preview = compute_activation_preview(
        activation_mode="cutover_only",
        device_scope=scope,
    )
    assert preview.effective_from_date is None


def test_returns_all_failed_conditions_not_just_first() -> None:
    """九项准入应返回全部失败条件，不能短路。"""
    gate = CrossPathSwitchGate()
    result = gate.evaluate(
        target_champion_model_ref=None,
        report=None,
        current_legacy_champion_ref=None,
        current_seq_champion_ref=None,
        activation_mode=None,
        device_scope=None,
        confirm=None,
    )
    assert result.all_passed is False
    assert len(result.failed_conditions) >= 5
# @AI_GENERATED: end
