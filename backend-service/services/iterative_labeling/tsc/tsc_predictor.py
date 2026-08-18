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

        # @AI_GENERATED: 时间连续性检查（2026-08-04，与训练侧 _split_by_time_gap 对称）
        # 原来直接 df.iloc[-window_length:] 取最后 N 行，不检查时间间隔。
        # 若设备数据有缺口（如当天数据不完整、两次查询结果拼接），会产出跨缝推理窗口。
        # 修复：只在最末连续段内取，若该段不足 window_length 则返回错误。
        segments = SlidingWindowSampler._split_by_time_gap(df["time"], cfg.max_gap_multiplier)
        last_seg = segments[-1] if segments else []
        if len(last_seg) < cfg.window_length:
            # 最末连续段不够长；尝试找第一个够长的段（从末往前找）
            for seg in reversed(segments):
                if len(seg) >= cfg.window_length:
                    last_seg = seg
                    break
            else:
                return {
                    "label": None,
                    "confidence": 0.0,
                    "window_start": None,
                    "window_end": None,
                    "model_name": self.model_name,
                    "error": (
                        f"所有连续段都不足 {cfg.window_length} 点（数据有时间缺口），"
                        f"最长连续段 {max(len(s) for s in segments) if segments else 0} 点"
                    ),
                }
        # 在所选段内取最后 window_length 个点
        window = df.iloc[last_seg[-cfg.window_length:]]
        # @AI_GENERATED: end
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

        # @AI_GENERATED: 时间连续性检查（2026-08-04，与训练侧 _split_by_time_gap 对称）
        # 原来直接在全序列 range(0, n-window+1, stride) 滑，不检查时间间隔。
        # 修复：先切连续段，只在各段内滑，不跨段。
        segments = SlidingWindowSampler._split_by_time_gap(df["time"], cfg.max_gap_multiplier)
        windows = []
        for seg in segments:
            seg_len = len(seg)
            if seg_len < cfg.window_length:
                continue
            for seg_start in range(0, seg_len - cfg.window_length + 1, stride):
                global_start = seg[seg_start]
                global_end = seg[seg_start + cfg.window_length - 1] + 1
                x = df.iloc[global_start:global_end][channels].values.astype(np.float32)
                windows.append(x)
        # @AI_GENERATED: end

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
