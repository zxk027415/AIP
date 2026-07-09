"""
tests/precision_ops/conftest.py — 精度运营测试共用 fixtures 与 hypothesis strategy builders

包含：
  - tmp_precision_data_dir : pytest fixture，提供隔离的临时数据目录
  - make_version_entry()   : hypothesis strategy，生成合法的 VersionEntry 字典
  - make_slot_config()     : hypothesis strategy，生成合法的 SlotConfig 字典（所有参数在有效范围内）
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pytest
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Pytest Fixtures — 测试隔离基础设施
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_precision_data_dir(tmp_path: Path) -> Path:
    """
    为每个测试用例提供独立的临时数据根目录。

    目录结构与生产环境一致：
        tmp_path/
          data/
            precision_ops/

    同时将 ``BASE_DATA_DIR`` monkey-patch 到该临时路径，
    确保测试间完全隔离，不污染真实数据目录。

    :return: ``tmp_path/data/precision_ops/`` 的 Path 对象
    """
    precision_dir = tmp_path / "data" / "precision_ops"
    precision_dir.mkdir(parents=True)

    # monkey-patch utils 模块的 BASE_DATA_DIR，使其指向临时目录
    import services.precision_ops.utils as _utils
    original = _utils.BASE_DATA_DIR
    _utils.BASE_DATA_DIR = precision_dir
    yield precision_dir
    # 测试结束后恢复，避免影响其他测试
    _utils.BASE_DATA_DIR = original


# ---------------------------------------------------------------------------
# Hypothesis Strategy Builders — 合法数据生成器
# ---------------------------------------------------------------------------

# VersionEntry 字段说明（对应 design.md 数据模型）：
#   workflow_id         — 工作流模板 ID（非空字符串）
#   version_tag         — 版本标签，最大 128 字符（非空字符串）
#   source_run_id       — 来源 AutoResearch run ID（可选）
#   source_candidate_id — 来源候选 ID（可选）
#   registered_at       — 注册时间，ISO 8601 字符串
#   status              — "production" | "shadow" | "retired"
#   slot                — 槽位（分区键），默认 "default"
#   baseline_mape       — 基线 MAPE（可选浮点数，>0）

def make_version_entry() -> st.SearchStrategy[dict]:
    """
    返回 hypothesis strategy，生成合法的 VersionEntry 字典。

    所有字段均在允许范围内：
    - ``workflow_id``    : 非空 ASCII 标识符格式字符串
    - ``version_tag``    : 非空字符串，长度 ≤ 128
    - ``status``         : "production" | "shadow" | "retired" 之一
    - ``slot``           : 非空字符串，通常为 "default" 或短标识符
    - ``registered_at``  : 合法的 ISO 8601 字符串（UTC）
    - ``baseline_mape``  : 可选，范围 (0, 100]

    示例用法::

        @given(make_version_entry())
        def test_something(entry: dict):
            ...
    """
    _wf_id = st.from_regex(r"workflow-[a-z0-9\-]{3,30}", fullmatch=True)
    _tag = st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_."),
        min_size=1,
        max_size=128,
    )
    _status = st.sampled_from(["production", "shadow", "retired"])
    _slot = st.from_regex(r"[a-z][a-z0-9\-]{0,19}", fullmatch=True)
    # ISO 8601 UTC 字符串：固定格式，年份在合理范围内
    _registered_at = st.builds(
        lambda y, mo, d, h, mi, s: f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}+00:00",
        y=st.integers(min_value=2020, max_value=2030),
        mo=st.integers(min_value=1, max_value=12),
        d=st.integers(min_value=1, max_value=28),
        h=st.integers(min_value=0, max_value=23),
        mi=st.integers(min_value=0, max_value=59),
        s=st.integers(min_value=0, max_value=59),
    )
    _baseline_mape = st.one_of(
        st.none(),
        st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    _opt_str = st.one_of(st.none(), st.from_regex(r"[a-z0-9\-]{4,20}", fullmatch=True))

    return st.fixed_dictionaries(
        {
            "workflow_id": _wf_id,
            "version_tag": _tag,
            "source_run_id": _opt_str,
            "source_candidate_id": _opt_str,
            "registered_at": _registered_at,
            "status": _status,
            "slot": _slot,
            "baseline_mape": _baseline_mape,
        }
    )


# SlotConfig 字段说明（对应 design.md 配置参数校验范围）：
#   slot                         — 槽位名称
#   evaluation_window_days       — 评估窗口天数，[1, 30]
#   degradation_threshold_pct    — 退化阈值（相对百分比），[5, 50]
#   switch_margin_pct            — 切换分差（相对百分比），[1, 30]
#   cooldown_hours               — 冷却期小时数，[1, 168]
#   min_valid_cycles             — 最少有效周期数，[1, 30]
#   shadow_timeout_seconds       — 影子预测超时秒数，[10, 600]
#   production_timeout_seconds   — 生产预测超时秒数，[10, 600]
#   max_shadow_versions          — 最大影子版本数，[2, 20]
#   rollback_window_hours        — 回滚窗口小时数，[1, 168]
#   auto_switch_enabled          — 是否启用自动切换，布尔值
#   prediction_retention_days    — 预测数据保留天数，合理范围 [7, 365]
#   min_eval_points              — 最少评估数据点，[1, 500]
#   post_switch_observation_points — 切换后观察数据点，[1, 200]
#   eval_window_points           — 评估窗口点数，[1, 500]

def make_slot_config() -> st.SearchStrategy[dict]:
    """
    返回 hypothesis strategy，生成所有参数均在有效范围内的 SlotConfig 字典。

    参数范围严格遵循 design.md §SlotConfig 的校验范围，
    可直接用于 Property 19（配置参数范围校验）等 property tests。

    示例用法::

        @given(make_slot_config())
        def test_config_is_valid(config: dict):
            ...
    """
    _slot = st.from_regex(r"[a-z][a-z0-9\-]{0,19}", fullmatch=True)

    return st.fixed_dictionaries(
        {
            "slot": _slot,
            # 以下范围严格对应 design.md 参数校验表格
            "evaluation_window_days": st.integers(min_value=1, max_value=30),
            "degradation_threshold_pct": st.integers(min_value=5, max_value=50),
            "switch_margin_pct": st.integers(min_value=1, max_value=30),
            "cooldown_hours": st.integers(min_value=1, max_value=168),
            "min_valid_cycles": st.integers(min_value=1, max_value=30),
            "shadow_timeout_seconds": st.integers(min_value=10, max_value=600),
            "production_timeout_seconds": st.integers(min_value=10, max_value=600),
            "max_shadow_versions": st.integers(min_value=2, max_value=20),
            "rollback_window_hours": st.integers(min_value=1, max_value=168),
            "auto_switch_enabled": st.booleans(),
            "prediction_retention_days": st.integers(min_value=7, max_value=365),
            "min_eval_points": st.integers(min_value=1, max_value=500),
            "post_switch_observation_points": st.integers(min_value=1, max_value=200),
            "eval_window_points": st.integers(min_value=1, max_value=500),
        }
    )
