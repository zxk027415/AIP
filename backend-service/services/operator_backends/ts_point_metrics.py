from services.timeseries_point.metrics import compute_point_metrics

OPERATOR_ID = "ts_point_metrics"


def execute(params: dict, inputs: dict) -> dict:
    outcomes = inputs.get("outcomes") or inputs.get("point_outcomes") or []
    if isinstance(outcomes, dict):
        outcomes = [outcomes]
    return {"metrics": compute_point_metrics(list(outcomes))}
