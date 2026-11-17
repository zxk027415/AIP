# @AI_GENERATED
"""
export_csv operator backend — 导出 DataFrame 到 CSV 文件。

默认保存路径：data/exports/export_YYYYMMDD_HHMMSS.csv（相对于 backend-service/）。
返回的 output_path 始终为相对路径，遵循 relative-paths-only 约定。
"""
import os
from datetime import datetime

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "export_csv"

_BACKEND_SERVICE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def execute(params: dict, inputs: dict) -> dict:
    """导出 DataFrame 到 CSV 文件。"""
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    output_path = params.get("output_path", "").strip()
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"data/exports/export_{ts}.csv"

    # 计算绝对路径
    abs_path = os.path.join(_BACKEND_SERVICE_DIR, output_path)
    parent_dir = os.path.dirname(abs_path)
    os.makedirs(parent_dir, exist_ok=True)

    data.to_csv(abs_path, index=False, encoding="utf-8-sig")

    # 确保返回相对路径
    rel_path = os.path.relpath(abs_path, _BACKEND_SERVICE_DIR)

    logger.info(f"[{OPERATOR_ID}] Exported {len(data)} rows to {rel_path}")
    return {"output_path": rel_path, "rows_written": len(data)}
# @AI_GENERATED: end
