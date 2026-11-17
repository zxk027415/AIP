# -*- coding: utf-8 -*-
"""喂数数据集注册（feed_sources）的单元测试。

覆盖：候选过滤、真实文件的事实（指纹/行数/真值标注）、悬空引用 fail-closed、
选中与清空的往返。选中状态写盘位置通过 monkeypatch 重定向到 tmp_path，
**不触碰真实 data/slot_datasets**。
"""

from __future__ import annotations

import pytest

from services.slot_datasets import feed_sources as fs

#: 实测存在的两个样本：一个无真值的喂数源、一个带 label 的金标。
_SOURCE_NO_GOLD = "datasets/pv_mock_feed_unseen.parquet"
_SOURCE_WITH_GOLD = "slot_datasets/pv_day/gold/all_labeled_combined.parquet"


def test_list_candidates_only_whitelisted_roots():
    items = fs.list_candidates(limit=300)
    assert items, "候选不应为空（至少应有 slot_datasets/datasets 下的喂数集）"
    aliases = {item["root_alias"] for item in items}
    assert aliases <= set(fs.CANDIDATE_ROOT_ALIASES), aliases
    assert "benchmark_raw" not in aliases, "研究派生数据不应进喂数候选"
    for item in items:
        assert item["dataset_ref"]
        assert "/" in item["dataset_ref"]


def test_describe_real_source_reports_facts():
    facts = fs.describe_source(_SOURCE_NO_GOLD)
    assert facts.exists is True
    assert facts.row_count == 22848
    assert facts.date_min == "2021-11-18"
    assert facts.date_max == "2021-11-24"
    assert facts.fingerprint == "a4be98a0bdbf162c"
    # 实测该源确实带 label 列（探针读列验证），因此判定为「自带真值」。
    # 这条同时锁住 _peek_columns 的行为：列探测必须真的读到 schema。
    assert facts.has_gold is True
    assert facts.gold_column == "label"
    assert facts.error is None


def test_describe_gold_source_marks_has_gold():
    facts = fs.describe_source(_SOURCE_WITH_GOLD)
    if not facts.exists:
        pytest.skip("金标文件不存在于当前工作区")
    assert facts.has_gold is True
    assert facts.gold_column == "label"


def test_describe_missing_source_reports_not_exists():
    facts = fs.describe_source("datasets/__definitely_missing__.parquet")
    assert facts.exists is False
    assert facts.row_count is None
    assert facts.fingerprint is None


def test_machine_absolute_path_is_reported_not_resolved():
    """机器绝对路径不得被解析成功：描述接口返回 exists=False 并带原因（宽容但不放行）。"""
    facts = fs.describe_source("C:/windows/system32/drivers/etc/hosts")
    assert facts.exists is False
    assert facts.error, "越界引用必须留下可解释的 error，不能静默当成不存在"


def test_absolute_path_cannot_be_selected(tmp_path, monkeypatch):
    """写盘路径上越界引用必须 fail-closed 抛错。"""
    monkeypatch.setattr(fs, "_BACKEND_DIR", tmp_path)
    with pytest.raises(fs.FeedSourceError):
        fs.select_source("pv_day", "C:/windows/system32/drivers/etc/hosts")
    assert fs.get_selection("pv_day") is None


def test_selection_roundtrip_and_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_BACKEND_DIR", tmp_path)

    assert fs.get_selection("pv_day") is None

    payload = fs.select_source("pv_day", _SOURCE_NO_GOLD, operator="test")
    assert payload["dataset_ref"] == _SOURCE_NO_GOLD
    assert payload["slot"] == "pv_day"

    restored = fs.get_selection("pv_day")
    assert restored is not None
    assert restored["dataset_ref"] == _SOURCE_NO_GOLD

    cleared = fs.select_source("pv_day", None, operator="test")
    assert cleared["dataset_ref"] is None
    assert fs.get_selection("pv_day")["dataset_ref"] is None


def test_select_missing_source_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_BACKEND_DIR", tmp_path)
    with pytest.raises(fs.FeedSourceError) as exc_info:
        fs.select_source("pv_day", "datasets/__missing__.parquet")
    assert exc_info.value.code == "dataset_not_found"
    assert fs.get_selection("pv_day") is None, "校验失败不得留下悬空选中"


def test_invalid_slot_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_BACKEND_DIR", tmp_path)
    with pytest.raises(fs.FeedSourceError):
        fs.get_selection("pv_unknown")
    with pytest.raises(fs.FeedSourceError):
        fs.select_source("", _SOURCE_NO_GOLD)


def test_describe_current_falls_back_when_unselected(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_BACKEND_DIR", tmp_path)
    current = fs.describe_current("pv_point")
    assert current["selected"] is False
    assert current["source"] is None
    assert current["semantics"]["granularity"] == "point"
    assert "回落" in current["note"]


def test_describe_current_carries_semantics(tmp_path, monkeypatch):
    from services.slot_datasets.feed_semantics import TSC_MIN_COVERAGE

    monkeypatch.setattr(fs, "_BACKEND_DIR", tmp_path)
    fs.select_source("pv_tsc", _SOURCE_NO_GOLD, operator="test")
    current = fs.describe_current("pv_tsc")
    assert current["selected"] is True
    assert current["source"]["dataset_ref"] == _SOURCE_NO_GOLD
    assert current["semantics"]["granularity"] == "device_day"
    assert current["semantics"]["arrival_gate"]["min_coverage"] == TSC_MIN_COVERAGE
