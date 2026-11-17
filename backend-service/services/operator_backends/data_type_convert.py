# @AI_GENERATED
"""
data_type_convert operator backend — 数据类型转换。

支持将指定列转为 int/float/str/datetime/bool 类型。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "data_type_convert"


def execute(params: dict, inputs: dict) -> dict:
    """
    数据类型转换。

    params:
        - conversions (dict): {列名: 目标类型}，如 {"age": "int", "date": "datetime"}
          支持类型: int, float, str, datetime, bool
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    conversions = params.get("conversions")
    if not conversions or not isinstance(conversions, dict):
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'conversions' must be a dict like {'col': 'type'}")

    result = data.copy()
    for col, target_type in conversions.items():
        if col not in result.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

        target_type = str(target_type).strip().lower()
        try:
            if target_type in ("int", "integer"):
                result[col] = pd.to_numeric(result[col], errors="coerce").astype("Int64")
            elif target_type in ("float", "double"):
                result[col] = pd.to_numeric(result[col], errors="coerce")
            elif target_type in ("str", "string"):
                result[col] = result[col].astype(str)
            elif target_type in ("datetime", "date"):
                result[col] = pd.to_datetime(result[col], errors="coerce")
            elif target_type in ("bool", "boolean"):
                result[col] = result[col].astype(bool)
            else:
                raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Unsupported type '{target_type}' for column '{col}'")
        except OperatorExecutionError:
            raise
        except Exception as e:
            raise OperatorExecutionError(OPERATOR_ID, "ConversionError", f"Failed to convert '{col}' to {target_type}: {e}")

    logger.info(f"[{OPERATOR_ID}] Converted {len(conversions)} column(s): {list(conversions.keys())}")
    return {"data": result}
# @AI_GENERATED: end
