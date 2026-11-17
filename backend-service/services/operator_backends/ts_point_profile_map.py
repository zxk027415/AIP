from services.operator_backends._ts_point_utils import parse_contract, require_dataframe
from services.timeseries_point.profile_map import apply_profile_map

OPERATOR_ID = "ts_point_profile_map"


def execute(params: dict, inputs: dict) -> dict:
    data = require_dataframe(inputs, OPERATOR_ID)
    contract = parse_contract(params)
    mapped, profile_contract = apply_profile_map(data, contract)
    return {"data": mapped, "contract": profile_contract}
