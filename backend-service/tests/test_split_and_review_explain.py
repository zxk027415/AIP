"""审核解释辅助单测。"""

from __future__ import annotations

import numpy as np

from services.iterative_labeling.review_explanations import (
    build_feature_matrix_from_batch,
    get_unit_feature_vector,
    unit_key_from_parts,
)
from services.iterative_labeling.shap_explainer import ShapExplainer


def test_feature_vector_shap_and_similar_helpers():
    from sklearn.ensemble import RandomForestClassifier

    uk = unit_key_from_parts("s", "d", "b", "2024-01-01")
    batch = {
        "feature_list": ["f0", "f1"],
        "unit_features": {
            uk: {"f0": 0.1, "f1": 0.9},
            unit_key_from_parts("s", "d2", "b", "2024-01-01"): {"f0": 0.12, "f1": 0.88},
            unit_key_from_parts("s", "d3", "b", "2024-01-02"): {"f0": 0.9, "f1": 0.1},
        },
        "predictions": [
            {"site_id": "s", "device_id": "d", "branch_id": "b", "time_window": "2024-01-01", "predicted_label": 1, "confidence": 0.5},
            {"site_id": "s", "device_id": "d2", "branch_id": "b", "time_window": "2024-01-01", "predicted_label": 1, "confidence": 0.6},
            {"site_id": "s", "device_id": "d3", "branch_id": "b", "time_window": "2024-01-02", "predicted_label": 2, "confidence": 0.7},
        ],
    }
    vec, names, reason = get_unit_feature_vector(batch, uk, ["f0", "f1"])
    assert reason == "ok"
    assert names == ["f0", "f1"]
    assert vec is not None and vec.shape == (2,)

    matrix, _, meta = build_feature_matrix_from_batch(batch, ["f0", "f1"])
    assert matrix.shape[0] == 3
    assert len(meta) == 3

    X = np.array([[0.1, 0.9], [0.12, 0.88], [0.9, 0.1]], dtype=float)
    y = [1, 1, 0]
    model = RandomForestClassifier(n_estimators=8, random_state=0).fit(X, y)
    out = ShapExplainer().compute_explanations(model, vec.reshape(1, -1), names, shap_top_k=2)
    assert out and out[0]["available"] is True
    assert len(out[0]["top_features"]) == 2
