# -*- coding: utf-8 -*-
"""
services/iterative_labeling/inference_sample.py — 预测侧样本生成

按模型持久化的 sample_strategy 切分待预测数据，``inf-`` 前缀 sample_id，不落库。

对应 design.md 组件 7。需求：12.x
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd

from services.iterative_labeling.daylight_window import DaylightWindow
from services.iterative_labeling.sample_builder import SampleStrategy, build_samples

# @AI_GENERATED: 与训练侧 snapshot_builder 共用派生列实现，保证 period_is_*/night_* 口径一致
from services.iterative_labeling.sample_columns import (
    NIGHT_FEATURE_COLUMNS,
    PERIOD_ONE_HOT_COLUMNS,
    sample_derived_columns,
)
# @AI_GENERATED: end

logger = logging.getLogger(__name__)

#: 预测侧样本行的派生列集合，供调用方校验模型特征契约是否可满足。
INFERENCE_DERIVED_COLUMNS = tuple(PERIOD_ONE_HOT_COLUMNS) + tuple(NIGHT_FEATURE_COLUMNS)


class InferenceSampleGenerator:
    """预测侧样本生成器。"""

    def generate_inference_samples(
        self,
        measurements: pd.DataFrame,
        model_path: str,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        strategy = self._load_sample_strategy(model_path)
        df = measurements.copy()
        if df.empty:
            return df, {"sample_count": 0, "strategy": strategy.split_mode}

        # 预测侧无标签：用占位 label_id=0 仅用于切分边界（by_day 按天、by_day_night 按时钟）
        work = df.copy()
        work["label_id"] = 0
        work["source"] = "inference_placeholder"
        work["op_id"] = "inf-placeholder"

        frames = []
        sample_total = 0
        discard_all = []
        for (s, d, b), device_rows in work.groupby(["site_id", "device_id", "branch_id"], sort=True):
            device_rows = device_rows.sort_values("time").reset_index(drop=True)
            samples, discards = build_samples(device_rows, strategy, namespace="inf")
            discard_all.extend(discards)
            if not samples:
                continue
            sample_total += len(samples)
            for sample in samples:
                sub = device_rows.iloc[list(sample.row_indices)].copy()
                sub["time_window"] = sample.sample_id
                sub["period_role"] = sample.period_role
                # @AI_GENERATED: 补齐 period_is_* / night_* 派生列。
                # 训练快照由 snapshot_builder._materialize_sample_rows 写入这些列；
                # 预测侧原先不写，逐点标签模型若把它们选进 feature_list，
                # feature_select(transform) 就会缺列。用共用实现保证取值口径一致。
                for column, value in sample_derived_columns(sample.period_role, sub).items():
                    sub[column] = value
                # @AI_GENERATED: end
                frames.append(sub)

        if not frames:
            raise ValueError("预测数据未产生任何推理样本")

        out = pd.concat(frames, ignore_index=True, sort=False)
        audit = {
            "sample_count": sample_total,
            "row_count": int(len(out)),
            "split_mode": strategy.split_mode,
            "min_points": strategy.min_points,
            "daylight_window_count": len(strategy.daylight_windows or {}),
            "strategy_version": strategy.version,
            "discards": discard_all,
        }
        return out, audit

    @staticmethod
    def _load_sample_strategy(model_path: str) -> SampleStrategy:
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, dict) or "sample_strategy" not in payload:
            raise ValueError("模型文件缺少 sample_strategy，预测终止")

        raw = payload["sample_strategy"]
        windows = {}
        for key, val in (raw.get("daylight_windows") or {}).items():
            if "|" not in str(key):
                continue
            sid, month_str = str(key).split("|", 1)
            from datetime import time as dt_time
            windows[(sid, int(month_str))] = DaylightWindow(
                daylight_start=dt_time.fromisoformat(val["daylight_start"]),
                daylight_end=dt_time.fromisoformat(val["daylight_end"]),
                source=str(val.get("source", "fixed")),
            )
        return SampleStrategy(
            split_mode=str(raw.get("split_mode", "by_day")),
            min_points=int(raw.get("min_points", 12)),
            daylight_window_source=str(raw.get("daylight_window_source", "empirical")),
            daylight_window_lookback_months=int(raw.get("daylight_window_lookback_months", 24)),
            daylight_windows=windows,
            version=str(raw.get("version", "sb-v1")),
        )
