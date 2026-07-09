# @AI_GENERATED
"""
services/deployment/metrics.py — 精度指标计算模块

对应设计文档 `.kiro/specs/algorithm-deployment-refactor/design.md` 中的
Correctness Property 2「精度指标计算正确性」以及 tasks.md 任务 2.3。

提供两个纯函数：

  - compute_mape(actual, predicted) — 平均绝对百分比误差 MAPE
      MAPE = mean(|actual - predicted| / |actual|) × 100

  - compute_rmse(actual, predicted) — 均方根误差 RMSE
      RMSE = sqrt(mean((actual - predicted)²))

设计要点：
  - 仅依赖 Python 标准库（math、typing），不引入 numpy / pandas，
    便于在轻量部署环境（如调度 worker、健康检查）中使用，
    也便于属性测试独立复现。
  - 输入使用 Sequence[float]，兼容 list / tuple 以及任何支持 len()/索引
    的序列；内部会显式转换为 float。
  - 对不满足前置条件的输入抛 ValueError，而不是静默返回 nan / inf。

前置条件（不满足时抛 ValueError）：
  - actual、predicted 均非空
  - actual、predicted 长度一致
  - 对 MAPE 而言，actual 中的所有元素必须非零
    （数学定义未涵盖除零场景，此处严格拒绝，不使用 epsilon 静默 guard）
"""
from typing import Sequence
import math


# ---------------------------------------------------------------------------
# 内部工具：输入校验与 float 转换
# ---------------------------------------------------------------------------

def _validate_and_coerce(
    actual: Sequence[float],
    predicted: Sequence[float],
) -> tuple[list[float], list[float]]:
    """
    校验一对数组并转换为 float 列表。

    参数：
      - actual    — 实际值序列
      - predicted — 预测值序列

    返回：
      (actual_list, predicted_list) — 两个已转换为 float 的列表

    异常：
      - ValueError：数组为空或长度不一致
      - TypeError：元素无法转换为 float（沿用 float() 的默认行为）
    """
    # 使用 list() 一次性物化，避免调用者传入生成器时被消费两次。
    actual_list = [float(x) for x in actual]
    predicted_list = [float(x) for x in predicted]

    if len(actual_list) == 0:
        raise ValueError("actual 与 predicted 不能为空")

    if len(actual_list) != len(predicted_list):
        raise ValueError(
            f"actual 与 predicted 长度不一致: "
            f"len(actual)={len(actual_list)}, len(predicted)={len(predicted_list)}"
        )

    return actual_list, predicted_list


# ---------------------------------------------------------------------------
# MAPE — Mean Absolute Percentage Error
# ---------------------------------------------------------------------------

def compute_mape(
    actual: Sequence[float],
    predicted: Sequence[float],
) -> float:
    """
    计算平均绝对百分比误差（Mean Absolute Percentage Error）。

    公式：
        MAPE = mean(|actual_i - predicted_i| / |actual_i|) × 100

    参数：
      - actual    — 实际值序列（非空、非零）
      - predicted — 预测值序列（非空、与 actual 长度一致）

    返回：
      - float — MAPE 值，单位为百分比（%）

    异常：
      - ValueError：
          - actual 或 predicted 为空
          - 两者长度不一致
          - actual 中存在 0 元素（数学上除零未定义，严格拒绝）
    """
    actual_list, predicted_list = _validate_and_coerce(actual, predicted)

    # 严格校验：actual 全部非零。设计文档明确要求
    # "actual values non-zero for MAPE"，此处直接抛 ValueError，
    # 不使用 epsilon 静默 guard，避免掩盖上游数据问题。
    for idx, a in enumerate(actual_list):
        if a == 0.0:
            raise ValueError(
                f"compute_mape 不支持 actual 中出现零值 (index={idx}); "
                f"请上游过滤或使用其他指标（如 SMAPE）"
            )

    total = 0.0
    for a, p in zip(actual_list, predicted_list):
        total += abs(a - p) / abs(a)

    return (total / len(actual_list)) * 100.0


# ---------------------------------------------------------------------------
# RMSE — Root Mean Squared Error
# ---------------------------------------------------------------------------

def compute_rmse(
    actual: Sequence[float],
    predicted: Sequence[float],
) -> float:
    """
    计算均方根误差（Root Mean Squared Error）。

    公式：
        RMSE = sqrt(mean((actual_i - predicted_i)²))

    参数：
      - actual    — 实际值序列（非空）
      - predicted — 预测值序列（非空、与 actual 长度一致）

    返回：
      - float — RMSE 值，单位与输入相同

    异常：
      - ValueError：
          - actual 或 predicted 为空
          - 两者长度不一致

    说明：
      与 MAPE 不同，RMSE 允许 actual 中包含零值，因为公式中不涉及除法。
    """
    actual_list, predicted_list = _validate_and_coerce(actual, predicted)

    total = 0.0
    for a, p in zip(actual_list, predicted_list):
        diff = a - p
        total += diff * diff

    return math.sqrt(total / len(actual_list))


__all__ = [
    "compute_mape",
    "compute_rmse",
]
# @AI_GENERATED: end
