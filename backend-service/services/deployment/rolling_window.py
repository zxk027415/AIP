# @AI_GENERATED
"""
services/deployment/rolling_window — 滚动训练窗口计算器

职责（Responsibilities）：
  - 根据每日触发日期 T，从可用历史数据中挑选训练窗口
  - 强制 Gap-One-Day 约束：训练数据截止 T-1，绝不使用 T 日或更新日期数据
  - 支持窗口截断（`max_window_days`）：仅保留最近 M 天数据，超出部分从最早端截断
  - 计算预测目标日期 = T + 1 日

用法（Usage）：
  被 `SchedulerEngine`（调度引擎）每日调用一次，输入为触发日期、最大窗口天数
  和当前可用的历史数据日期集合，输出一个纯值对象 `TrainingWindow`，描述本次
  训练应使用的日期范围与实际入选的日期列表。

设计要点（Design notes）：
  - 纯函数、无 I/O、无副作用，便于属性测试（Property Test）
  - 只依赖标准库（datetime、dataclasses、typing）
  - 输入可以是 `datetime.date`，也可以是 `datetime.datetime`（会规范化为 date）
  - 输入无序、含重复均可容忍，内部会去重并升序排序
  - 对应 design.md 中 Correctness Property 1 与 requirements 4.2/4.3/4.4/4.7

术语对照（Terminology）：
  - `trigger_date` — 触发日期（记为 T），一般为当日日期
  - `max_window_days` — 最大窗口天数 M；None 表示不限制
  - `available_data` — 可用的历史数据日期集合（每条数据的日期，通常是数据落库日）
  - `training_end` — 训练窗口结束日期（含），受 Gap-One-Day 约束 ≤ T-1
  - `training_start` — 训练窗口起始日期（含）
  - `predict_target` — 预测目标日期，恒等于 T+1（即便没有训练数据）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Union

DateLike = Union[date, datetime]


@dataclass(frozen=True)
class TrainingWindow:
    """训练窗口计算结果 — 不可变值对象

    字段说明（Fields）：
      trigger_date         — 触发日期 T（保留用于审计与日志）
      training_start       — 训练窗口起始日期（含）；无可用数据时为 None
      training_end         — 训练窗口结束日期（含）；无可用数据时为 None
                             恒 ≤ trigger_date - 1（Gap-One-Day 约束）
      predict_target       — 预测目标日期 = trigger_date + 1 日（总是有值）
      window_days          — 实际窗口天数 = training_end - training_start + 1
                             无可用数据时为 0（注意：≠ max_window_days）
      truncated            — 是否因 max_window_days 触发了从最早端的截断
                             为 True 表示原始数据中存在早于窗口起点的日期被丢弃
      included_dates       — 实际入选参与训练的日期（去重、升序）
                             严格满足 date ≤ trigger_date - 1
    """

    trigger_date: date
    training_start: Optional[date]
    training_end: Optional[date]
    predict_target: date
    window_days: int
    truncated: bool
    included_dates: List[date] = field(default_factory=list)


def _to_date(value: DateLike) -> date:
    """将 `date` 或 `datetime` 规范化为 `date`

    说明：`datetime` 是 `date` 的子类，`isinstance(dt, date)` 会为 True。
    这里显式判断 `datetime` 并取其 `.date()`，避免把带时分秒的对象直接塞进
    日期集合造成排序 / 去重语义混乱。
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(
        f"available_data 中的元素必须是 datetime.date 或 datetime.datetime，"
        f"实际收到：{type(value).__name__}"
    )


def compute_training_window(
    trigger_date: DateLike,
    max_window_days: Optional[int],
    available_data: Iterable[DateLike],
) -> TrainingWindow:
    """根据触发日期与可用数据计算训练窗口

    参数（Parameters）：
      trigger_date       — 触发日期 T（`date` 或 `datetime`）
      max_window_days    — 最大窗口天数 M；`None` 表示不做长度截断；
                           必须为 `None` 或正整数（> 0），否则抛 ValueError
      available_data     — 可用历史数据的日期集合（可迭代，允许重复 / 乱序）

    返回（Returns）：
      TrainingWindow — 见类文档

    语义（Semantics，对应 Correctness Property 1）：
      (a) training_end ≤ T-1（Gap-One-Day，绝不使用 T 日或未来数据）
      (b) 训练集包含 available_data 中所有 date ≤ T-1 的记录
      (c) 若可用数据跨度超过 M 天，只保留最近 M 天，即窗口起点 = T-1-M+1
      (d) predict_target = T+1
      (e) 新数据到达后无需重配，下一次调用自动纳入
      (f) 结果中不会出现 date ≥ T 的任何记录（Gap 强制执行）
    """
    trigger_d: date = _to_date(trigger_date)

    # (d) 预测目标 = T + 1（无论训练窗口是否为空，预测目标恒有值）
    predict_target: date = trigger_d + timedelta(days=1)

    # 校验 max_window_days：允许 None 或正整数
    if max_window_days is not None:
        if not isinstance(max_window_days, int) or isinstance(max_window_days, bool):
            raise TypeError(
                f"max_window_days 必须是 int 或 None，实际收到：{type(max_window_days).__name__}"
            )
        if max_window_days <= 0:
            raise ValueError(
                f"max_window_days 必须为正整数或 None，实际收到：{max_window_days}"
            )

    # Gap-One-Day 边界：训练允许的最晚日期
    gap_cutoff: date = trigger_d - timedelta(days=1)

    # (a)(b)(f) 过滤：只保留 date ≤ T-1 的记录；顺便去重
    filtered: set[date] = set()
    for raw in available_data:
        d = _to_date(raw)
        if d <= gap_cutoff:
            filtered.add(d)

    # 无可用训练数据 → 返回空窗口
    if not filtered:
        return TrainingWindow(
            trigger_date=trigger_d,
            training_start=None,
            training_end=None,
            predict_target=predict_target,
            window_days=0,
            truncated=False,
            included_dates=[],
        )

    sorted_dates: List[date] = sorted(filtered)
    earliest: date = sorted_dates[0]

    # (c) 窗口长度截断：若指定 M，则起点 = max(earliest, T-1-M+1)
    truncated = False
    if max_window_days is not None:
        # 窗口最早允许的日期：T-1 减去 (M-1) 天
        window_floor: date = gap_cutoff - timedelta(days=max_window_days - 1)
        if earliest < window_floor:
            truncated = True
            sorted_dates = [d for d in sorted_dates if d >= window_floor]
            # 过滤后可能变空（数据都比 max_window_days 窗口还老）
            if not sorted_dates:
                return TrainingWindow(
                    trigger_date=trigger_d,
                    training_start=None,
                    training_end=None,
                    predict_target=predict_target,
                    window_days=0,
                    truncated=True,
                    included_dates=[],
                )

    training_start: date = sorted_dates[0]
    training_end: date = sorted_dates[-1]
    window_days: int = (training_end - training_start).days + 1

    return TrainingWindow(
        trigger_date=trigger_d,
        training_start=training_start,
        training_end=training_end,
        predict_target=predict_target,
        window_days=window_days,
        truncated=truncated,
        included_dates=sorted_dates,
    )


__all__ = [
    "TrainingWindow",
    "compute_training_window",
]
# @AI_GENERATED: end
