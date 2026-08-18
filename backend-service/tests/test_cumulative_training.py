# @AI_GENERATED: 正常光伏累计训练集的幂等、改判、导入、快照与重训请求聚焦测试
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.iterative_labeling.cumulative_training import CumulativeTrainingService
from services.iterative_labeling.pv_model_registry import PVModelRegistry


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
    # 单元测试固定使用临时 CSV 快照，禁止默认 point_label 模式误连真实数据库。
    state = service._load_state()
    state["snapshot_mode"] = "legacy"
    service._save_state(state)
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
            "modeling_path": "legacy_day",
            "accuracy_record": {"macro_f1_mean": 0.91, "accuracy_mean": 0.88},
        },
    )
    service.register_labeled_dataset("historical_labeled_b.csv")
    # 自动重训要求“阈值 AND 周期”；把目标路径上次成功时间固定到周期外。
    with service._lock:
        raw_state = service._load_state()
        raw_state["retrain_watermarks"]["legacy_day"]["last_consumed_at"] = (
            "2000-01-01T00:00:00"
        )
        service._save_state(raw_state)

    state = service.get_state()
    completed = state["latest_completed_retrain"]
    assert completed["model_ref"] == "model-test-1"
    assert completed["train_summary"]["accuracy_record"]["macro_f1_mean"] == 0.91
    assert state["latest_completed_model_ref"] == "model-test-1"
    assert state["production_model_ref"] == "model-test-1"
    assert state["production_model"]["is_production"] is True
    assert state["production_model"]["request_id"] == request_id
    assert state["latest_retrain_request"]["status"] == "queued"
    assert state["pending_change_count"] == 2
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
async def test_retrain_api_registers_model_version_before_production_switch(
    monkeypatch, tmp_path: Path
):
    import api.iterative_labeling as iterative_api

    events = []

    class FakeService:
        def get_retrain_request(self, request_id):
            return {
                "request_id": request_id,
                "status": "queued",
                "dataset_path": "backend-service/data/snapshot.csv",
                "snapshot_id": "snapshot-a",
                "sample_count": 123,
            }

        def mark_retrain_request(self, request_id, status, **kwargs):
            events.append(("state", status, kwargs))
            return {"request_id": request_id, "status": status, **kwargs}

        def update_retrain_progress(self, request_id, **kwargs):
            events.append(("progress", kwargs["stage"], kwargs))
            return {"request_id": request_id, "status": "running", "progress": kwargs}

        def get_production_model_ref(self):
            return "pv_fault_rfc_20260720T080000Z_abc123"

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
    monkeypatch.setattr(
        iterative_api,
        "_pv_model_registry",
        PVModelRegistry(
            base_dir=tmp_path / "registry",
            events_base_dir=tmp_path / "events",
        ),
    )

    response = await iterative_api.run_cumulative_retrain_request("retrain-1", slot="pv_fault")

    assert response["publication"] == "promoted_within_path"
    assert response["production_model_ref"] == "pv_fault_rfc_20260720T080000Z_abc123"
    assert events[0][0:2] == ("state", "running")
    progress_stages = [event[1] for event in events if event[0] == "progress"]
    assert progress_stages == [
        "preparing_snapshot",
        "training_and_evaluation",
        "registering_model",
        "registering_challenger",
    ]
    registry_event = next(event for event in events if event[0] == "registry")
    assert registry_event[1]["training_sample_count"] == 123
    assert registry_event[1]["label_space_version"] == "ls-v2"
    assert events[-1][0:2] == ("state", "completed")


def test_freeform_import_counts_as_one_unit_and_keeps_window_in_snapshot(tmp_path: Path):
    """自由窗切片按 1 次变更计入阈值，且与无 time_window 的整天行共存。"""
    service = _service(tmp_path, threshold=20)
    project_root = service.project_root
    day_csv = project_root / "day_labeled.csv"
    free_csv = project_root / "freeform_labeled.csv"
    times = pd.date_range("2026-07-20 10:00:00", periods=4, freq="15min")
    pd.DataFrame(
        {
            "time": times,
            "site_id": ["s1"] * 4,
            "device_id": ["d1"] * 4,
            "branch_id": ["b1"] * 4,
            "value": [1, 2, 3, 4],
            "label": [0, 0, 0, 0],
        }
    ).to_csv(day_csv, index=False)
    free_key = "2026-07-20T10:00:00__2026-07-20T10:45:00#freeform"
    pd.DataFrame(
        {
            "time": times,
            "site_id": ["s1"] * 4,
            "device_id": ["d1"] * 4,
            "branch_id": ["b1"] * 4,
            "value": [1, 2, 3, 4],
            "label": [2, 2, 2, 2],
            "time_window": [free_key] * 4,
        }
    ).to_csv(free_csv, index=False)

    day = service.register_labeled_dataset("day_labeled.csv", change_units=1)
    free = service.register_labeled_dataset("freeform_labeled.csv", change_units=1)
    assert day["pending_change_count"] == 1
    assert free["pending_change_count"] == 2
    assert free["change_units"] == 1

    # 强制低于阈值时手工建快照
    with service._lock:
        state = service._load_state()
        snapshot = service._create_snapshot(state)
    frame = pd.read_csv(service.project_root / snapshot["dataset_path"])
    assert free_key in set(frame["time_window"].astype(str))
    # 同时间戳两条（整天无窗键 / 自由窗）都应保留
    assert len(frame) == 8


def test_manual_retrain_request_does_not_require_threshold(tmp_path: Path):
    service = _service(tmp_path, threshold=20)
    dataset_path = service.project_root / "historical_labeled.csv"
    pd.DataFrame(
        {
            "time": ["2026-07-14 00:00:00", "2026-07-14 00:15:00"],
            "site_id": ["site-a", "site-a"],
            "device_id": ["device-1", "device-1"],
            "branch_id": ["branch-1", "branch-1"],
            "value": [1.0, 2.0],
            "label": [0, 1],
        }
    ).to_csv(dataset_path, index=False)
    service.register_labeled_dataset("historical_labeled.csv", change_units=1)

    result = service.request_manual_retrain()
    request = result["retrain_request"]

    assert request is not None
    assert request["status"] == "queued"
    assert request["trigger_reason"] == "manual"
    assert request["auto_execute"] is False
    assert result["pending_change_count"] == 1


def test_auto_threshold_request_reserves_counter_until_training_succeeds(tmp_path: Path):
    service = _service(tmp_path, threshold=2)
    dataset_path = service.project_root / "historical_labeled.csv"
    pd.DataFrame(
        {
            "time": ["2026-07-14 00:00:00", "2026-07-14 00:15:00"],
            "site_id": ["site-a", "site-a"],
            "device_id": ["device-1", "device-1"],
            "branch_id": ["branch-1", "branch-1"],
            "value": [1.0, 2.0],
            "label": [0, 1],
        }
    ).to_csv(dataset_path, index=False)

    result = service.register_labeled_dataset("historical_labeled.csv", change_units=2)
    request = result["retrain_request"]

    assert request is not None
    assert request["trigger_reason"] == "auto_threshold_and_period"
    assert request["auto_execute"] is True
    assert result["pending_change_count"] == 2
    assert result["_auto_retrain_request_id"] == request["request_id"]
# @AI_GENERATED: end

# @AI_GENERATED: seq_annotation 实验登记与安全 Promote 门控
def test_seq_annotation_model_is_registered_without_automatic_promotion(tmp_path: Path):
    service = _service(tmp_path)
    reserved = service.reserve_manual_retrain_request("seq_annotation")
    request = reserved["retrain_request"]

    completed = service.mark_retrain_request(
        request["request_id"],
        "completed",
        model_ref="seqann-bilstm-attn-test",
        train_summary={
            "modeling_path": "seq_annotation",
            "model_path": "data/models/seq_annotation/seqann-bilstm-attn-test",
            "artifact_format": "torch_state_dict_dir",
            "trained_full_day": True,
            "sequence_contract": {
                "model_name": "bilstm_attn",
                "loss": "cross_entropy",
                "seq_len": 288,
                "channels": ["value", "i_cal", "is_measured"],
                "trained_full_day": True,
                "grid_aligned": True,
                "sequence_weighting": {
                    "field": "data_type",
                    "match": "segment_boundary",
                    "multiplier": 4.0,
                },
                "postprocessing": {
                    "enabled": True,
                    "force_normal_outside_fault_window": True,
                    "fault_window_hours": [7, 17],
                    "min_fault_segment_points": 3,
                    "short_run_policy": "same_neighbors_else_normal",
                },
            },
            "accuracy_record": {
                "point_macro_f1": 0.62,
                "binary_f1": 0.88,
                "segment_iou": 0.71,
                "n_samples": 200,
            },
            "macro_f1_mean": 0.62,
            "n_samples": 200,
        },
        promote_to_production=False,
    )

    paths = service.get_modeling_paths()
    assert completed["promote_to_production"] is False
    assert paths["production_path"] == "legacy_day"
    assert paths["production_model_ref"] is None
    seq_entry = paths["path_models"]["seq_annotation"]
    assert seq_entry["model_ref"] == "seqann-bilstm-attn-test"
    assert seq_entry["trained_full_day"] is True
    assert seq_entry["metrics"]["segment_iou"] == 0.71

    promoted = service.set_modeling_paths("seq_annotation", "legacy_day")
    assert promoted["production_path"] == "seq_annotation"
    assert promoted["production_model_ref"] == "seqann-bilstm-attn-test"

    with pytest.raises(ValueError, match="只能通过正式重训登记"):
        service.register_path_model("seq_annotation", "seqann-bypass")
    assert service.get_production_model_ref() == "seqann-bilstm-attn-test"


def test_seq_annotation_cannot_be_promoted_without_full_day_model(tmp_path: Path):
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="尚无已登记模型"):
        service.set_modeling_paths("seq_annotation", "legacy_day")

    reserved = service.reserve_manual_retrain_request("seq_annotation")
    request_id = reserved["retrain_request"]["request_id"]
    invalid_summary = {
        "modeling_path": "seq_annotation",
        "model_path": "data/models/seq_annotation/seqann-daylight-only",
        "artifact_format": "torch_state_dict_dir",
        "trained_full_day": False,
        "sequence_contract": {"seq_len": 120, "trained_full_day": False},
        "accuracy_record": {"n_samples": 100},
    }
    with pytest.raises(ValueError, match="最终生产契约"):
        service.mark_retrain_request(
            request_id,
            "completed",
            model_ref="seqann-daylight-only",
            train_summary=invalid_summary,
            promote_to_production=True,
        )
    assert service.get_production_model_ref() is None

    service.mark_retrain_request(
        request_id,
        "completed",
        model_ref="seqann-daylight-only",
        train_summary=invalid_summary,
        promote_to_production=False,
    )
    with pytest.raises(ValueError, match="最终生产契约"):
        service.set_modeling_paths("seq_annotation", "legacy_day")


# ============================================================================
# 安全修复回归测试（2026-08-12）：
#   R4 未 Promote 的 seq 实验模型不得被兼容回退误当成生产模型
# ============================================================================


def test_unpromoted_experimental_seq_model_is_not_production_ref(tmp_path: Path):
    """R4 主场景：只有 promote_to_production=False 的实验 seq 模型时，生产 ref 必须为空。"""
    service = _service(tmp_path)
    reserved = service.reserve_manual_retrain_request("seq_annotation")
    request = reserved["retrain_request"]
    service.mark_retrain_request(
        request["request_id"],
        "completed",
        model_ref="seqann-experiment-only",
        train_summary={
            "modeling_path": "seq_annotation",
            "model_path": "data/models/seq_annotation/seqann-experiment-only",
            "artifact_format": "torch_state_dict_dir",
            "trained_full_day": True,
            "sequence_contract": {"seq_len": 288, "trained_full_day": True},
            "accuracy_record": {"point_macro_f1": 0.5, "n_samples": 100},
        },
        promote_to_production=False,
    )

    # 显式 production_model_ref 与兼容回退都不应返回实验模型
    assert service.get_production_model_ref() is None
    assert service.get_latest_completed_model_ref() is None
    state = service.get_state()
    assert state.get("production_model_ref") is None


def test_legacy_completed_request_still_promotes_for_backward_compat(tmp_path: Path):
    """R4 兼容边界：历史状态里无 promote 字段的 completed 请求仍按自动晋升语义处理。"""
    service = _service(tmp_path)
    # 绕过 mark_retrain_request，直接构造一个"旧格式"已完成请求（无 promote_to_production 字段）
    with service._lock:
        state = service._load_state()
        request_id = "legacy-request-1"
        state["retrain_requests"][request_id] = {
            "request_id": request_id,
            "status": "completed",
            "model_ref": "legacy-prod-model",
            "finished_at": "2026-08-01T00:00:00",
            "updated_at": "2026-08-01T00:00:00",
            "created_at": "2026-08-01T00:00:00",
        }
        # 不写 production_model_ref，模拟旧状态
        state.pop("production_model_ref", None)
        service._save_state(state)

    # 兼容回退：无显式 ref 时，历史 completed 请求应作为生产模型返回
    assert service.get_production_model_ref() == "legacy-prod-model"


def test_experimental_seq_does_not_shadow_older_promoted_model(tmp_path: Path):
    """R4 关键：实验 seq 模型登记后，不得覆盖/抢走既有的生产模型 ref。"""
    service = _service(tmp_path, threshold=2)
    # 先造一个已 Promote 的 legacy 生产模型
    dataset_path = service.project_root / "hist.csv"
    pd.DataFrame(
        {
            "time": ["2026-07-14 00:00:00", "2026-07-14 00:15:00"],
            "site_id": ["site-a", "site-a"],
            "device_id": ["device-1", "device-1"],
            "branch_id": ["branch-1", "branch-1"],
            "value": [1.0, 2.0],
            "label": [0, 1],
        }
    ).to_csv(dataset_path, index=False)
    registered = service.register_labeled_dataset("hist.csv")
    prod_request_id = registered["retrain_request"]["request_id"]
    service.mark_retrain_request(
        prod_request_id,
        "completed",
        model_ref="legacy-prod-model",
        train_summary={
            "modeling_path": "legacy_day",
            "accuracy_record": {"macro_f1_mean": 0.9},
        },
        promote_to_production=True,
    )
    assert service.get_production_model_ref() == "legacy-prod-model"

    # 再登记一个实验 seq 模型（不 Promote）
    reserved = service.reserve_manual_retrain_request("seq_annotation")
    seq_request = reserved["retrain_request"]
    service.mark_retrain_request(
        seq_request["request_id"],
        "completed",
        model_ref="seqann-experiment-2",
        train_summary={
            "modeling_path": "seq_annotation",
            "model_path": "data/models/seq_annotation/seqann-experiment-2",
            "artifact_format": "torch_state_dict_dir",
            "trained_full_day": True,
            "sequence_contract": {"seq_len": 288, "trained_full_day": True},
            "accuracy_record": {"point_macro_f1": 0.6, "n_samples": 100},
        },
        promote_to_production=False,
    )

    # 生产 ref 仍应是 legacy 生产模型，实验 seq 模型不得抢走
    assert service.get_production_model_ref() == "legacy-prod-model"
    state = service.get_state()
    assert state["production_model_ref"] == "legacy-prod-model"
# @AI_GENERATED: end

# @AI_GENERATED: seq_annotation 快照全天网格门控回归测试
@pytest.mark.parametrize(
    ("grid_validated", "expected_full_day"),
    [(False, False), (True, True)],
)
def test_seq_snapshot_full_day_requires_real_grid_validation(
    tmp_path: Path,
    monkeypatch,
    grid_validated: bool,
    expected_full_day: bool,
):
    """累计训练快照不能只凭 288 长度宣称全天，必须携带真实网格验证证据。"""
    import services.iterative_labeling.seq_annotation.dataset_builder as builder_module

    service = _service(tmp_path)
    relative_output = "data/seq_annotation_datasets/snapshots/snap-grid-test"
    dataset_dir = service.project_root / "backend-service" / relative_output
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "dataset.npz").write_bytes(b"grid-snapshot-test")

    report = {
        "seq_len": 288,
        "daylight_hours": [0, 24],
        "n_sequences": 3,
        "n_classes": 2,
        "channels": ["value", "i_cal", "is_measured"],
        "full_day_grid_validated": grid_validated,
        "grid_contract": {
            "grid_aligned": True,
            "slots_per_day": 288,
            "slot_minutes": 5,
            "require_all_hours_covered": True,
        },
        "label_snapshot_hash": "hash-grid-test",
        "night_label_policy": "weak_to_normal_explicit_preserved",
    }
    monkeypatch.setattr(
        builder_module,
        "build_dataset",
        lambda **kwargs: {
            "version": "snap-grid-test",
            "output_dir": relative_output,
            "report": report,
        },
    )

    state = service._load_state()
    snapshot = service._create_snapshot_seq_annotation(state)

    assert snapshot["sample_strategy"]["trained_full_day"] is expected_full_day
    assert snapshot["sample_strategy"]["full_day_grid_validated"] is grid_validated
    assert snapshot["grid_contract"]["grid_aligned"] is True
# @AI_GENERATED: end
