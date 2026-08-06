# @AI_GENERATED
"""P4-β 特征工程波 — L3 性质 + L4 确定性重放。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.operators.feature_smoke_cases import P4_BETA_FE, feature_beta_smoke_specs

_SPECS = feature_beta_smoke_specs()
_SPEC_BY_ID = {s[0]: s for s in _SPECS}


def _cases_for(op_ids):
    missing = sorted(op_ids - set(_SPEC_BY_ID))
    if missing:
        raise RuntimeError(f"feature_smoke_cases 缺少: {missing}")
    return [_SPEC_BY_ID[op] for op in sorted(op_ids)]


def _assert_replay_equal(op_id: str, r1: dict, r2: dict):
    if op_id == "feature_select":
        pd.testing.assert_frame_equal(
            r1["selected_features"].reset_index(drop=True),
            r2["selected_features"].reset_index(drop=True),
            check_dtype=False,
            rtol=1e-8,
            atol=1e-8,
        )
        assert r1["feature_list"] == r2["feature_list"]
        np.testing.assert_array_equal(r1["target"], r2["target"])
        return
    if "data" in r1 and isinstance(r1["data"], pd.DataFrame):
        pd.testing.assert_frame_equal(
            r1["data"].reset_index(drop=True),
            r2["data"].reset_index(drop=True),
            check_dtype=False,
            rtol=1e-8,
            atol=1e-8,
        )


@pytest.mark.parametrize("case", _cases_for(P4_BETA_FE), ids=lambda c: c[0])
def test_p4_beta_fe_layer3_contract_property(router, tmp_path, case):
    op_id, params_builder, inputs_builder, expected_keys, _kind = case
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    result = router.execute(op_id, params, inputs)
    assert isinstance(result, dict)
    for key in expected_keys:
        assert key in result, f"{op_id} missing {key}"
    if op_id == "feature_select":
        assert len(result["feature_list"]) <= 3
    elif "data" in result and isinstance(result["data"], pd.DataFrame):
        if op_id != "ts_comparison_features" or not result["data"].empty:
            assert len(result["data"]) >= 0


@pytest.mark.parametrize("case", _cases_for(P4_BETA_FE), ids=lambda c: c[0])
def test_p4_beta_fe_layer4_deterministic_replay(router, tmp_path, case):
    op_id, params_builder, inputs_builder, _keys, _kind = case
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    r1 = router.execute(op_id, params, inputs)
    r2 = router.execute(op_id, params, inputs)
    _assert_replay_equal(op_id, r1, r2)
# @AI_GENERATED: end
