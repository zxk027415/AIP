# @AI_GENERATED
# -*- coding: utf-8 -*-
"""Property 13：缺游标时只用当前 Epoch 的 effective_from_date。"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Mapping, Optional, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st

from services.scheduler.pv_dual_path.path_isolation import PathIsolationRegistry


_CursorKey = Tuple[str, str, str, str, str]
_PATHS = ("legacy_day", "seq_annotation")


@dataclass
class _CursorRow:
    last_predicted_time: Optional[datetime]


def _key_from_pk(pk: Mapping[str, object]) -> _CursorKey:
    return (
        str(pk["slot"]),
        str(pk["modeling_path"]),
        str(pk["site_id"]),
        str(pk["device_id"]),
        str(pk["branch_id"]),
    )


class _FakeSession:
    def __init__(self, adapter: "_FakeAdapter") -> None:
        self._adapter = adapter

    def get(self, model, pk: Mapping[str, object]) -> Optional[_CursorRow]:
        del model
        copied = dict(pk)
        self._adapter.queried_primary_keys.append(copied)
        return self._adapter.store.get(_key_from_pk(copied))


class _FakeSessionScope(AbstractContextManager["_FakeSession"]):
    def __init__(self, adapter: "_FakeAdapter") -> None:
        self._adapter = adapter

    def __enter__(self) -> _FakeSession:
        return _FakeSession(self._adapter)

    def __exit__(self, exc_type, exc, traceback) -> bool:
        del exc_type, exc, traceback
        return False


class _FakeAdapter:
    def __init__(self, initial: Optional[Mapping[_CursorKey, _CursorRow]] = None) -> None:
        self.store = dict(initial or {})
        self.queried_primary_keys: List[Dict[str, object]] = []

    def get_sync_session(self) -> _FakeSessionScope:
        return _FakeSessionScope(self)


_safe_id = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=12,
)
_epoch_id = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd")),
    min_size=1,
    max_size=16,
)
_boundaries = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))
_naive_datetimes = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2035, 12, 31, 23, 59, 59),
    timezones=st.none(),
)


# Feature: pv-fault-dual-path-serving, Property 13: 缺分区使用本 Epoch 初始边界
@given(
    site_id=_safe_id,
    device_id=_safe_id,
    branch_id=_safe_id,
    missing_path=st.sampled_from(_PATHS),
    epoch_id=_epoch_id,
    boundary=_boundaries,
    other_time=_naive_datetimes,
)
@settings(max_examples=100, deadline=None)
def test_property_13_missing_cursor_uses_current_epoch_boundary(
    site_id: str,
    device_id: str,
    branch_id: str,
    missing_path: str,
    epoch_id: str,
    boundary: date,
    other_time: datetime,
) -> None:
    """缺目标分区 Cursor 时返回当前 Epoch 设备边界，不读另一条路径。"""
    other_path = "seq_annotation" if missing_path == "legacy_day" else "legacy_day"
    other_key = ("pv_fault", other_path, site_id, device_id, branch_id)
    seen: List[tuple] = []

    def reader(requested_epoch: str, device) -> date:
        seen.append((requested_epoch, dict(device)))
        return boundary

    adapter = _FakeAdapter({other_key: _CursorRow(other_time)})
    registry = PathIsolationRegistry(  # type: ignore[arg-type]
        adapter,
        boundary_reader=reader,
    )
    device = {"site_id": site_id, "device_id": device_id, "branch_id": branch_id}
    result = registry.get_cursor_or_initial("pv_fault", missing_path, device, epoch_id)
    assert result == boundary
    assert seen == [(epoch_id, device)]
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
# @AI_GENERATED: end
