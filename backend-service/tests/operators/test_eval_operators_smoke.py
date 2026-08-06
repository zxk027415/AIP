# @AI_GENERATED
"""P4-β 评估/采样波烟测（L2）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.operators.eval_smoke_cases import eval_beta_smoke_specs


def _extra(kind: str):
    if kind == "dataframe":
        def _check(r):
            assert isinstance(r.get("data"), pd.DataFrame)
        return _check
    if kind == "confusion_matrix":
        def _check(r):
            assert isinstance(r["matrix"], pd.DataFrame)
            assert isinstance(r["report"], str)
        return _check
    if kind == "regression_metrics":
        def _check(r):
            for k in ("mse", "rmse", "mae"):
                assert np.isfinite(float(r[k]))
        return _check
    if kind == "score":
        def _check(r):
            assert np.isfinite(float(r["score"]))
        return _check
    if kind == "classification_metrics":
        def _check(r):
            for k in ("accuracy", "precision", "recall", "f1"):
                assert np.isfinite(float(r[k]))
        return _check
    if kind == "stratified_cv":
        def _check(r):
            assert isinstance(r["confusion_matrix"], dict)
            assert "data" in r["confusion_matrix"]
        return _check
    if kind == "classifier_train":
        def _check(r):
            assert len(r["predictions"]) == len(r["y_true"])
            assert len(r["feature_list"]) > 0
        return _check
    if kind == "smote":
        def _check(r):
            assert len(r["features"]) == len(r["target"]) == 40
        return _check
    return lambda _r: None


_SPECS = eval_beta_smoke_specs()
CASES = [(s[0], s[1], s[2], s[3], _extra(s[4])) for s in _SPECS]


@pytest.mark.parametrize(
    "op_id,params_builder,inputs_builder,expected_keys,extra_asserts",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_eval_beta_smoke(router, tmp_path, op_id, params_builder, inputs_builder, expected_keys, extra_asserts):
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    result = router.execute(op_id, params, inputs)
    assert isinstance(result, dict), op_id
    for key in expected_keys:
        assert key in result, f"{op_id} missing {key}"
    extra_asserts(result)
# @AI_GENERATED: end
