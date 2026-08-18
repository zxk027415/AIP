# @AI_GENERATED
# -*- coding: utf-8 -*-
"""生产车道责任窗口：Epoch 边界与 historical_backfill 排他。"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from services.scheduler.pv_dual_path.path_activation import DeviceScope
from services.scheduler.pv_dual_path.production_window import (
    is_historical_backfill_date,
    is_production_responsible_date,
)


class _FakeActivation:
    def __init__(self, *, from_date: date, historical=None, production=None) -> None:
        self.from_date = from_date
        self.historical = historical
        self.production = production

    def current_device_boundary(self, epoch_id, scope):
        return SimpleNamespace(effective_from_date=self.from_date)

    def current_claim(self, epoch_id, scope, business_date, *, lane=None):
        if lane == "historical_backfill":
            return self.historical if (
                self.historical is not None
                and self.historical["start"] <= business_date < self.historical["end"]
            ) else None
        if lane == "production":
            return self.production if business_date >= self.from_date else None
        return None


def test_historical_backfill_dates_are_excluded() -> None:
    activation = _FakeActivation(
        from_date=date(2021, 1, 1),
        historical={"start": date(2021, 1, 1), "end": date(2021, 1, 8)},
        production=object(),
    )
    scope = DeviceScope("s", "d", "b")
    assert is_historical_backfill_date(activation, "epoch-1", scope, date(2021, 1, 5))
    assert not is_production_responsible_date(activation, "epoch-1", scope, date(2021, 1, 5))
    assert is_production_responsible_date(activation, "epoch-1", scope, date(2021, 1, 8))


def test_missing_effective_from_is_not_production() -> None:
    activation = _FakeActivation(from_date=None)  # type: ignore[arg-type]
    activation.from_date = None
    scope = DeviceScope("s", "d", "b")
    assert not is_production_responsible_date(activation, "epoch-1", scope, date(2021, 1, 1))


def test_no_activation_keeps_legacy_tests_permissive() -> None:
    scope = DeviceScope("s", "d", "b")
    assert is_production_responsible_date(None, "", scope, date(2021, 1, 1))
# @AI_GENERATED: end
