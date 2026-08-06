"""建模路径 A/B 对比：指标提取、差值与落盘（工作流执行用 mock）。"""

from __future__ import annotations

import json

from services.iterative_labeling import modeling_path_compare as mpc


def test_compute_deltas_vs_legacy():
    results = [
        {"path_key": "legacy_day", "status": "ok", "macro_f1_mean": 0.6, "accuracy_mean": 0.7},
        {"path_key": "point_label_by_day_night", "status": "ok", "macro_f1_mean": 0.65, "accuracy_mean": 0.72},
    ]
    deltas = mpc._compute_deltas(results)
    assert deltas["point_label_by_day_night"]["macro_f1_delta"] == 0.05
    assert deltas["point_label_by_day_night"]["accuracy_delta"] == 0.02


def test_compare_modeling_paths_with_mocked_runner(tmp_path, monkeypatch):
    calls = []

    def fake_run_one_path(**kwargs):
        key = kwargs.get("path_key")
        calls.append(key)
        score = {
            "legacy_day": 0.55,
            "point_label_by_day": 0.62,
            "point_label_by_day_night": 0.68,
        }.get(key, 0.5)
        return {
            "path_key": key,
            "label": mpc.PATH_LABELS.get(key, key),
            "status": "ok",
            "elapsed_sec": 0.1,
            "n_samples": 200,
            "macro_f1_mean": score,
            "accuracy_mean": score + 0.03,
            "per_class_recall_mean": {"0": 0.8, "1": 0.7},
            "error": None,
        }

    def fake_dataset(path_key, **kwargs):
        return f"backend-service/data/demo/{path_key}.parquet"

    monkeypatch.setattr(mpc, "run_one_path", fake_run_one_path)
    monkeypatch.setattr(mpc, "_dataset_for_path", fake_dataset)
    monkeypatch.setattr(mpc, "resolve_legacy_dataset_path", lambda explicit=None: "backend-service/datasets/x.parquet")
    monkeypatch.setattr(mpc, "_BACKEND", tmp_path)

    out = mpc.compare_modeling_paths(
        slot="pv_fault",
        paths=["legacy_day", "point_label_by_day_night"],
        n_repeats=1,
    )
    assert out["best_path_key"] == "point_label_by_day_night"
    assert out["deltas_vs_legacy"]["point_label_by_day_night"]["macro_f1_delta"] == 0.13
    assert calls == ["legacy_day", "point_label_by_day_night"]
    saved = json.loads(
        (tmp_path / "data" / "iterative_labeling" / "modeling_path_compare" / "pv_fault" / "latest.json")
        .read_text(encoding="utf-8")
    )
    assert saved["best_path_key"] == "point_label_by_day_night"
    assert mpc.load_compare_status("pv_fault")["status"] == "completed"


def test_cumulative_modeling_paths(tmp_path, monkeypatch):
    from services.iterative_labeling.cumulative_training import CumulativeTrainingService

    monkeypatch.setenv("AIP_DATA_ROOT", str(tmp_path / "data"))
    svc = CumulativeTrainingService(slot="pv_fault_test")
    summary = svc.set_modeling_paths("legacy_day", "point_label_by_day_night")
    assert summary["production_path"] == "legacy_day"
    assert summary["fallback_path"] == "point_label_by_day_night"

    reg = svc.register_path_model(
        "point_label_by_day_night",
        "data/models/test.pkl",
        request_id="req-1",
        metrics={"macro_f1_mean": 0.7},
    )
    assert reg["path_models"]["point_label_by_day_night"]["model_ref"] == "data/models/test.pkl"

    switched = svc.switch_to_fallback_path("精度回退 smoke")
    assert switched["production_path"] == "point_label_by_day_night"
    assert switched["fallback_path"] == "legacy_day"
    assert switched["production_model_ref"] == "data/models/test.pkl"
