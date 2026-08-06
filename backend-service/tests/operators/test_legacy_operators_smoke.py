# @AI_GENERATED
"""P4 Legacy Wave L1 + ks_test 烟测。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.operators.legacy_smoke_cases import legacy_wave_l1_smoke_specs


def _extra(kind: str):
    if kind == "dataframe":
        def _check_df(r):
            assert isinstance(r.get("data"), pd.DataFrame)
        return _check_df
    if kind == "ks_test":
        def _check(r):
            assert isinstance(r["statistic"], float)
            assert isinstance(r["pvalue"], float)
            assert isinstance(r["drift_detected"], bool)
        return _check
    return lambda _r: None


_SPECS = legacy_wave_l1_smoke_specs()
CASES = [(s[0], s[1], s[2], s[3], _extra(s[4])) for s in _SPECS]


@pytest.mark.parametrize(
    "op_id,params_builder,inputs_builder,expected_keys,extra_asserts",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_legacy_wave_l1_smoke(router, tmp_path, op_id, params_builder, inputs_builder, expected_keys, extra_asserts):
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    result = router.execute(op_id, params, inputs)
    assert isinstance(result, dict), op_id
    for key in expected_keys:
        assert key in result, f"{op_id} missing {key}"
    extra_asserts(result)
# @AI_GENERATED: end
