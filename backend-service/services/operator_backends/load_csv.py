# @AI_GENERATED
"""
load_csv operator backend — Reads CSV/Excel files into a DataFrame.

Supports delimiter, encoding, header_row parameters.
Advanced params: parent_field/child_field/parent_id/child_id for row filtering.
Output is sorted by timestamp_column and deduplicated.
"""
import os
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "load_csv"


def execute(params: dict, inputs: dict) -> dict:
    """
    Read a CSV file and return a DataFrame.

    Args:
        params: Operator parameters including:
            - file_path (str, required): Path to the CSV file
            - timestamp_column (str, optional): Column to parse as datetime
            - value_columns (list, optional): Columns to keep
            - delimiter (str, optional): CSV delimiter, default ","
            - encoding (str, optional): File encoding, default "utf-8"
            - header_row (int, optional): Header row number, default 0
            - parent_field (str, optional): Parent ID column name
            - child_field (str, optional): Child ID column name
            - parent_id (str, optional): Parent ID value to filter
            - child_id (str, optional): Child ID value to filter
        inputs: Not used for data source operators.

    Returns:
        {"data": DataFrame}
    """
    file_path = params.get("file_path")
    if not file_path:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "file_path parameter is required"
        )

    # @AI_GENERATED
    # Resolve relative paths: search multiple candidate directories
    if not os.path.isabs(file_path) and not os.path.exists(file_path):
        # __file__ = backend/services/operator_backends/load_csv.py
        # backend_dir = backend/
        # aip_dir = AIP-service/
        # workspace_root = project root (where datasets/ lives)
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        aip_dir = os.path.dirname(backend_dir)
        workspace_root = os.path.dirname(aip_dir)

        for base in [workspace_root, aip_dir, backend_dir, os.getcwd()]:
            candidate = os.path.join(base, file_path)
            if os.path.exists(candidate):
                file_path = candidate
                break
    # @AI_GENERATED: end

    if not os.path.exists(file_path):
        raise OperatorExecutionError(
            OPERATOR_ID, "FileNotFoundError", f"File not found: {file_path}"
        )

    delimiter = params.get("delimiter", ",")
    encoding = params.get("encoding", "utf-8")
    header_row = params.get("header_row", 0)
    timestamp_column = params.get("timestamp_column") or params.get("time_field")
    value_columns = params.get("value_columns")

    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".parquet":
            df = pd.read_parquet(file_path)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, header=header_row)
        else:
            df = pd.read_csv(
                file_path,
                delimiter=delimiter,
                encoding=encoding,
                header=header_row,
            )
    except Exception as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParseError", f"Failed to parse file: {e}"
        )

    # @AI_GENERATED
    # 可选列重命名：把源文件列名映射为流水线期望列名（如 data_date->time, branch->branch_id）。
    # 接受 dict 或 JSON 字符串；只重命名实际存在的列，缺省不做任何改动（向后兼容）。
    rename_map = params.get("rename_columns")
    if isinstance(rename_map, str):
        try:
            rename_map = json.loads(rename_map)
        except (json.JSONDecodeError, ValueError):
            rename_map = None
    if isinstance(rename_map, dict) and rename_map:
        actual = {k: v for k, v in rename_map.items() if k in df.columns and v}
        if actual:
            df = df.rename(columns=actual)
            logger.info(f"[load_csv] Renamed columns: {actual}")
    # @AI_GENERATED: end

    # Parse timestamp column (only needed for CSV; parquet already has correct types)
    if timestamp_column and timestamp_column in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df[timestamp_column]):
            df[timestamp_column] = pd.to_datetime(df[timestamp_column], errors="coerce")

    # Filter by value_columns if specified
    if value_columns:
        cols_to_keep = list(value_columns)
        if timestamp_column and timestamp_column not in cols_to_keep:
            cols_to_keep.insert(0, timestamp_column)
        existing = [c for c in cols_to_keep if c in df.columns]
        df = df[existing]

    # Advanced params: filter by parent_field/child_field
    parent_field = params.get("parent_field")
    child_field = params.get("child_field")
    parent_id = params.get("parent_id")
    child_id = params.get("child_id")

    if parent_field and parent_id and parent_field in df.columns:
        df = df[df[parent_field] == parent_id]
    if child_field and child_id and child_field in df.columns:
        df = df[df[child_field] == child_id]

    # Sort by timestamp and remove duplicates
    sort_col = timestamp_column or params.get("time_field")
    if sort_col and sort_col in df.columns:
        df = df.sort_values(by=sort_col).reset_index(drop=True)

    logger.info(
        f"[load_csv] Loaded {len(df)} rows, {len(df.columns)} columns from {file_path}"
    )
    return {"data": df}
# @AI_GENERATED: end
