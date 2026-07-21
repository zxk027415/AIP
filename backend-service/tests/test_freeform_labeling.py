# -*- coding: utf-8 -*-
"""自由时间窗打标：窗口键、重叠检测与服务编排。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from services.iterative_labeling.freeform_labeling import (
    FreeformLabelingService,
    freeform_time_window_key,
    freeform_unit_key,
)


def test_freeform_time_window_key_is_stable():
    key = freeform_time_window_key("2026-07-20 10:00:00", "2026-07-20 11:30:00")
    assert key == "2026-07-20T10:00:00__2026-07-20T11:30:00#freeform"
    assert "freeform" in freeform_unit_key(
        "s1", "d1", "b1", "2026-07-20 10:00:00", "2026-07-20 11:30:00"
    )


class _FakeReviewService:
    def __init__(self, session: Dict[str, Any]):
        self.session = session
        self.review_repo = self

    def get_session(self, review_id: str) -> Dict[str, Any]:
        if review_id != self.session.get("review_id"):
            raise KeyError(review_id)
        return self.session

    def save_verdict(self, slot: str, review_id: str, verdict: Dict[str, Any]) -> None:
        self.session = verdict


class _FakeRegistry:
    def allocate_label(self, name: str) -> Dict[str, Any]:
        return {"label_id": 99, "label_name": name}


class _FakeWorkspace:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def create_confirmed_time_slice(self, **kwargs) -> Dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "slice_id": "slice-abc",
            "dataset_path": (
                "backend-service/data/iterative_labeling/training_workspace/"
                "pv_fault/time_slices/slice-abc.csv"
            ),
            "row_count": 4,
        }


class _FakeCumulative:
    def __init__(self):
        self.paths: List[str] = []

    def register_labeled_dataset(
        self, dataset_path: str, source_name: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        self.paths.append(dataset_path)
        return {
            "import_id": "imp-1",
            "admitted": True,
            "imported": True,
            "source_name": source_name,
            "change_units": kwargs.get("change_units", 1),
            "next_retrain_in": 19,
        }


def _base_session() -> Dict[str, Any]:
    return {
        "review_id": "rev-freeform-test",
        "status": "reviewing",
        "units": [
            {
                "unit_key": "s1|d1|b1|2026-07-20",
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b1",
            }
        ],
        "freeform_labels": [],
        "prediction_context": {"source_csv_path": "backend-service/data/uploads/src.csv"},
    }


def test_create_freeform_label_uses_window_override_and_registers():
    session = _base_session()
    review = _FakeReviewService(session)
    workspace = _FakeWorkspace()
    cumulative = _FakeCumulative()
    service = FreeformLabelingService(
        slot="pv_fault",
        review_service=review,  # type: ignore[arg-type]
        registry=_FakeRegistry(),  # type: ignore[arg-type]
        workspace=workspace,  # type: ignore[arg-type]
        cumulative=cumulative,  # type: ignore[arg-type]
    )

    record = service.create_label(
        "rev-freeform-test",
        t_start="2026-07-20 10:00:00",
        t_end="2026-07-20 10:45:00",
        action_type="correct",
        verdict_label=0,
        source_unit_key="s1|d1|b1|2026-07-20",
        reviewer="tester",
    )

    assert record["time_window"] == "2026-07-20T10:00:00__2026-07-20T10:45:00#freeform"
    assert workspace.calls[0]["time_window_override"] == record["time_window"]
    assert workspace.calls[0]["label_id"] == 0
    assert cumulative.paths == [record["dataset_path"]]
    assert len(service.list_labels("rev-freeform-test")) == 1

    with pytest.raises(ValueError, match="重叠"):
        service.create_label(
            "rev-freeform-test",
            t_start="2026-07-20 10:30:00",
            t_end="2026-07-20 11:00:00",
            action_type="correct",
            verdict_label=0,
            source_unit_key="s1|d1|b1|2026-07-20",
        )

    revoked = service.revoke_label("rev-freeform-test", record["unit_key"])
    assert revoked["remaining"] == 0


def test_create_freeform_new_label_allocates_registry_id():
    session = _base_session()
    workspace = _FakeWorkspace()
    service = FreeformLabelingService(
        slot="pv_fault",
        review_service=_FakeReviewService(session),  # type: ignore[arg-type]
        registry=_FakeRegistry(),  # type: ignore[arg-type]
        workspace=workspace,  # type: ignore[arg-type]
        cumulative=_FakeCumulative(),  # type: ignore[arg-type]
    )
    record = service.create_label(
        "rev-freeform-test",
        t_start="2026-07-20 12:00:00",
        t_end="2026-07-20 12:30:00",
        action_type="new_label",
        new_label_name="夜间漏电流",
        source_unit_key="s1|d1|b1|2026-07-20",
    )
    assert record["verdict_label"] == 99
    assert workspace.calls[0]["label_id"] == 99
