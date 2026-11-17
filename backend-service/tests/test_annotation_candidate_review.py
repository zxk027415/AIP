"""annotation candidate -> rev-* review session (detection group)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.iterative_labeling.label_registry import LabelRegistryService
from services.iterative_labeling.storage.file_backend import FileReviewResultRepository
from services.slot_datasets.annotation_candidate_review import (
    create_review_session_from_detection_group,
    detection_group_id,
    list_pending_detection_groups,
)

EXEC_ID = "rq-test-batch"


@pytest.fixture()
def review_tmp(tmp_path, monkeypatch):
    backend_dir = tmp_path
    source = backend_dir / "data" / "slot_datasets" / "pv_point" / "snapshots" / "snap-pv_point-v5.parquet"
    source.parent.mkdir(parents=True, exist_ok=True)

    import pandas as pd

    frame = pd.DataFrame(
        {
            "time": pd.to_datetime(["2021-08-23 08:00:00+00:00", "2021-08-24 08:00:00+00:00"], utc=True),
            "site_id": ["s1", "s1"],
            "device_id": ["d1", "d2"],
            "branch_id": ["b1", "b1"],
            "value": [1.0, 1.1],
            "label": [9, 10],
        }
    )
    frame.to_parquet(source, index=False)

    review_root = backend_dir / "data" / "iterative_labeling"
    review_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ITERATIVE_LABELING_DATA_ROOT", str(review_root))

    import services.slot_datasets.annotation_candidates as ac
    import services.slot_datasets.annotation_candidate_review as acr

    monkeypatch.setattr(ac, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(ac, "_DATA_DIR", backend_dir / "data" / "slot_datasets")
    monkeypatch.setattr(acr, "_BACKEND_DIR", backend_dir)
    rel_source = source.relative_to(backend_dir).as_posix()
    monkeypatch.setattr(acr, "_SLOT_DEFAULT_SOURCE", {"pv_point": rel_source})

    return backend_dir, rel_source


def test_one_detection_group_one_review_session(review_tmp):
    _backend_dir, rel_source = review_tmp
    import services.slot_datasets.annotation_candidates as ac

    ac._save_items(
        "pv_point",
        [
            {
                "annotation_candidate_id": "ac-test001",
                "slot": "pv_point",
                "source_workflow_id": "path-a-manual-gold",
                "source_execution_id": EXEC_ID,
                "entity_key": "s1|d1|b1",
                "boundary_start": "2021-08-23T00:00:00+00:00",
                "boundary_end": "2021-08-24T00:00:00+00:00",
                "suggested_label": 9,
                "review_status": "pending",
                "date": "2021-08-23",
                "source_day_snapshot_path": rel_source,
                "registered_at": "2026-08-28T10:00:00+00:00",
            },
            {
                "annotation_candidate_id": "ac-test002",
                "slot": "pv_point",
                "source_workflow_id": "path-a-manual-gold",
                "source_execution_id": EXEC_ID,
                "entity_key": "s1|d2|b1",
                "boundary_start": "2021-08-24T00:00:00+00:00",
                "boundary_end": "2021-08-25T00:00:00+00:00",
                "suggested_label": 10,
                "review_status": "pending",
                "date": "2021-08-24",
                "source_day_snapshot_path": rel_source,
                "registered_at": "2026-08-28T10:00:00+00:00",
            },
        ],
    )

    groups = list_pending_detection_groups("pv_point")
    assert len(groups) == 1
    assert groups[0]["candidate_count"] == 2
    assert groups[0]["detection_date"] == "2021-08-23~2021-08-24"

    repo = FileReviewResultRepository()
    registry = LabelRegistryService(slot="pv_point")
    group_key = detection_group_id(
        slot="pv_point",
        candidate={"source_execution_id": EXEC_ID, "registered_at": "2026-08-28T10:00:00+00:00", "date": "2021-08-23"},
    )

    created = create_review_session_from_detection_group(
        slot="pv_point",
        detection_group_id_value=group_key,
        review_repo=repo,
        registry_service=registry,
    )
    assert created["total_count"] == 2
    assert created["candidate_count"] == 2
    assert created["review_id"].startswith("rev-")

    replay = create_review_session_from_detection_group(
        slot="pv_point",
        detection_group_id_value=group_key,
        review_repo=repo,
        registry_service=registry,
    )
    assert replay["idempotent_replay"] is True
    assert replay["review_id"] == created["review_id"]

    assert list_pending_detection_groups("pv_point") == []
