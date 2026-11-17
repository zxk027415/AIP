# @AI_GENERATED
# -*- coding: utf-8 -*-
"""把一天里已占用的时段挖掉，得到「当天其余」区间。

天路径拆成点路径时：故障段写成 cluster + 故障类；其余区间写成 cluster + 0。
两段不重叠，不需要第二个 source，也不靠优先级去压 day_label。
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Sequence, Tuple

Interval = Tuple[datetime, datetime]


def merge_intervals(intervals: Iterable[Interval]) -> List[Interval]:
    """合并重叠或相接的半开区间 [start, end)。"""
    items = sorted((a, b) for a, b in intervals if a < b)
    if not items:
        return []
    merged: List[Interval] = [items[0]]
    for start, end in items[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def complement_intervals(day_start: datetime, day_end: datetime, occupied: Sequence[Interval]) -> List[Interval]:
    """[day_start, day_end) 里去掉 occupied 后剩下的区间，即当天其余点。"""
    if not (day_start < day_end):
        return []
    holes: List[Interval] = []
    cursor = day_start
    for start, end in merge_intervals(occupied):
        clipped_start = max(start, day_start)
        clipped_end = min(end, day_end)
        if clipped_start >= clipped_end:
            continue
        if cursor < clipped_start:
            holes.append((cursor, clipped_start))
        cursor = max(cursor, clipped_end)
        if cursor >= day_end:
            break
    if cursor < day_end:
        holes.append((cursor, day_end))
    return holes
# @AI_GENERATED: end
