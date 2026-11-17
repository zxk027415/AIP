# -*- coding: utf-8 -*-
"""
services/iterative_labeling/sample_id.py — 统一 sample_id 生成与解析

训练样本用 ``smp-`` 前缀，推理样本用 ``inf-`` 前缀；格式恒含 ``#`` 供
time_window_split 透传判定。可解析回设备哈希、起点时刻、period_role、序号。

对应 design.md 组件 5。需求：8.1~8.6, 8.8, 8.9, 8.11
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, Optional

_SAMPLE_ID_RE = re.compile(
    r"^(?P<ns>smp|inf)-(?P<dev_hash>[0-9a-f]{8})-"
    r"(?P<t_start>\d{8}T\d{6})#(?P<period_role>[a-z_]+)#(?P<seq>\d+)$"
)


def device_hash8(site_id: str, device_id: str, branch_id: str) -> str:
    """设备三元组的 8 位十六进制哈希（写入 sample_id）。"""
    key = f"{site_id}|{device_id}|{branch_id}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def make_sample_id(
    site_id: str,
    device_id: str,
    branch_id: str,
    t_start: datetime,
    period_role: str,
    seq: int,
    namespace: str = "smp",
) -> str:
    """生成 ``{namespace}-{dev_hash8}-{t_start}#{period_role}#{seq}``。"""
    dev = device_hash8(site_id, device_id, branch_id)
    ts = t_start.strftime("%Y%m%dT%H%M%S")
    return f"{namespace}-{dev}-{ts}#{period_role}#{int(seq)}"


def parse_sample_id(sample_id: str) -> Dict[str, Any]:
    """解析 sample_id，返回 namespace/dev_hash/t_start/period_role/seq。"""
    text = str(sample_id or "").strip()
    match = _SAMPLE_ID_RE.match(text)
    if not match:
        raise ValueError(f"无法解析 sample_id: {text!r}")
    groups = match.groupdict()
    return {
        "namespace": groups["ns"],
        "dev_hash8": groups["dev_hash"],
        "t_start": datetime.strptime(groups["t_start"], "%Y%m%dT%H%M%S"),
        "period_role": groups["period_role"],
        "seq": int(groups["seq"]),
        "sample_id": text,
    }


def is_sample_id(value: Optional[str]) -> bool:
    """判断字符串是否为合法 sample_id（含 ``#``）。"""
    if not value or "#" not in str(value):
        return False
    try:
        parse_sample_id(str(value))
        return True
    except ValueError:
        return False
