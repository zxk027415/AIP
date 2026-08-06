"""切分模式对比：指标提取与落盘（工作流执行用 mock）。"""

from __future__ import annotations

import json

from services.iterative_labeling import split_mode_compare as smc


def test_extract_metrics_from_top_level():
    metrics = smc._extract_metrics({"metrics": {"macro_f1_mean": 0.8, "accuracy_mean": 0.9}})
    assert metrics["macro_f1_mean"] == 0.8


def test_compare_split_modes_with_mocked_runner(tmp_path, monkeypatch):
    calls = []

    def fake_run_one_mode(**kwargs):
        mode = kwargs.get("solar_mode") or ""
        calls.append(mode)
        score = {"daylight": 0.7, "day_and_night": 0.85, "": 0.6}.get(mode, 0.5)
        return {
            "solar_mode": mode,
            "label": smc.MODE_LABELS.get(mode, mode),
            "status": "ok",
            "elapsed_sec": 0.1,
            "n_samples": 100,
            "n_classes": 5,
            "macro_f1_mean": score,
            "macro_f1_std": 0.01,
            "accuracy_mean": score + 0.05,
            "accuracy_std": 0.01,
            "error": None,
        }

    monkeypatch.setattr(smc, "run_one_mode", fake_run_one_mode)
    monkeypatch.setattr(smc, "_BACKEND", tmp_path)

    out = smc.compare_split_modes(
        slot="pv_fault",
        dataset_path="backend-service/data/demo/x.csv",
        modes=["", "daylight", "day_and_night"],
        n_repeats=1,
    )
    assert out["best_solar_mode"] == "day_and_night"
    assert out["best_macro_f1_mean"] == 0.85
    assert calls == ["", "daylight", "day_and_night"]
    saved = json.loads(
        (tmp_path / "data" / "iterative_labeling" / "split_mode_compare" / "pv_fault" / "latest.json")
        .read_text(encoding="utf-8")
    )
    assert saved["best_solar_mode"] == "day_and_night"
    status = json.loads(
        (tmp_path / "data" / "iterative_labeling" / "split_mode_compare" / "pv_fault" / "status.json")
        .read_text(encoding="utf-8")
    )
    assert status["status"] == "completed"
    loaded = smc.load_latest_compare("pv_fault")
    assert loaded and loaded["best_solar_mode"] == "day_and_night"
    assert smc.load_compare_status("pv_fault")["status"] == "completed"
