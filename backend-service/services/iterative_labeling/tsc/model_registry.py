# @AI_GENERATED
"""
模型注册表 — 管理所有可用的时序分类模型。

提供:
  - MODEL_REGISTRY: 模型元信息字典
  - get_model(name, **overrides) → TSCModelWrapper: 工厂函数
  - list_models(tier_filter, gpu_available) → list[dict]: 查询

设计文档: .kiro/specs/pv-fault-timeseries-diagnosis/design.md §2.2.2
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .model_wrapper import TSCModelWrapper

logger = logging.getLogger(__name__)

# aeon 深度学习分类器的 Keras 检查点写入目录（相对 backend-service）。
# 目录在模块加载时确保存在，避免训练中途 PermissionError。
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_KERAS_CKPT_PATH = _BACKEND_DIR / "data" / "tsc_experiments" / "_keras_ckpt"
try:
    _KERAS_CKPT_PATH.mkdir(parents=True, exist_ok=True)
except OSError:  # pragma: no cover - 只影响 Tier 2 深度模型
    logger.warning("无法创建 Keras 检查点目录 %s，Tier 2 深度模型可能训练失败", _KERAS_CKPT_PATH)
# aeon 内部用字符串拼接 file_path + 文件名，故补一个平台原生分隔符
_KERAS_CKPT_DIR = str(_KERAS_CKPT_PATH) + os.sep

MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # Tier 1: 轻量基线（秒级训练，无 GPU 依赖）
    # -------------------------------------------------------------------------
    "minirocket": {
        "class_path": "aeon.classification.convolution_based.MiniRocketClassifier",
        "tier": 1,
        "gpu_required": False,
        "is_aeon": True,
        "default_params": {},
        "description": "MiniRocket: 固定卷积核 + Ridge 线性分类，极快",
    },
    "multirocket": {
        "class_path": "aeon.classification.convolution_based.MultiRocketClassifier",
        "tier": 1,
        "gpu_required": False,
        "is_aeon": True,
        "default_params": {},
        "description": "MultiRocket: 多池化算子扩展，精度接近 HC2",
    },
    "rocket": {
        "class_path": "aeon.classification.convolution_based.RocketClassifier",
        "tier": 1,
        "gpu_required": False,
        "is_aeon": True,
        "default_params": {"n_kernels": 10000},
        "description": "ROCKET: 10000 随机卷积核 + Ridge",
    },
    # -------------------------------------------------------------------------
    # Tier 2: 中量级深度模型（分钟级训练，GPU 可选）
    # -------------------------------------------------------------------------
    # 注意：aeon 的深度学习分类器训练时会往 file_path 写 .keras 检查点，
    # 默认 './' 在部分运行目录下不可写，故显式指向 data/tsc_experiments/_keras_ckpt。
    # 需要 tensorflow（不是 torch）：pip install tensorflow-cpu
    "inceptiontime": {
        "class_path": "aeon.classification.deep_learning.InceptionTimeClassifier",
        "tier": 2,
        "gpu_required": False,
        "is_aeon": True,
        "default_params": {"n_epochs": 100, "batch_size": 64, "file_path": _KERAS_CKPT_DIR},
        "description": "InceptionTime: 多尺度 Inception 模块集成（需 tensorflow）",
    },
    "resnet": {
        "class_path": "aeon.classification.deep_learning.ResNetClassifier",
        "tier": 2,
        "gpu_required": False,
        "is_aeon": True,
        "default_params": {"n_epochs": 100, "batch_size": 64, "file_path": _KERAS_CKPT_DIR},
        "description": "ResNet-1D: 残差卷积网络（需 tensorflow）",
    },
    # 单个 Inception 网络。已知问题：aeon 1.3.0 的 InceptionTimeClassifier（5 模型
    # ensemble）在 Windows + Keras 3.12 下写检查点会 PermissionError，故用单模型版本
    # 评估 Inception 架构本身；ensemble 通常只比单模型高 1~2%。
    "inception_single": {
        "class_path": "aeon.classification.deep_learning.IndividualInceptionClassifier",
        "tier": 2,
        "gpu_required": False,
        "is_aeon": True,
        "default_params": {"n_epochs": 100, "batch_size": 64, "file_path": _KERAS_CKPT_DIR},
        "description": "Inception 单模型: 多尺度卷积（InceptionTime 的单成员，需 tensorflow）",
    },
    # -------------------------------------------------------------------------
    # Tier 3: 重型/领域特化（需 GPU）
    # -------------------------------------------------------------------------
    "cnn_lstm": {
        "class_path": "services.iterative_labeling.tsc.custom_models.cnn_lstm.CnnLstmClassifier",
        "tier": 3,
        "gpu_required": True,
        "is_aeon": False,
        "default_params": {
            "cnn_filters": [64, 128],
            "lstm_units": 64,
            "dropout": 0.3,
            "n_epochs": 200,
            "batch_size": 32,
            "lr": 1e-3,
        },
        "description": "CNN-LSTM: 卷积提形态 + LSTM 抓时序依赖",
    },
    "cnn_bilstm_attention": {
        "class_path": "services.iterative_labeling.tsc.custom_models.cnn_bilstm_attention.CnnBiLstmAttentionClassifier",
        "tier": 3,
        "gpu_required": True,
        "is_aeon": False,
        "default_params": {
            "cnn_filters": [64, 128, 256],
            "kernel_sizes": [3, 7, 15, 31],
            "lstm_units": 128,
            "attention_heads": 4,
            "dropout": 0.3,
            "n_epochs": 200,
            "batch_size": 32,
            "lr": 1e-3,
        },
        "description": "CNN-BiLSTM-Attention: 多尺度卷积 + 双向 LSTM + 时间注意力",
    },
    # -------------------------------------------------------------------------
    # 补充对照: 两阶段混合
    # -------------------------------------------------------------------------
    "rocket_rf": {
        "class_path": "services.iterative_labeling.tsc.custom_models.rocket_rf.RocketRFClassifier",
        "tier": 1,
        "gpu_required": False,
        "is_aeon": False,
        "default_params": {"n_kernels": 10000, "n_estimators": 200},
        "description": "ROCKET 特征提取 + RandomForest 分类（与 RF 路线对照）",
    },
}


def _import_class(class_path: str) -> type:
    """动态导入模型类。"""
    parts = class_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ImportError(f"无效的 class_path: {class_path}")
    module_path, class_name = parts
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_model(name: str, **override_params) -> TSCModelWrapper:
    """
    工厂函数：按名称创建模型包装器。

    Parameters
    ----------
    name : str
        注册表中的模型名。
    **override_params
        覆盖默认参数。

    Returns
    -------
    TSCModelWrapper 实例（未 fit）。
    """
    if name not in MODEL_REGISTRY:
        available = ", ".join(sorted(MODEL_REGISTRY.keys()))
        raise ValueError(f"未知模型 '{name}'，可用: {available}")

    entry = MODEL_REGISTRY[name]
    params = {**entry["default_params"], **override_params}

    try:
        model_cls = _import_class(entry["class_path"])
    except (ImportError, AttributeError) as e:
        raise ImportError(
            f"无法导入模型 {name} ({entry['class_path']}): {e}. "
            f"请确认依赖已安装（aeon/torch）。"
        ) from e

    model_instance = model_cls(**params)

    wrapper = TSCModelWrapper(
        model_name=name,
        model=model_instance,
        is_aeon=entry["is_aeon"],
        hyperparams=params,
    )
    return wrapper


def list_models(
    tier_filter: Optional[int] = None,
    gpu_available: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    列出可用模型。

    Parameters
    ----------
    tier_filter : int, optional
        只返回指定 tier 的模型。
    gpu_available : bool, optional
        若为 False，排除 gpu_required=True 的模型。

    Returns
    -------
    list of dicts，每个含 name, tier, gpu_required, description。
    """
    results = []
    for name, entry in MODEL_REGISTRY.items():
        if tier_filter is not None and entry["tier"] != tier_filter:
            continue
        if gpu_available is False and entry["gpu_required"]:
            continue
        results.append({
            "name": name,
            "tier": entry["tier"],
            "gpu_required": entry["gpu_required"],
            "description": entry["description"],
        })
    return results
# @AI_GENERATED: end
