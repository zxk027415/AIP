from services.operator_backends._ts_point_utils import parse_contract, require_dataframe
from services.timeseries_point.train_adapter import train_real_point_classifier

OPERATOR_ID = "ts_point_train_classifier"


def _optional_positive_int(params: dict, key: str, *, missing_default: int | None) -> int | None:
    if key not in params:
        return missing_default
    raw = params.get(key)
    if raw in (None, "", "full"):
        return None
    return int(raw)


def execute(params: dict, inputs: dict) -> dict:
    data = require_dataframe(inputs, OPERATOR_ID)
    contract = parse_contract(params)
    if "contract" in inputs and isinstance(inputs["contract"], dict):
        contract = {**inputs["contract"], **contract}
    result = train_real_point_classifier(
        data,
        contract={
            **contract,
            "split_column": "_split",
            "label_column": contract.get("label_column") or "label",
        },
        output_root=str(params.get("output_root") or "backend-service/data/models/timeseries_point"),
        epochs=int(params.get("epochs") or 1),
        max_train_batches=_optional_positive_int(params, "max_train_batches", missing_default=2),
        context_length=int(params.get("context_length") or contract.get("context_length") or 8),
    )
    return {
        "model_path": result["model_path"],
        "dataset_dir": result["dataset_dir"],
        "train_result": result["train_result"],
        "contract": result["contract"],
    }
