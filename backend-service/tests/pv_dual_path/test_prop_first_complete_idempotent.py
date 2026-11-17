# -*- coding: utf-8 -*-
# @AI_GENERATED
# Feature: pv-fault-dual-path-serving, Property 11: 首达完整幂等
"""
tests/pv_dual_path/test_prop_first_complete_idempotent.py

Property 11: 首达完整幂等
  For any 设备-天到达序列，``completed_at`` 只在 ``point_count`` 首次达阈值时被写入一次，
  后续达标事件不改变 ``completed_at``。

**Validates: Requirements 4.6**

被测对象：``IngestionTrackerRepository.record_arrival()``
（services/db/repositories/ingestion_tracker.py）的 ``newly_complete`` 分支——
首次跨过完整性阈值时以 UTC 记 ``completed_at`` 并置 ``is_complete=True``，此后不再重写。

隔离策略：不接真实 MySQL。用内存 fake 的 session/adapter
（``_FakeAdapter`` / ``_FakeSession``）承接 ``get_sync_session().get/add/flush``，
仓库内部真实构造的 ORM 行 ``MeasurementIngestionDaily`` 作为普通内存对象读写，
从而只聚焦 ``record_arrival`` 的首达完整幂等纯逻辑。

运行（conda 环境 cp_web）：
    conda activate cp_web
    cd backend-service
    PYTHONPATH=. pytest tests/pv_dual_path/test_prop_first_complete_idempotent.py -q
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st

from services.db.models.pv_fault import MeasurementIngestionDaily
from services.db.repositories.ingestion_tracker import IngestionTrackerRepository


# ---------------------------------------------------------------------------
# 内存 fake：隔离真实数据库，只承接 record_arrival 用到的 session/adapter 契约
# ---------------------------------------------------------------------------

#: 主键元组类型：(site_id, device_id, branch_id, business_date)
_PkKey = Tuple[str, str, str, date]


def _row_key(row: MeasurementIngestionDaily) -> _PkKey:
    return (row.site_id, row.device_id, row.branch_id, row.business_date)


class _FakeSession:
    """最小实现 record_arrival 依赖的 session 契约：get / add / flush。

    共享同一个 ``store`` dict（由 adapter 持有），使多次 record_arrival 调用之间
    行数据得以累积，模拟同一设备-天多批到达。
    """

    def __init__(self, store: Dict[_PkKey, MeasurementIngestionDaily]) -> None:
        self._store = store

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def get(self, model, pk: Dict[str, object]) -> Optional[MeasurementIngestionDaily]:
        key: _PkKey = (
            pk["site_id"], pk["device_id"], pk["branch_id"], pk["business_date"],
        )
        return self._store.get(key)

    def add(self, row: MeasurementIngestionDaily) -> None:
        self._store[_row_key(row)] = row

    def flush(self) -> None:  # 内存 fake 无需真正 flush
        return None


class _FakeAdapter:
    """持有内存 store 的 fake adapter，get_sync_session 每次包同一 store。"""

    def __init__(self) -> None:
        self._store: Dict[_PkKey, MeasurementIngestionDaily] = {}

    def get_sync_session(self) -> _FakeSession:
        return _FakeSession(self._store)


# ---------------------------------------------------------------------------
# strategies（策略生成器）
# ---------------------------------------------------------------------------

# _point_deltas — 一批批到达的新增点数序列，每批 >= 0（含 0 批：不推进但仍是一次到达）
_point_deltas = st.lists(st.integers(min_value=0, max_value=150), min_size=1, max_size=12)

# _expected_points — 该设备-天理论应有点数，范围 [1, 288]
_expected_points = st.integers(min_value=1, max_value=288)

# _ratio — 完整性阈值比例，范围 [0.0, 1.0]
_ratio = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=200, deadline=None)
@given(deltas=_point_deltas, expected=_expected_points, ratio=_ratio)
def test_first_complete_is_idempotent(deltas: List[int], expected: int, ratio: float) -> None:
    """完整性首次达标写一次 completed_at，后续到达不改写。"""
    repo = IngestionTrackerRepository(_FakeAdapter(), completeness_ratio=ratio)

    site_id, device_id, branch_id = "siteA", "devA", "brA"
    business_date = date(2021, 1, 5)
    base_time = datetime(2021, 1, 5, 0, 0, 0)

    # 参考模型：复刻 record_arrival 的 newly_complete 判定（point_count/threshold, ">=")
    threshold = expected * ratio
    cumulative = 0
    expected_is_complete = False
    expected_completed_at_iso: Optional[str] = None

    for i, delta in enumerate(deltas):
        arrived_at = base_time + timedelta(seconds=i)  # 每批一个可区分的到达时刻
        result = repo.record_arrival(
            site_id, device_id, branch_id, business_date,
            point_delta=delta,
            expected_point_count=expected,
            arrived_at=arrived_at,
        )

        # 参考模型推进：首次跨过阈值时记录该批到达时刻为期望 completed_at
        cumulative += delta
        if (not expected_is_complete) and cumulative >= threshold:
            expected_is_complete = True
            expected_completed_at_iso = arrived_at.isoformat()

        # 累计点数一致（间接确认判定输入正确）
        assert result["point_count"] == cumulative
        # is_complete 与参考模型一致
        assert result["is_complete"] is expected_is_complete
        # 核心：completed_at 只在首次达标写入一次，之后逐批不变
        assert result["completed_at"] == expected_completed_at_iso


@settings(max_examples=200, deadline=None)
@given(
    # pre_delta — 首次即跨阈值的一批点数
    total=st.integers(min_value=1, max_value=288),
    # extra_batches — 达标后继续到达的批次（含 0），不得改写 completed_at
    extra_batches=st.lists(st.integers(min_value=0, max_value=150), min_size=1, max_size=8),
)
def test_completed_at_frozen_after_first_crossing(total: int, extra_batches: List[int]) -> None:
    """一旦达标，后续任意到达（含 0 批、含超量批）都不改写 completed_at。"""
    # ratio=1.0、expected=total、首批 delta=total → 首批即恰好达标
    repo = IngestionTrackerRepository(_FakeAdapter(), completeness_ratio=1.0)

    site_id, device_id, branch_id = "siteB", "devB", "brB"
    business_date = date(2021, 2, 10)
    first_time = datetime(2021, 2, 10, 8, 0, 0)

    first = repo.record_arrival(
        site_id, device_id, branch_id, business_date,
        point_delta=total, expected_point_count=total, arrived_at=first_time,
    )
    assert first["is_complete"] is True
    assert first["completed_at"] == first_time.isoformat()

    frozen_completed_at = first["completed_at"]
    for i, delta in enumerate(extra_batches):
        later_time = first_time + timedelta(minutes=i + 1)  # 严格晚于首次达标时刻
        result = repo.record_arrival(
            site_id, device_id, branch_id, business_date,
            point_delta=delta, expected_point_count=total, arrived_at=later_time,
        )
        assert result["is_complete"] is True
        # 关键：即便传入更晚的 arrived_at，completed_at 仍冻结在首次达标时刻
        assert result["completed_at"] == frozen_completed_at
# @AI_GENERATED: end
