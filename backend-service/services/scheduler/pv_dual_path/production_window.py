# @AI_GENERATED
# -*- coding: utf-8 -*-
"""生产车道责任窗口：Epoch 边界与 historical_backfill 排他。

两条生产策略共用：业务日必须落在当前 Epoch 设备责任内，且不得落入
``historical_backfill`` 半开区间。缺边界的设备本轮不生产检测。
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from services.scheduler.pv_dual_path.path_activation import (
    DeviceScope,
    HISTORICAL_BACKFILL_LANE,
    PathActivationService,
)


def is_historical_backfill_date(
    activation: Optional[PathActivationService],
    epoch_id: str,
    scope: DeviceScope,
    business_date: date,
) -> bool:
    if activation is None or not epoch_id:
        return False
    claim = activation.current_claim(
        epoch_id,
        scope,
        business_date,
        lane=HISTORICAL_BACKFILL_LANE,
    )
    return claim is not None


def is_production_responsible_date(
    activation: Optional[PathActivationService],
    epoch_id: str,
    scope: DeviceScope,
    business_date: date,
) -> bool:
    """True 当且仅当该自然日属于当前 Epoch 生产车道且未被历史回放认领。"""
    if activation is None or not str(epoch_id or "").strip():
        return True
    device_scope = activation.current_device_boundary(epoch_id, scope)
    if device_scope is None or device_scope.effective_from_date is None:
        return False
    if business_date < device_scope.effective_from_date:
        return False
    if is_historical_backfill_date(activation, epoch_id, scope, business_date):
        return False
    production_claim = activation.current_claim(epoch_id, scope, business_date, lane="production")
    if production_claim is None:
        return False
    return True
# @AI_GENERATED: end
