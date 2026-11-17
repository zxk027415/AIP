"""G3: pv_day product templates must be graph-equivalent to quickval baselines."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.workflows_enhanced import load_workflow_from_file
from services.slot_governance.workflow_equiv import metadata_product_fields, workflow_graph_signature


@pytest.mark.parametrize(
    ("product_id", "baseline_id", "expected_role"),
    [
        (
            "workflow-pv-day-train-eval-v1",
            "workflow-pv-fault-diag-quickval-cv-v1",
            "train_eval",
        ),
        (
            "workflow-pv-day-predict-v1",
            "workflow-pv-fault-diag-quickval-predict-v1",
            "predict",
        ),
    ],
)
def test_pv_day_template_graph_matches_quickval_baseline(product_id, baseline_id, expected_role):
    product = load_workflow_from_file(product_id)
    baseline = load_workflow_from_file(baseline_id)
    assert product is not None, product_id
    assert baseline is not None, baseline_id

    assert workflow_graph_signature(product) == workflow_graph_signature(baseline)

    product_meta = metadata_product_fields(product.metadata)
    assert product_meta["slot"] == "pv_day"
    assert product_meta["template_role"] == expected_role
    assert product_meta.get("slot_config_ref")


def test_quickval_baseline_has_no_product_slot_metadata():
    baseline = load_workflow_from_file("workflow-pv-fault-diag-quickval-cv-v1")
    assert baseline is not None
    meta = metadata_product_fields(baseline.metadata)
    assert meta["slot"] is None
    assert meta["template_role"] is None
