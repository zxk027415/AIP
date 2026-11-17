from services.operator_backends._ts_point_utils import outcome_to_dict
from services.timeseries_point.causal_window import build_causal_window_for_pending_point
from services.timeseries_point.contract import WindowResult
from services.timeseries_point.predict import predict_point_outcome

OPERATOR_ID = "ts_point_predict"


def execute(params: dict, inputs: dict) -> dict:
    window_payload = inputs.get("window_result")
    if isinstance(window_payload, dict):
        window = WindowResult(
            status=str(window_payload.get("status") or "not_ready"),
            reason=window_payload.get("reason"),
            window_tensor=window_payload.get("window_tensor"),
            entity_key=window_payload.get("entity_key"),
            point_time=window_payload.get("point_time"),
            context_length=int(window_payload.get("context_length") or 0),
        )
    else:
        window = WindowResult(status="not_ready", reason="missing_window_result")

    artifact_dir = params.get("model_ref") or inputs.get("model_ref") or inputs.get("model_path")
    outcome = predict_point_outcome(window, artifact_dir=artifact_dir)
    return {"point_outcome": outcome_to_dict(outcome)}
