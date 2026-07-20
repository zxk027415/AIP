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


def test_get_state_supersedes_stale_queued_when_pending_exceeds_threshold(tmp_path: Path):
    service = _service(tmp_path, threshold=2)
    first_path = service.project_root / "historical_labeled_a.csv"
    second_path = service.project_root / "historical_labeled_b.csv"
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
    ).to_csv(first_path, index=False)
    pd.DataFrame(
        {
            "time": ["2026-07-14 01:00:00", "2026-07-14 01:15:00"],
            "site_id": ["site-b", "site-b"],
            "device_id": ["device-2", "device-2"],
            "branch_id": ["branch-2", "branch-2"],
            "value": [3.0, 4.0],
            "i_cal": [3.1, 4.1],
            "label": [1, 2],
        }
    ).to_csv(second_path, index=False)

    first = service.register_labeled_dataset("historical_labeled_a.csv", "first import")
    old_request_id = first["retrain_request"]["request_id"]

    service.register_labeled_dataset("historical_labeled_b.csv", "second import")
    state = service.get_state()
    latest = state["latest_retrain_request"]
    assert latest["status"] == "queued"
    assert latest["request_id"] != old_request_id
    cancelled = service.get_retrain_request(old_request_id)
    assert cancelled["status"] == "cancelled"
    assert cancelled.get("cancelled_reason") == "superseded_by_newer_snapshot"


def test_completed_retrain_persists_train_summary_and_reconciles_pending(tmp_path: Path):
    service = _service(tmp_path, threshold=2)
    first_path = service.project_root / "historical_labeled_a.csv"
    second_path = service.project_root / "historical_labeled_b.csv"
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
    ).to_csv(first_path, index=False)
    pd.DataFrame(
        {
            "time": ["2026-07-14 01:00:00", "2026-07-14 01:15:00"],
            "site_id": ["site-b", "site-b"],
            "device_id": ["device-2", "device-2"],
            "branch_id": ["branch-2", "branch-2"],
            "value": [3.0, 4.0],
            "i_cal": [3.1, 4.1],
            "label": [1, 2],
        }
    ).to_csv(second_path, index=False)
    registered = service.register_labeled_dataset("historical_labeled_a.csv")
    request_id = registered["retrain_request"]["request_id"]

    service.mark_retrain_request(
        request_id,
        "completed",
        model_ref="model-test-1",
        train_summary={
            "model_ref": "model-test-1",
            "accuracy_record": {"macro_f1_mean": 0.91, "accuracy_mean": 0.88},
        },
    )
    service.register_labeled_dataset("historical_labeled_b.csv")

    state = service.get_state()
    completed = state["latest_completed_retrain"]
    assert completed["model_ref"] == "model-test-1"
    assert completed["train_summary"]["accuracy_record"]["macro_f1_mean"] == 0.91
    assert state["latest_completed_model_ref"] == "model-test-1"
    assert state["production_model_ref"] == "model-test-1"
    assert state["production_model"]["is_production"] is True
    assert state["production_model"]["request_id"] == request_id
    assert state["latest_retrain_request"]["status"] == "queued"
    assert state["pending_change_count"] == 0
    assert len(state["retrain_history"]) == 2

    next_request_id = state["latest_retrain_request"]["request_id"]
    service.mark_retrain_request(next_request_id, "failed", error="training failed")
    failed_state = service.get_state()
    assert failed_state["production_model_ref"] == "model-test-1"
    assert failed_state["production_model"]["request_id"] == request_id
    assert failed_state["latest_retrain_request"]["progress"]["stage"] == "failed"
    assert failed_state["latest_retrain_request"]["progress"]["message"] == "training failed"


def test_retrain_progress_is_persisted_for_polling(tmp_path: Path):
    service = _service(tmp_path, threshold=1)
    dataset_path = service.project_root / "progress_labeled.csv"
    pd.DataFrame(
        {
            "time": ["2026-07-20 00:00:00", "2026-07-20 00:15:00"],
            "device_id": ["device-1", "device-1"],
            "value": [3.0, 3.1],
            "i_cal": [3.2, 3.2],
            "label": [0, 1],
        }
    ).to_csv(dataset_path, index=False)
    registered = service.register_labeled_dataset("progress_labeled.csv")
    request_id = registered["retrain_request"]["request_id"]

    service.mark_retrain_request(request_id, "running")
    service.update_retrain_progress(
        request_id,
        stage="training_and_evaluation",
        percent=25,
        message="正在训练模型并执行分层交叉验证",
    )

    request = service.get_retrain_request(request_id)
    assert request["status"] == "running"
    assert request["progress"]["stage"] == "training_and_evaluation"
    assert request["progress"]["percent"] == 25


@pytest.mark.asyncio
async def test_retrain_api_registers_model_version_before_production_switch(monkeypatch):
    import api.iterative_labeling as iterative_api

    events = []

    class FakeService:
        def get_retrain_request(self, request_id):
            return {
                "request_id": request_id,
                "status": "queued",
                "dataset_path": "backend-service/data/snapshot.csv",
                "sample_count": 123,
            }

        def mark_retrain_request(self, request_id, status, **kwargs):
            events.append(("state", status, kwargs))
            return {"request_id": request_id, "status": status, **kwargs}

        def update_retrain_progress(self, request_id, **kwargs):
            events.append(("progress", kwargs["stage"], kwargs))
            return {"request_id": request_id, "status": "running", "progress": kwargs}

    class FakeOrchestrator:
        def create_loop(self, base_dataset_version):
            return {"loop_id": "loop-1"}

        def trigger_train_eval(self, loop_id, dataset_version):
            return {
                "model_ref": "pv_fault_rfc_20260720T080000Z_abc123",
                "model_path": "backend-service/data/models/pv_fault_rfc_20260720T080000Z_abc123.pkl",
                "accuracy_record": {"macro_f1_mean": 0.91},
                "label_space_snapshot": {"label_space_version": "ls-v2"},
            }

    class FakeRepository:
        def save_model_version(self, version_data):
            events.append(("registry", version_data))

    monkeypatch.setattr(iterative_api, "_cumulative_training_for_slot", lambda slot: FakeService())
    monkeypatch.setattr(iterative_api, "_orchestrator_for_slot", lambda slot: FakeOrchestrator())
    monkeypatch.setattr(iterative_api, "_pv_repo_instance", FakeRepository())

    response = await iterative_api.run_cumulative_retrain_request("retrain-1", slot="pv_fault")

    assert response["publication"] == "auto_promoted"
    assert response["production_model_ref"] == "pv_fault_rfc_20260720T080000Z_abc123"
    assert events[0][0:2] == ("state", "running")
    progress_stages = [event[1] for event in events if event[0] == "progress"]
    assert progress_stages == [
        "preparing_snapshot",
        "training_and_evaluation",
        "registering_model",
        "promoting_model",
    ]
    registry_event = next(event for event in events if event[0] == "registry")
    assert registry_event[1]["training_sample_count"] == 123
    assert registry_event[1]["label_space_version"] == "ls-v2"
    assert events[-1][0:2] == ("state", "completed")
# @AI_GENERATED: end
