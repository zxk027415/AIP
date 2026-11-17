from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "ts_point_persistence_alarm"


def execute(params: dict, inputs: dict) -> dict:
    raise OperatorExecutionError(
        OPERATOR_ID,
        "Disabled",
        "P1 deferred: persistence alarm not enabled in P0",
    )
