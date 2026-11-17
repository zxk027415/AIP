from services.operator_backends._ts_point_utils import parse_contract, require_dataframe
from services.timeseries_point.temporal_split import temporal_entity_split

OPERATOR_ID = "ts_point_temporal_split"


def execute(params: dict, inputs: dict) -> dict:
    data = require_dataframe(inputs, OPERATOR_ID)
    contract = parse_contract(params)
    if "contract" in inputs and isinstance(inputs["contract"], dict):
        contract = {**inputs["contract"], **contract}
    split_df, audit = temporal_entity_split(
        data,
        entity_keys=list(contract.get("entity_keys") or []),
        time_column=str(contract.get("time_column") or "event_time"),
        train_ratio=float(params.get("train_ratio") or contract.get("train_ratio") or 0.7),
        val_ratio=float(params.get("val_ratio") or contract.get("val_ratio") or 0.15),
    )
    return {"data": split_df, "audit": audit, "contract": contract}
