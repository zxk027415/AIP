# @AI_GENERATED
# -*- coding: utf-8 -*-
"""Property 23、25：相对路径落盘与严格 JSON boolean。"""
from __future__ import annotations

from pathlib import Path
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from services.scheduler.pv_dual_path.persistence_utils import (
    atomic_write_json,
    require_strict_json_boolean,
    to_relative_path,
)
from services.scheduler.pv_dual_path.path_isolation import PathIsolationRegistry, PartitionWriteError


_relatives = st.text(
    alphabet=st.sampled_from(list("abcdef012345/-_")),
    min_size=1,
    max_size=24,
).filter(lambda value: value.strip() not in {".", "/", "-"} and not value.startswith("/") and ".." not in value)
_bools = st.booleans()
_truthy = st.sampled_from(["true", "True", "1", "yes", 1, 1.0, "false", 0, "yes"])


# Feature: pv-fault-dual-path-serving, Property 23: 持久化路径恒为相对路径
@given(name=_relatives)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_23_persisted_paths_are_relative(tmp_path: Path, name: str) -> None:
    relative = f"{uuid.uuid4().hex}/{Path(str(name).strip('/') or 'artifact.json').name}"
    written = atomic_write_json(relative, {"ok": True}, base_dir=tmp_path)
    assert not Path(written).is_absolute()
    assert "\\" not in written
    inside = tmp_path / "models" / "a.pkl"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text("x", encoding="utf-8")
    converted = to_relative_path(inside, base_dir=tmp_path)
    assert converted == "models/a.pkl"
    outside = Path("C:/windows/temp/secret.pkl") if tmp_path.drive else Path("/tmp/outside-secret.pkl")
    with pytest.raises(ValueError):
        to_relative_path(outside, base_dir=tmp_path)


# Feature: pv-fault-dual-path-serving, Property 25: 审计布尔严格 JSON
@given(flag=_bools, bad=_truthy)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_25_audit_booleans_reject_string_truthy(tmp_path: Path, flag: bool, bad: object) -> None:
    assert require_strict_json_boolean(flag, "confirm") is flag
    with pytest.raises(TypeError):
        require_strict_json_boolean(bad, "confirm")
    adapter = type("A", (), {"get_sync_session": lambda self: None})()
    registry = PathIsolationRegistry(adapter, backend_service_dir=tmp_path / uuid.uuid4().hex)  # type: ignore[arg-type]
    relative = registry.write_batch(
        "pv_fault",
        "legacy_day",
        f"batch-{uuid.uuid4().hex}",
        {
            "set_as_production": flag,
            "artifact_path": "data/models/a.pkl",
            "business_date": "2026-01-01",
            "input_fingerprint": "a" * 64,
            "supersedes_batch_id": None,
        },
    )
    assert not Path(relative).is_absolute()
    with pytest.raises((TypeError, PartitionWriteError, ValueError)):
        registry.write_batch(
            "pv_fault",
            "legacy_day",
            "batch-bad",
            {
                "set_as_production": bad,
                "artifact_path": "data/models/b.pkl",
                "business_date": "2026-01-01",
                "input_fingerprint": "b" * 64,
                "supersedes_batch_id": None,
            },
        )
# @AI_GENERATED: end
