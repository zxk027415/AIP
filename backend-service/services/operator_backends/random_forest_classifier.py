# @AI_GENERATED
"""
random_forest_classifier operator backend — 随机森林分类器（训练 + 预测）。

移植自 fault-diag-algo-release-3.1 训练/预测链路。

模式：
  train   — fit RandomForestClassifier，保存模型到磁盘，返回 model + model_id + feature_list
  predict — 从 model_id 加载模型或接受内存 model 对象执行推理
"""
import logging
import os
import pickle
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "random_forest_classifier"

logger = logging.getLogger(__name__)

# 模型保存目录（相对于 backend-service/）
_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "models")


def _ensure_models_dir():
    os.makedirs(_MODELS_DIR, exist_ok=True)


def _save_model(
    clf,
    feature_list: list,
    metrics: dict = None,
    sample_strategy: dict = None,
    label_snapshot_hash: str = None,
) -> str:
    """序列化模型到磁盘，返回 model_id（文件名不含扩展名）。

    Args:
        sample_strategy: 训练时的样本切分策略。逐点标签路径的预测侧必须靠它复现
            训练切分口径（见 services/iterative_labeling/inference_sample.py）；
            原实现不写该字段，用本算子训出的模型天生缺策略，预测时才暴露。
        label_snapshot_hash: 训练时逐点标签内容哈希，用于追溯。
    """
    _ensure_models_dir()
    trained_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    model_id = f"pv_fault_rfc_{trained_at}_{uuid.uuid4().hex[:6]}"
    path = os.path.join(_MODELS_DIR, f"{model_id}.pkl")
    # @AI_GENERATED: 与 stratified_cv_eval 的 pkl 结构对齐，补 sample_strategy / label_snapshot_hash
    payload = {
        "model": clf,
        "feature_list": feature_list,
        "sample_strategy": sample_strategy,
        "label_snapshot_hash": label_snapshot_hash,
    }
    # @AI_GENERATED: end
    with open(path, "wb") as f:
        pickle.dump(payload, f)
    logger.info(f"[{OPERATOR_ID}] Model saved: {path}")
    # 同时保存评估指标到 JSON（供预测时读取展示）
    if metrics:
        import json
        metrics_path = os.path.join(_MODELS_DIR, f"{model_id}_metrics.json")
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        logger.info(f"[{OPERATOR_ID}] Metrics saved: {metrics_path}")
    return model_id


def _load_model(model_id: str, model_path: str = ""):
    """从磁盘加载模型，返回 (clf, feature_list)。

    优先级：
      1. model_path 非空 → 直接加载该路径的 pkl 文件
      2. model_id == "latest" → 自动加载 data/models/ 下最新的模型
      3. model_id 为具体 ID → 加载 data/models/{model_id}.pkl
    """
    # 优先使用显式路径
    if model_path and model_path.strip():
        path = model_path.strip()
        if not os.path.exists(path):
            raise OperatorExecutionError(
                OPERATOR_ID, "FileNotFoundError",
                f"指定的模型路径不存在: {path}"
            )
        with open(path, "rb") as f:
            payload = pickle.load(f)
        logger.info(f"[{OPERATOR_ID}] Model loaded from explicit path: {path}")
        return payload["model"], payload.get("feature_list", [])

    _ensure_models_dir()
    if model_id.strip().lower() == "latest":
        pkls = sorted(
            [f for f in os.listdir(_MODELS_DIR) if f.endswith(".pkl")],
            reverse=True,
        )
        if not pkls:
            raise OperatorExecutionError(
                OPERATOR_ID, "FileNotFoundError",
                f"No saved models found in {_MODELS_DIR}. Run the training pipeline first."
            )
        model_id = pkls[0][:-4]
        logger.info(f"[{OPERATOR_ID}] 'latest' resolved to: {model_id}")

    path = os.path.join(_MODELS_DIR, f"{model_id}.pkl")
    if not os.path.exists(path):
        raise OperatorExecutionError(
            OPERATOR_ID, "FileNotFoundError",
            f"Model file not found: {path}. "
            f"Available models: {[f[:-4] for f in os.listdir(_MODELS_DIR) if f.endswith('.pkl')]}"
        )
    with open(path, "rb") as f:
        payload = pickle.load(f)
    return payload["model"], payload.get("feature_list", [])


def _load_model_metrics(model_id: str) -> dict:
    """加载模型对应的评估指标 JSON（训练时保存）。找不到返回空 dict。"""
    import json
    _ensure_models_dir()
    if model_id.strip().lower() == "latest":
        pkls = sorted(
            [f for f in os.listdir(_MODELS_DIR) if f.endswith(".pkl")],
            reverse=True,
        )
        if pkls:
            model_id = pkls[0][:-4]
    metrics_path = os.path.join(_MODELS_DIR, f"{model_id}_metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def execute(params: dict, inputs: dict) -> dict:
    """
    随机森林分类器。

    Args:
        params:
            - mode         (str): "train" | "predict"，默认 "train"
            - n_estimators (int): 树的数量，默认 80
            - random_state (int): 随机种子，默认 90
            - n_jobs       (int): 并行数，默认 -1
            - save_model   (bool): train 模式是否保存模型到磁盘，默认 true
            - model_id     (str): predict 模式时指定已保存的模型 ID（或直接传 model 对象）
        inputs (train mode):
            - features     (pd.DataFrame): 训练特征矩阵
            - target       (np.ndarray): 训练标签（int）
            - feature_list (list, optional): 特征名列表（来自 feature_select，保存进模型文件）
        inputs (predict mode):
            - model        (RandomForestClassifier, optional): 已训练模型对象
            - predict_features (pd.DataFrame): 预测特征矩阵

    Returns (train mode):
        {
            "model":               RandomForestClassifier,
            "model_id":            str,           # 可传给预测模板
            "feature_list":        list[str],     # 可传给 feature_select transform 模式
            "predictions":         np.ndarray,    # 训练集自测
            "y_true":              np.ndarray,
            "feature_importances": np.ndarray,
        }
    Returns (predict mode):
        {
            "predictions": np.ndarray (int),
        }
    """
    # ── 解析参数 ──────────────────────────────────────────────────────────────
    mode = str(params.get("mode") or "train").strip().lower()
    if mode not in ("train", "predict"):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"Invalid mode '{mode}'. Must be 'train' or 'predict'"
        )

    try:
        n_estimators = int(params.get("n_estimators") or 80)
    except (TypeError, ValueError):
        n_estimators = 80

    try:
        random_state = int(params.get("random_state") or 90)
    except (TypeError, ValueError):
        random_state = 90

    try:
        n_jobs = int(params.get("n_jobs") or -1)
    except (TypeError, ValueError):
        n_jobs = -1

    save_model_flag = str(params.get("save_model", "true")).lower() not in ("false", "0", "no")
    model_id_param = params.get("model_id") or ""
    model_path_param = params.get("model_path") or ""

    # ── 训练模式 ──────────────────────────────────────────────────────────────
    if mode == "train":
        features = inputs.get("features")
        target = inputs.get("target")

        if features is None or not isinstance(features, pd.DataFrame):
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "train mode requires input 'features' as pd.DataFrame"
            )
        if target is None:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "train mode requires input 'target'"
            )

        y = np.asarray(target)
        if len(features) != len(y):
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                f"features rows ({len(features)}) != target length ({len(y)})"
            )
        if len(features) == 0:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "features is empty"
            )

        # 按时间顺序切分：SMOTE 后 shuffle → 前 80% 训练，后 20% 评估
        # SMOTE 后数据按类排列，必须 shuffle 才能保证测试集各类均匀
        n_total = len(features)
        shuffle_idx = np.random.RandomState(random_state).permutation(n_total)
        features_shuffled = features.iloc[shuffle_idx].reset_index(drop=True)
        y_shuffled = y[shuffle_idx]

        n_train = int(n_total * 0.8)
        X_train, X_test = features_shuffled.iloc[:n_train], features_shuffled.iloc[n_train:]
        y_train, y_test = y_shuffled[:n_train], y_shuffled[n_train:]

        clf_eval = RandomForestClassifier(
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=n_jobs,
        )
        clf_eval.fit(X_train, y_train)
        predictions_test = clf_eval.predict(X_test).astype(int)
        feature_importances = clf_eval.feature_importances_

        # 用全量数据重训最终模型（部署用）
        clf = RandomForestClassifier(
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=n_jobs,
        )
        clf.fit(features, y)

        # 获取 feature_list（来自上游 feature_select 算子）
        feature_list = inputs.get("feature_list") or list(features.columns)

        # 保存模型到磁盘（全量训练的模型）
        model_id = ""
        if save_model_flag:
            # 计算测试集评估指标，保存供预测时展示
            from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
            from sklearn.metrics import confusion_matrix as sk_confusion_matrix, classification_report
            eval_metrics = {
                "accuracy": round(float(accuracy_score(y_test, predictions_test)), 4),
                "precision": round(float(precision_score(y_test, predictions_test, average="macro", zero_division=0)), 4),
                "recall": round(float(recall_score(y_test, predictions_test, average="macro", zero_division=0)), 4),
                "f1": round(float(f1_score(y_test, predictions_test, average="macro", zero_division=0)), 4),
            }
            # 混淆矩阵
            labels_sorted = sorted(set(y_test.tolist()) | set(predictions_test.tolist()))
            cm = sk_confusion_matrix(y_test, predictions_test, labels=labels_sorted)
            eval_metrics["confusion_matrix"] = {
                "labels": [str(x) for x in labels_sorted],
                "data": cm.tolist(),
            }
            eval_metrics["classification_report"] = classification_report(
                y_test, predictions_test, labels=labels_sorted, zero_division=0
            )
            # @AI_GENERATED: 透传样本策略，使本算子产出的模型也能被逐点标签预测路径使用
            _strategy = params.get("sample_strategy")
            if isinstance(_strategy, str):
                import json as _json
                try:
                    _strategy = _json.loads(_strategy)
                except Exception as exc:
                    raise OperatorExecutionError(
                        OPERATOR_ID, "ParameterError",
                        f"sample_strategy 不是合法 JSON，无法随模型持久化: {exc}",
                    )
            if _strategy is not None and not isinstance(_strategy, dict):
                raise OperatorExecutionError(
                    OPERATOR_ID, "ParameterError",
                    f"sample_strategy 必须是对象，实际为 {type(_strategy).__name__}",
                )
            model_id = _save_model(
                clf,
                feature_list,
                metrics=eval_metrics,
                sample_strategy=_strategy,
                label_snapshot_hash=params.get("label_snapshot_hash"),
            )
            # @AI_GENERATED: end

        logger.info(
            f"[{OPERATOR_ID}] train: n_estimators={n_estimators}, "
            f"n_samples={n_total} (train={n_train}, test={n_total-n_train}), "
            f"n_features={features.shape[1]}, model_id={model_id or '(not saved)'}"
        )

        return {
            "model": clf,
            "model_id": model_id,
            "feature_list": feature_list,
            "predictions": predictions_test,
            "y_true": y_test.astype(int),
            "feature_importances": feature_importances,
        }

    # ── 预测模式 ──────────────────────────────────────────────────────────────
    else:  # predict
        model = inputs.get("model")
        loaded_feature_list = []

        # 优先从 model_id 加载（跨流水线持久化场景）
        resolved_model_id = model_id_param
        if model is None and (model_id_param or model_path_param):
            model, loaded_feature_list = _load_model(model_id_param or "latest", model_path_param)
            # _load_model 内部会 resolve "latest" 为实际 ID
            if model_id_param.strip().lower() == "latest":
                _ensure_models_dir()
                pkls = sorted([f for f in os.listdir(_MODELS_DIR) if f.endswith(".pkl")], reverse=True)
                if pkls:
                    resolved_model_id = pkls[0][:-4]
            logger.info(f"[{OPERATOR_ID}] Loaded model from disk: {resolved_model_id}")

        if model is None:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "predict mode requires either inputs['model'] or params['model_id']"
            )

        predict_features = inputs.get("predict_features") if inputs.get("predict_features") is not None else inputs.get("data") if inputs.get("data") is not None else inputs.get("selected_features")

        if predict_features is None or not isinstance(predict_features, pd.DataFrame):
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "predict mode requires input 'predict_features' (or 'data') as pd.DataFrame"
            )
        if len(predict_features) == 0:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "predict_features is empty"
            )

        # 如果从磁盘加载了 feature_list，自动筛选列对齐
        if loaded_feature_list:
            present = [f for f in loaded_feature_list if f in predict_features.columns]
            if present:
                predict_features = predict_features[present]

        predictions = model.predict(predict_features).astype(int)

        # 置信度：取每行最大类别概率（predict_proba），供人工审核参考
        confidences = None
        try:
            if hasattr(model, "predict_proba"):
                import numpy as _np
                proba = model.predict_proba(predict_features)
                confidences = _np.max(proba, axis=1).astype(float)
        except Exception as _e:
            logger.warning(f"[{OPERATOR_ID}] predict_proba 失败，置信度置空: {_e}")
            confidences = None

        logger.info(
            f"[{OPERATOR_ID}] predict: n_samples={len(predict_features)}, "
            f"model_id={model_id_param or '(in-memory)'}"
        )

        # 加载该模型训练时保存的评估指标（供前端展示"模型历史评估"）
        saved_metrics = {}
        if model_id_param:
            saved_metrics = _load_model_metrics(model_id_param)

        from collections import Counter

        label_counts = {str(key): int(value) for key, value in sorted(Counter(predictions.tolist()).items())}
        result = {
            "predictions": predictions,
            "model_metrics": saved_metrics,
            "model_id": resolved_model_id,
            "prediction_summary": {
                "n_predicted": int(len(predictions)),
                "label_counts": label_counts,
            },
        }
        if confidences is not None:
            result["confidences"] = confidences
        # 供审核 SHAP/相似案例：保留本次预测实际喂给模型的特征表（与 predictions 行对齐）
        try:
            result["explain_features"] = predict_features.copy()
        except Exception:
            pass
        return result
