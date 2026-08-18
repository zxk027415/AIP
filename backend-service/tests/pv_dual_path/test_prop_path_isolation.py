# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
tests/pv_dual_path/test_prop_path_isolation.py — PathIsolationRegistry 属性测试

本文件用内存 fake adapter/session 模拟 DevicePredictionCursor 按
``(site_id, device_id, branch_id, modeling_path)`` 复合主键存储，不连接真实数据库。
覆盖：
  - Property 12：推进某路径只修改目标分区，另一路径的值与行数保持不变。
  - Property 13：目标分区缺失时返回固定初始水位 None，且查询主键显式带目标路径。
  - Property 14：游标事务写失败不提交部分修改；批次原子替换失败不破坏原文件。

Validates: Requirements 5.1, 5.3, 5.5, 5.6, 5.7, 10.5
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects import mysql

from services.scheduler.pv_dual_path.path_isolation import (
    PartitionWriteError,
    PathIsolationRegistry,
)


_CursorKey = Tuple[str, str, str, str, str]
_PATHS = ("legacy_day", "seq_annotation")


@dataclass
class _CursorRow:
    """内存游标行，仅保留本组属性断言需要的业务时间水位。"""

    last_predicted_time: Optional[datetime]


def _key_from_pk(pk: Mapping[str, object]) -> _CursorKey:
    return (
        str(pk["slot"]),
        str(pk["modeling_path"]),
        str(pk["site_id"]),
        str(pk["device_id"]),
        str(pk["branch_id"]),
    )


def _clone_store(store: Mapping[_CursorKey, _CursorRow]) -> Dict[_CursorKey, _CursorRow]:
    return {key: _CursorRow(row.last_predicted_time) for key, row in store.items()}


class _FakeSession:
    """事务工作副本：execute 可在变更后注入异常，由 scope 决定是否提交。"""

    def __init__(self, adapter: "_FakeAdapter") -> None:
        self._adapter = adapter
        self.working_store = _clone_store(adapter.store)

    def get(self, model, pk: Mapping[str, object]) -> Optional[_CursorRow]:
        del model
        copied_pk = dict(pk)
        self._adapter.queried_primary_keys.append(copied_pk)
        return self.working_store.get(_key_from_pk(copied_pk))

    def execute(self, statement) -> None:
        params = statement.compile(dialect=mysql.dialect()).params
        key: _CursorKey = (
            str(params["slot"]),
            str(params["modeling_path"]),
            str(params["site_id"]),
            str(params["device_id"]),
            str(params["branch_id"]),
        )
        self.working_store[key] = _CursorRow(params["last_predicted_time"])
        if self._adapter.fail_after_execute:
            raise RuntimeError("injected cursor write failure")


class _FakeSessionScope(AbstractContextManager[_FakeSession]):
    """模拟 DBAdapter 的成功 commit / 异常 rollback 上下文管理语义。"""

    def __init__(self, adapter: "_FakeAdapter") -> None:
        self._adapter = adapter
        self._session = _FakeSession(adapter)

    def __enter__(self) -> _FakeSession:
        return self._session

    def __exit__(self, exc_type, exc, traceback) -> bool:
        del exc, traceback
        if exc_type is None:
            self._adapter.store = _clone_store(self._session.working_store)
        return False


class _FakeAdapter:
    """持有按 slot + modeling_path + 设备三元组五元主键分区的游标内存登记。"""

    def __init__(
        self,
        initial: Optional[Mapping[_CursorKey, _CursorRow]] = None,
        *,
        fail_after_execute: bool = False,
    ) -> None:
        self.store = _clone_store(initial or {})
        self.fail_after_execute = fail_after_execute
        self.queried_primary_keys: List[Dict[str, object]] = []

    def get_sync_session(self) -> _FakeSessionScope:
        return _FakeSessionScope(self)


_safe_id = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=12,
)
_naive_datetimes = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2035, 12, 31, 23, 59, 59),
    timezones=st.none(),
)


# Feature: pv-fault-dual-path-serving, Property 12: 分区写入隔离
@given(
    site_id=_safe_id,
    device_id=_safe_id,
    branch_id=_safe_id,
    target_path=st.sampled_from(_PATHS),
    legacy_time=_naive_datetimes,
    seq_time=_naive_datetimes,
    new_time=_naive_datetimes,
)
@settings(max_examples=100, deadline=None)
def test_property_12_cursor_write_is_isolated_by_modeling_path(
    site_id: str,
    device_id: str,
    branch_id: str,
    target_path: str,
    legacy_time: datetime,
    seq_time: datetime,
    new_time: datetime,
) -> None:
    """推进目标路径只改该复合主键分区，另一路径值和总数量不变。

    Validates: Requirements 5.1, 5.3, 5.5
    """
    legacy_key = ("pv_fault", "legacy_day", site_id, device_id, branch_id)
    seq_key = ("pv_fault", "seq_annotation", site_id, device_id, branch_id)
    adapter = _FakeAdapter(
        {
            legacy_key: _CursorRow(legacy_time),
            seq_key: _CursorRow(seq_time),
        }
    )
    registry = PathIsolationRegistry(adapter)  # type: ignore[arg-type]
    other_path = "seq_annotation" if target_path == "legacy_day" else "legacy_day"
    other_key = seq_key if other_path == "seq_annotation" else legacy_key
    other_before = adapter.store[other_key].last_predicted_time
    count_before = len(adapter.store)

    result = registry.advance_cursor(
        "pv_fault",
        target_path,
        site_id,
        device_id,
        branch_id,
        new_time,
    )

    target_key = legacy_key if target_path == "legacy_day" else seq_key
    assert result == new_time
    assert adapter.store[target_key].last_predicted_time == new_time
    assert adapter.store[other_key].last_predicted_time == other_before
    assert len(adapter.store) == count_before


# Feature: pv-fault-dual-path-serving, Property 13: 缺分区回退初始水位
@given(
    site_id=_safe_id,
    device_id=_safe_id,
    branch_id=_safe_id,
    missing_path=st.sampled_from(_PATHS),
    other_time=_naive_datetimes,
)
@settings(max_examples=100, deadline=None)
def test_property_13_missing_partition_returns_none_without_cross_path_fallback(
    site_id: str,
    device_id: str,
    branch_id: str,
    missing_path: str,
    other_time: datetime,
) -> None:
    """缺目标分区时返回 None，并且只用包含目标 modeling_path 的主键查询。

    Validates: Requirements 5.6
    """
    other_path = "seq_annotation" if missing_path == "legacy_day" else "legacy_day"
    other_key = ("pv_fault", other_path, site_id, device_id, branch_id)
    adapter = _FakeAdapter({other_key: _CursorRow(other_time)})
    registry = PathIsolationRegistry(adapter)  # type: ignore[arg-type]

    result = registry.read_cursor(
        "pv_fault",
        missing_path,
        site_id,
        device_id,
        branch_id,
    )

    assert result is None
    assert len(adapter.store) == 1
    assert adapter.store[other_key].last_predicted_time == other_time
    assert adapter.queried_primary_keys == [
        {
            "site_id": site_id,
            "device_id": device_id,
            "branch_id": branch_id,
            "modeling_path": missing_path,
            "slot": "pv_fault",
        }
    ]


# Feature: pv-fault-dual-path-serving, Property 14: 分区写失败不产生部分写
@given(
    site_id=_safe_id,
    device_id=_safe_id,
    branch_id=_safe_id,
    target_path=st.sampled_from(_PATHS),
    target_time=_naive_datetimes,
    other_time=_naive_datetimes,
    attempted_time=_naive_datetimes,
    original_marker=st.text(min_size=0, max_size=32),
    replacement_marker=st.text(min_size=0, max_size=32),
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_property_14_failed_partition_writes_are_atomic(
    tmp_path: Path,
    site_id: str,
    device_id: str,
    branch_id: str,
    target_path: str,
    target_time: datetime,
    other_time: datetime,
    attempted_time: datetime,
    original_marker: str,
    replacement_marker: str,
) -> None:
    """游标异常回滚工作副本，批次替换异常保留原文件且清理临时文件。

    Validates: Requirements 5.7, 10.5
    """
    other_path = "seq_annotation" if target_path == "legacy_day" else "legacy_day"
    target_key = ("pv_fault", target_path, site_id, device_id, branch_id)
    other_key = ("pv_fault", other_path, site_id, device_id, branch_id)
    initial = {
        target_key: _CursorRow(target_time),
        other_key: _CursorRow(other_time),
    }
    adapter = _FakeAdapter(initial, fail_after_execute=True)
    registry = PathIsolationRegistry(  # type: ignore[arg-type]
        adapter,
        backend_service_dir=tmp_path,
    )
    cursor_snapshot = {
        key: row.last_predicted_time for key, row in adapter.store.items()
    }

    with pytest.raises(PartitionWriteError) as cursor_exc:
        registry.advance_cursor(
            "pv_fault",
            target_path,
            site_id,
            device_id,
            branch_id,
            attempted_time,
        )

    assert cursor_exc.value.slot == "pv_fault"
    assert cursor_exc.value.modeling_path == target_path
    assert {
        key: row.last_predicted_time for key, row in adapter.store.items()
    } == cursor_snapshot

    batch_id = "atomic-batch"
    batch_path = registry.batch_dir("pv_fault", target_path) / f"{batch_id}.json"
    batch_path.parent.mkdir(parents=True, exist_ok=True)
    original_payload = {
        "modeling_path": target_path,
        "marker": original_marker,
    }
    original_bytes = json.dumps(
        original_payload,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    batch_path.write_bytes(original_bytes)

    with patch.object(
        Path,
        "replace",
        side_effect=OSError("injected atomic replace failure"),
    ):
        with pytest.raises(PartitionWriteError) as batch_exc:
            registry.write_batch(
                "pv_fault",
                target_path,
                batch_id,
                {"marker": replacement_marker},
            )

    assert batch_exc.value.slot == "pv_fault"
    assert batch_exc.value.modeling_path == target_path
    assert batch_path.read_bytes() == original_bytes
    assert list(batch_path.parent.glob("*.tmp")) == []
# @AI_GENERATED: end
