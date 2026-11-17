# @AI_GENERATED
"""
算子验证状态登记 — 前端「已验证」徽标的单一事实来源。

硬规则（2026-07-21 起）：
  只有通过六重测试（L1–L6）的算子才可写入本集合。
  覆盖事实源：services.operator_test_coverage
  门禁：tests/test_operator_verification.py

未达标算子在前端显示「可执行·未验证」，不得标「已验证」。
环境依赖算子（如 load_hdf5 / load_mongodb）刻意不进六重交集。
"""
from __future__ import annotations

from typing import Iterable, List, Set

from services.operator_test_coverage import six_layer_passed

# 仅允许六重交集；禁止手工塞入未覆盖 ID。
VERIFIED_OPERATOR_IDS: frozenset[str] = six_layer_passed()


def filter_verified_registered(registered: Iterable[str]) -> List[str]:
    """返回已注册 ∩ 六重已通过 的排序列表。"""
    registered_set: Set[str] = set(registered)
    return sorted(op for op in VERIFIED_OPERATOR_IDS if op in registered_set)
# @AI_GENERATED: end
