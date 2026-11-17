# -*- coding: utf-8 -*-
"""
services/iterative_labeling/snapshot_builder.py — 快照预物化

从 point_labels ⨝ training_samples 读标签+测量，按设备分组调 SampleBuilder，
赋 sample_id 写入 time_window 列，产出训练快照 parquet。

对应 design.md 组件 6。需求：9.x, 10.x, 21.7~21.12
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from services.db.repositories.point_label import PointLabelRepository
from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.daylight_window import DaylightWindow
from services.iterative_labeling.sample_builder import (
    Sample,
    SampleStrategy,
    build_samples,
    compute_group_keys,
)
# @AI_GENERATED: 派生列构造与预测侧共用，见 sample_columns 模块说明
from services.iterative_labeling.sample_columns import (
    NIGHT_BAD_VALUE_THRESHOLD,
    SAMPLING_INTERVAL_SECONDS,
    compute_night_features,
    night_feature_defaults,
    period_one_hot,
    sanitize_night_values,
)
# @AI_GENERATED: end

logger = logging.getLogger(__name__)


def compute_label_snapshot_hash(active_ops: Sequence[Dict[str, Any]]) -> str:
    """active label_ops 按 op_id 升序取 10 字段规范序列化后 SHA-256。"""
    fields = (
        "op_id", "site_id", "device_id", "branch_id",
        "t_start", "t_end", "label_id", "source", "status", "label_space_version",
    )
    rows = []
    for op in sorted(active_ops, key=lambda o: str(o.get("op_id", ""))):
        if op.get("status") != "active":
            continue
        row = {}
        for f in fields:
            val = op.get(f)
            if isinstance(val, datetime):
                val = val.isoformat()
            row[f] = val
        rows.append(row)
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# @AI_GENERATED: period_is_* / night_* 的构造已移到 services/iterative_labeling/sample_columns.py，
# 由训练侧（本模块）与预测侧（inference_sample）共用同一份实现，从结构上保证特征口径一致。
# 下面几个名字保留为薄别名，避免改动既有调用点与测试。
_period_one_hot = period_one_hot
_night_feature_defaults = night_feature_defaults
_sanitize_night_values = sanitize_night_values
_compute_night_features = compute_night_features
# @AI_GENERATED: end


class SnapshotBuilder:
    """读逐点标签 + 测量数据，构建带 sample_id 的快照。"""

    def __init__(
        self,
        point_label_repo: PointLabelRepository,
        pv_fault_repo: PVFaultRepository,
    ) -> None:
        self._labels = point_label_repo
        self._samples = pv_fault_repo

    def build(
        self,
        strategy: SampleStrategy,
        *,
        site_id: Optional[str] = None,
        measurements_df: Optional[pd.DataFrame] = None,
        active_ops: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """构建快照 DataFrame 与元数据。"""
        if active_ops is None:
            active_ops = self._labels.query_all_active_ops()
        label_hash = compute_label_snapshot_hash(active_ops)

        if measurements_df is None:
            measurements_df = self._load_measurements(site_id)

        if measurements_df.empty:
            raise ValueError("测量数据为空，无法构建快照")

        labeled = self._join_point_labels(measurements_df)
        frames: List[pd.DataFrame] = []
        discard_all: List[Dict[str, Any]] = []
        sample_count = 0

        group_cols = ["site_id", "device_id", "branch_id"]
        for (s, d, b), device_rows in labeled.groupby(group_cols, sort=True):
            device_rows = device_rows.sort_values("time").reset_index(drop=True)
            samples, discards = build_samples(device_rows, strategy)
            discard_all.extend(discards)
            if not samples:
                continue
            gkeys = compute_group_keys(samples, device_rows, str(s), str(d), str(b))
            device_out = self._materialize_sample_rows(device_rows, samples, gkeys, strategy)
            frames.append(device_out)
            sample_count += len(samples)

        if not frames:
            raise ValueError("未产生任何训练样本（全部被 unknown/min_points 过滤）")

        combined = pd.concat(frames, ignore_index=True, sort=False)
        self._assert_time_window_valid(combined)

        meta = {
            "label_snapshot_hash": label_hash,
            "sample_strategy": {
                "split_mode": strategy.split_mode,
                "min_points": strategy.min_points,
                "daylight_window_source": strategy.daylight_window_source,
                "daylight_window_lookback_months": strategy.daylight_window_lookback_months,
                "daylight_windows": {
                    f"{sid}|{month}": {
                        "daylight_start": w.daylight_start.isoformat(),
                        "daylight_end": w.daylight_end.isoformat(),
                        "source": w.source,
                    }
                    for (sid, month), w in strategy.daylight_windows.items()
                },
                "version": strategy.version,
            },
            "row_count": int(len(combined)),
            "sample_count": int(sample_count),
            "discard_reasons": discard_all,
            "built_at": datetime.utcnow().isoformat(),
        }
        return combined, meta

    def _load_measurements(self, site_id: Optional[str]) -> pd.DataFrame:
        rows = self._samples.query_training_samples(site_id=site_id)
        records = []
        for r in rows:
            records.append({
                "time": r.time,
                "site_id": r.site_id,
                "device_id": r.device_id,
                "branch_id": r.branch_id,
                "value": r.value,
                "i_cal": r.i_cal,
            })
        return pd.DataFrame(records)

    def _join_point_labels(self, measurements: pd.DataFrame) -> pd.DataFrame:
        df = measurements.copy()
        label_rows = []
        for (s, d, b), grp in df.groupby(["site_id", "device_id", "branch_id"], sort=False):
            t_start = pd.to_datetime(grp["time"].min()).to_pydatetime()
            t_end = pd.to_datetime(grp["time"].max()).to_pydatetime() + timedelta(seconds=SAMPLING_INTERVAL_SECONDS)
            points = self._labels.query_points(str(s), str(d), str(b), t_start, t_end)
            label_rows.extend(points)
        if not label_rows:
            df["label_id"] = pd.NA
            df["source"] = pd.NA
            df["op_id"] = pd.NA
            return df
        labels = pd.DataFrame(label_rows)
        merged = df.merge(
            labels[["site_id", "device_id", "branch_id", "time", "label_id", "source", "op_id"]],
            on=["site_id", "device_id", "branch_id", "time"],
            how="left",
        )
        return merged

    def _materialize_sample_rows(
        self,
        device_rows: pd.DataFrame,
        samples: Sequence[Sample],
        group_keys: Dict[str, str],
        strategy: SampleStrategy,
    ) -> pd.DataFrame:
        out_rows: List[Dict[str, Any]] = []
        for sample in samples:
            sub = device_rows.iloc[list(sample.row_indices)].copy()
            one_hot = _period_one_hot(sample.period_role)
            night_feats = (
                _compute_night_features(sub)
                if sample.period_role == "night"
                else _night_feature_defaults()
            )
            gkey = group_keys.get(sample.sample_id, "")
            for _, row in sub.iterrows():
                label_val = row.get("label_id")
                if pd.isna(label_val):
                    continue
                rec = {
                    "time": row["time"],
                    "site_id": row["site_id"],
                    "device_id": row["device_id"],
                    "branch_id": row["branch_id"],
                    "value": row.get("value"),
                    "i_cal": row.get("i_cal"),
                    "label": int(label_val),
                    "time_window": sample.sample_id,
                    "group_key": gkey,
                    "period_role": sample.period_role,
                    **one_hot,
                    **night_feats,
                    "label_source": sample.label_source,
                    "label_source_purity": sample.label_source_purity,
                    "label_op_id": sample.label_op_id,
                }
                out_rows.append(rec)
        return pd.DataFrame(out_rows)

    @staticmethod
    def _assert_time_window_valid(df: pd.DataFrame) -> None:
        if "time_window" not in df.columns:
            raise ValueError("快照缺少 time_window 列")
        tw = df["time_window"].astype(str)
        bad = ~tw.str.contains("#", na=False)
        if bad.any():
            examples = tw[bad].head(5).tolist()
            raise ValueError(
                f"time_window 必须 100% 含 '#', 不满足 {int(bad.sum())} 行, 示例: {examples}"
            )

    def write_parquet(
        self,
        df: pd.DataFrame,
        meta: Dict[str, Any],
        output_path: Path,
    ) -> str:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, index=False)
        meta_path = output_path.with_suffix(".meta.json")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return str(output_path)
