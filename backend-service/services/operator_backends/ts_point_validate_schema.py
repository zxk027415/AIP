from services.operator_backends._ts_point_utils import parse_contract, require_dataframe
from services.operator_execution.router import OperatorExecutionError
from services.timeseries_point.validate_schema import validate_point_schema

OPERATOR_ID = "ts_point_validate_schema"


def _normalize_point_frame(data, contract: dict) -> tuple:
    import pandas as pd

    frame = data.copy()
    audit = {"dropped_invalid_timestamps": 0, "deduplicated_rows": 0}
    time_column = contract.get("time_column")
    if time_column and time_column in frame.columns and str(contract.get("clock_mode") or "event_time") == "event_time":
        try:
            parsed = pd.to_datetime(frame[time_column], errors="coerce", utc=True, format="mixed")
        except (TypeError, ValueError):
            parsed = pd.to_datetime(frame[time_column], errors="coerce", utc=True)
        dropped = int(parsed.isna().sum())
        frame[time_column] = parsed
        if dropped:
            frame = frame.loc[parsed.notna()].copy()
            audit["dropped_invalid_timestamps"] = dropped
    keys = [key for key in list(contract.get("entity_keys") or []) + [time_column] if key]
    if keys and all(key in frame.columns for key in keys):
        before = len(frame)
        # 冻结快照会叠多次 label-space 重编号；keep first 才能保住正常类 0。
        frame = frame.drop_duplicates(subset=keys, keep="first").copy()
        audit["deduplicated_rows"] = before - len(frame)
    return frame, audit


def execute(params: dict, inputs: dict) -> dict:
    data = require_dataframe(inputs, OPERATOR_ID)
    contract = parse_contract(params)
    if "contract" in inputs and isinstance(inputs["contract"], dict):
        contract = {**inputs["contract"], **contract}
    data, audit = _normalize_point_frame(data, contract)
    report = validate_point_schema(data, contract)
    if audit.get("deduplicated_rows") or audit.get("dropped_invalid_timestamps"):
        report = {**report, **audit, "normalized": True}
    if not report["valid"]:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "SchemaError",
            f"invalid point schema: {report.get('issues')}",
        )
    return {"valid": True, "report": report, "data": data, "contract": contract}
