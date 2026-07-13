# @AI_GENERATED
"""
tests/test_accuracy_operations_models.py

Property 14: 数据模型序列化 round-trip
  - 使用 hypothesis 生成合法的 AccuracyAlert / RCAReport /
    RecoveryDecision / TrainingAdjustmentTask 实例，
    序列化为 JSON 再反序列化应产出等价对象（Pydantic model round-trip）。

**Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5**
"""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from services.accuracy_operations.models import (
    AccuracyAlert,
    AlertSeverity,
    AlertStatus,
    DecisionStatus,
    DegradationTrend,
    ModelForm,
    RCAReport,
    RCATriggerType,
    RCAStatus,
    RecoveryChannel,
    RecoveryDecision,
    TrainingAdjustmentTask,
    TrainingTaskStatus,
)

# ---------------------------------------------------------------------------
# 共享基础 strategies（策略生成器）
# ---------------------------------------------------------------------------

# iso_text — 用作时间戳字段的合法 ISO 8601 字符串
_iso_text = st.just("2024-01-15T10:00:00+00:00")

# safe_text — 不含 null 字符的普通文本（用于字符串字段）
_safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=0,
    max_size=50,
)

# optional_safe_text — 可选字符串字段（None 或普通文本）
_optional_safe_text = st.none() | _safe_text

# ---------------------------------------------------------------------------
# AccuracyAlert strategy
# ---------------------------------------------------------------------------

_accuracy_alert_st = st.builds(
    AccuracyAlert,
    # alert_id — 告警唯一ID，有 default_factory，也可由 hypothesis 注入
    alert_id=st.just("alert-abcd1234"),
    slot=st.just("default"),
    model_form=st.sampled_from(ModelForm),
    workflow_id=_safe_text,
    version_tag=_safe_text,
    baseline_mape=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    current_rolling_mape=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    degradation_pct=st.floats(min_value=-100.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    degradation_trend=st.sampled_from(DegradationTrend),
    severity=st.sampled_from(AlertSeverity),
    status=st.sampled_from(AlertStatus),
    cooldown_until=_optional_safe_text,
    rca_report_id=_optional_safe_text,
    recovery_decision_id=_optional_safe_text,
    # recovery_evidence — dict 或 None
    recovery_evidence=st.none() | st.just({"type": "passed", "ref": "test-ref", "at": "2024-01-15T10:00:00+00:00"}),
    created_at=_iso_text,
    updated_at=_iso_text,
)

# ---------------------------------------------------------------------------
# RCAReport strategy
# ---------------------------------------------------------------------------

_rca_report_st = st.builds(
    RCAReport,
    rca_report_id=st.just("rca-abcd1234"),
    alert_id=st.just("alert-abcd1234"),
    trigger_type=st.sampled_from(RCATriggerType),
    root_cause=_safe_text,
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    reasoning=_safe_text,
    # supporting_evidence — list，strategy 产出空列表或含简单元素的列表
    supporting_evidence=st.lists(st.text(min_size=0, max_size=20), max_size=5),
    undetermined=st.booleans(),
    candidate_strategies=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    recommended_strategy_id=_optional_safe_text,
    artifacts_dir=_safe_text,
    status=st.sampled_from(RCAStatus),
    created_at=_iso_text,
)

# ---------------------------------------------------------------------------
# RecoveryDecision strategy
# ---------------------------------------------------------------------------

_recovery_decision_st = st.builds(
    RecoveryDecision,
    decision_id=st.just("rec-abcd1234"),
    alert_id=st.just("alert-abcd1234"),
    rca_report_id=st.just("rca-abcd1234"),
    channel=st.sampled_from(RecoveryChannel),
    decision_reason=_safe_text,
    confidence_gate_passed=st.booleans(),
    switch_event_id=_optional_safe_text,
    training_task_id=_optional_safe_text,
    sla_deadline=_iso_text,
    rollback_of=_optional_safe_text,
    status=st.sampled_from(DecisionStatus),
    created_at=_iso_text,
    updated_at=_iso_text,
)

# ---------------------------------------------------------------------------
# TrainingAdjustmentTask strategy
# ---------------------------------------------------------------------------

_training_task_st = st.builds(
    TrainingAdjustmentTask,
    task_id=st.just("tadj-abcd1234"),
    decision_id=st.just("rec-abcd1234"),
    rca_report_id=st.just("rca-abcd1234"),
    # recipe_patch — dict，strategy 产出空 dict 或含字符串键值对的 dict
    recipe_patch=st.fixed_dictionaries({}) | st.just({"train_days": 90, "model": "xgboost"}),
    target_workflow_id=_safe_text,
    status=st.sampled_from(TrainingTaskStatus),
    prelaunch_id=_optional_safe_text,
    created_at=_iso_text,
    updated_at=_iso_text,
)


# ===========================================================================
# Property 14 — 数据模型序列化 round-trip
# Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5
# ===========================================================================


@given(alert=_accuracy_alert_st)
@settings(max_examples=50)
def test_accuracy_alert_json_roundtrip(alert: AccuracyAlert):
    """
    **Validates: Requirements 13.1**

    AccuracyAlert 实例序列化为 JSON 后反序列化，产出等价对象。
    验证：model.dict() round-trip 与 model.json() round-trip 均一致。
    """
    # dict round-trip
    data_dict = alert.dict()
    restored_from_dict = AccuracyAlert.parse_obj(data_dict)
    assert restored_from_dict.dict() == data_dict, (
        f"AccuracyAlert dict round-trip 失败: {data_dict}"
    )

    # json round-trip
    json_str = alert.json()
    restored_from_json = AccuracyAlert.parse_raw(json_str)
    assert restored_from_json.dict() == data_dict, (
        f"AccuracyAlert json round-trip 失败: {json_str}"
    )

    # 确保 JSON 是合法的 JSON 字符串（可被标准库解析）
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)


@given(report=_rca_report_st)
@settings(max_examples=50)
def test_rca_report_json_roundtrip(report: RCAReport):
    """
    **Validates: Requirements 13.2**

    RCAReport 实例序列化为 JSON 后反序列化，产出等价对象。
    """
    data_dict = report.dict()
    restored_from_dict = RCAReport.parse_obj(data_dict)
    assert restored_from_dict.dict() == data_dict, (
        f"RCAReport dict round-trip 失败: {data_dict}"
    )

    json_str = report.json()
    restored_from_json = RCAReport.parse_raw(json_str)
    assert restored_from_json.dict() == data_dict, (
        f"RCAReport json round-trip 失败: {json_str}"
    )

    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)


@given(decision=_recovery_decision_st)
@settings(max_examples=50)
def test_recovery_decision_json_roundtrip(decision: RecoveryDecision):
    """
    **Validates: Requirements 13.3, 13.5**

    RecoveryDecision 实例序列化为 JSON 后反序列化，产出等价对象。
    同时验证 channel 字段仅取合法枚举值（Requirement 13.5）。
    """
    data_dict = decision.dict()
    restored_from_dict = RecoveryDecision.parse_obj(data_dict)
    assert restored_from_dict.dict() == data_dict, (
        f"RecoveryDecision dict round-trip 失败: {data_dict}"
    )

    json_str = decision.json()
    restored_from_json = RecoveryDecision.parse_raw(json_str)
    assert restored_from_json.dict() == data_dict, (
        f"RecoveryDecision json round-trip 失败: {json_str}"
    )

    # Requirement 13.5 — channel 字段仅取合法枚举值
    valid_channels = {"shadow_switch", "training_adjust", "parallel", "observe"}
    assert data_dict["channel"] in valid_channels, (
        f"RecoveryDecision.channel 值非法: {data_dict['channel']}"
    )

    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)


@given(task=_training_task_st)
@settings(max_examples=50)
def test_training_adjustment_task_json_roundtrip(task: TrainingAdjustmentTask):
    """
    **Validates: Requirements 13.4**

    TrainingAdjustmentTask 实例序列化为 JSON 后反序列化，产出等价对象。
    """
    data_dict = task.dict()
    restored_from_dict = TrainingAdjustmentTask.parse_obj(data_dict)
    assert restored_from_dict.dict() == data_dict, (
        f"TrainingAdjustmentTask dict round-trip 失败: {data_dict}"
    )

    json_str = task.json()
    restored_from_json = TrainingAdjustmentTask.parse_raw(json_str)
    assert restored_from_json.dict() == data_dict, (
        f"TrainingAdjustmentTask json round-trip 失败: {json_str}"
    )

    # recipe_patch 必须是 dict 类型（Requirement 13.4）
    assert isinstance(data_dict["recipe_patch"], dict), (
        f"TrainingAdjustmentTask.recipe_patch 不是 dict: {data_dict['recipe_patch']}"
    )

    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)
# @AI_GENERATED: end
