# @AI_GENERATED
"""三条路径的喂数到达语义 —— 单一事实来源，供回放链路与观测 API 消费。

设计意图（用户原话）：

    "点路径的按照点的形式来推进来喂数据，tsc 和 rf 要求要等一天达到"
    "每个路径设备到达缺失的处理方式也不一样"

三条路径的粒度、到达判据、缺失处置**本来就不同**，这是设计而非缺陷。本模块把它们
集中声明出来，避免回放链路 / 观测 API / 前端各自猜一套、各自漂移。

数值一律引用既有唯一来源，**不另立常量**：

  - 日级阈值：``services/slot_datasets/observability_ledger.py``
    （``EXPECTED_POINTS=288`` / ``OCCUPANCY_READY=173`` / ``HOLD_DAYS=3``）
  - TSC 窗口覆盖率：``services/iterative_labeling/tsc/sliding_window_sampler.py``
    的 ``SamplerConfig.min_coverage``（默认 0.9），与 ``config/pv_tsc.yaml`` 同值
  - 点级因果：``services/timeseries_point/replay_activity.py``
    的 ``PointReplaySession.batch_policy``（``max_points_per_step=1``）

本模块只做声明与判据：不写盘、不持有状态、模块级不 import 重型依赖。
"""

from __future__ import annotations

from typing import Any, Dict

#: 推进粒度 —— 点级按单个测点推进；设备日级攒满一天再推进。
GRANULARITY_POINT = "point"
GRANULARITY_DEVICE_DAY = "device_day"

#: 三条产品路径（与 frontend-sevice/src/config/slotProductConfig.ts 的 PV_PRODUCT_SLOTS 对齐）。
SUPPORTED_SLOTS = ("pv_day", "pv_point", "pv_tsc")

#: TSC 窗口覆盖率下限。与
#: ``services/iterative_labeling/tsc/sliding_window_sampler.py`` 的
#: ``SamplerConfig.min_coverage`` 和 ``config/pv_tsc.yaml`` 的 ``min_coverage`` 同值；
#: 由 test_feed_semantics_gates.py 断言三者一致，避免任一处改动后静默漂移。
TSC_MIN_COVERAGE = 0.9

_GRANULARITY: Dict[str, str] = {
    "pv_point": GRANULARITY_POINT,
    "pv_day": GRANULARITY_DEVICE_DAY,
    "pv_tsc": GRANULARITY_DEVICE_DAY,
}

#: 到达判据：点级无整日门槛；日级等 occupancy 到齐；TSC 另外加窗口覆盖率门槛。
_ARRIVAL_GATE: Dict[str, str] = {
    "pv_point": "per_point",
    "pv_day": "occupancy_ready",
    "pv_tsc": "coverage_gated",
}

#: 缺失处置：点缺失不牵连其它点；日级等待后超期放弃并留痕；TSC 用 ``is_measured`` 掩码承载。
_MISSING_POLICY: Dict[str, str] = {
    "pv_point": "point_absent",
    "pv_day": "wait_then_expire",
    "pv_tsc": "masked_is_measured",
}

#: ``resolve_arrival_status`` 的三种出口状态。
STATUS_READY = "ready"
STATUS_WAITING = "waiting"
STATUS_EXPIRED = "expired_incomplete"


class FeedSemanticsError(ValueError):
    """未知 slot —— fail-closed，不猜默认语义。"""

    def __init__(self, slot: str) -> None:
        self.slot = str(slot or "")
        super().__init__(
            f"unknown slot for feed semantics: {self.slot!r}; "
            f"expected one of {SUPPORTED_SLOTS!r}"
        )


def _assert_slot(slot: str) -> str:
    key = str(slot or "").strip()
    if key not in SUPPORTED_SLOTS:
        raise FeedSemanticsError(key)
    return key


def _day_thresholds() -> Dict[str, int]:
    """日级阈值 —— 从唯一来源读取，不在本模块复制数值。"""
    from services.slot_datasets.observability_ledger import (
        EXPECTED_POINTS,
        HOLD_DAYS,
        OCCUPANCY_READY,
    )

    return {
        "expected_points": int(EXPECTED_POINTS),
        "occupancy_ready": int(OCCUPANCY_READY),
        "hold_days": int(HOLD_DAYS),
    }


def granularity_for(slot: str) -> str:
    """该路径的推进粒度（``point`` 或 ``device_day``）。"""
    return _GRANULARITY[_assert_slot(slot)]


def arrival_gate_for(slot: str) -> Dict[str, Any]:
    """该路径的到达判据，含阈值与阈值来源，便于 UI 原样展示。"""
    key = _assert_slot(slot)
    gate = _ARRIVAL_GATE[key]
    day = _day_thresholds() if gate != "per_point" else None
    if gate == "per_point":
        return {
            "slot": key,
            "gate": gate,
            "threshold_source": "replay_activity.PointReplaySession.batch_policy",
            "min_points": None,
            "expected_points": None,
            "min_coverage": None,
            "hold_days": None,
            "note": "按点到达即可推进，不设整日门槛",
        }
    if gate == "occupancy_ready":
        assert day is not None
        return {
            "slot": key,
            "gate": gate,
            "threshold_source": "observability_ledger.OCCUPANCY_READY",
            "min_points": day["occupancy_ready"],
            "expected_points": day["expected_points"],
            "min_coverage": None,
            "hold_days": day["hold_days"],
            "note": (
                f"等整日到齐：需 >= {day['occupancy_ready']}/{day['expected_points']} 点；"
                f"未齐进 waiting，超 {day['hold_days']} 天转 expired_incomplete"
            ),
        }
    assert day is not None
    return {
        "slot": key,
        "gate": gate,
        "threshold_source": "sliding_window_sampler.SamplerConfig.min_coverage",
        "min_points": day["occupancy_ready"],
        "expected_points": day["expected_points"],
        "min_coverage": TSC_MIN_COVERAGE,
        "hold_days": day["hold_days"],
        "note": (
            f"等整日 + 窗口覆盖率 >= {TSC_MIN_COVERAGE}；"
            f"缺测由 is_measured 掩码承载，不丢样本；超 {day['hold_days']} 天转 expired_incomplete"
        ),
    }


def missing_policy_for(slot: str) -> Dict[str, Any]:
    """该路径的缺失处置语义。"""
    key = _assert_slot(slot)
    policy = _MISSING_POLICY[key]
    notes = {
        "point_absent": "点级：该点没到就是没到，不牵连同设备其它点；因果窗只读已提交历史",
        "wait_then_expire": "设备日级：整台设备当天未到齐则 waiting，超期转 expired_incomplete 并留痕",
        "masked_is_measured": "设备日级：缺测由第三通道 is_measured 置 0 承载，样本不丢弃",
    }
    return {"slot": key, "policy": policy, "note": notes[policy]}


def resolve_arrival_status(
    slot: str,
    *,
    arrived_points: int = 0,
    waited_days: int = 0,
    coverage: float | None = None,
) -> Dict[str, Any]:
    """判定某设备-日（或某点）当前是否可推进。

    返回 ``{"status": ..., "reason": ..., "gate": ...}``，其中 ``status`` 取
    ``ready`` / ``waiting`` / ``expired_incomplete``。

    - 点级（pv_point）：恒 ``ready`` —— 点到达即可用，没有整日门槛。
    - 日级（pv_day）：``arrived_points >= OCCUPANCY_READY`` → ready；
      否则 ``waited_days >= HOLD_DAYS`` → expired_incomplete，否则 waiting。
    - TSC（pv_tsc）：在日级门槛之上再要求 ``coverage >= TSC_MIN_COVERAGE``；
      未达覆盖率时同样受 hold_days 约束。

    本函数是纯判据，不读盘、不写状态；调用方负责提供 arrived_points / waited_days /
    coverage。缺参时按最保守解释（未到齐 / 未超期 → waiting）。
    """
    key = _assert_slot(slot)
    gate = arrival_gate_for(key)
    arrived = max(0, int(arrived_points))
    waited = max(0, int(waited_days))

    if gate["gate"] == "per_point":
        return {
            "status": STATUS_READY,
            "reason": "per_point_arrival",
            "gate": gate,
        }

    day = _day_thresholds()
    coverage_ok = True
    if gate["gate"] == "coverage_gated":
        if coverage is None:
            coverage_ok = False
        else:
            coverage_ok = float(coverage) >= TSC_MIN_COVERAGE

    if arrived >= day["occupancy_ready"] and coverage_ok:
        return {
            "status": STATUS_READY,
            "reason": "occupancy_and_coverage_met" if gate["gate"] == "coverage_gated" else "occupancy_met",
            "gate": gate,
        }

    if waited >= day["hold_days"]:
        return {
            "status": STATUS_EXPIRED,
            "reason": "expired_incomplete",
            "gate": gate,
        }

    return {
        "status": STATUS_WAITING,
        "reason": "incomplete_coverage" if not coverage_ok else "incomplete_occupancy",
        "gate": gate,
    }


def describe_slot(slot: str) -> Dict[str, Any]:
    """把该 slot 的完整语义打包，供 API 直接返回给前端。"""
    key = _assert_slot(slot)
    return {
        "slot": key,
        "granularity": granularity_for(key),
        "arrival_gate": arrival_gate_for(key),
        "missing_policy": missing_policy_for(key),
    }


def describe_all() -> Dict[str, Any]:
    """三条路径的语义清单。"""
    return {slot: describe_slot(slot) for slot in SUPPORTED_SLOTS}
