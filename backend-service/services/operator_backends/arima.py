# @AI_GENERATED
"""
arima operator backend — ARIMA 时序预测。

基于 statsmodels.tsa.arima.model.ARIMA 实现单步/多步预测。
输入数据按 timestamp_column 升序排列，对 value_column 建模。
预测日期通过推断相邻时间戳频率自动生成。

参数 (params)
-------------
- timestamp_column   (str): 时间戳列名，默认 "timestamp"
- value_column       (str): 目标值列名，默认 "value"
- forecast_horizon   (int): 预测步数，默认 24
- p (int): AR 阶数，默认 1
- d (int): 差分阶数，默认 1
- q (int): MA 阶数，默认 1

输入 (inputs)
-------------
- data (pd.DataFrame): 包含 timestamp_column 和 value_column 的时序数据

返回 (dict)
-----------
- forecast        (list[float]):  预测值序列，长度 = forecast_horizon
- forecast_dates  (list[str]):    对应预测时间戳（ISO 8601 字符串），长度 = forecast_horizon

错误
----
- InputError: data 不是 DataFrame 或数据点 < 10
"""
import logging

import pandas as pd

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "arima"

logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    ARIMA 时序预测。

    Args:
        params:
            - timestamp_column (str): 时间戳列名，默认 "timestamp"
            - value_column     (str): 目标值列名，默认 "value"
            - forecast_horizon (int): 预测步数，默认 24
            - p (int): AR 阶数，默认 1
            - d (int): 差分阶数，默认 1
            - q (int): MA 阶数，默认 1
        inputs:
            - data (pd.DataFrame): 时序数据

    Returns:
        {
            "forecast":       list[float],  # 预测值
            "forecast_dates": list[str],    # 预测时间戳（ISO 字符串）
        }
    """
    from statsmodels.tsa.arima.model import ARIMA

    # ── 解析输入 ──────────────────────────────────────────────────────────────
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'data' must be a pandas DataFrame"
        )

    # ── 解析参数 ──────────────────────────────────────────────────────────────
    timestamp_column = params.get("timestamp_column", "timestamp")
    value_column = params.get("value_column", "value")
    try:
        forecast_horizon = int(params.get("forecast_horizon") or 24)
    except (TypeError, ValueError):
        forecast_horizon = 24
    try:
        p = int(params.get("p") or 1)
    except (TypeError, ValueError):
        p = 1
    try:
        d = int(params.get("d") or 1)
    except (TypeError, ValueError):
        d = 1
    try:
        q = int(params.get("q") or 1)
    except (TypeError, ValueError):
        q = 1

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

    # ── 排序、转换类型 ────────────────────────────────────────────────────────
    df = data[[timestamp_column, value_column]].copy()
    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_column]):
        df[timestamp_column] = pd.to_datetime(df[timestamp_column], errors="coerce")
    df = df.dropna(subset=[timestamp_column, value_column])
    df = df.sort_values(by=timestamp_column).reset_index(drop=True)

    if len(df) < 10:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"ARIMA requires at least 10 data points, got {len(df)}"
        )

    # ── 推断频率 ──────────────────────────────────────────────────────────────
    timestamps = df[timestamp_column]
    # 取相邻时间差的中位数作为频率
    diffs = timestamps.diff().dropna()
    median_diff = diffs.median()
    # 转为 pandas freq 字符串（保底用秒）
    try:
        inferred_freq = pd.tseries.frequencies.to_offset(median_diff)
    except Exception:
        inferred_freq = pd.tseries.frequencies.to_offset("h")

    last_ts = timestamps.iloc[-1]

    # ── 拟合 ARIMA ────────────────────────────────────────────────────────────
    series = df[value_column].astype(float)
    try:
        model = ARIMA(series, order=(p, d, q))
        model_fit = model.fit()
    except Exception as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "ModelFitError",
            f"ARIMA model fitting failed: {e}"
        )

    # ── 预测 ──────────────────────────────────────────────────────────────────
    forecast_values = model_fit.forecast(steps=forecast_horizon)

    # ── 生成预测日期 ──────────────────────────────────────────────────────────
    forecast_index = pd.date_range(
        start=last_ts + inferred_freq,
        periods=forecast_horizon,
        freq=inferred_freq,
    )
    forecast_dates = [ts.isoformat() for ts in forecast_index]
    forecast_list = [float(v) for v in forecast_values]

    logger.info(
        f"[{OPERATOR_ID}] order=({p},{d},{q}), horizon={forecast_horizon}, "
        f"n_train={len(series)}, inferred_freq={inferred_freq}"
    )

    return {
        "forecast": forecast_list,
        "forecast_dates": forecast_dates,
    }
# @AI_GENERATED: end
