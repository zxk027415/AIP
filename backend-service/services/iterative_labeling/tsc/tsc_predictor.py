# @AI_GENERATED
"""TSC 预测接口：恢复训练契约、连续段滑窗，并按目标业务日聚合。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .data_loader import preprocess_X
from .model_wrapper import TSCModelWrapper
from .sliding_window_sampler import SamplerConfig, SlidingWindowSampler

# @AI_GENERATED: 网格模型推理复用训练侧同一网格对齐与 mask-aware 预处理，杜绝 train/serve skew
from services.iterative_labeling.seq_annotation.grid_align import (
    MASK_CHANNEL,
    MAX_DAYTIME_GAP_SLOTS,
    MIN_DAYTIME_OCCUPANCY,
    MIN_OCCUPIED_SLOTS,
    REQUIRE_ALL_HOURS_COVERED,
    SLOTS_PER_DAY,
    align_day_to_grid,
)
from .grid_day_builder import MEASURE_CHANNELS, preprocess_grid_X
# @AI_GENERATED: end

logger = logging.getLogger(__name__)


class TSCPredictor:
    """从模型目录加载 MultiRocket，并严格复用训练时窗口与预处理配置。"""

    def __init__(self, model_path: str) -> None:
        self._wrapper = TSCModelWrapper.load(model_path)
        self._window_config = dict(self._wrapper.window_config or {})
        self._sampler_config = (
            SamplerConfig.from_dict(self._window_config)
            if self._window_config
            else SamplerConfig()
        )
        self._preprocess_method = str(
            self._window_config.get("preprocess_method") or "per_sample_zscore"
        )
        # @AI_GENERATED: 网格模式检测 —— 契约存在 grid_contract 或通道含 is_measured 即按 288 网格单日对齐
        raw_contract = self._window_config.get("grid_contract")
        self._grid_contract = dict(raw_contract) if isinstance(raw_contract, dict) else None
        config_channels = list(self._window_config.get("channels") or [])
        self._is_grid = bool(
            (self._grid_contract and self._grid_contract.get("grid_aligned"))
            or MASK_CHANNEL in config_channels
        )
        # @AI_GENERATED: end

    @property
    def model_name(self) -> str:
        return self._wrapper.model_name

    @property
    def window_length(self) -> int:
        return self._sampler_config.window_length

    @property
    def channels(self) -> List[str]:
        return list(self._sampler_config.channels)

    @property
    def window_config(self) -> Dict[str, Any]:
        # @AI_GENERATED: 保留原始契约（含 grid_contract/channels），网格模型证据不被 SamplerConfig 抹平
        merged: Dict[str, Any] = {
            **self._sampler_config.to_dict(),
            **self._window_config,
            "preprocess_method": self._preprocess_method,
            "label_classes": self._wrapper.class_labels(),
        }
        return merged
        # @AI_GENERATED: end

    @property
    def is_grid(self) -> bool:
        """当前模型是否按 288 时钟网格 + is_measured 掩码契约推理。"""
        return self._is_grid

    def predict_device(
        self,
        device_timeseries: pd.DataFrame,
        preprocess_method: Optional[str] = None,
    ) -> Dict[str, Any]:
        """对最后一个足长连续段取最近一个窗口预测。"""
        prepared, error = self._prepare_frame(device_timeseries)
        if error:
            return self._error_result(error)
        cfg = self._sampler_config
        segments = SlidingWindowSampler._split_by_time_gap(
            prepared["time"], cfg.max_gap_multiplier
        )
        selected = next(
            (segment for segment in reversed(segments) if len(segment) >= cfg.window_length),
            None,
        )
        if selected is None:
            longest = max((len(segment) for segment in segments), default=0)
            return self._error_result(
                f"所有连续段都不足 {cfg.window_length} 点，最长连续段 {longest} 点"
            )
        window = prepared.iloc[selected[-cfg.window_length :]]
        X = window[self.channels].to_numpy(dtype=np.float32)[np.newaxis, ...]
        X = preprocess_X(X, method=preprocess_method or self._preprocess_method)
        prediction = int(self._wrapper.predict(X)[0])
        probabilities = self._wrapper.predict_proba(X)
        confidence = float(probabilities[0].max()) if probabilities is not None else 0.0
        return {
            "label": prediction,
            "confidence": round(confidence, 4),
            "window_start": self._iso(window["time"].iloc[0]),
            "window_end": self._iso(window["time"].iloc[-1]),
            "model_name": self.model_name,
            "error": None,
        }

    def predict_device_multi_window(
        self,
        device_timeseries: pd.DataFrame,
        stride: Optional[int] = None,
        preprocess_method: Optional[str] = None,
        aggregation: str = "majority",
        target_day: Optional[str | date] = None,
    ) -> Dict[str, Any]:
        """滑动预测并聚合；传 ``target_day`` 时仅使用窗口终点落在该日的窗口。

        调度侧会提供“前一日 + 当前日”的两日上下文。288 点窗口、72 点步长因此
        在完整目标日通常得到 4 个终点落在目标日的窗口，而不是把单日 288 点误称为多窗。
        """
        if aggregation not in {"majority", "avg_proba"}:
            return self._error_result(f"未知 aggregation={aggregation!r}")
        # @AI_GENERATED: 网格模型走单日 288 槽对齐路径，与训练口径一致
        if self._is_grid:
            return self._predict_grid_target_day(
                device_timeseries,
                preprocess_method=preprocess_method,
                target_day=target_day,
            )
        # @AI_GENERATED: end
        prepared, error = self._prepare_frame(device_timeseries)
        if error:
            return self._error_result(error)
        cfg = self._sampler_config
        effective_stride = int(stride or cfg.stride)
        if effective_stride <= 0:
            return self._error_result("stride 必须大于 0")
        requested_day = pd.Timestamp(target_day).date() if target_day is not None else None

        windows: List[np.ndarray] = []
        bounds: List[tuple[pd.Timestamp, pd.Timestamp]] = []
        segments = SlidingWindowSampler._split_by_time_gap(
            prepared["time"], cfg.max_gap_multiplier
        )
        for segment in segments:
            if len(segment) < cfg.window_length:
                continue
            for local_start in range(0, len(segment) - cfg.window_length + 1, effective_stride):
                indices = segment[local_start : local_start + cfg.window_length]
                window = prepared.iloc[indices]
                start_time = pd.Timestamp(window["time"].iloc[0])
                end_time = pd.Timestamp(window["time"].iloc[-1])
                if requested_day is not None and end_time.date() != requested_day:
                    continue
                windows.append(window[self.channels].to_numpy(dtype=np.float32))
                bounds.append((start_time, end_time))
        if not windows:
            suffix = f"（目标日 {requested_day.isoformat()}）" if requested_day else ""
            return self._error_result(f"无法切出有效连续窗口{suffix}")

        X = preprocess_X(
            np.stack(windows, axis=0),
            method=preprocess_method or self._preprocess_method,
        )
        predictions = np.asarray(self._wrapper.predict(X))
        probabilities = self._wrapper.predict_proba(X)
        if aggregation == "avg_proba" and probabilities is not None:
            average = probabilities.mean(axis=0)
            classes = self._wrapper.class_labels(n_columns=len(average))
            final_label = int(classes[int(average.argmax())])
            confidence = float(average.max())
        else:
            values, counts = np.unique(predictions, return_counts=True)
            winner = int(counts.argmax())
            final_label = int(values[winner])
            confidence = float(counts[winner] / len(predictions))

        window_details: List[Dict[str, Any]] = []
        for index, (prediction, window_bounds) in enumerate(zip(predictions, bounds)):
            per_window_confidence = (
                float(probabilities[index].max()) if probabilities is not None else 0.0
            )
            window_details.append(
                {
                    "window_start": self._iso(window_bounds[0]),
                    "window_end": self._iso(window_bounds[1]),
                    "predicted_label": int(prediction),
                    "confidence": round(per_window_confidence, 4),
                }
            )
        return {
            "label": final_label,
            "confidence": round(confidence, 4),
            "n_windows": len(windows),
            "per_window_predictions": [int(value) for value in predictions.tolist()],
            "per_window_details": window_details,
            "aggregation": aggregation,
            "target_day": requested_day.isoformat() if requested_day else None,
            "model_name": self.model_name,
            "error": None,
        }

    # @AI_GENERATED: 网格模型单日推理 —— 只用目标日行做 288 槽对齐，覆盖不足则延后（不推进游标）
    def _predict_grid_target_day(
        self,
        device_timeseries: pd.DataFrame,
        *,
        preprocess_method: Optional[str] = None,
        target_day: Optional[str | date] = None,
    ) -> Dict[str, Any]:
        if target_day is None:
            return self._error_result("网格模型推理必须提供 target_day")
        if not isinstance(device_timeseries, pd.DataFrame):
            return self._error_result("device_timeseries 必须是 DataFrame")
        required = ["time", *MEASURE_CHANNELS]
        missing = [name for name in required if name not in device_timeseries.columns]
        if missing:
            return self._error_result(f"待预测数据缺少列: {missing}")

        requested_day = pd.Timestamp(target_day).date()
        frame = device_timeseries.copy()
        frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
        frame = frame[frame["time"].notna() & (frame["time"].dt.date == requested_day)]
        if frame.empty:
            return self._error_result(f"目标日 {requested_day.isoformat()} 无数据")
        for channel in MEASURE_CHANNELS:
            frame[channel] = pd.to_numeric(frame[channel], errors="coerce")
        frame = frame.sort_values("time").drop_duplicates("time", keep="last")

        values = np.stack(
            [
                frame[MEASURE_CHANNELS[0]].to_numpy(dtype=np.float64),
                frame[MEASURE_CHANNELS[1]].to_numpy(dtype=np.float64),
            ],
            axis=-1,
        )
        contract = self._grid_contract or {}
        aligned = align_day_to_grid(
            frame["time"],
            values,
            labels=None,
            min_occupied_slots=int(contract.get("min_occupied_slots", MIN_OCCUPIED_SLOTS)),
            min_daytime_occupancy=float(contract.get("min_daytime_occupancy", MIN_DAYTIME_OCCUPANCY)),
            max_daytime_gap_slots=int(contract.get("max_daytime_gap_slots", MAX_DAYTIME_GAP_SLOTS)),
            require_all_hours_covered=bool(
                contract.get("require_all_hours_covered", REQUIRE_ALL_HOURS_COVERED)
            ),
        )
        if not aligned.ok:
            return self._error_result(
                f"目标日 {requested_day.isoformat()} 网格覆盖不足: {aligned.reason}"
            )

        sample = np.concatenate(
            [aligned.values, aligned.measured_mask[:, np.newaxis]], axis=-1
        ).astype(np.float32)
        X = preprocess_grid_X(
            sample[np.newaxis, ...],
            mask_channel_index=len(MEASURE_CHANNELS),
            method=preprocess_method or self._preprocess_method,
        )
        prediction = int(self._wrapper.predict(X)[0])
        probabilities = self._wrapper.predict_proba(X)
        confidence = float(probabilities[0].max()) if probabilities is not None else 0.0

        day_start = pd.Timestamp(requested_day)
        window_detail = {
            "window_start": self._iso(day_start),
            "window_end": self._iso(day_start + pd.Timedelta(hours=23, minutes=55)),
            "predicted_label": prediction,
            "confidence": round(confidence, 4),
            "occupied_slots": int(aligned.occupied_slots),
            "daytime_occupancy": round(float(aligned.daytime_occupancy), 4),
            "longest_daytime_gap": int(aligned.longest_daytime_gap),
        }
        return {
            "label": prediction,
            "confidence": round(confidence, 4),
            "n_windows": 1,
            "per_window_predictions": [prediction],
            "per_window_details": [window_detail],
            "aggregation": "grid_full_day",
            "target_day": requested_day.isoformat(),
            "model_name": self.model_name,
            "error": None,
            "grid_meta": aligned.as_meta(),
        }
    # @AI_GENERATED: end

    def _prepare_frame(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, Optional[str]]:
        if not isinstance(frame, pd.DataFrame):
            return pd.DataFrame(), "device_timeseries 必须是 DataFrame"
        required = ["time", *self.channels]
        missing = [name for name in required if name not in frame.columns]
        if missing:
            return pd.DataFrame(), f"待预测数据缺少列: {missing}"
        prepared = frame.copy()
        prepared["time"] = pd.to_datetime(prepared["time"], errors="coerce")
        if prepared["time"].isna().any():
            return pd.DataFrame(), "待预测数据包含无效 time"
        prepared = prepared.sort_values("time").drop_duplicates("time", keep="last")
        for channel in self.channels:
            prepared[channel] = pd.to_numeric(prepared[channel], errors="coerce")
        if prepared[self.channels].isna().any().any():
            return pd.DataFrame(), "待预测通道包含空值或非数值"
        if len(prepared) < self.window_length:
            return pd.DataFrame(), f"数据不足: 需要 {self.window_length} 点, 只有 {len(prepared)} 点"
        return prepared.reset_index(drop=True), None

    def _error_result(self, message: str) -> Dict[str, Any]:
        return {
            "label": None,
            "confidence": 0.0,
            "n_windows": 0,
            "per_window_predictions": [],
            "per_window_details": [],
            "model_name": self.model_name,
            "error": message,
        }

    @staticmethod
    def _iso(value: Any) -> str:
        return pd.Timestamp(value).isoformat()
# @AI_GENERATED: end
