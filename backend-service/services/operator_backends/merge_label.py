"""
merge_label operator backend — 源数据与标签数据按设备+时间对齐合并。

移植自 fault-diag-algo-release-3.1 MlflowFaultDiagnosis.init_train_data 的核心逻辑：
  1. 自动检测 id_fields（site_id / device_id / branch_id）
  2. 按 id_fields + time merge_asof 对齐（标签的时间粒度通常是天，源数据是15分钟）
  3. 输出带整型 label 列的 DataFrame，丢弃无标签的行

接口:
  params:
      id_fields (list):        设备分组字段，默认 ["site_id","device_id","branch_id"]
      time_field (str):        时间列名，默认 "time"
      label_col (str):         标签列名（在标签 DataFrame 里），默认 "custom_label_id"
      output_label_col (str):  输出标签列名，默认 "label"
  inputs:
      source_data (pd.DataFrame):  时序测量数据
      label_data  (pd.DataFrame):  标签数据
  returns:
      {"data": pd.DataFrame}  # 含 output_label_col (int) 列
"""
import json
import logging

import numpy as np
import pandas as pd

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "merge_label"
logger = logging.getLogger(__name__)


def _parse_list(value, default: list) -> list:
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass
        return [x.strip() for x in value.split(",") if x.strip()]
    return list(default)


def execute(params: dict, inputs: dict) -> dict:
    """
    源数据合并标签。

    Args:
        params:
            id_fields (list | str):      设备分组字段，默认 ["site_id","device_id","branch_id"]
            time_field (str):            时间列名，默认 "time"
            label_col (str):             标签数据中的标签列名，默认 "custom_label_id"
            output_label_col (str):      输出标签列名，默认 "label"
        inputs:
            source_data (pd.DataFrame):  时序测量数据
            label_data  (pd.DataFrame):  标签数据

    Returns:
        {"data": pd.DataFrame}  # 带 label(int) 列，已丢弃无标签行
    """
    source = inputs.get("source_data") if inputs.get("source_data") is not None else inputs.get("data")
    label = inputs.get("label_data") if inputs.get("label_data") is not None else inputs.get("label")

    if source is None or not isinstance(source, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'source_data' must be a pandas DataFrame"
        )
    if label is None or not isinstance(label, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'label_data' must be a pandas DataFrame"
        )

    # ── 参数解析 ──────────────────────────────────────────────────────────────
    id_fields = _parse_list(
        params.get("id_fields"),
        ["site_id", "device_id", "branch_id"]
    )
    time_field = str(params.get("time_field") or "time").strip()
    label_col = str(params.get("label_col") or "custom_label_id").strip()
    out_col = str(params.get("output_label_col") or "label").strip()

    # ── 自动检测实际存在的 id_fields ─────────────────────────────────────────
    actual_id = [f for f in id_fields if f in source.columns and f in label.columns]
    if not actual_id:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"None of id_fields {id_fields} found in both source and label DataFrames. "
            f"Source cols: {list(source.columns)}, Label cols: {list(label.columns)}"
        )

    # ── 校验标签列存在 ───────────────────────────────────────────────────────
    if label_col not in label.columns:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"label_col '{label_col}' not found in label DataFrame. "
            f"Available: {list(label.columns)}"
        )

    # ── 时间列处理 ───────────────────────────────────────────────────────────
    src = source.copy()
    lbl = label.copy()

    src[time_field] = pd.to_datetime(src[time_field], errors="coerce")

    # 标签的时间列可能是日期字符串（天粒度），统一转成 datetime
    lbl[time_field] = pd.to_datetime(lbl[time_field], errors="coerce")

    # id_fields 统一为 str
    for col in actual_id:
        src[col] = src[col].astype(str)
        lbl[col] = lbl[col].astype(str)

    # 单文件模式：源数据可能已自带 label 列（源和标签是同一份文件），
    # 合并前先从源数据丢弃，避免与 label_data 的标签列冲突成 label_x/label_y。
    # 权威标签以 label_data 去重后的值为准。两文件模式下源数据没有该列，此处无影响。
    _drop_from_src = [c for c in {label_col, out_col} if c in src.columns]
    if _drop_from_src:
        src = src.drop(columns=_drop_from_src)
        logger.info(f"[{OPERATOR_ID}] 源数据已含标签列 {_drop_from_src}，合并前丢弃，以 label_data 为准")

    # ── 按天粒度对齐：给标签添加 date 列，源数据也添加 date 列 ────────────────
    # merge_asof 要求两个 DataFrame 都按 time 排序；
    # 但标签粒度是天、源数据是分钟，直接 merge_asof 会把跨天的行全都对到最近标签。
    # 更准确的方式：按 (id_fields + date) 做 left join。
    src["__date__"] = src[time_field].dt.date
    lbl["__date__"] = lbl[time_field].dt.date

    merge_key = actual_id + ["__date__"]
    merged = src.merge(
        lbl[merge_key + [label_col]].drop_duplicates(subset=merge_key),
        on=merge_key,
        how="left",
    )
    merged.drop(columns=["__date__"], inplace=True)

    # ── 仅保留有标签的行 ─────────────────────────────────────────────────────
    before = len(merged)
    merged = merged[merged[label_col].notna()].copy()
    after = len(merged)

    if merged.empty:
        raise OperatorExecutionError(
            OPERATOR_ID, "MergeError",
            "No rows remain after joining source_data with label_data. "
            "Check that id_fields and date ranges overlap between the two datasets."
        )

    # ── 转换为整型标签列 ─────────────────────────────────────────────────────
    try:
        merged[out_col] = merged[label_col].astype(int)
    except (ValueError, TypeError) as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "TypeError",
            f"Cannot convert label column '{label_col}' to int: {e}"
        ) from e

    # 如果 out_col != label_col，保留原始列方便调试；否则直接覆盖
    if out_col != label_col:
        merged.drop(columns=[label_col], inplace=True, errors="ignore")

    logger.info(
        f"[{OPERATOR_ID}] source={before} rows → after_merge={after} rows "
        f"(id_fields={actual_id}, label_col={label_col}→{out_col})"
    )

    return {"data": merged}
