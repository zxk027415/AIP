# @AI_GENERATED
"""P4-β 特征工程波烟测（L2）。"""
from __future__ import annotations

import pandas as pd
import pytest

from tests.operators.feature_smoke_cases import feature_beta_smoke_specs


def _extra(kind: str):
    if kind == "dataframe":
        def _check_df(r):
            assert isinstance(r.get("data"), pd.DataFrame)
        return _check_df
    if kind == "feature_select":
        def _check(r):
            assert isinstance(r["selected_features"], pd.DataFrame)
            assert isinstance(r["feature_list"], list) and len(r["feature_list"]) > 0
            assert len(r["target"]) == len(r["selected_features"])
        return _check
    return lambda _r: None


_SPECS = feature_beta_smoke_specs()
CASES = [(s[0], s[1], s[2], s[3], _extra(s[4])) for s in _SPECS]


@pytest.mark.parametrize(
    "op_id,params_builder,inputs_builder,expected_keys,extra_asserts",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_feature_beta_smoke(router, tmp_path, op_id, params_builder, inputs_builder, expected_keys, extra_asserts):
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    result = router.execute(op_id, params, inputs)
    assert isinstance(result, dict), op_id
    for key in expected_keys:
        assert key in result, f"{op_id} missing {key}"
    extra_asserts(result)
# @AI_GENERATED: end
