# -*- coding: utf-8 -*-
# @AI_GENERATED
"""序列标注预测器：加载正式工件并输出天级、逐点和连续分段结果。"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import torch

from services.iterative_labeling.seq_annotation.grid_align import (
    MASK_CHANNEL,
    MAX_DAYTIME_GAP_SLOTS,
    MIN_DAYTIME_OCCUPANCY,
    MIN_OCCUPIED_SLOTS,
    REQUIRE_ALL_HOURS_COVERED,
    SLOTS_PER_DAY,
    align_day_to_grid,
    grid_timestamps,
    split_mask_channel,
)

from services.iterative_labeling.seq_annotation.postprocessing import (
    normalize_postprocessing_contract,
    postprocess_point_predictions,
)

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[3]
DEFAULT_SEQ_LEN = SLOTS_PER_DAY
DEFAULT_CHANNELS = ["value", "i_cal"]
_REQUIRED_METADATA = {
    "artifact_format",
    "modeling_path",
    "model_ref",
    "model_name",
    "n_classes",
    "labels",
    "channels",
    "seq_len",
    "trained_full_day",
    "normalization",
}


class SeqAnnotationPredictor:
    """对单个设备日执行逐点分类，天级众数仅作为旧审核契约兼容字段。"""

    def __init__(self, model_path: str):
        self._model_path = self._resolve_model_path(model_path)
        self._model: torch.nn.Module
        self._metadata: Dict[str, Any] = {}
        self._seq_len = DEFAULT_SEQ_LEN
        self._channels = list(DEFAULT_CHANNELS)
        self._measured_channels = list(DEFAULT_CHANNELS)
        self._mask_channel_index: int | None = None
        self._grid_contract: Dict[str, Any] = {}
        self._postprocessing_contract: Dict[str, Any] = normalize_postprocessing_contract(None)
        self._grid_aligned = False
        self._daylight_start_hour = 0
        self._daylight_end_hour = 24
        self._labels: List[int] = []
        self._load()

    def _load(self) -> None:
        """严格校验 ``metadata.json + model.pt``；缺失时拒绝随机权重推理。"""
        if not self._model_path.is_dir():
            raise FileNotFoundError(f"序列标注模型目录不存在: {self._model_path}")
        metadata_path = self._model_path / "metadata.json"
        weight_path = self._model_path / "model.pt"
        missing_files = [
            path.name for path in (metadata_path, weight_path) if not path.is_file()
        ]
        if missing_files:
            raise FileNotFoundError(
                f"序列标注模型工件不完整，缺少: {', '.join(missing_files)}"
            )

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("metadata.json 顶层必须为对象")
        missing_fields = sorted(_REQUIRED_METADATA.difference(metadata))
        if missing_fields:
            raise ValueError(f"metadata.json 缺少字段: {', '.join(missing_fields)}")
        if metadata["artifact_format"] != "torch_state_dict_dir":
            raise ValueError(f"不支持的模型工件格式: {metadata['artifact_format']}")
        if metadata["modeling_path"] != "seq_annotation":
            raise ValueError("模型工件 modeling_path 不是 seq_annotation")
        if metadata["normalization"] != "per_sequence_channel_zscore":
            raise ValueError(f"不支持的归一化契约: {metadata['normalization']}")

        self._seq_len = int(metadata["seq_len"])
        self._channels = [str(channel) for channel in metadata["channels"]]
        self._measured_channels, self._mask_channel_index = split_mask_channel(self._channels)
        declared_labels = sorted(int(label) for label in metadata["labels"])
        self._labels = [
            int(label)
            for label in metadata.get("class_index_to_label", metadata["labels"])
        ]
        n_classes = int(metadata["n_classes"])
        if self._seq_len <= 0 or not self._channels or not self._labels:
            raise ValueError("metadata.json 的 seq_len/channels/labels 不能为空")
        if not self._measured_channels:
            raise ValueError("metadata.json 的 channels 至少要有一个实测通道")
        if n_classes != len(self._labels) or sorted(self._labels) != declared_labels:
            raise ValueError(
                "metadata.json 的 n_classes/class_index_to_label/labels 不一致"
            )
        trained_full_day = metadata["trained_full_day"]
        if not isinstance(trained_full_day, bool):
            raise ValueError("metadata.trained_full_day 必须为 JSON boolean")
        if trained_full_day and self._seq_len != DEFAULT_SEQ_LEN:
            raise ValueError("trained_full_day=true 时 seq_len 必须为 288")

        # 网格契约：训练侧写入的对齐门槛。推理必须复用同一套，否则会重现
        # 「训练按时钟槽对齐、推理按行数尾部补零」的 train/serve 错位。
        raw_grid_contract = metadata.get("grid_contract")
        if raw_grid_contract is None:
            self._grid_contract = {}
        elif isinstance(raw_grid_contract, dict):
            self._grid_contract = dict(raw_grid_contract)
        else:
            raise ValueError("metadata.grid_contract 必须为对象")
        self._postprocessing_contract = normalize_postprocessing_contract(
            metadata.get("postprocessing")
        )
        grid_aligned = self._grid_contract.get("grid_aligned", False)
        if not isinstance(grid_aligned, bool):
            raise ValueError("metadata.grid_contract.grid_aligned 必须为 JSON boolean")
        self._grid_aligned = grid_aligned
        if self._grid_aligned and self._seq_len != SLOTS_PER_DAY:
            raise ValueError("grid_aligned=true 时 seq_len 必须为 288")
        if self._mask_channel_index is not None and not self._grid_aligned:
            raise ValueError(
                f"通道含 {MASK_CHANNEL} 但 metadata.grid_contract 未声明 grid_aligned"
            )

        expected_sha = str(metadata.get("model_sha256") or "").strip()
        if expected_sha and self._sha256_file(weight_path) != expected_sha:
            raise ValueError("model.pt SHA256 与 metadata.json 不一致")

        from services.iterative_labeling.seq_annotation.models import get_model

        model_name = str(metadata["model_name"])
        self._model = get_model(
            model_name,
            in_channels=len(self._channels),
            n_classes=n_classes,
        )
        try:
            state = torch.load(weight_path, map_location="cpu", weights_only=True)
        except TypeError:
            state = torch.load(weight_path, map_location="cpu")
        if not isinstance(state, dict):
            raise ValueError("model.pt 不是合法 state_dict")
        self._model.load_state_dict(state, strict=True)
        self._model.eval()

        self._metadata = metadata
        self._daylight_start_hour = int(metadata.get("daylight_start_hour", 0))
        self._daylight_end_hour = int(metadata.get("daylight_end_hour", 24))
        logger.info(
            "SeqAnnotationPredictor 加载完成: model=%s seq_len=%d full_day=%s grid_aligned=%s",
            model_name,
            self._seq_len,
            self.supports_night,
            self._grid_aligned,
        )

    def predict_device_day(
        self,
        device_timeseries: pd.DataFrame,
        include_night: bool = True,
    ) -> Dict[str, Any]:
        """输出兼容天级审核的众数标签，并附带逐点置信度和连续标签段。"""
        if include_night and not self.supports_night:
            raise ValueError("当前模型未使用全天 288 点训练，禁止执行夜间诊断")
        # 掩码通道由对齐过程派生，不要求调用方提供。
        required_columns = {"time", *self._measured_channels}
        missing = sorted(required_columns.difference(device_timeseries.columns))
        if missing:
            return self._empty_result(f"缺少列: {', '.join(missing)}")

        df = device_timeseries.loc[:, ["time", *self._measured_channels]].copy()
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = (
            df.dropna(subset=["time"])
            .sort_values("time")
            .drop_duplicates(subset=["time"], keep="last")
            .reset_index(drop=True)
        )
        if df.empty:
            return self._empty_result("没有有效时间戳", include_night=include_night)
        if df["time"].dt.normalize().nunique() != 1:
            return self._empty_result(
                "输入必须仅包含单个自然日，禁止把多天数据覆盖到同一时钟网格",
                include_night=include_night,
            )

        if self._grid_aligned:
            prepared = self._prepare_grid_input(df, include_night=include_night)
        else:
            prepared = self._prepare_legacy_input(df, include_night=include_night)
        if isinstance(prepared, dict):  # 预处理失败时直接返回空结果
            return prepared
        X, times, report_idx, measured_flags = prepared

        X_normalized = self._normalize_sequence(X)
        if not np.isfinite(X_normalized).all():
            return self._empty_result(
                "归一化后出现非有限值",
                include_night=include_night,
            )

        with torch.no_grad():
            tensor = torch.from_numpy(X_normalized).float().unsqueeze(0)
            logits = self._model(tensor)
            probabilities = torch.softmax(logits, dim=-1)[0].cpu().numpy()
        class_predictions = probabilities.argmax(axis=-1)
        # 模型输出是连续类别索引 0..K-1；先映射为完整 288 槽业务标签，再按工件
        # 契约执行后处理，最后才裁剪上报窗口。这样逐点、分段和天级众数口径一致。
        class_index_to_label = np.asarray(self._labels, dtype=np.int64)
        raw_predictions_all = class_index_to_label[class_predictions]
        processed_predictions_all, postprocessing_audit = postprocess_point_predictions(
            raw_predictions_all,
            self._postprocessing_contract,
        )
        predictions = processed_predictions_all[report_idx]
        raw_predictions = raw_predictions_all[report_idx]
        label_to_class_index = {
            int(label): index for index, label in enumerate(self._labels)
        }
        processed_class_indices = np.asarray(
            [label_to_class_index[int(label)] for label in processed_predictions_all],
            dtype=np.int64,
        )
        point_confidences = probabilities[
            np.arange(len(processed_class_indices)), processed_class_indices
        ][report_idx]
        effective_len = int(len(report_idx))
        if effective_len == 0:
            return self._empty_result("没有可上报的槽位", include_night=include_night)

        segments = self._aggregate_segments(times, predictions.tolist())
        counts = Counter(predictions.tolist())
        day_label, day_count = counts.most_common(1)[0]
        day_confidence = float(day_count / effective_len)

        return {
            "predicted_label": int(day_label),
            "confidence": round(day_confidence, 4),
            "timestamps": [pd.Timestamp(value).isoformat() for value in times],
            "point_predictions": [int(value) for value in predictions],
            "raw_point_predictions": [int(value) for value in raw_predictions],
            "point_confidences": [round(float(value), 4) for value in point_confidences],
            "point_is_measured": measured_flags,
            "postprocessing": postprocessing_audit,
            "segment_predictions": segments,
            "segments": segments,
            "n_points_predicted": effective_len,
            "n_points_measured": int(sum(measured_flags)) if measured_flags else effective_len,
            "grid_aligned": self._grid_aligned,
            "model_name": self.model_name,
            "model_ref": self._metadata["model_ref"],
            "seq_len_used": self._seq_len,
            "include_night": include_night,
            "trained_full_day": self.supports_night,
            "error": None,
        }

    def _prepare_grid_input(
        self,
        df: pd.DataFrame,
        *,
        include_night: bool,
    ) -> Any:
        """按训练侧同一套 288 槽网格对齐推理输入。

        这里**不能**先按白天过滤再喂模型：网格对齐的前提是「下标 i 等于当天第 i 个
        5 分钟槽」，任何裁剪都会破坏这个位置语义。因此始终对齐整天，
        ``include_night=False`` 只影响最终上报哪些槽。
        """
        day = pd.Timestamp(df["time"].iloc[0]).normalize()
        values = df[self._measured_channels].to_numpy(dtype=np.float64)
        aligned = align_day_to_grid(
            df["time"],
            values,
            None,
            min_occupied_slots=int(
                self._grid_contract.get("min_occupied_slots", MIN_OCCUPIED_SLOTS)
            ),
            min_daytime_occupancy=float(
                self._grid_contract.get("min_daytime_occupancy", MIN_DAYTIME_OCCUPANCY)
            ),
            max_daytime_gap_slots=int(
                self._grid_contract.get("max_daytime_gap_slots", MAX_DAYTIME_GAP_SLOTS)
            ),
            # 训练侧要求 24 小时都有实测；推理必须执行同一条，缺省也按要求处理，
            # 避免旧契约缺字段时线上悄悄放宽。
            require_all_hours_covered=(
                self._grid_contract.get(
                    "require_all_hours_covered", REQUIRE_ALL_HOURS_COVERED
                )
                is True
            ),
            daylight_start_hour=self._report_daylight_window()[0],
            daylight_end_hour=self._report_daylight_window()[1],
        )
        if not aligned.ok:
            return self._empty_result(
                f"网格覆盖不足({aligned.reason})：实测槽 {aligned.occupied_slots}/"
                f"{SLOTS_PER_DAY}，白天占有率 {aligned.daytime_occupancy:.2f}，"
                f"白天最长空槽 {aligned.longest_daytime_gap}",
                include_night=include_night,
            )

        grid = np.zeros((SLOTS_PER_DAY, len(self._channels)), dtype=np.float32)
        measured_positions = [
            index for index, name in enumerate(self._channels) if name != MASK_CHANNEL
        ]
        grid[:, measured_positions] = aligned.values
        if self._mask_channel_index is not None:
            grid[:, self._mask_channel_index] = aligned.measured_mask

        timestamps = grid_timestamps(day)
        report_idx = np.arange(SLOTS_PER_DAY)
        if not include_night:
            start_hour, end_hour = self._report_daylight_window()
            slot_hour = report_idx // (SLOTS_PER_DAY // 24)
            report_idx = report_idx[(slot_hour >= start_hour) & (slot_hour < end_hour)]
        times = [timestamps[index] for index in report_idx]
        measured_flags = [int(aligned.measured_mask[index] > 0.5) for index in report_idx]
        return grid, times, report_idx, measured_flags

    def _prepare_legacy_input(
        self,
        df: pd.DataFrame,
        *,
        include_night: bool,
    ) -> Any:
        """旧工件（无 grid_contract）的原路径：按行截断 + 尾部补零。

        保留这条路径是为了和旧模型的训练口径保持一致——它们当初就是这样对齐的，
        换成网格对齐反而会造成推理与训练不一致。新工件一律走 ``_prepare_grid_input``。
        """
        if not include_night:
            hours = df["time"].dt.hour
            df = df[
                (hours >= self._daylight_start_hour)
                & (hours < self._daylight_end_hour)
            ].reset_index(drop=True)

        min_points = max(60, int(np.ceil(self._seq_len * 0.5)))
        if len(df) < min_points:
            return self._empty_result(
                f"有效采样点不足：{len(df)} < {min_points}",
                include_night=include_night,
            )

        X = df[self._measured_channels].to_numpy(dtype=np.float32)
        for channel_index, channel_name in enumerate(self._measured_channels):
            column = X[:, channel_index]
            finite = np.isfinite(column)
            if not finite.any():
                return self._empty_result(
                    f"通道 {channel_name} 全部缺失",
                    include_night=include_night,
                )
            if not finite.all():
                valid_indices = np.flatnonzero(finite)
                missing_indices = np.flatnonzero(~finite)
                column[missing_indices] = np.interp(
                    missing_indices,
                    valid_indices,
                    column[valid_indices],
                )
                X[:, channel_index] = column

        effective_len = min(len(X), self._seq_len)
        X = X[:effective_len]
        times = df["time"].iloc[:effective_len].tolist()
        if effective_len < self._seq_len:
            X = np.pad(
                X,
                ((0, self._seq_len - effective_len), (0, 0)),
                constant_values=0,
            )
        return X, times, np.arange(effective_len), [1] * effective_len

    def _report_daylight_window(self) -> tuple[int, int]:
        """上报口径下的白天窗口。

        全天模型的 ``daylight_start/end_hour`` 是 0/24，无法用来筛掉夜间，
        因此优先用网格契约里的物理白天时段（默认 7~17）。
        """
        hours = self._grid_contract.get("weak_label_fault_hours")
        if isinstance(hours, (list, tuple)) and len(hours) == 2:
            return int(hours[0]), int(hours[1])
        return self._daylight_start_hour, self._daylight_end_hour

    def _normalize_sequence(self, X: np.ndarray) -> np.ndarray:
        """逐通道 z-score，掩码通道保持 0/1 原值（与训练侧口径一致）。"""
        mean = X.mean(axis=0, keepdims=True)
        std = X.std(axis=0, keepdims=True)
        normalized = (X - mean) / np.maximum(std, 1e-8)
        if self._mask_channel_index is not None:
            normalized[:, self._mask_channel_index] = X[:, self._mask_channel_index]
        return normalized

    @staticmethod
    def _aggregate_segments(
        times: List[pd.Timestamp],
        predictions: List[int],
    ) -> List[Dict[str, Any]]:
        """把逐点结果压缩为连续同标签段。"""
        if not predictions:
            return []
        segments: List[Dict[str, Any]] = []
        current_label = predictions[0]
        start_index = 0
        for index in range(1, len(predictions) + 1):
            if index < len(predictions) and predictions[index] == current_label:
                continue
            segments.append(
                {
                    "t_start": pd.Timestamp(times[start_index]).isoformat(),
                    "t_end": pd.Timestamp(times[index - 1]).isoformat(),
                    "label": int(current_label),
                    "n_points": int(index - start_index),
                }
            )
            if index < len(predictions):
                current_label = predictions[index]
                start_index = index
        return segments

    def _empty_result(
        self,
        reason: str,
        *,
        include_night: bool = False,
    ) -> Dict[str, Any]:
        return {
            "predicted_label": None,
            "confidence": 0.0,
            "timestamps": [],
            "point_predictions": [],
            "raw_point_predictions": [],
            "point_confidences": [],
            "point_is_measured": [],
            "postprocessing": {
                "enabled": bool(self._postprocessing_contract.get("enabled")),
                "changed_points": 0,
                "contract": dict(self._postprocessing_contract),
            },
            "segment_predictions": [],
            "segments": [],
            "n_points_predicted": 0,
            "n_points_measured": 0,
            "grid_aligned": self._grid_aligned,
            "model_name": self.model_name,
            "model_ref": self._metadata.get("model_ref"),
            "seq_len_used": self._seq_len,
            "include_night": include_night,
            "trained_full_day": self.supports_night,
            "error": reason,
        }

    @staticmethod
    def _resolve_model_path(model_path: str) -> Path:
        raw = str(model_path or "").strip()
        if not raw:
            raise ValueError("model_path 不能为空")
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = _BACKEND_DIR / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(_BACKEND_DIR.parent)
        except ValueError as exc:
            raise ValueError("模型目录必须位于项目根目录内") from exc
        return resolved

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @property
    def model_name(self) -> str:
        return str(self._metadata.get("model_name") or "unknown")

    @property
    def seq_len(self) -> int:
        return self._seq_len

    @property
    def channels(self) -> List[str]:
        return list(self._channels)

    @property
    def supports_night(self) -> bool:
        return self._metadata.get("trained_full_day", False) is True

    @property
    def metadata(self) -> Dict[str, Any]:
        return dict(self._metadata)
# @AI_GENERATED: end
