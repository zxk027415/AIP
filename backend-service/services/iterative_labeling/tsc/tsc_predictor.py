# @AI_GENERATED
"""
TSCPredictor — 预测侧接口。

从持久化模型加载 + 按保存的窗口配置切分输入 + 预测。
保证预测使用与训练完全相同的 window_length / channels / normalization。

设计文档: .kiro/specs/pv-fault-timeseries-diagnosis/design.md §1.5
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .data_loader import preprocess_X
from .model_wrapper import TSCModelWrapper
from .sliding_window_sampler import SamplerConfig, SlidingWindowSampler

logger = logging.getLogger(__name__)


class TSCPredictor:
    """
    时序分类预测器。

    从持久化模型目录加载模型 + 窗口配置，对新数据做预测。

    Parameters
    ----------
    model_path : str
        模型持久化目录（含 model.pkl + metadata.json）。
    """

    def __init__(self, model_path: str):
        self._wrapper = TSCModelWrapper.load(model_path)
        self._window_config = self._wrapper.window_config or {}
        self._sampler_config = SamplerConfig.from_dict(self._window_config) if self._window_config else SamplerConfig()

    @property
    def model_name(self) -> str:
        return self._wrapper.model_name

    @property
    def window_length(self) -> int:
        return self._sampler_config.window_length

    @property
    def channels(self) -> List[str]:
        return self._sampler_config.channels

    def predict_device(
        self,
        device_timeseries: pd.DataFrame,
        preprocess_method: str = "per_sample_zscore",
    ) -> Dict[str, Any]:
        """
        对单台设备做单窗口预测（取最近 window_length 个点）。

        Parameters
        ----------
        device_timeseries : DataFrame
            含 'time' 列 + channels 列，按 time 升序。

        Returns
        -------
        dict: {label, confidence, window_start, window_end, model_name}
        """
        cfg = self._sampler_config
        channels = cfg.channels

        df = device_timeseries.sort_values("time").reset_index(drop=True)
        if len(df) < cfg.window_length:
            return {
                "label": None,
                "confidence": 0.0,
                "window_start": None,
                "window_end": None,
                "model_name": self.model_name,
                "error": f"数据不足: 需要 {cfg.window_length} 点, 只有 {len(df)} 点",
            }

        # 取最近 window_length 个点
        window = df.iloc[-cfg.window_length:]
        x = window[channels].values.astype(np.float32)  # [window_length, n_channels]
        X = x[np.newaxis, ...]  # [1, window_length, n_channels]

        # 预处理
        X = preprocess_X(X, method=preprocess_method)

        # 预测
        pred = self._wrapper.predict(X)[0]
        proba = self._wrapper.predict_proba(X)
        confidence = float(proba[0].max()) if proba is not None else 0.0

        return {
            "label": int(pred),
            "confidence": round(confidence, 4),
            "window_start": window["time"].iloc[0],
            "window_end": window["time"].iloc[-1],
            "model_name": self.model_name,
            "error": None,
        }

    def predict_device_multi_window(
        self,
        device_timeseries: pd.DataFrame,
        stride: Optional[int] = None,
        preprocess_method: str = "per_sample_zscore",
        aggregation: str = "majority",
    ) -> Dict[str, Any]:
        """
        对单台设备做多窗口滑动预测 + 聚合。

        Parameters
        ----------
        device_timeseries : DataFrame
            含 'time' 列 + channels 列。
        stride : int, optional
            滑动步长，默认使用训练时的 stride。
        aggregation : str
            聚合方式: 'majority'（多数投票）或 'avg_proba'（平均概率）。

        Returns
        -------
        dict: {label, confidence, n_windows, per_window_predictions, model_name}
        """
        cfg = self._sampler_config
        channels = cfg.channels
        stride = stride or cfg.stride

        df = device_timeseries.sort_values("time").reset_index(drop=True)
        n_points = len(df)

        if n_points < cfg.window_length:
            return {
                "label": None,
                "confidence": 0.0,
                "n_windows": 0,
                "model_name": self.model_name,
                "error": f"数据不足: 需要 {cfg.window_length} 点, 只有 {n_points} 点",
            }

        # 滑窗切多个窗口
        windows = []
        for start in range(0, n_points - cfg.window_length + 1, stride):
            end = start + cfg.window_length
            x = df.iloc[start:end][channels].values.astype(np.float32)
            windows.append(x)

        if not windows:
            return {
                "label": None,
                "confidence": 0.0,
                "n_windows": 0,
                "model_name": self.model_name,
                "error": "无法切出有效窗口",
            }

        X = np.stack(windows, axis=0)  # [n_windows, window_length, n_channels]
        X = preprocess_X(X, method=preprocess_method)

        preds = self._wrapper.predict(X)
        probas = self._wrapper.predict_proba(X)

        # 聚合
        if aggregation == "avg_proba" and probas is not None:
            avg_proba = probas.mean(axis=0)
            final_label = int(avg_proba.argmax())
            confidence = float(avg_proba.max())
        else:
            # majority vote
            unique, counts = np.unique(preds, return_counts=True)
            final_label = int(unique[counts.argmax()])
            confidence = float(counts.max() / len(preds))

        return {
            "label": final_label,
            "confidence": round(confidence, 4),
            "n_windows": len(windows),
            "per_window_predictions": preds.tolist(),
            "model_name": self.model_name,
            "error": None,
        }
# @AI_GENERATED: end
