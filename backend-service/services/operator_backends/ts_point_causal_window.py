from services.operator_backends._ts_point_utils import parse_contract, require_dataframe, window_result_to_dict
from services.timeseries_point.causal_window import build_causal_window_for_pending_point

OPERATOR_ID = "ts_point_causal_window"


def execute(params: dict, inputs: dict) -> dict:
    data = require_dataframe(inputs, OPERATOR_ID)
    contract = parse_contract(params)
    if "contract" in inputs and isinstance(inputs["contract"], dict):
        contract = {**inputs["contract"], **contract}
    pending_index = int(params.get("pending_row_index") or inputs.get("pending_row_index") or len(data) - 1)
    context_length = int(params.get("context_length") or contract.get("context_length") or 8)
    max_gap = params.get("max_gap_seconds")
    if max_gap is not None:
        max_gap = float(max_gap)
    result = build_causal_window_for_pending_point(
        data,
        entity_keys=list(contract.get("entity_keys") or []),
        time_column=str(contract.get("time_column") or "event_time"),
        feature_columns=list(contract.get("feature_columns") or []),
        pending_row_index=pending_index,
        context_length=context_length,
        max_gap_seconds=max_gap,
    )
    return {"window_result": window_result_to_dict(result)}
