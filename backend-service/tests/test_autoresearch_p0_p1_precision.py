import json
from unittest.mock import patch

import pytest

from api import workflows_enhanced as wf


def test_pool_evidence_from_summary_single_window_positive():
    entry = {
        "source_run_id": "ares-test",
        "source_iteration": 2,
        "summary": {
            "windows_total": 1,
            "windows_comparable": 1,
            "windows_challenger_better": 1,
            "score_advantage": 0.12,
        },
        "window_results": [{"status": "success"}],
        "effective_parameter_patch": {"train_days": 45},
    }
    evidence = wf._pool_evidence_from_entry(entry, run_id="ares-test")
    assert evidence["evidence_strength"] == "single_window_positive"
    assert evidence["mape_improvement"] == pytest.approx(0.12)


def test_pool_evidence_from_summary_multi_window_confirmed():
    entry = {
        "source_run_id": "ares-test",
        "source_iteration": 3,
        "summary": {
            "windows_total": 3,
            "windows_comparable": 3,
            "windows_challenger_better": 2,
            "score_advantage": 0.25,
        },
        "window_results": [
            {"status": "success"},
            {"status": "success"},
            {"status": "success"},
        ],
    }
    evidence = wf._pool_evidence_from_entry(entry, run_id="ares-test")
    assert evidence["evidence_strength"] == "multi_window_confirmed"


def test_auto_enqueue_uses_derived_evidence(tmp_path, monkeypatch):
    candidate = {
        "id": "cand-test-auto-enq",
        "source_run_id": "ares-test",
        "source_iteration": 1,
        "baseline_workflow_id": "wf-base",
        "challenger_workflow_id": "wf-base",
        "evaluation_contract": {},
        "summary": {
            "windows_total": 1,
            "windows_comparable": 1,
            "windows_challenger_better": 1,
            "score_advantage": 0.05,
        },
        "window_results": [{"status": "success"}],
        "novelty_audit": {"is_novel": True},
        "effective_parameter_patch": {"train_days": 60},
    }
    pool_path = tmp_path / "candidate_pool.json"
    queue_path = tmp_path / "verification_queue.json"
    pool_path.write_text(json.dumps({"candidates": [candidate]}), encoding="utf-8")
    queue_path.write_text(json.dumps({"items": []}), encoding="utf-8")

    monkeypatch.setattr(wf, "_CANDIDATE_POOL_JSON", str(pool_path))
    monkeypatch.setattr(wf, "_VERIFICATION_QUEUE_JSON", str(queue_path))
    logs = []

    count = wf._auto_enqueue_candidates_for_verification(
        "ares-test",
        max_batch=2,
        logger_fn=lambda msg, _typ: logs.append(msg),
    )
    assert count == 1
    assert any("auto-enqueue" in msg for msg in logs)
    saved_pool = json.loads(pool_path.read_text(encoding="utf-8"))["candidates"][0]
    assert saved_pool["evidence"]["evidence_strength"] == "single_window_positive"
    saved_queue = json.loads(queue_path.read_text(encoding="utf-8"))["items"]
    assert len(saved_queue) == 1
    assert saved_queue[0]["candidate_id"] == "cand-test-auto-enq"


def test_bootstrap_train_profile_marks_full_training_dataset(monkeypatch):
    import pandas as pd

    class _FakeProfile:
        profile_quality = {"source": "time_load_dataframe", "point_count": 100}

        def to_dict(self):
            return {"profile_quality": dict(self.profile_quality)}

    def _fake_load(*_args, **_kwargs):
        ts = pd.date_range("2026-01-01", periods=96 * 3, freq="15min")
        return pd.DataFrame({"record_time": ts, "load": range(len(ts))})

    monkeypatch.setattr(wf, "load_workflow_from_file", lambda _wid: object())
    monkeypatch.setattr(wf, "_load_csv_config_from_workflow", lambda _wf: {"file_path": "datasets/x.csv"})
    monkeypatch.setattr(wf.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(
        "services.reference_rolling_backtest.data_io.resolve_dataset_path",
        lambda rel, _backend: rel,
    )
    monkeypatch.setattr(
        "services.reference_rolling_backtest.data_io.load_wide_or_long_load_series",
        _fake_load,
    )
    monkeypatch.setattr(
        "services.dataset_profiler.DatasetProfiler.compute_train_profile",
        lambda self, df, train_fit_mape=None: _FakeProfile(),
    )

    profile = wf._bootstrap_train_profile_at_run_start(
        "workflow-test",
        [{"start_date": "2026-03-01", "end_date": "2026-03-08"}],
        {"train_days": 30},
    )
    assert profile is not None
    assert profile.profile_quality["source"] == "full_training_dataset"
