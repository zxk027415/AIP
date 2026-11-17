# @AI_GENERATED
"""
load_hdf5 operator backend — HDF5 文件加载。

用 pandas.read_hdf 读取 .h5 / .hdf5 文件。需要 pytables 依赖。
"""
import pandas as pd
from loguru import logger

from services.operator_backends._path_utils import resolve_file_path
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "load_hdf5"


def execute(params: dict, inputs: dict) -> dict:
    """
    读取 HDF5 文件。

    params:
        - file_path (str, 必填): HDF5 文件路径
        - key (str | None): HDF5 内部数据集 key，None 则自动读第一个
        - columns (list[str] | None): 列投影
    inputs: 无
    returns: {"data": pd.DataFrame}
    """
    file_path = params.get("file_path")
    if not file_path:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "file_path parameter is required")

    try:
        resolved = resolve_file_path(file_path)
    except FileNotFoundError as e:
        raise OperatorExecutionError(OPERATOR_ID, "FileNotFoundError", str(e))

    key = params.get("key")
    columns = params.get("columns") or None

    try:
        if key:
            df = pd.read_hdf(resolved, key=key, columns=columns)
        else:
            df = pd.read_hdf(resolved, columns=columns)
    except ImportError:
        raise OperatorExecutionError(
            OPERATOR_ID, "DependencyError",
            "pytables (tables) package required. Install: pip install tables"
        )
    except Exception as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParseError", f"Failed to read HDF5 file '{resolved}': {e}"
        )

    logger.info(f"[{OPERATOR_ID}] Loaded {len(df)} rows, {len(df.columns)} cols from '{resolved}' (key={key})")
    return {"data": df}
# @AI_GENERATED: end
