# @AI_GENERATED
"""
load_json operator backend — 读取 JSON / JSONL 文件并返回 DataFrame。

使用共享路径解析工具 _path_utils.resolve_file_path() 处理相对路径。
根据扩展名自动检测 .jsonl 文件（逐行 JSON），通过 orient 参数控制解析格式。
空 JSON 数组 [] 正常返回 0 行 DataFrame，不报错。

参数 (params)
-------------
- file_path (str, 必填): JSON / JSONL 文件路径（相对或绝对均可）
- orient    (str, 可选): pandas read_json 的 orient 参数，默认 "records"

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
- ParseError:        JSON 解析失败
"""
import logging
import os

import pandas as pd

from services.operator_backends._path_utils import resolve_file_path
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "load_json"

logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    读取 JSON 或 JSONL 文件。

    Args:
        params:
            - file_path (str): JSON/JSONL 文件路径，必填
            - orient    (str): pandas orient 参数，默认 "records"
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

    orient = params.get("orient", "records") or "records"

    # ── 路径解析 ──────────────────────────────────────────────────────────────
    try:
        resolved_path = resolve_file_path(file_path)
    except FileNotFoundError as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "FileNotFoundError", str(e)
        )

    # ── 检测是否为 JSONL（逐行 JSON）──────────────────────────────────────────
    ext = os.path.splitext(resolved_path)[1].lower()
    is_jsonl = ext == ".jsonl"

    # ── 读取文件 ──────────────────────────────────────────────────────────────
    try:
        if is_jsonl:
            df = pd.read_json(resolved_path, lines=True, orient=orient)
        else:
            df = pd.read_json(resolved_path, orient=orient)
    except ValueError as e:
        # 空 JSON 数组 [] 在某些 orient 下会触发 ValueError；安全回退为空 DataFrame
        err_str = str(e).lower()
        if "no columns to parse" in err_str or "empty" in err_str or "if using all scalar values" in err_str:
            logger.warning(
                f"[{OPERATOR_ID}] Empty or scalar-only JSON, returning empty DataFrame. "
                f"Detail: {e}"
            )
            df = pd.DataFrame()
        else:
            raise OperatorExecutionError(
                OPERATOR_ID, "ParseError",
                f"Failed to parse JSON file '{resolved_path}': {e}"
            )
    except Exception as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParseError",
            f"Failed to read JSON file '{resolved_path}': {e}"
        )

    logger.info(
        f"[{OPERATOR_ID}] Loaded {len(df)} rows, {len(df.columns)} columns "
        f"from '{resolved_path}' (jsonl={is_jsonl}, orient={orient})"
    )

    return {"data": df}
# @AI_GENERATED: end
