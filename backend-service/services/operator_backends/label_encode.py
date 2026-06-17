# @AI_GENERATED
"""
label_encode operator backend — 标签编码 / 反编码。

移植自 fault-diag-algo-release-3.1/enos_fault_diag/fault_main.py 的
check_param() 和 parse_label() 方法。

支持两种模式：
  encode  — 正向映射：字符串业务标签 → int（不可映射的置为 -1）
  decode  — 反向映射：int 预测标签 → 字符串业务标签（通过 label_map 取反）

校验：
  - label_map 中存在重复的 int 值时，抛 ValueError（decode 时 int→str 不唯一）
  - encode 后全部为 -1（无有效映射）时抛错
"""
import json
import logging

import numpy as np
import pandas as pd

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "label_encode"

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 辅助：解析 label_map
# ──────────────────────────────────────────────

def _parse_label_map(raw) -> dict:
    """
    解析 label_map 参数，支持 JSON 字符串或 dict。
    返回 {str_key: int_value} 形式的字典。

    对应 fault_main.py check_param() 中的 json.loads 逻辑。
    """
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"label_map JSON 解析失败: {exc}") from exc
    elif isinstance(raw, dict):
        parsed = raw
    else:
        raise ValueError(f"label_map 类型错误，期望 str 或 dict，实际为 {type(raw).__name__}")

    # 统一 key 为 str，value 为 int
    # 原代码：int keys will become str after serialization
    result = {}
    for k, v in parsed.items():
        try:
            result[str(k)] = int(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"label_map 值必须可转换为 int: key={k!r}, value={v!r} — {exc}"
            ) from exc
    return result


def _validate_no_duplicate_values(label_map: dict) -> None:
    """
    校验 label_map 的 int 值不重复。
    对应 fault_main.py check_param() 中：
        if not len(self.label_map) == len(set(self.label_map.values())):
            raise ParamException('Duplicate labels in label_map')
    """
    values = list(label_map.values())
    if len(values) != len(set(values)):
        # 找出重复的 value 以便报错信息更清晰
        seen = {}
        duplicates = []
        for k, v in label_map.items():
            if v in seen:
                duplicates.append((seen[v], k, v))
            else:
                seen[v] = k
        dup_str = "; ".join(f"keys {a!r} and {b!r} both map to {v}" for a, b, v in duplicates)
        raise ValueError(f"label_map 存在重复的映射值（decode 时无法唯一反查）: {dup_str}")


# ──────────────────────────────────────────────
# encode 模式
# ──────────────────────────────────────────────

def _encode(df: pd.DataFrame, label_col: str, label_map: dict) -> pd.DataFrame:
    """
    正向映射：label_col 中的字符串 → int。
    不可映射的值置为 -1。
    对应 fault_main.py parse_label() 中的 lambda 逻辑。
    """
    result = df.copy()

    def _map_one(x):
        key = str(x)
        if key in label_map:
            return int(label_map[key])
        return -1

    result[label_col] = result[label_col].apply(_map_one)

    # 检查是否全部为 -1（无有效映射）
    unique_vals = result[label_col].unique()
    if len(unique_vals) == 1 and unique_vals[0] == -1:
        raise OperatorExecutionError(
            OPERATOR_ID, "MappingError",
            "encode 后全部标签均为 -1，label_map 与数据标签完全不匹配，"
            "请检查 label_map 的 key 是否与数据中的标签值一致"
        )

    mapped_count = (result[label_col] != -1).sum()
    total = len(result)
    logger.info(
        f"[{OPERATOR_ID}] encode: {mapped_count}/{total} 条成功映射，"
        f"{total - mapped_count} 条设为 -1"
    )
    return result


# ──────────────────────────────────────────────
# decode 模式
# ──────────────────────────────────────────────

def _build_reverse_map(label_map: dict) -> dict:
    """
    构造反向映射 {int: str}，即 label_map 取反。
    前提：_validate_no_duplicate_values 已校验无重复值。
    """
    return {v: k for k, v in label_map.items()}


def _decode(df: pd.DataFrame, label_col: str, label_map: dict) -> pd.DataFrame:
    """
    反向映射：label_col 中的 int → 字符串业务标签。
    未命中的 int 保持原值（转为字符串 "unknown_N" 以示区分）。
    """
    reverse_map = _build_reverse_map(label_map)
    result = df.copy()

    def _rmap_one(x):
        try:
            key = int(x)
        except (TypeError, ValueError):
            return str(x)
        if key in reverse_map:
            return reverse_map[key]
        return f"unknown_{key}"

    result[label_col] = result[label_col].apply(_rmap_one)

    logger.info(f"[{OPERATOR_ID}] decode: {label_col} 列已完成反向映射")
    return result


# ──────────────────────────────────────────────
# 主 execute()
# ──────────────────────────────────────────────

def execute(params: dict, inputs: dict) -> dict:
    """
    标签编码 / 反编码。

    Args:
        params:
            - mode      (str):        "encode" | "decode"，默认 "encode"
            - label_col (str):        标签列名，默认 "label"
            - label_map (str | dict): JSON 或 dict，格式 {"业务标签": int, ...}
        inputs:
            - data (pd.DataFrame): 含标签列的数据

    Returns:
        {"data": pd.DataFrame}  # label_col 列已转换

    encode 流程：
        1. 解析 label_map（JSON → dict）
        2. 校验 label_map 值无重复
        3. 字符串 → int，不可映射置 -1
        4. 若全 -1 则报错

    decode 流程：
        1. 解析 label_map
        2. 校验 label_map 值无重复（保证反查唯一）
        3. int → 字符串（取反 label_map）
    """
    # ── 解析输入 ──────────────────────────────────────────────────────────────
    data = inputs.get("data")

    # 兼容上游 random_forest_classifier predict 模式直接传 predictions array
    if data is None:
        predictions = inputs.get("predictions")
        if predictions is not None:
            import numpy as np
            label_col_param = str(params.get("label_col") or "predictions").strip()
            data = pd.DataFrame({label_col_param: np.asarray(predictions).ravel()})

    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'data' must be a pandas DataFrame"
        )

    # ── 解析参数 ──────────────────────────────────────────────────────────────
    mode = str(params.get("mode") or "encode").strip().lower()
    label_col = str(params.get("label_col") or "label").strip()

    if mode not in ("encode", "decode"):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"Invalid mode '{mode}'. Must be 'encode' or 'decode'"
        )

    raw_label_map = params.get("label_map")
    if raw_label_map is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            "Parameter 'label_map' is required"
        )

    # ── 解析 label_map ─────────────────────────────────────────────────────
    try:
        label_map = _parse_label_map(raw_label_map)
    except ValueError as exc:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", str(exc)
        ) from exc

    if not label_map:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            "label_map 不能为空"
        )

    # ── 校验 label_map 值无重复 ───────────────────────────────────────────────
    try:
        _validate_no_duplicate_values(label_map)
    except ValueError as exc:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", str(exc)
        ) from exc

    # ── 校验 label_col 存在 ───────────────────────────────────────────────────
    if label_col not in data.columns:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"label_col '{label_col}' not found in data columns: {list(data.columns)}"
        )

    # ── 执行 encode / decode ─────────────────────────────────────────────────
    if mode == "encode":
        try:
            result = _encode(data, label_col, label_map)
        except OperatorExecutionError:
            raise
        except Exception as exc:
            raise OperatorExecutionError(
                OPERATOR_ID, "MappingError",
                f"encode 过程异常: {exc}"
            ) from exc
    else:  # decode
        try:
            result = _decode(data, label_col, label_map)
        except OperatorExecutionError:
            raise
        except Exception as exc:
            raise OperatorExecutionError(
                OPERATOR_ID, "MappingError",
                f"decode 过程异常: {exc}"
            ) from exc

    return {"data": result}
# @AI_GENERATED: end
