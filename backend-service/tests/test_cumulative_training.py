# @AI_GENERATED: 正常光伏累计训练集的幂等、改判、导入、快照与重训请求聚焦测试
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.iterative_labeling.cumulative_training import CumulativeTrainingService


def _service(tmp_path: Path, threshold: int = 20) -> CumulativeTrainingService:
    """创建所有持久化位置均位于 pytest 临时项目根内的正常累计训练服务。"""
    project_root = tmp_path / "project"
    data_root = project_root / "backend-service" / "data" / "iterative_labeling"
    project_root.mkdir(parents=True)
    service = CumulativeTrainingService(
        slot="default",
        data_root=data_root,
        retrain_label_threshold=threshold,
    )
    # 服务运行时允许使用临时项目根；对外持久化字段仍只保存该根下的相对路径。
    service.project_root = project_root
    return service


def _ground_truth_verdict(label: int, action_type: str = "correct") -> dict:
    return {
        "unit_key": "site-a|device-1|branch-1|2026-07-15 00:00:00",
        "verdict_label": label,
        "action_type": action_type,
        "is_ground_truth": True,
        "reviewer": "tester",
        "reviewed_at": "2026-07-15T00:00:00",
    }


def _session() -> dict:
    return {"prediction_context": {"source_csv_path": "source.csv"}}


def test_duplicate_verdict_does_not_increment_pending_change_count(tmp_path: Path):
    service = _service(tmp_path)

    first = service.admit_verdict("rev-1", _session(), _ground_truth_verdict(1))
    repeated_verdict = _ground_truth_verdict(1)
    # ReviewSessionService 会刷新 reviewed_at；该元数据变化不能消耗重训阈值。
    repeated_verdict["reviewed_at"] = "2026-07-15T00:02:00"
    duplicate = service.admit_verdict("rev-1", _session(), repeated_verdict)

    assert first["admitted"] is True
    assert first["pending_change_count"] == 1
    assert duplicate["admitted"] is False
    assert duplicate["reason"] == "duplicate_verdict"
    assert duplicate["pending_change_count"] == 1
    assert duplicate["effective_labeled_unit_count"] == 1


def test_changed_verdict_replaces_entry_and_skip_removes_it(tmp_path: Path):
    service = _service(tmp_path)

    service.admit_verdict("rev-1", _session(), _ground_truth_verdict(1))
    corrected = service.admit_verdict("rev-1", _session(), _ground_truth_verdict(2))
    skipped = service.admit_verdict(
        "rev-1",
        _session(),
        {
            "unit_key": "site-a|device-1|branch-1|2026-07-15 00:00:00",
            "verdict_label": None,
            "action_type": "skip",
            "is_ground_truth": False,
            "reviewer": "tester",
            "reviewed_at": "2026-07-15T00:01:00",
        },
    )

    assert corrected["admitted"] is True
    assert corrected["effective_labeled_unit_count"] == 1
    assert corrected["pending_change_count"] == 2
    assert skipped["removed"] is True
    assert skipped["effective_labeled_unit_count"] == 0
    assert skipped["pending_change_count"] == 3


def test_labeled_import_creates_relative_snapshot_and_queued_request(tmp_path: Path):
    service = _service(tmp_path, threshold=2)
    dataset_path = service.project_root / "historical_labeled.csv"
    pd.DataFrame(
        {
            "time": ["2026-07-14 00:00:00", "2026-07-14 00:15:00"],
            "site_id": ["site-a", "site-a"],
            "device_id": ["device-1", "device-1"],
            "branch_id": ["branch-1", "branch-1"],
            "value": [1.0, 2.0],
            "i_cal": [1.1, 2.1],
            "label": [0, 1],
        }
    ).to_csv(dataset_path, index=False)

    result = service.register_labeled_dataset("historical_labeled.csv", "历史真值导入")

    request = result["retrain_request"]
    assert result["imported"] is True
    assert request is not None
    assert request["status"] == "queued"
    assert request["dataset_path"].startswith("backend-service/data/iterative_labeling/")
    assert not Path(request["dataset_path"]).is_absolute()
    snapshot_path = service.project_root / request["dataset_path"]
    assert snapshot_path.exists()
    snapshot = pd.read_csv(snapshot_path)
    assert set(snapshot["label"].tolist()) == {0, 1}


def test_import_without_label_is_rejected(tmp_path: Path):
    service = _service(tmp_path)
    dataset_path = service.project_root / "unlabeled.csv"
    pd.DataFrame(
        {
            "time": ["2026-07-14 00:00:00"],
            "site_id": ["site-a"],
            "device_id": ["device-1"],
            "branch_id": ["branch-1"],
            "value": [1.0],
            "i_cal": [1.1],
        }
    ).to_csv(dataset_path, index=False)

    with pytest.raises(ValueError, match="缺少 label 列"):
        service.register_labeled_dataset("unlabeled.csv")
# @AI_GENERATED: end
