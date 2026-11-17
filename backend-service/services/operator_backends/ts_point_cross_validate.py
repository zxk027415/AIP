from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "ts_point_cross_validate"


def execute(params: dict, inputs: dict) -> dict:
    raise OperatorExecutionError(
        OPERATOR_ID,
        "Disabled",
        "P1 deferred: point cross-validation not enabled in P0",
    )
