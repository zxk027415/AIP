# @AI_GENERATED
"""
prophet operator backend — Facebook Prophet 时序预测。

依赖 `prophet` 包（非 fbprophet）。若未安装，抛出 DependencyError。
输入 DataFrame 的列名可以是任意名称，通过 timestamp_column/value_column 参数指定，
内部会重命名为 Prophet 要求的 ds/y 格式。

参数 (params)
-------------
- timestamp_column   (str): 时间戳列名，默认 "ds"
- value_column       (str): 目标值列名，默认 "y"
- forecast_horizon   (int): 预测步数，默认 24
- freq               (str): 预测频率（pandas freq 字符串），默认 "h"

输入 (inputs)
-------------
- data (pd.DataFrame): 包含 timestamp_column 和 value_column 的时序数据

返回 (dict)
-----------
- forecast         (list[float]):  预测值（yhat），长度 = forecast_horizon
- forecast_dates   (list[str]):    对应预测时间戳（ISO 字符串），长度 = forecast_horizon
- forecast_lower   (list[float]):  预测下界（yhat_lower），长度 = forecast_horizon
- forecast_upper   (list[float]):  预测上界（yhat_upper），长度 = forecast_horizon

错误
----
- DependencyError: prophet 包未安装
- InputError:      data 不是 DataFrame 或数据点 < 10
"""
import logging

import pandas as pd

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "prophet"

logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    Prophet 时序预测。

    Args:
        params:
            - timestamp_column (str): 时间戳列名，默认 "ds"
            - value_column     (str): 目标值列名，默认 "y"
            - forecast_horizon (int): 预测步数，默认 24
            - freq             (str): 预测频率，默认 "h"
        inputs:
            - data (pd.DataFrame): 时序数据

    Returns:
        {
            "forecast":       list[float],  # 预测均值 yhat
            "forecast_dates": list[str],    # 预测时间戳（ISO 字符串）
            "forecast_lower": list[float],  # 预测下界 yhat_lower
            "forecast_upper": list[float],  # 预测上界 yhat_upper
        }
    """
    # ── 检查 prophet 依赖 ──────────────────────────────────────────────────────
    try:
        from prophet import Prophet
    except ImportError:
        raise OperatorExecutionError(
            OPERATOR_ID, "DependencyError",
            "prophet package not installed. Install with: pip install prophet"
        )

    # ── 解析输入 ──────────────────────────────────────────────────────────────
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'data' must be a pandas DataFrame"
        )

    # ── 解析参数 ──────────────────────────────────────────────────────────────
    timestamp_column = params.get("timestamp_column", "ds")
    value_column = params.get("value_column", "y")
    try:
        forecast_horizon = int(params.get("forecast_horizon") or 24)
    except (TypeError, ValueError):
        forecast_horizon = 24
    freq = params.get("freq", "h") or "h"

    # ── 校验列存在 ────────────────────────────────────────────────────────────
    if timestamp_column not in data.columns:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"timestamp_column '{timestamp_column}' not found in DataFrame"
        )
    if value_column not in data.columns:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"value_column '{value_column}' not found in DataFrame"
        )

    # ── 准备 Prophet 格式数据（ds/y）─────────────────────────────────────────
    df = data[[timestamp_column, value_column]].copy()
    df = df.rename(columns={timestamp_column: "ds", value_column: "y"})
    if not pd.api.types.is_datetime64_any_dtype(df["ds"]):
        df["ds"] = pd.to_datetime(df["ds"], errors="coerce")
    df = df.dropna(subset=["ds", "y"])
    df = df.sort_values("ds").reset_index(drop=True)

    if len(df) < 10:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"Prophet requires at least 10 data points, got {len(df)}"
        )

    # ── 拟合模型 ──────────────────────────────────────────────────────────────
    try:
        m = Prophet()
        m.fit(df)
    except Exception as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "ModelFitError",
            f"Prophet model fitting failed: {e}"
        )

    # ── 生成未来数据框并预测 ──────────────────────────────────────────────────
    future = m.make_future_dataframe(periods=forecast_horizon, freq=freq)
    forecast_df = m.predict(future)

    # 只取最后 forecast_horizon 行（未来时段）
    result_df = forecast_df.tail(forecast_horizon).reset_index(drop=True)

    forecast_dates = [ts.isoformat() for ts in result_df["ds"]]
    forecast_list = [float(v) for v in result_df["yhat"]]
    forecast_lower = [float(v) for v in result_df["yhat_lower"]]
    forecast_upper = [float(v) for v in result_df["yhat_upper"]]

    logger.info(
        f"[{OPERATOR_ID}] horizon={forecast_horizon}, freq={freq}, "
        f"n_train={len(df)}"
    )

    return {
        "forecast": forecast_list,
        "forecast_dates": forecast_dates,
        "forecast_lower": forecast_lower,
        "forecast_upper": forecast_upper,
    }
# @AI_GENERATED: end
