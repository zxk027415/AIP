# @AI_GENERATED
"""P4-β 评估/采样波 — L3 性质 + L4 确定性重放。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.operators.eval_smoke_cases import P4_BETA_EVAL, eval_beta_smoke_specs

_SPECS = eval_beta_smoke_specs()
_SPEC_BY_ID = {s[0]: s for s in _SPECS}

MODEL_ROUNDTRIP_OPS = frozenset({"random_forest_classifier"})


def _cases_for(op_ids):
    missing = sorted(op_ids - set(_SPEC_BY_ID))
    if missing:
        raise RuntimeError(f"eval_smoke_cases 缺少: {missing}")
    return [_SPEC_BY_ID[op] for op in sorted(op_ids)]


def _assert_replay_equal(op_id: str, r1: dict, r2: dict):
    if op_id == "confusion_matrix":
        pd.testing.assert_frame_equal(r1["matrix"], r2["matrix"])
        assert r1["report"] == r2["report"]
        return
    if op_id == "mse_rmse_mae":
        for k in ("mse", "rmse", "mae"):
            assert float(r1[k]) == pytest.approx(float(r2[k]), rel=1e-9, abs=1e-9)
        return
    if op_id == "smape_score":
        assert float(r1["score"]) == pytest.approx(float(r2["score"]), rel=1e-9, abs=1e-9)
        return
    if op_id == "precision_recall_f1":
        for k in ("accuracy", "precision", "recall", "f1"):
            assert float(r1[k]) == pytest.approx(float(r2[k]), rel=1e-9, abs=1e-9)
        return
    if op_id == "stratified_cv_eval":
        assert r1["accuracy_mean"] == r2["accuracy_mean"]
        assert r1["macro_f1_mean"] == r2["macro_f1_mean"]
        assert r1["confusion_matrix"]["data"] == r2["confusion_matrix"]["data"]
        return
    if op_id == "random_forest_classifier":
        np.testing.assert_array_equal(r1["predictions"], r2["predictions"])
        np.testing.assert_array_equal(r1["y_true"], r2["y_true"])
        return
    if op_id == "smote_oversample":
        pd.testing.assert_frame_equal(
            r1["features"].reset_index(drop=True),
            r2["features"].reset_index(drop=True),
            check_dtype=False,
            rtol=1e-8,
            atol=1e-8,
        )
        np.testing.assert_array_equal(r1["target"], r2["target"])
        return
    if op_id == "tsfresh_extract":
        pd.testing.assert_frame_equal(
            r1["data"], r2["data"], check_dtype=False, rtol=1e-8, atol=1e-8,
        )


@pytest.mark.parametrize("case", _cases_for(P4_BETA_EVAL), ids=lambda c: c[0])
def test_p4_beta_eval_layer3_contract_property(router, tmp_path, case):
    op_id, params_builder, inputs_builder, expected_keys, _kind = case
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    result = router.execute(op_id, params, inputs)
    assert isinstance(result, dict)
    for key in expected_keys:
        assert key in result, f"{op_id} missing {key}"


@pytest.mark.parametrize(
    "case",
    [c for c in _cases_for(P4_BETA_EVAL) if c[0] not in MODEL_ROUNDTRIP_OPS],
    ids=lambda c: c[0],
)
def test_p4_beta_eval_layer4_deterministic_replay(router, tmp_path, case):
    op_id, params_builder, inputs_builder, _keys, _kind = case
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    r1 = router.execute(op_id, params, inputs)
    r2 = router.execute(op_id, params, inputs)
    _assert_replay_equal(op_id, r1, r2)
# @AI_GENERATED: end
