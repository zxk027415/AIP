# @AI_GENERATED
"""
tests/pv_dual_path/test_watermark.py — DataWatermarkService 示例单元测试（Task 3.2）

被测对象：services/scheduler/pv_dual_path/watermark.py 的 DataWatermarkService。
它计算某设备三元组 (site_id, device_id, branch_id) 已入库数据点的最大 Event_Time
（事件时间/业务时间），作为双路径检测的统一时间进度基准（不看墙钟）。

- device_watermark(): 主口径 MAX(training_samples.time)（限定 data_source in (mock, production)）；
  主口径为空时回退 MAX(measurement_ingestion_daily.business_date) 并转成该自然日 00:00:00。
- device_watermark_date(): 返回上者所在自然日；无数据返回 None。

测试策略：完全 mock 掉 DBAdapter 的同步 session（不连真实数据库）。用一个「查询感知」的
FakeSession：解析被执行 select 语句的目标表名与设备三元组 bind 参数，返回预置的可控值，
从而覆盖以下场景：
  1. 有 training_samples 主口径 → 返回该 datetime；device_watermark_date 返回其 date。
  2. 主口径为空、有 ingestion 回退业务日 → 返回该日 00:00:00。
  3. 主口径与回退都无 → None；device_watermark_date → None。
  4. 多设备独立：不同三元组返回各自不同的水位，互不串扰。

对应需求：Req1.8（两条策略共用 Data_Watermark、按数据推进不用墙钟）、Req3.1（Seq 以
Data_Watermark 所在自然日为「数据今天」基准）。

运行（conda 环境 cp_web）：
    conda activate cp_web
    cd backend-service
    PYTHONPATH=. pytest tests/pv_dual_path/test_watermark.py -q
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

import pytest

# 确保 backend-service 在 PYTHONPATH（与其它测试保持一致）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TESTS_DIR = os.path.dirname(_THIS_DIR)
_BACKEND_DIR = os.path.dirname(_TESTS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.scheduler.pv_dual_path.watermark import DataWatermarkService

# 设备三元组类型别名：(site_id, device_id, branch_id)
DeviceKey = Tuple[str, str, str]


# ────────────────────────────────────────────────────────────────────────────
# Mock 基础设施：查询感知的 FakeSession / FakeAdapter（不连真实数据库）
# ────────────────────────────────────────────────────────────────────────────


class _FakeResult:
    """模拟 session.execute() 的返回，仅需实现 scalar_one_or_none()。"""

    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


def _find_param(params: Dict[str, Any], prefix: str) -> Optional[Any]:
    """从编译后的 bind 参数里按前缀取第一个匹配值（如 site_id_1 / device_id_1）。"""
    for key, val in params.items():
        if key.startswith(prefix):
            return val
    return None


class _FakeSession:
    """查询感知的假 session：按目标表名 + 设备三元组返回预置水位值。

    device_data: {(site, device, branch): {"sample": datetime|None, "fallback": date|None}}
    未登记的设备一律视为「无数据」（两口径均 None）。
    """

    def __init__(self, device_data: Dict[DeviceKey, Dict[str, Any]]) -> None:
        self._device_data = device_data

    def execute(self, stmt: Any) -> _FakeResult:
        sql = str(stmt)
        params = stmt.compile().params
        key: DeviceKey = (
            _find_param(params, "site_id"),
            _find_param(params, "device_id"),
            _find_param(params, "branch_id"),
        )
        entry = self._device_data.get(key, {})
        if "training_samples" in sql:
            return _FakeResult(entry.get("sample"))
        if "measurement_ingestion_daily" in sql:
            return _FakeResult(entry.get("fallback"))
        # 未预期的查询：返回 None，避免误判
        return _FakeResult(None)

    # get_sync_session 的 with 语义在 FakeAdapter 里用 contextmanager 兜住，
    # 这里补齐 session 生命周期方法以防被直接调用。
    def commit(self) -> None:  # pragma: no cover - 未被 watermark 主动调用
        pass

    def rollback(self) -> None:  # pragma: no cover
        pass

    def close(self) -> None:  # pragma: no cover
        pass


class _FakeAdapter:
    """假 DBAdapter：get_sync_session() 产出查询感知的 FakeSession。

    每次进入 with 都新建一个 FakeSession，模拟真实的「一次会话一个上下文」，
    保证多设备连续查询时彼此独立。
    """

    def __init__(self, device_data: Dict[DeviceKey, Dict[str, Any]]) -> None:
        self._device_data = device_data

    @contextmanager
    def get_sync_session(self):
        yield _FakeSession(self._device_data)


def _make_service(device_data: Dict[DeviceKey, Dict[str, Any]]) -> DataWatermarkService:
    """用给定设备数据构造被测服务（注入假 adapter）。"""
    return DataWatermarkService(_FakeAdapter(device_data))  # type: ignore[arg-type]


# ────────────────────────────────────────────────────────────────────────────
# 用例
# ────────────────────────────────────────────────────────────────────────────


def test_watermark_returns_sample_max_when_present() -> None:
    """有 training_samples 主口径 → 返回该 datetime；date 版返回其自然日。

    Validates: Requirements 1.8, 3.1
    """
    dev: DeviceKey = ("siteA", "devA", "br1")
    sample_max = datetime(2021, 3, 15, 12, 30, 0)
    svc = _make_service({dev: {"sample": sample_max, "fallback": date(2021, 3, 10)}})

    assert svc.device_watermark(*dev) == sample_max
    # 主口径命中时不应回退到 ingestion 的更早业务日
    assert svc.device_watermark_date(*dev) == date(2021, 3, 15)


def test_watermark_falls_back_to_ingestion_when_no_samples() -> None:
    """主口径为空、有 ingestion 最大业务日 → 回退返回该日 00:00:00。

    Validates: Requirements 1.8, 3.1
    """
    dev: DeviceKey = ("siteB", "devB", "br2")
    svc = _make_service({dev: {"sample": None, "fallback": date(2020, 7, 1)}})

    assert svc.device_watermark(*dev) == datetime(2020, 7, 1, 0, 0, 0)
    assert svc.device_watermark_date(*dev) == date(2020, 7, 1)


def test_watermark_returns_none_when_no_data() -> None:
    """主口径与回退都无 → device_watermark 与 device_watermark_date 均为 None。

    Validates: Requirements 1.8, 3.1
    """
    dev: DeviceKey = ("siteC", "devC", "br3")
    svc = _make_service({dev: {"sample": None, "fallback": None}})

    assert svc.device_watermark(*dev) is None
    assert svc.device_watermark_date(*dev) is None


def test_watermark_none_for_unregistered_device() -> None:
    """完全未登记的设备（连记录都没有）→ None，验证查询感知 mock 的默认分支。

    Validates: Requirements 1.8
    """
    svc = _make_service({})
    assert svc.device_watermark("nope", "nope", "nope") is None
    assert svc.device_watermark_date("nope", "nope", "nope") is None


def test_multiple_devices_independent() -> None:
    """多设备独立：不同三元组返回各自水位，互不串扰（含主口径/回退/无数据混合）。

    Validates: Requirements 1.8, 3.1
    """
    dev_sample: DeviceKey = ("site1", "dev1", "b1")   # 走主口径
    dev_fallback: DeviceKey = ("site2", "dev2", "b2")  # 走回退
    dev_empty: DeviceKey = ("site3", "dev3", "b3")     # 无数据
    svc = _make_service({
        dev_sample: {"sample": datetime(2021, 1, 2, 8, 0, 0), "fallback": None},
        dev_fallback: {"sample": None, "fallback": date(2019, 12, 31)},
        dev_empty: {"sample": None, "fallback": None},
    })

    assert svc.device_watermark(*dev_sample) == datetime(2021, 1, 2, 8, 0, 0)
    assert svc.device_watermark(*dev_fallback) == datetime(2019, 12, 31, 0, 0, 0)
    assert svc.device_watermark(*dev_empty) is None

    # date 版同样彼此独立
    assert svc.device_watermark_date(*dev_sample) == date(2021, 1, 2)
    assert svc.device_watermark_date(*dev_fallback) == date(2019, 12, 31)
    assert svc.device_watermark_date(*dev_empty) is None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
# @AI_GENERATED: end
