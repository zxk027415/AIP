from services.operator_backends._ts_point_utils import parse_contract, require_dataframe
from services.timeseries_point.label_join import join_point_labels

OPERATOR_ID = "ts_point_label_join"


def execute(params: dict, inputs: dict) -> dict:
    data = require_dataframe(inputs, OPERATOR_ID)
    labels = inputs.get("labels")
    contract = parse_contract(params)
    if "contract" in inputs and isinstance(inputs["contract"], dict):
        contract = {**inputs["contract"], **contract}
    joined, audit = join_point_labels(
        data,
        labels,
        entity_keys=list(contract.get("entity_keys") or []),
        time_column=str(contract.get("time_column") or "event_time"),
        label_column=str(contract.get("label_column") or "label"),
    )
    return {"data": joined, "audit": audit, "contract": contract}
