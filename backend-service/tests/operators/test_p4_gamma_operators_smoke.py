# @AI_GENERATED
"""P4-γ 剩余算子烟测（L2）。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from tests.operators.p4_gamma_smoke_cases import P4_GAMMA, gamma_smoke_specs

_OPTIONAL_DEPS = {
    "lightgbm_forecast": "lightgbm",
    "auto_tune_lightgbm": "lightgbm",
    "catboost_forecast": "catboost",
    "auto_tune_catboost": "catboost",
}


def _extra(kind: str):
    if kind == "dataframe":
        def _check(r):
            assert isinstance(r.get("data"), pd.DataFrame)
        return _check
    if kind == "split_ts":
        def _check(r):
            assert len(r["train_features"]) > len(r["test_features"])
        return _check
    if kind == "multi_step":
        def _check(r):
            assert isinstance(r["forecast_config"], dict)
            assert r["forecast_config"].get("forecast_steps") == 4
        return _check
    if kind == "forecast_train":
        def _check(r):
            assert len(r["predictions"]) > 0
        return _check
    if kind == "ensemble":
        def _check(r):
            assert len(r["y_pred"]) == 4
        return _check
    if kind == "artifact":
        def _check(r):
            assert r.get("saved") is True or r.get("model") is not None
        return _check
    if kind == "batch_predict":
        def _check(r):
            assert isinstance(r["predictions"], pd.DataFrame)
            assert r["failure_count"] == 0
        return _check
    if kind == "auto_tune":
        def _check(r):
            assert isinstance(r["best_params"], dict)
            assert r["model"] is not None
        return _check
    return lambda _r: None


_SPECS = gamma_smoke_specs()
CASES = [(s[0], s[1], s[2], s[3], _extra(s[4])) for s in _SPECS]


def _skip_if_missing_dep(op_id: str):
    mod = _OPTIONAL_DEPS.get(op_id)
    if mod:
        pytest.importorskip(mod)


@pytest.mark.parametrize(
    "op_id,params_builder,inputs_builder,expected_keys,extra_asserts",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_p4_gamma_smoke(router, tmp_path, op_id, params_builder, inputs_builder, expected_keys, extra_asserts):
    _skip_if_missing_dep(op_id)
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)

    if op_id == "load_api":
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = [{"record_time": "2024-01-01", "value": 1.0}]
        with patch("services.operator_backends.load_api.requests.get", return_value=mock_resp):
            result = router.execute(op_id, params, inputs)
    else:
        result = router.execute(op_id, params, inputs)

    assert isinstance(result, dict), op_id
    for key in expected_keys:
        assert key in result, f"{op_id} missing {key}"
    extra_asserts(result)
# @AI_GENERATED: end
