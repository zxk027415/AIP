# @AI_GENERATED
"""P4-γ 剩余算子 — L3 性质 + L4 确定性重放。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.operators.p4_gamma_smoke_cases import P4_GAMMA, gamma_smoke_specs

_SPECS = gamma_smoke_specs()
_SPEC_BY_ID = {s[0]: s for s in _SPECS}

_SKIP_L4 = frozenset()  # 全部走重放；forecast 只比数值输出


def _cases_for(op_ids):
    missing = sorted(op_ids - set(_SPEC_BY_ID))
    if missing:
        raise RuntimeError(f"p4_gamma_smoke_cases 缺少: {missing}")
    return [_SPEC_BY_ID[op] for op in sorted(op_ids)]


def _assert_replay_equal(op_id: str, r1: dict, r2: dict):
    if op_id in {"ridge_forecast", "xgboost_forecast", "lightgbm_forecast", "catboost_forecast"}:
        np.testing.assert_allclose(r1["predictions"], r2["predictions"], rtol=1e-8, atol=1e-8)
        return
    if op_id.startswith("auto_tune_"):
        assert r1["best_params"].keys() == r2["best_params"].keys()
        return
    if op_id == "ensemble_forecast":
        np.testing.assert_allclose(r1["y_pred"], r2["y_pred"], rtol=1e-9, atol=1e-9)
        return
    if op_id == "batch_predict_classifier":
        pd.testing.assert_frame_equal(r1["predictions"], r2["predictions"])
        assert r1["failure_count"] == r2["failure_count"]
        return
    if op_id == "load_model_artifact":
        assert r1["model_ref"] == r2["model_ref"]
        return
    if op_id == "save_model_artifact":
        assert r1["model_ref"] == r2["model_ref"]
        assert r1["saved"] == r2["saved"]
        return
    if "data" in r1 and isinstance(r1.get("data"), pd.DataFrame):
        pd.testing.assert_frame_equal(
            r1["data"].reset_index(drop=True),
            r2["data"].reset_index(drop=True),
            check_dtype=False,
            rtol=1e-8,
            atol=1e-8,
        )
    if op_id == "train_test_split_ts":
        pd.testing.assert_frame_equal(r1["train_features"], r2["train_features"])
        np.testing.assert_array_equal(r1["train_target"], r2["train_target"])
    if op_id == "multi_step_forecast":
        assert r1["forecast_config"] == r2["forecast_config"]


@pytest.mark.parametrize("case", _cases_for(P4_GAMMA - {"load_api"}), ids=lambda c: c[0])
def test_p4_gamma_layer3_contract_property(router, tmp_path, case):
    op_id, params_builder, inputs_builder, expected_keys, _kind = case
    if op_id in {"lightgbm_forecast", "auto_tune_lightgbm"}:
        pytest.importorskip("lightgbm")
    if op_id in {"catboost_forecast", "auto_tune_catboost"}:
        pytest.importorskip("catboost")
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    result = router.execute(op_id, params, inputs)
    for key in expected_keys:
        assert key in result, f"{op_id} missing {key}"


@pytest.mark.parametrize(
    "case",
    [c for c in _cases_for(P4_GAMMA - {"load_api"}) if c[0] not in _SKIP_L4],
    ids=lambda c: c[0],
)
def test_p4_gamma_layer4_deterministic_replay(router, tmp_path, case):
    op_id, params_builder, inputs_builder, _keys, _kind = case
    if op_id in {"lightgbm_forecast", "auto_tune_lightgbm"}:
        pytest.importorskip("lightgbm")
    if op_id in {"catboost_forecast", "auto_tune_catboost"}:
        pytest.importorskip("catboost")
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    r1 = router.execute(op_id, params, inputs)
    r2 = router.execute(op_id, params, inputs)
    _assert_replay_equal(op_id, r1, r2)
# @AI_GENERATED: end
