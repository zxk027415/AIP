# @AI_GENERATED
"""
Base interface definition for operator backends.

Every operator backend module in this directory should follow this pattern:

    OPERATOR_ID: str = "your_operator_id"

    def execute(params: dict, inputs: dict) -> dict:
        '''
        Execute the operator.

        Args:
            params: Operator parameters (from node config + advanced params + global config)
            inputs: Upstream operator data (key = port name)

        Returns:
            dict: Execution result (key = output port name)

        Raises:
            OperatorExecutionError: On execution failure
        '''
        ...

The OperatorRouter auto-discovers modules that export OPERATOR_ID and execute().
"""
from services.operator_execution.router import OperatorExecutionError

__all__ = ["OperatorExecutionError"]
# @AI_GENERATED: end
