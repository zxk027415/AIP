from services.operator_backends._ts_point_utils import parse_contract
from services.timeseries_point.candidate_intervals import build_candidate_intervals

OPERATOR_ID = "ts_point_candidate_intervals"


def execute(params: dict, inputs: dict) -> dict:
    outcomes = inputs.get("outcomes") or inputs.get("point_outcomes") or []
    if isinstance(outcomes, dict):
        outcomes = [outcomes]
    contract = parse_contract(params)
    if "contract" in inputs and isinstance(inputs["contract"], dict):
        contract = {**inputs["contract"], **contract}
    intervals = build_candidate_intervals(
        list(outcomes),
        entity_keys=list(contract.get("entity_keys") or ["entity_id"]),
        min_consecutive=int(params.get("min_consecutive") or 2),
    )
    return {"candidate_intervals": intervals}
