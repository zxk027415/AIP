"""review session complete-and-admit -> one cumulative freeze."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.iterative_labeling.storage.file_backend import FileReviewResultRepository
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.review_session_admission import complete_review_session_and_admit
from services.slot_datasets.snapshots import get_cumulative_ledger


@pytest.fixture()
def admit_tmp(tmp_path, monkeypatch):
    backend_dir = tmp_path
    review_root = backend_dir / "data" / "iterative_labeling"
    review_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ITERATIVE_LABELING_DATA_ROOT", str(review_root))

    slice_dir = review_root / "time_slices"
    slice_dir.mkdir(parents=True, exist_ok=True)
    slice_path = slice_dir / "slice-test.csv"
    pd.DataFrame(
        {
            "time": pd.to_datetime(["2021-08-23 08:00:00+00:00"], utc=True),
            "site_id": ["s1"],
            "device_id": ["d1"],
            "branch_id": ["b1"],
            "value": [1.0],
            "label": [9],
        }
    ).to_csv(slice_path, index=False)

    import services.slot_datasets.snapshots as snapshots
    import services.slot_datasets.labeled_versions as lv
    import services.slot_datasets.canvas_datasets as cd

    ds_dir = backend_dir / "data" / "slot_datasets"
    ds_dir.mkdir(parents=True)
    monkeypatch.setattr(snapshots, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(snapshots, "_DATA_DIR", ds_dir)
    monkeypatch.setattr(lv, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(lv, "_DATA_DIR", ds_dir)
    import services.slot_datasets.review_admission as ra
    import services.slot_datasets.review_session_admission as rsa

    monkeypatch.setattr(cd, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(cd, "_DATA_DIR", ds_dir)
    monkeypatch.setattr(rsa, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(ra, "_BACKEND_DIR", backend_dir)

    repo = FileReviewResultRepository()
    review_id = "rev-admit-test"
    rel_slice = slice_path.relative_to(review_root).as_posix()
    session = {
        "review_id": review_id,
        "status": "reviewing",
        "reviewed_count": 1,
        "total_count": 1,
        "freeform_labels": [
            {
                "unit_key": "u1",
                "dataset_path": rel_slice,
                "row_count": 1,
            }
        ],
        "prediction_context": {"source_csv_path": "data/test.csv"},
    }
    repo.save_verdict("pv_point", review_id, session)
    return backend_dir, review_id, repo


def test_complete_and_admit_freezes_once(admit_tmp):
    _backend_dir, review_id, repo = admit_tmp
    first = complete_review_session_and_admit(
        slot="pv_point",
        review_id=review_id,
        review_repo=repo,
        reviewer="tester",
    )
    assert first["idempotent_replay"] is False
    assert first.get("dataset_version_id")

    ledger = get_cumulative_ledger("pv_point")
    assert ledger["event_count"] == 1
    assert ledger["latest_freeze"] is None

    replay = complete_review_session_and_admit(
        slot="pv_point",
        review_id=review_id,
        review_repo=repo,
        reviewer="tester",
    )
    assert replay["idempotent_replay"] is True
    ledger2 = get_cumulative_ledger("pv_point")
    assert ledger2["event_count"] == 1
    assert ledger2["latest_freeze"] is None


def test_complete_and_admit_dedupes_shared_slice_path(admit_tmp):
    backend_dir, review_id, repo = admit_tmp
    session = repo.load_session("pv_point", review_id)
    assert session is not None
    shared_path = session["freeform_labels"][0]["dataset_path"]
    session["units"] = [
        {"unit_key": "u1", "status": "confirmed"},
        {"unit_key": "u2", "status": "confirmed"},
    ]
    session["freeform_labels"] = [
        {"unit_key": "u1", "dataset_path": shared_path, "row_count": 1},
        {"unit_key": "u2", "dataset_path": shared_path, "row_count": 1},
    ]
    repo.save_verdict("pv_point", review_id, session)

    result = complete_review_session_and_admit(
        slot="pv_point",
        review_id=review_id,
        review_repo=repo,
        reviewer="tester",
    )
    assert result["row_count"] == 1
    merged = backend_dir / result["file_path"]
    assert merged.is_file()
    assert len(pd.read_csv(merged)) == 1


def _write_slice(review_root, name: str, device: str, day: str, label: int):
    slice_dir = review_root / "time_slices"
    slice_dir.mkdir(parents=True, exist_ok=True)
    path = slice_dir / name
    pd.DataFrame(
        {
            "time": pd.to_datetime([f"{day} 08:00:00+00:00"], utc=True),
            "site_id": ["s1"],
            "device_id": [device],
            "branch_id": ["b1"],
            "value": [1.0],
            "label": [label],
        }
    ).to_csv(path, index=False)
    return path.relative_to(review_root).as_posix()


def test_complete_rejects_unboxed_units(admit_tmp, monkeypatch):
    backend_dir, review_id, repo = admit_tmp
    import services.slot_datasets.annotation_candidates as ac

    monkeypatch.setattr(ac, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(ac, "_DATA_DIR", backend_dir / "data" / "slot_datasets")
    ac._save_items(
        "pv_point",
        [
            {"annotation_candidate_id": "ac-1", "review_status": "in_review"},
            {"annotation_candidate_id": "ac-2", "review_status": "in_review"},
        ],
    )

    session = repo.load_session("pv_point", review_id)
    session["units"] = [
        {
            "unit_key": "s1|d1|b1|2021-08-23",
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": "b1",
            "time_window": "2021-08-23",
        },
        {
            "unit_key": "s1|d2|b1|2021-08-24",
            "site_id": "s1",
            "device_id": "d2",
            "branch_id": "b1",
            "time_window": "2021-08-24",
        },
    ]
    session["freeform_labels"][0]["source_unit_key"] = "s1|d1|b1|2021-08-23"
    session["prediction_context"]["annotation_candidate_ids"] = ["ac-1", "ac-2"]
    repo.save_verdict("pv_point", review_id, session)

    with pytest.raises(SlotDatasetError) as exc:
        complete_review_session_and_admit(
            slot="pv_point",
            review_id=review_id,
            review_repo=repo,
            reviewer="tester",
        )
    assert exc.value.code == "incomplete_review"
    assert get_cumulative_ledger("pv_point")["event_count"] == 0
    statuses = {item["annotation_candidate_id"]: item["review_status"] for item in ac._load_items("pv_point")}
    assert statuses == {"ac-1": "in_review", "ac-2": "in_review"}


def test_holdout_boxed_but_not_admitted(admit_tmp, monkeypatch):
    backend_dir, review_id, repo = admit_tmp
    import services.slot_datasets.annotation_candidates as ac

    monkeypatch.setattr(ac, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(ac, "_DATA_DIR", backend_dir / "data" / "slot_datasets")
    review_root = backend_dir / "data" / "iterative_labeling"
    holdout_rel = _write_slice(review_root, "slice-holdout.csv", "d2", "2021-08-24", 10)

    ac._save_items(
        "pv_point",
        [
            {"annotation_candidate_id": "ac-learn", "review_status": "in_review"},
            {"annotation_candidate_id": "ac-hold", "review_status": "in_review"},
        ],
    )

    session = repo.load_session("pv_point", review_id)
    session["units"] = [
        {
            "unit_key": "s1|d1|b1|2021-08-23",
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": "b1",
            "time_window": "2021-08-23",
        },
        {
            "unit_key": "s1|d2|b1|2021-08-24",
            "site_id": "s1",
            "device_id": "d2",
            "branch_id": "b1",
            "time_window": "2021-08-24",
        },
    ]
    session["freeform_labels"] = [
        {
            "unit_key": "free-learn",
            "source_unit_key": "s1|d1|b1|2021-08-23",
            "dataset_path": session["freeform_labels"][0]["dataset_path"],
            "row_count": 1,
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": "b1",
            "t_start": "2021-08-23 08:00:00",
        },
        {
            "unit_key": "free-hold",
            "source_unit_key": "s1|d2|b1|2021-08-24",
            "dataset_path": holdout_rel,
            "row_count": 1,
            "site_id": "s1",
            "device_id": "d2",
            "branch_id": "b1",
            "t_start": "2021-08-24 08:00:00",
        },
    ]
    session["prediction_context"] = {
        "source_csv_path": "data/test.csv",
        "annotation_candidate_ids": ["ac-learn", "ac-hold"],
        "candidate_units": [
            {
                "unit_key": "s1|d1|b1|2021-08-23",
                "annotation_candidate_id": "ac-learn",
                "annotation_role_recommended": "learning",
            },
            {
                "unit_key": "s1|d2|b1|2021-08-24",
                "annotation_candidate_id": "ac-hold",
                "annotation_role_recommended": "holdout",
            },
        ],
    }
    repo.save_verdict("pv_point", review_id, session)

    result = complete_review_session_and_admit(
        slot="pv_point",
        review_id=review_id,
        review_repo=repo,
        reviewer="tester",
    )
    assert result["learning_label_count"] == 1
    assert result["holdout_label_count"] == 1
    assert result.get("dataset_version_id")

    ledger = get_cumulative_ledger("pv_point")
    assert ledger["event_count"] == 1
    artifact = backend_dir / result["file_path"]
    frame = pd.read_csv(artifact)
    assert set(frame["device_id"].astype(str)) == {"d1"}

    statuses = {item["annotation_candidate_id"]: item["review_status"] for item in ac._load_items("pv_point")}
    assert statuses == {"ac-learn": "approved", "ac-hold": "holdout"}
