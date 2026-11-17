from services.operator_backends._ts_point_utils import parse_contract, require_dataframe
from services.timeseries_point.causal_impute import causal_impute_existing_rows

OPERATOR_ID = "ts_point_causal_impute"


def execute(params: dict, inputs: dict) -> dict:
    data = require_dataframe(inputs, OPERATOR_ID)
    contract = parse_contract(params)
    if "contract" in inputs and isinstance(inputs["contract"], dict):
        contract = {**inputs["contract"], **contract}
    imputed, audit = causal_impute_existing_rows(
        data,
        entity_keys=list(contract.get("entity_keys") or []),
        time_column=str(contract.get("time_column") or "event_time"),
        feature_columns=list(contract.get("feature_columns") or []),
    )
    return {"data": imputed, "audit": audit, "contract": contract}
