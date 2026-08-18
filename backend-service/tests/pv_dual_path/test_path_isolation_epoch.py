# @AI_GENERATED
# -*- coding: utf-8 -*-
"""PathIsolationRegistry 的 Epoch 初始边界、必填记录与不可变修订批次测试。"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import pytest

from services.scheduler.pv_dual_path.path_isolation import (
    PartitionBoundaryError,
    PartitionWriteError,
    PathIsolationRegistry,
)


class _EmptyCursorSession:
    def get(self, _model, _pk):
        return None


class _Adapter:
    @contextmanager
    def get_sync_session(self):
        yield _EmptyCursorSession()


class _Repo:
    def __init__(self):
        self.records = []

    def insert_prediction_records(self, records):
        self.records.extend(records)
        return records


def _device():
    return {"site_id": "s", "device_id": "d", "branch_id": "b"}


def test_missing_cursor_uses_current_epoch_boundary_and_never_other_path(tmp_path: Path) -> None:
    seen = []
    registry = PathIsolationRegistry(
        _Adapter(),  # type: ignore[arg-type]
        backend_service_dir=tmp_path,
        boundary_reader=lambda epoch_id, device: seen.append((epoch_id, device)) or date(2026, 6, 19),
    )
    assert registry.get_cursor_or_initial("pv_fault", "seq_annotation", _device(), "epoch-2") == date(2026, 6, 19)
    assert seen == [("epoch-2", _device())]


def test_missing_epoch_boundary_returns_diagnostic_error(tmp_path: Path) -> None:
    registry = PathIsolationRegistry(
        _Adapter(),  # type: ignore[arg-type]
        backend_service_dir=tmp_path,
        boundary_reader=lambda *_: None,
    )
    with pytest.raises(PartitionBoundaryError) as exc:
        registry.get_cursor_or_initial("pv_fault", "seq_annotation", _device(), "epoch-2")
    assert exc.value.activation_epoch_id == "epoch-2"
    assert exc.value.reason == "effective_from_date_missing"


def test_prediction_records_are_stamped_and_require_business_date(tmp_path: Path) -> None:
    repo = _Repo()
    registry = PathIsolationRegistry(_Adapter(), backend_service_dir=tmp_path)  # type: ignore[arg-type]
    written = registry.write_prediction_records(
        repo,
        "pv_fault",
        "seq_annotation",
        [{"site_id": "s", "device_id": "d", "branch_id": "b", "business_date": "2026-06-19"}],
    )
    assert written[0]["slot"] == "pv_fault"
    assert written[0]["modeling_path"] == "seq_annotation"
    assert written[0]["business_date"] == date(2026, 6, 19)

    with pytest.raises(PartitionWriteError, match="business_date"):
        registry.write_prediction_records(repo, "pv_fault", "seq_annotation", [_device()])


def test_revision_batch_is_immutable_and_points_to_previous_batch(tmp_path: Path) -> None:
    registry = PathIsolationRegistry(
        _Adapter(), backend_service_dir=tmp_path,  # type: ignore[arg-type]
    )
    first_ref = registry.write_batch(
        "pv_fault",
        "seq_annotation",
        "batch-1",
        {
            "business_date": "2026-06-19",
            "input_fingerprint": "a" * 64,
            "supersedes_batch_id": None,
            "artifact_path": "data/models/a.pkl",
        },
    )
    first_path = tmp_path / first_ref
    original = first_path.read_bytes()
    second_ref = registry.write_batch(
        "pv_fault",
        "seq_annotation",
        "batch-2",
        {
            "business_date": "2026-06-19",
            "input_fingerprint": "b" * 64,
            "supersedes_batch_id": "batch-1",
        },
    )
    assert first_path.read_bytes() == original
    second = json.loads((tmp_path / second_ref).read_text(encoding="utf-8"))
    assert second["supersedes_batch_id"] == "batch-1"
    assert not Path(first_ref).is_absolute() and not Path(second_ref).is_absolute()

    with pytest.raises(PartitionWriteError, match="不可覆盖"):
        registry.write_batch(
            "pv_fault",
            "seq_annotation",
            "batch-1",
            {
                "business_date": "2026-06-19",
                "input_fingerprint": "c" * 64,
                "supersedes_batch_id": "batch-2",
            },
        )
# @AI_GENERATED: end
