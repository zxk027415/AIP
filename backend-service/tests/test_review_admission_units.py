"""Daily-review unit matching uses time→date and entity_key."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_datasets.review_admission import _filter_unit_rows


def test_filter_unit_rows_from_time_column():
    frame = pd.DataFrame(
        [
            {
                "time": "2024-03-01T08:00:00",
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": 101,
                "value": 1.0,
            },
            {
                "time": "2024-03-02T08:00:00",
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": 101,
                "value": 2.0,
            },
        ]
    )
    hit = _filter_unit_rows(frame, "s1|d1|101|2024-03-01")
    assert len(hit) == 1
    assert float(hit.iloc[0]["value"]) == 1.0


def test_filter_unit_rows_by_entity_key():
    frame = pd.DataFrame(
        [
            {"entity_key": "s1|d1|101|2024-03-01", "value": 9},
            {"entity_key": "s2|d2|201|2024-03-01", "value": 8},
        ]
    )
    hit = _filter_unit_rows(frame, "s1|d1|101|2024-03-01")
    assert len(hit) == 1
    assert int(hit.iloc[0]["value"]) == 9

# @AI_GENERATED: direct-created pv_tsc session completes without annotation candidates
def test_direct_pv_tsc_review_admits_once_without_candidate(tmp_path, monkeypatch):
    from services.iterative_labeling.storage.file_backend import FileReviewResultRepository
    from services.slot_datasets import canvas_datasets as cd
    from services.slot_datasets import labeled_versions as lv
    from services.slot_datasets import review_admission
    from services.slot_datasets import review_session_admission as rsa
    from services.slot_datasets import snapshots

    backend_dir = tmp_path / "backend-service"
    data_root = backend_dir / "data" / "iterative_labeling"
    slot_dir = backend_dir / "data" / "slot_datasets"
    data_root.mkdir(parents=True)
    slot_dir.mkdir(parents=True)
    monkeypatch.setenv("ITERATIVE_LABELING_DATA_ROOT", str(data_root))
    monkeypatch.setattr(rsa, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(review_admission, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(lv, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(lv, "_DATA_DIR", slot_dir)
    monkeypatch.setattr(cd, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(cd, "_DATA_DIR", slot_dir)
    monkeypatch.setattr(snapshots, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(snapshots, "_DATA_DIR", slot_dir)

    review_id = "rev-tsc-direct"
    unit_key = "s1|d1|b1|2024-03-05"
    slice_rel = f"data/iterative_labeling/freeform_labels/{review_id}/slice.csv"
    slice_abs = backend_dir / slice_rel
    slice_abs.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "time": ["2024-03-05T08:00:00Z", "2024-03-05T08:05:00Z"],
            "site_id": ["s1", "s1"],
            "device_id": ["d1", "d1"],
            "branch_id": ["b1", "b1"],
            "value": [1.0, 1.2],
            "i_cal": [2.0, 2.2],
            "label": [1, 1],
        }
    ).to_csv(slice_abs, index=False)

    repo = FileReviewResultRepository()
    repo.save_verdict(
        "pv_tsc",
        review_id,
        {
            "review_id": review_id,
            "loop_id": "tsc-direct",
            "status": "reviewing",
            "total_count": 1,
            "reviewed_count": 1,
            "units": [
                {
                    "unit_key": unit_key,
                    "site_id": "s1",
                    "device_id": "d1",
                    "branch_id": "b1",
                    "time_window": "2024-03-05",
                    "annotation_role_recommended": "learning",
                }
            ],
            "freeform_labels": [
                {
                    "unit_key": f"freeform:{review_id}:1",
                    "source_unit_key": unit_key,
                    "site_id": "s1",
                    "device_id": "d1",
                    "branch_id": "b1",
                    "t_start": "2024-03-05T00:00:00Z",
                    "t_end": "2024-03-05T23:59:59Z",
                    "dataset_path": slice_rel,
                    "verdict_label": 1,
                }
            ],
            "prediction_context": {
                "modeling_path": "tsc",
                "prediction_granularity": "day",
                "evidence_granularity": "overlapping_model_window",
            },
        },
    )

    first = rsa.complete_review_session_and_admit(
        slot="pv_tsc",
        review_id=review_id,
        review_repo=repo,
        reviewer="tester",
    )
    assert first["dataset_version_id"]
    assert first["row_count"] == 2
    assert snapshots.get_cumulative_ledger("pv_tsc")["event_count"] == 1

    replay = rsa.complete_review_session_and_admit(
        slot="pv_tsc",
        review_id=review_id,
        review_repo=repo,
        reviewer="tester",
    )
    assert replay["idempotent_replay"] is True
    assert snapshots.get_cumulative_ledger("pv_tsc")["event_count"] == 1
# @AI_GENERATED: end