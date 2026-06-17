# @AI_GENERATED
"""
batch_predict_classifier operator backend — 批量分类预测算子。

将大量设备的特征数据按 batch_size 分批执行分类器预测，
失败批次自动拆分为单对象逐条重试，记录每批处理数量和耗时。

移植自 fault_main.py MlflowFaultDiagnosis.predict() 的批量预测循环逻辑。

接口:
    params:
        batch_size (int): 每批对象数，默认 10000
        id_fields (list): 分组字段，如 ["site_id", "device_id", "time_window"]
    inputs:
        model: 训练好的 sklearn 分类器（含 .predict() 方法）
        predict_features: pd.DataFrame，以 id_fields 为 MultiIndex，列为特征值
    returns:
        predictions: pd.DataFrame，含 id_fields + predict_label 列
        failure_count: int，最终预测失败的对象数
"""
import time
import traceback

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "batch_predict_classifier"


def _load_model_metrics_safe(model_id: str) -> dict:
    """尝试加载模型训练时保存的评估指标。找不到或出错返回空 dict。"""
    if not model_id:
        return {}
    try:
        from services.operator_backends.random_forest_classifier import _load_model_metrics
        return _load_model_metrics(model_id)
    except Exception:
        return {}


def _batch_predict(
    model,
    features_df: pd.DataFrame,
    id_fields: list[str],
    batch_size: int,
) -> tuple[pd.DataFrame, int]:
    """
    按 batch_size 分批预测，失败批次拆分为单对象逐条重试。

    Args:
        model: sklearn 分类器，需实现 .predict(X) 方法
        features_df: 以 id_fields 为 MultiIndex 的特征 DataFrame
        id_fields: 分组标识字段列表
        batch_size: 每批最大对象数

    Returns:
        (result_df, failure_count)
        result_df: 含 id_fields + predict_label 的 DataFrame
        failure_count: 最终失败的对象数
    """
    unique_ids = features_df.index  # MultiIndex，每行对应一个唯一对象
    total = len(unique_ids)

    merge_list: list[pd.DataFrame] = []
    failed_ids: list = []

    # ── 第一阶段：按 batch_size 分批预测 ──────────────────────────────────
    for start in range(0, total, batch_size):
        batch_ids = unique_ids[start: start + batch_size]
        batch_df = features_df.loc[batch_ids]
        batch_count = len(batch_df)
        t0 = time.perf_counter()
        try:
            preds = model.predict(batch_df)
            elapsed = time.perf_counter() - t0
            id_frame = batch_df.index.to_frame(index=False)
            id_frame["predict_label"] = preds
            merge_list.append(id_frame)
            logger.info(
                f"[{OPERATOR_ID}] 批次 {start}~{start + batch_count - 1} "
                f"({batch_count} 条) 预测成功，耗时 {elapsed:.3f}s"
            )
        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.error(
                f"[{OPERATOR_ID}] 批次 {start}~{start + batch_size - 1} 预测失败，"
                f"耗时 {elapsed:.3f}s：{e}"
            )
            failed_ids.extend(batch_ids.tolist())

    # ── 第二阶段：逐条重试失败批次 ────────────────────────────────────────
    failure_count = 0
    if failed_ids:
        logger.info(
            f"[{OPERATOR_ID}] 开始逐条重试 {len(failed_ids)} 个失败对象"
        )
        for obj_id in failed_ids:
            t0 = time.perf_counter()
            try:
                # 用 [[obj_id]] 保持 DataFrame 形态（loc 单个 key 会降维）
                single_df = features_df.loc[[obj_id]]
                pred = model.predict(single_df)
                elapsed = time.perf_counter() - t0
                id_frame = single_df.index.to_frame(index=False)
                id_frame["predict_label"] = pred
                merge_list.append(id_frame)
                logger.info(
                    f"[{OPERATOR_ID}] 单条重试成功 id={obj_id}，耗时 {elapsed:.3f}s"
                )
            except Exception:
                elapsed = time.perf_counter() - t0
                failure_count += 1
                logger.error(
                    f"[{OPERATOR_ID}] 单条重试失败 id={obj_id}，"
                    f"耗时 {elapsed:.3f}s：\n{traceback.format_exc()}"
                )

    # ── 合并结果 ──────────────────────────────────────────────────────────
    if not merge_list:
        # 全部失败，返回空 DataFrame（含正确列结构）
        empty = pd.DataFrame(columns=id_fields + ["predict_label"])
        return empty, failure_count

    result_df = pd.concat(merge_list, ignore_index=True)
    return result_df, failure_count


def execute(params: dict, inputs: dict) -> dict:
    """
    批量分类预测算子入口。

    Args:
        params:
            batch_size (int, optional): 每批对象数，默认 10000
            id_fields (list, optional): 分组字段列表，默认 ["site_id", "device_id", "time_window"]
        inputs:
            model: 训练好的分类器对象（sklearn API）
            predict_features (pd.DataFrame): 特征数据，以 id_fields 为 MultiIndex

    Returns:
        {
            "predictions": pd.DataFrame,  # id_fields + predict_label
            "failure_count": int           # 最终预测失败的对象数
        }
    """
    # ── 参数解析 ──────────────────────────────────────────────────────────
    batch_size = int(params.get("batch_size") or 10000)
    id_fields: list[str] = params.get("id_fields") or [
        "site_id", "device_id", "time_window"
    ]
    if isinstance(id_fields, str):
        import json
        try:
            id_fields = json.loads(id_fields)
        except (json.JSONDecodeError, ValueError):
            id_fields = [id_fields]

    if batch_size <= 0:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"batch_size 必须为正整数，当前值：{batch_size}",
        )

    # ── 输入校验 ──────────────────────────────────────────────────────────
    model = inputs.get("model")
    if model is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "inputs['model'] 不能为空"
        )
    if not hasattr(model, "predict"):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            "inputs['model'] 必须实现 .predict() 方法（sklearn API）",
        )

    features_df: pd.DataFrame | None = inputs.get("predict_features")
    if features_df is None or not isinstance(features_df, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            "inputs['predict_features'] 必须是 pandas DataFrame",
        )
    if features_df.empty:
        logger.warning(f"[{OPERATOR_ID}] predict_features 为空，直接返回空预测结果")
        empty = pd.DataFrame(columns=id_fields + ["predict_label"])
        return {"predictions": empty, "failure_count": 0}

    # 若 features_df 尚未设置 MultiIndex，则尝试按 id_fields 设置
    if not isinstance(features_df.index, pd.MultiIndex):
        present = [f for f in id_fields if f in features_df.columns]
        if present:
            features_df = features_df.set_index(present)
            logger.info(
                f"[{OPERATOR_ID}] 已将 {present} 设为 MultiIndex"
            )
        else:
            logger.warning(
                f"[{OPERATOR_ID}] id_fields {id_fields} 不在 columns 中，"
                "将使用默认 RangeIndex，predict_label 仅含位置索引"
            )

    total_objs = len(features_df)
    logger.info(
        f"[{OPERATOR_ID}] 开始批量预测：total={total_objs}，batch_size={batch_size}"
    )

    t_start = time.perf_counter()
    predictions, failure_count = _batch_predict(
        model=model,
        features_df=features_df,
        id_fields=id_fields,
        batch_size=batch_size,
    )
    total_elapsed = time.perf_counter() - t_start

    success_count = total_objs - failure_count
    logger.info(
        f"[{OPERATOR_ID}] 预测完成：total={total_objs}，"
        f"success={success_count}，failure={failure_count}，"
        f"总耗时 {total_elapsed:.3f}s"
    )

    return {
        "predictions": predictions,
        "failure_count": failure_count,
        "model_metrics": _load_model_metrics_safe(params.get("model_id", "")),
    }
# @AI_GENERATED: end
