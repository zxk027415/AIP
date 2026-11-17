"""G10-S2: clustering confirm publishes labeled version without cumulative rows."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.iterative_labeling.pv_training_workspace import PVTrainingWorkspaceService
from services.slot_datasets import canvas_datasets as cd
from services.slot_datasets import labeled_versions as lv


@pytest.fixture()
def clustering_env(tmp_path, monkeypatch):
    project_root = tmp_path
    backend_dir = project_root / "backend-service"
    workspace_dir = backend_dir / "data" / "iterative_labeling" / "training_workspace" / "pv_fault"
    workspace_dir.mkdir(parents=True)
    slot_ds_dir = backend_dir / "data" / "slot_datasets"
    slot_ds_dir.mkdir(parents=True)

    import services.iterative_labeling.pv_training_workspace as ws_mod

    monkeypatch.setattr(ws_mod, "_PROJECT_ROOT", project_root)
    monkeypatch.setattr(ws_mod, "_BACKEND_SERVICE_DIR", backend_dir)
    monkeypatch.setattr(ws_mod, "_WORKSPACE_DIR", workspace_dir)
    monkeypatch.setattr(lv, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(lv, "_DATA_DIR", slot_ds_dir)
    monkeypatch.setattr(cd, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(cd, "_DATA_DIR", slot_ds_dir)

    import services.slot_datasets.snapshots as snapshots
    import services.slot_datasets.review_admission as admission

    monkeypatch.setattr(snapshots, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(snapshots, "_DATA_DIR", slot_ds_dir)
    monkeypatch.setattr(admission, "_BACKEND_DIR", backend_dir)

    return PVTrainingWorkspaceService()


def _sample_rows() -> list[dict]:
    rows = []
    for idx in range(8):
        rows.append(
            {
                "time": f"2024-03-01T08:{idx:02d}:00",
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": 101 if idx % 2 == 0 else 102,
                "value": 1.0 + idx * 0.4,
                "i_cal": 2.0 + idx * 0.2,
            }
        )
    return rows


def _prepare_run_for_confirm(service: PVTrainingWorkspaceService, slot: str = "pv_point") -> tuple[dict, dict]:
    run = service.create_clustering_run(samples=_sample_rows(), n_clusters=2, slot=slot)
    for cluster_id, cluster in run["clusters"].items():
        service.update_cluster(
            run_id=run["run_id"],
            cluster_id=cluster_id,
            proposed_label_name=f"fault_{cluster_id}",
            selected_member_keys=cluster["member_keys"],
        )
    label_id_map = {f"fault_{cluster_id}": int(cluster_id) + 1 for cluster_id in run["clusters"]}
    return run, label_id_map


def test_create_clustering_run_excludes_entity_id_columns(clustering_env):
    run = clustering_env.create_clustering_run(samples=_sample_rows(), n_clusters=2, slot="pv_point")
    feature_cols = run["clustering_feature_columns"]

    assert "branch_id" not in feature_cols
    assert "site_id" not in feature_cols
    assert "device_id" not in feature_cols
    assert any(col.startswith("value_") for col in feature_cols)


def test_confirm_publishes_labeled_version_without_cumulative_snapshot(clustering_env):
    run, label_id_map = _prepare_run_for_confirm(clustering_env, slot="pv_point")

    result = clustering_env.confirm_clustering_run(
        run_id=run["run_id"],
        label_id_map=label_id_map,
        slot="pv_point",
    )

    assert result["dataset_version_id"]
    assert result["dataset_id"] == result["dataset_version_id"]

    labeled_rows = lv.list_labeled_versions("pv_point")
    assert len(labeled_rows) == 1
    assert labeled_rows[0]["dataset_version_id"] == result["dataset_version_id"]
    assert labeled_rows[0]["status"] == "curated"

    trainable = cd.list_trainable_datasets("pv_point")
    assert len(trainable["labeled_versions"]) == 1
    assert trainable["labeled_versions"][0]["kind"] == "labeled_version"
    assert trainable["labeled_versions"][0]["dataset_id"] == result["dataset_id"]
    assert len(trainable["cumulative_snapshots"]) == 0
    assert result["cumulative_include"]["source"] == "path_a"
    assert not result["cumulative_include"].get("freeze_dataset_id")


def test_unconfirmed_clustering_run_not_in_trainable_registry(clustering_env):
    run = clustering_env.create_clustering_run(samples=_sample_rows(), n_clusters=2, slot="pv_point")

    assert run["status"] == "pending_naming"
    assert lv.list_labeled_versions("pv_point") == []

    trainable = cd.list_trainable_datasets("pv_point")
    assert trainable["labeled_versions"] == []
    assert trainable["cumulative_snapshots"] == []


def test_prepared_but_unconfirmed_clustering_not_registered(clustering_env):
    run, _ = _prepare_run_for_confirm(clustering_env, slot="pv_point")

    assert run["status"] != "confirmed"
    assert lv.list_labeled_versions("pv_point") == []
    assert cd.list_trainable_datasets("pv_point")["labeled_versions"] == []

# @AI_GENERATED: row-level clustering must not bypass the pv_tsc device-day proposal contract
def test_http_clustering_confirm_rejects_pv_tsc(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from api import iterative_labeling as api

    class _Workspace:
        @staticmethod
        def get_clustering_run(_run_id):
            return {"run_id": "cluster-tsc", "clusters": {}}

    monkeypatch.setattr(api, "_get_pv_workspace", lambda: _Workspace())
    request = api.ConfirmClusteringRunRequest(
        confirm_inclusion=True,
        slot="pv_tsc",
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.confirm_clustering_run("cluster-tsc", request))
    assert error.value.status_code == 422
    assert "pv_day 或 pv_point" in str(error.value.detail)
# @AI_GENERATED: end