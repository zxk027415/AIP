"""PV slot dataset contracts (G11)."""

from __future__ import annotations

from typing import Any

from services.operator_execution.schema_validator import DataContract

PV_RAW_MEASUREMENT = DataContract(
    contract_id="pv_raw_measurement",
    data_type="MATRIX",
    required_columns=["time", "value"],
    column_types={"time": "datetime64", "value": "float64"},
    constraints=["time_ordered"],
    description="PV 原始测点：时间 + 至少一个测点列",
)

PV_WINDOWED = DataContract(
    contract_id="pv_windowed",
    data_type="MATRIX",
    required_columns=["time"],
    column_types={"time": "datetime64"},
    constraints=["time_ordered"],
    description="切窗后的诊断单元表",
)

PV_FEATURE_MATRIX = DataContract(
    contract_id="pv_feature_matrix",
    data_type="MATRIX",
    required_columns=[],
    column_types={},
    constraints=["numeric_features"],
    description="聚类/降维前的特征矩阵",
)

PV_LABELED_CURATED = DataContract(
    contract_id="pv_labeled_curated",
    data_type="MATRIX",
    required_columns=["label"],
    column_types={"label": "int"},
    constraints=["curated_only"],
    description="专家确认后的带 label 数据集",
)

PV_CONTRACTS = {
    "pv_raw_measurement": PV_RAW_MEASUREMENT,
    "pv_windowed": PV_WINDOWED,
    "pv_feature_matrix": PV_FEATURE_MATRIX,
    "pv_labeled_curated": PV_LABELED_CURATED,
}


def build_dataset_contract(
    *,
    slot: str,
    kind: str,
    dataset_id: str,
    columns: list[str],
    entity_keys: list[str] | None = None,
    time_field: str = "time",
    measure_fields: list[str] | None = None,
    label_field: str = "label",
) -> dict[str, Any]:
    """Build a JSON-serializable dataset_contract for downstream operators."""
    entity_keys = entity_keys or ["site_id", "device_id", "branch_id"]
    measure_fields = measure_fields or [c for c in ("value", "i_cal") if c in columns]
    present_entities = [c for c in entity_keys if c in columns]
    contract_id = "pv_labeled_curated" if label_field in columns else "pv_raw_measurement"
    return {
        "contract_id": contract_id,
        "slot": slot,
        "kind": kind,
        "dataset_id": dataset_id,
        "entity_keys": present_entities,
        "time_field": time_field if time_field in columns else None,
        "measure_fields": measure_fields,
        "label_field": label_field if label_field in columns else None,
        "window_key": "date" if "date" in columns else None,
        "columns": list(columns),
    }
