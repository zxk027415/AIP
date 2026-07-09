# @AI_GENERATED
"""
load_parquet operator backend — 读取 Parquet 文件并返回 DataFrame。

使用共享路径解析工具 _path_utils.resolve_file_path() 处理相对路径，
支持可选列投影（columns 参数）。

参数 (params)
-------------
- file_path (str, 必填): Parquet 文件路径（相对或绝对均可）
- columns   (list[str], 可选): 仅读取指定列（列投影），不传则读取所有列

输入 (inputs)
-------------
（无 — 数据源算子）

返回 (dict)
-----------
- data (pd.DataFrame): 读取到的数据表

错误
----
- ParameterError:    file_path 参数缺失
- FileNotFoundError: 文件不存在
- ParseError:        Parquet 文件解析失败
"""
import logging

import pandas as pd

from services.operator_backends._path_utils import resolve_file_path
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "load_parquet"

logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    读取 Parquet 文件。

    Args:
        params:
            - file_path (str): Parquet 文件路径，必填
            - columns (list[str]): 列投影，可选
        inputs:
            （无）

    Returns:
        {"data": pd.DataFrame}
    """
    # ── 解析必填参数 ──────────────────────────────────────────────────────────
    file_path = params.get("file_path")
    if not file_path:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "file_path parameter is required"
        )

    columns = params.get("columns") or None
    if isinstance(columns, str):
        # 支持逗号分隔字符串格式
        columns = [c.strip() for c in columns.split(",") if c.strip()] or None

    # ── 路径解析 ──────────────────────────────────────────────────────────────
    try:
        resolved_path = resolve_file_path(file_path)
    except FileNotFoundError as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "FileNotFoundError", str(e)
        )

    # ── 读取 Parquet ──────────────────────────────────────────────────────────
    try:
        df = pd.read_parquet(resolved_path, columns=columns)
    except Exception as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParseError",
            f"Failed to read parquet file '{resolved_path}': {e}"
        )

    logger.info(
        f"[{OPERATOR_ID}] Loaded {len(df)} rows, {len(df.columns)} columns "
        f"from '{resolved_path}'"
        + (f" (projected columns: {columns})" if columns else "")
    )

    return {"data": df}
# @AI_GENERATED: end
