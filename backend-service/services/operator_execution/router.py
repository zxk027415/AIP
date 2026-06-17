# @AI_GENERATED
"""
Operator Router - Routes operator IDs to their backend execute functions.
Auto-discovers operator backends from the operator_backends/ directory.
"""
import importlib
import os
import sys
from typing import Callable, Dict
from loguru import logger


class OperatorExecutionError(Exception):
    """Raised when an operator execution fails."""

    def __init__(self, operator_id: str, error_type: str, message: str):
        self.operator_id = operator_id
        self.error_type = error_type
        self.message = message
        super().__init__(f"[{operator_id}] {error_type}: {message}")


class OperatorRouter:
    """
    Routes operator IDs from functions.json to their backend execute functions.
    New operators only need to add a module in operator_backends/ with OPERATOR_ID and execute().
    """

    def __init__(self):
        self._registry: Dict[str, Callable] = {}

    def register(self, operator_id: str, execute_fn: Callable) -> None:
        """Register an operator backend execute function."""
        self._registry[operator_id] = execute_fn
        logger.info(f"Registered operator backend: {operator_id}")

    def auto_discover(self, backends_dir: str) -> None:
        """
        Scan backends_dir for Python modules that export OPERATOR_ID and execute().
        Auto-register each discovered operator.
        """
        if not os.path.isdir(backends_dir):
            logger.warning(f"Operator backends directory not found: {backends_dir}")
            return

        # Add parent dir to sys.path if needed
        parent_dir = os.path.dirname(backends_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        package_name = os.path.basename(backends_dir)

        for filename in sorted(os.listdir(backends_dir)):
            if filename.endswith(".py") and not filename.startswith("_"):
                module_name = filename[:-3]
                try:
                    module = importlib.import_module(f"{package_name}.{module_name}")
                    op_id = getattr(module, "OPERATOR_ID", None)
                    execute_fn = getattr(module, "execute", None)

                    if op_id and callable(execute_fn):
                        self.register(op_id, execute_fn)
                    else:
                        logger.debug(
                            f"Skipping {module_name}: missing OPERATOR_ID or execute()"
                        )
                except Exception as e:
                    logger.error(f"Failed to load operator backend {module_name}: {e}")

    def execute(self, operator_id: str, params: dict, inputs: dict) -> dict:
        """
        Execute an operator by its ID.

        Args:
            operator_id: The operator ID from functions.json
            params: Operator parameters (from node config + advanced params + global config)
            inputs: Upstream operator data (key = port name)

        Returns:
            dict: Execution result (key = output port name)

        Raises:
            OperatorExecutionError: If operator not found or execution fails
        """
        if operator_id not in self._registry:
            raise OperatorExecutionError(
                operator_id,
                "OperatorNotFoundError",
                f"Operator '{operator_id}' is not registered. "
                f"Available: {sorted(self._registry.keys())}",
            )

        execute_fn = self._registry[operator_id]
        try:
            return execute_fn(params, inputs)
        except OperatorExecutionError:
            raise
        except Exception as e:
            raise OperatorExecutionError(
                operator_id, type(e).__name__, str(e)
            ) from e

    def has_operator(self, operator_id: str) -> bool:
        """Check if an operator is registered."""
        return operator_id in self._registry

    def list_operators(self) -> list:
        """List all registered operator IDs."""
        return sorted(self._registry.keys())
# @AI_GENERATED: end
