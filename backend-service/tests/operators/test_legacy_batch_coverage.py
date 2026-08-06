# @AI_GENERATED
"""
P4 Legacy Wave L1 + ks_test — L3 性质 + L4 确定性重放。

从 legacy_smoke_cases 复用入参，补齐六重中的 L3/L4。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.operators.legacy_smoke_cases import P4_NEW_OPERATORS, LEGACY_WAVE_L1, legacy_wave_l1_smoke_specs

P4_ALPHA = LEGACY_WAVE_L1 | P4_NEW_OPERATORS

_SPECS = legacy_wave_l1_smoke_specs()
_SPEC_BY_ID = {s[0]: s for s in _SPECS}


def _cases_for(op_ids):
    missing = sorted(op_ids - set(_SPEC_BY_ID))
    if missing:
        raise RuntimeError(f"legacy_smoke_cases 缺少: {missing}")
    return [_SPEC_BY_ID[op] for op in sorted(op_ids)]


def _assert_replay_equal(op_id: str, r1: dict, r2: dict):
    if "data" in r1 and isinstance(r1["data"], pd.DataFrame):
        pd.testing.assert_frame_equal(
            r1["data"].reset_index(drop=True),
            r2["data"].reset_index(drop=True),
            check_dtype=False,
            rtol=1e-8,
            atol=1e-8,
        )
    if "outlier_indices" in r1:
        assert r1["outlier_indices"] == r2["outlier_indices"]
    if "statistic" in r1:
        assert float(r1["statistic"]) == pytest.approx(float(r2["statistic"]), rel=1e-9, abs=1e-9)
        assert float(r1["pvalue"]) == pytest.approx(float(r2["pvalue"]), rel=1e-9, abs=1e-9)
        assert r1["drift_detected"] == r2["drift_detected"]


@pytest.mark.parametrize("case", _cases_for(P4_ALPHA), ids=lambda c: c[0])
def test_p4_alpha_layer3_contract_property(router, tmp_path, case):
    op_id, params_builder, inputs_builder, expected_keys, _kind = case
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    result = router.execute(op_id, params, inputs)
    assert isinstance(result, dict)
    for key in expected_keys:
        assert key in result, f"{op_id} missing {key}"
    if "data" in result and isinstance(result["data"], pd.DataFrame):
        assert len(result["data"]) > 0, op_id
    if "statistic" in result:
        assert np.isfinite(float(result["statistic"]))
        assert np.isfinite(float(result["pvalue"]))


@pytest.mark.parametrize("case", _cases_for(P4_ALPHA), ids=lambda c: c[0])
def test_p4_alpha_layer4_deterministic_replay(router, tmp_path, case):
    op_id, params_builder, inputs_builder, _keys, _kind = case
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    r1 = router.execute(op_id, params, inputs)
    r2 = router.execute(op_id, params, inputs)
    _assert_replay_equal(op_id, r1, r2)
# @AI_GENERATED: end
