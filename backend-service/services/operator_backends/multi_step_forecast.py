# @AI_GENERATED
"""
multi_step_forecast operator backend — Multi-step forecast configuration.

Outputs a forecast_config object and passes through upstream train/test data.
Params: forecast_steps (required), strategy (recursive/direct/hybrid, default "recursive"),
        step_size (default 1).
Advanced param: forecast_start_time.
Error if forecast_steps <= 0.
"""
import json

from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "multi_step_forecast"

VALID_STRATEGIES = {"recursive", "direct", "hybrid"}


def execute(params: dict, inputs: dict) -> dict:
    """
    Configure multi-step forecast and passthrough upstream data.

    Args:
        params: Operator parameters including:
            - forecast_steps (int, required): Number of forecast steps. Must be > 0.
            - strategy (str, optional): Forecast strategy. Default "recursive".
              One of: recursive, direct, hybrid.
            - step_size (int, optional): Step size per forecast step. Default 1.
            - forecast_start_time (str, optional): Forecast start timestamp.
        inputs: {"train_features": DataFrame, "train_target": ndarray,
                 "test_features": DataFrame, "test_target": ndarray}

    Returns:
        {"forecast_config": dict,
         "train_features": DataFrame, "train_target": ndarray,
         "test_features": DataFrame, "test_target": ndarray}
    """
    # Parse options
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    forecast_steps_raw = params.get("forecast_steps")
    if forecast_steps_raw is None:
        forecast_steps_raw = options.get("forecast_steps")
    if forecast_steps_raw is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "forecast_steps parameter is required"
        )

    forecast_steps = int(forecast_steps_raw)
    if forecast_steps <= 0:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"forecast_steps must be > 0, got {forecast_steps}",
        )

    strategy = str(
        params.get("strategy") or options.get("strategy") or "recursive"
    ).lower()
    if strategy not in VALID_STRATEGIES:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"strategy must be one of {VALID_STRATEGIES}, got '{strategy}'",
        )

    step_size = int(params.get("step_size") or options.get("step_size") or 1)
    if step_size <= 0:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"step_size must be > 0, got {step_size}",
        )

    forecast_start_time = (
        params.get("forecast_start_time") or options.get("forecast_start_time")
    )

    forecast_config = {
        "strategy": strategy,
        "forecast_steps": forecast_steps,
        "step_size": step_size,
    }
    if forecast_start_time:
        forecast_config["forecast_start_time"] = str(forecast_start_time)

    logger.info(
        f"[{OPERATOR_ID}] Configured: steps={forecast_steps}, "
        f"strategy={strategy}, step_size={step_size}"
    )

    # Passthrough upstream data
    result = {"forecast_config": forecast_config}

    for key in ("data", "train_features", "train_target", "test_features", "test_target"):
        if key in inputs:
            result[key] = inputs[key]

    return result
# @AI_GENERATED: end
