"""采样策略与 day_and_night 切分对齐验收。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from services.iterative_labeling.sampling_strategy import SamplingStrategy
from services.iterative_labeling.iaa_evaluator import IAAEvaluator
from services.iterative_labeling.pseudo_backfill import PseudoBackfillService
from services.iterative_labeling.shap_explainer import ShapExplainer
from services.iterative_labeling.pv_training_workspace import PVTrainingWorkspaceService


def _units():
    return [
        {
            "unit_key": "a",
            "disagreement": False,
            "classifier_prediction": {"confidence": 0.9, "predicted_label": 1},
        },
        {
            "unit_key": "b",
            "disagreement": True,
            "classifier_prediction": {"confidence": 0.2, "predicted_label": 2},
        },
        {
            "unit_key": "c",
            "disagreement": False,
            "classifier_prediction": {"confidence": 0.5, "predicted_label": 1},
        },
    ]


def test_uncertainty_sorts_low_confidence_first():
    ordered = SamplingStrategy().sort_units(_units(), strategy="uncertainty")
    assert [u["unit_key"] for u in ordered] == ["b", "c", "a"]


def test_disagreement_first_strategy():
    ordered = SamplingStrategy().sort_units(_units(), strategy="disagreement_first")
    assert ordered[0]["unit_key"] == "b"
    assert ordered[0]["disagreement"] is True


def test_cohen_kappa_perfect_agreement():
    evaluator = IAAEvaluator()
    result = evaluator.compute_kappa(
        {
            "r1": [{"unit_key": "u1", "verdict_label": 1}, {"unit_key": "u2", "verdict_label": 0}],
            "r2": [{"unit_key": "u1", "verdict_label": 1}, {"unit_key": "u2", "verdict_label": 0}],
        }
    )
    assert result["iaa_method"] == "cohen"
    assert result["iaa_score"] == 1.0


def test_pseudo_backfill_truncates(tmp_path):
    svc = PseudoBackfillService(data_root=tmp_path)
    preds = [
        {"unit_key": f"u{i}", "predicted_label": 1, "confidence": 0.99}
        for i in range(10)
    ]
    out = svc.execute(
        slot="pv_fault",
        loop_id="loop-1",
        prediction_batch_id="pred-test",
        predictions=preds,
        pseudo_label_threshold=0.9,
        pseudo_label_max_ratio=0.3,
    )
    assert out["final_pseudo_count"] == 3
    assert out["truncated"] is True
    assert Path(tmp_path / "pseudo_backfills" / "pv_fault" / f"{out['backfill_id']}.json").exists()


def test_shap_importance_fallback():
    from sklearn.ensemble import RandomForestClassifier

    X = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.1]], dtype=float)
    y = [0, 1, 0]
    model = RandomForestClassifier(n_estimators=5, random_state=0).fit(X, y)
    # Force fallback path by monkeypatching import failure is heavy; call _importance_fallback directly
    out = ShapExplainer()._importance_fallback(model, X, ["f0", "f1"], top_k=1)
    assert len(out) == 3
    assert out[0]["available"] is True
    assert len(out[0]["top_features"]) == 1


def test_train_predict_workflows_share_day_and_night():
    root = Path(__file__).resolve().parents[1]
    wf_dir = root / "data" / "workflows_enhanced"
    train = json.loads(
        (wf_dir / "workflow-pv-fault-diag-quickval-cv-v1.json").read_text(encoding="utf-8")
    )
    predict = json.loads(
        (wf_dir / "workflow-pv-fault-diag-quickval-predict-v1.json").read_text(encoding="utf-8")
    )

    def _split_cfg(wf):
        for node in wf.get("nodes") or []:
            cfg = ((node.get("data") or {}).get("config") or {})
            if cfg.get("functionId") == "time_window_split":
                return cfg
        raise AssertionError("time_window_split node missing")

    t_cfg = _split_cfg(train)
    p_cfg = _split_cfg(predict)
    assert t_cfg.get("window") == p_cfg.get("window") == "1d"
    # split parity 机制已移除（pv-fault-label-segment-redesign task 21）；策略随模型持久化
