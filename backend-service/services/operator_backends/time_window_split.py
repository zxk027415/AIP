# @AI_GENERATED
"""
time_window_split operator backend — 按诊断窗口将时序数据切分为独立诊断单元。

核心逻辑移植自 fault-diag-algo-release-3.1/enos_fault_diag/utils/time.py 的
set_time_window 和 get_standard_freq 函数。

每个设备 × 窗口组合成为一个独立的诊断单元，输出新增 time_window 列。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "time_window_split"

# 频率单位映射：pandas 非标准单位 → 标准 alias
# m（分钟）→ t；w（周）→ w-mon（以周一为起始日）
_FREQ_UNIT_MAPPING = {
    "m": "t",
    "w": "w-mon",
}


def _parse_freq(window: str) -> str:
    """
    将窗口字符串转为 pandas resample 标准频率字符串。

    示例：
        "1d"  → "1d"
        "12h" → "12h"
        "30m" → "30t"  （分钟需映射 m→t）
        "1w"  → "1w-mon"（周需映射 w→w-mon）
    """
    if not window or not isinstance(window, str):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Invalid window parameter: {window!r}. Expected format like '1d', '12h', '30m', '1w'.",
        )

    # 末尾单位字符（可能是 1~2 个字母，如 'w-mon'，但输入只有单字母）
    unit = window[-1].lower()
    num = window[:-1]

    if not num:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Window '{window}' missing numeric part. Expected format like '1d', '12h'.",
        )

    mapped_unit = _FREQ_UNIT_MAPPING.get(unit, unit)
    return num + mapped_unit


def _split_time_window(
    df: pd.DataFrame,
    id_fields: list,
    time_field: str,
    freq: str,
) -> pd.DataFrame:
    """
    按设备分组，用 resample + merge_asof 为每条记录分配所属时间窗口标签。

    参数：
        df: 输入 DataFrame
        id_fields: 实际存在于 df 中的分组字段列表
        time_field: 时间列名
        freq: pandas 标准频率字符串（已由 _parse_freq 转换）

    返回：
        新增 time_window 列的 DataFrame
    """
    merge_list = []

    groups = df.groupby(id_fields) if id_fields else [(None, df)]

    for key, group in groups:
        tmp_df = group.copy()

        # 去除同一设备 + 时间点的重复行，保留首条
        dedup_cols = id_fields + [time_field] if id_fields else [time_field]
        tmp_df.drop_duplicates(subset=dedup_cols, inplace=True)

        tmp_df[time_field] = pd.to_datetime(tmp_df[time_field])
        tmp_df.set_index(time_field, inplace=True)
        tmp_df.sort_index(inplace=True)

        # resample 生成每个窗口的起始时间戳骨架
        df_resample = tmp_df.resample(freq, label="left").asfreq()
        df_resample["time_window"] = df_resample.index

        # merge_asof：将每条原始记录对齐到最近的（≤自身时间的）窗口起始点
        tmp_df = pd.merge_asof(
            tmp_df,
            df_resample[["time_window"]],
            left_index=True,
            right_index=True,
        )
        tmp_df.reset_index(inplace=True)
        merge_list.append(tmp_df)

    if not merge_list:
        # 输入为空，直接返回带 time_window 列的空 DataFrame
        result = df.copy()
        result["time_window"] = pd.NaT
        return result

    return pd.concat(merge_list, ignore_index=True)


def execute(params: dict, inputs: dict) -> dict:
    """
    时间窗口切分算子入口。

    params:
        window (str, 必填)：窗口大小，如 "1d"、"1w"、"12h"、"30m"
        id_fields (list, 可选)：分组字段列表，默认 ["site_id", "device_id", "branch_id"]
        time_field (str, 可选)：时间列名，默认 "time"
    inputs:
        data (pd.DataFrame)：输入时序数据
    returns:
        {"data": pd.DataFrame}  # 新增 time_window 列
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # ---- 解析参数 ----
    window = params.get("window")
    if not window:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            "Parameter 'window' is required. Example: '1d', '1w', '12h', '30m'.",
        )

    default_id_fields = ["site_id", "device_id", "branch_id"]
    id_fields_raw = params.get("id_fields", default_id_fields)
    # 兼容前端传来的 JSON 字符串形式
    if isinstance(id_fields_raw, str):
        import json
        try:
            id_fields_raw = json.loads(id_fields_raw)
        except (json.JSONDecodeError, ValueError):
            id_fields_raw = [f.strip() for f in id_fields_raw.split(",") if f.strip()]

    time_field: str = params.get("time_field") or "time"

    # ---- 频率字符串转换 ----
    freq = _parse_freq(window)

    # ---- 自动检测实际存在的 id_fields（过滤掉 DataFrame 中不存在的列）----
    actual_id_fields = [f for f in id_fields_raw if f in data.columns]
    if id_fields_raw and not actual_id_fields:
        logger.warning(
            f"[{OPERATOR_ID}] None of id_fields {id_fields_raw} found in DataFrame columns "
            f"{list(data.columns)}. Treating entire DataFrame as one group."
        )

    # ---- 时间列存在性检查 ----
    if time_field not in data.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"Time field '{time_field}' not found in DataFrame. "
            f"Available columns: {list(data.columns)}",
        )

    logger.info(
        f"[{OPERATOR_ID}] window={window} (freq={freq}), "
        f"id_fields={actual_id_fields}, time_field={time_field}, "
        f"input_rows={len(data)}"
    )

    # 若输入已含 time_window 列（如 parquet 自带），先删除再重新计算
    df_input = data.drop(columns=["time_window"], errors="ignore")

    result = _split_time_window(df_input, actual_id_fields, time_field, freq)

    n_windows = result["time_window"].nunique() if "time_window" in result.columns else 0
    logger.info(
        f"[{OPERATOR_ID}] Done: output_rows={len(result)}, "
        f"unique_time_windows={n_windows}"
    )

    return {"data": result}
# @AI_GENERATED: end
