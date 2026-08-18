# @AI_GENERATED
"""
滑动窗口切分器 — 把设备时序 + 逐点标签切成等长窗口样本。

核心参数:
  - window_length: 窗口点数（288=1天@5min采样）
  - stride: 滑动步长
  - label_strategy: 窗口级标签聚合策略（majority / fault_priority / boundary_align）
  - purity_threshold: 众数占比低于此值的窗口丢弃
  - min_coverage: 窗口内非NaN比例最低要求
  - channels: 输入通道列名列表
  - max_gap_multiplier: 时间缺口检测倍数，相邻点间隔超过
    采样间隔 × max_gap_multiplier 则认定为连续段边界

时间连续性修复（2026-08-04）：
  切分器原本按行号滑窗，不检查相邻点的实际时间间隔。当同一条序列的数据
  来自多个不连续的时间段（如累计训练快照把 5 月和 8 月的数据 concat 在一起），
  窗口会静默跨过时间缺口，前半段和后半段来自不同月份，产出物理上不存在的样本。
  实测：pv_cumulative_labeled_merged.parquet 中 66.98% 的窗口跨缝，最大缺口 92.4 天。
  修复方案：transform() 在滑窗前先用 _split_by_time_gap() 把时间序列按缺口切成
  连续段，只在段内滑窗，不跨段。dataset_combined（7 天单块）实测修复前后
  macro F1 差异 +0.0114，在 std 噪声范围内，选型结论不变。

设计文档: .kiro/specs/pv-fault-timeseries-diagnosis/design.md §一
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SamplerConfig:
    """滑窗切分器配置（可序列化，随模型持久化）。"""

    window_length: int = 288
    """窗口点数。288=1天(5min采样×288=24h)，144=半天，576=2天。"""

    stride: int = 72
    """滑动步长。72=6小时(5min×72=6h)，即 75% 重叠。"""

    min_coverage: float = 0.9
    """窗口内非NaN点最低比例，低于则丢弃该窗口。"""

    min_std: float = 0.0
    """
    首通道最小标准差；低于此值的窗口视为退化窗口并丢弃。0 表示不过滤。

    动机（2026-08-03 数据审计）：实测 4.4% 的窗口是常数序列（多为夜间全零），
    其中 302/303 被标为同一类。这些窗口在不同设备间**内容完全相同**，
    导致 train/test 出现 46 个字节级重复窗口（占 test 3.7%）——属于直接泄漏，
    且模型可无成本地"猜对"这些样本，虚高精度。
    建议正式评估时设为一个小正数（如 1e-6）以剔除常数窗口。
    """

    label_strategy: str = "majority"
    """窗口级标签聚合策略: majority / fault_priority / boundary_align。"""

    purity_threshold: float = 0.7
    """majority 策略下，众数占比低于此值的窗口标记为 mixed 并丢弃。"""

    channels: List[str] = field(default_factory=lambda: ["value", "i_cal"])
    """输入通道列名列表（对应 parquet 中的数值列）。"""

    series_keys: List[str] = field(
        default_factory=lambda: ["site_id", "device_id", "branch_id"]
    )
    """
    时序序列主键列。**必须唯一标识一条连续物理时序**。

    光伏数据里一台 device 可能挂多条 branch（实测 15.2% 的设备有 2~16 条），
    只按 device_id 分组会把不同支路的时序交错混在一起切窗，产出跨物理序列的脏样本。
    实测 (site_id, device_id, branch_id) 上 (key, time) 无重复，是正确的序列主键。

    运行时会自动跳过数据里不存在的列，故单设备单支路的数据集也能用。
    """

    fault_priority_min_ratio: float = 0.1
    """fault_priority 策略下，故障点数 >= window_length * ratio 即标为故障。"""

    normal_label: int = 0
    """正常类标签值。"""

    # @AI_GENERATED: 时间连续性修复参数（2026-08-04）
    max_gap_multiplier: float = 2.0
    """
    时间缺口检测倍数。相邻两点的时间间隔超过
    「推断采样间隔 × max_gap_multiplier」时，认定为连续段边界，不跨段滑窗。

    推断采样间隔 = 序列内相邻点时间差的中位数（对缺失点鲁棒）。
    默认 2.0 = 允许一个点的抖动/偶发缺失；要拦截单点缺口可改为 1.5。
    设为 0 或负数可关闭时间缺口检测（退化为旧行为，不推荐）。
    """
    # @AI_GENERATED: end

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SamplerConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class SlidingWindowSampler:
    """
    滑动窗口切分器。

    用法:
        sampler = SlidingWindowSampler(SamplerConfig(window_length=144, stride=36))
        X, y, meta = sampler.transform(device_timeseries, point_labels)

    输入:
        device_timeseries: DataFrame，必须含 'time' 列 + channels 列，按 time 排序
        point_labels: DataFrame，必须含 'time' 和 'label' 列

    输出:
        X: ndarray [n_samples, window_length, n_channels]
        y: ndarray [n_samples] 窗口级标签（int）
        meta: DataFrame [n_samples 行] 含 sample_id, t_start, t_end, purity, device_id
    """

    def __init__(self, config: Optional[SamplerConfig] = None):
        self.config = config or SamplerConfig()

    def get_config(self) -> dict:
        """返回当前配置字典（用于持久化）。"""
        return self.config.to_dict()

    # @AI_GENERATED: 时间缺口切分（2026-08-04 修复跨缝窗口 bug）
    @staticmethod
    def _split_by_time_gap(
        time_series: pd.Series,
        max_gap_multiplier: float,
    ) -> List[List[int]]:
        """
        把时间序列按缺口切成连续段，返回每段的行号列表。

        Parameters
        ----------
        time_series : pd.Series
            已按时间升序排列的 time 列（datetime64）。
        max_gap_multiplier : float
            缺口阈值倍数。相邻点间隔 > 中位采样间隔 × 倍数时断开。
            <= 0 表示不检测缺口，整列视为一段。

        Returns
        -------
        list of list[int]
            每个子列表是一段内的行号（对应 DataFrame 的 iloc 索引）。

        Notes
        -----
        用中位数而非固定常量推断采样间隔，对偶发缺失和不同采样频率的数据集
        都有更好的鲁棒性（单个异常大间隔不会把中位数拉偏）。
        """
        n = len(time_series)
        if n == 0:
            return []
        if max_gap_multiplier <= 0 or n == 1:
            return [list(range(n))]

        tv = time_series.to_numpy(dtype="datetime64[ns]")
        diffs = np.diff(tv).astype("timedelta64[s]").astype(np.int64)  # 秒

        if len(diffs) == 0:
            return [[0]]

        # 中位采样间隔（秒）；过滤掉 0 和负值（时间戳异常）
        valid_diffs = diffs[diffs > 0]
        if len(valid_diffs) == 0:
            return [list(range(n))]
        median_interval = float(np.median(valid_diffs))
        threshold = median_interval * max_gap_multiplier

        segments: List[List[int]] = []
        current: List[int] = [0]
        for i, gap in enumerate(diffs):
            if gap > threshold:
                segments.append(current)
                current = [i + 1]
            else:
                current.append(i + 1)
        segments.append(current)
        return segments
    # @AI_GENERATED: end

    def transform(
        self,
        device_timeseries: pd.DataFrame,
        point_labels: pd.DataFrame,
        device_id: str = "",
    ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """
        对单台设备的时序数据进行滑动窗口切分。

        Parameters
        ----------
        device_timeseries : DataFrame
            必须含 'time' 列 + self.config.channels 中的列，按 time 升序。
        point_labels : DataFrame
            必须含 'time' 和 'label' 列。
        device_id : str
            设备标识，写入 meta。

        Returns
        -------
        X : ndarray, shape [n_samples, window_length, n_channels]
        y : ndarray, shape [n_samples]
        meta : DataFrame with columns [sample_id, t_start, t_end, purity, device_id, label_strategy]
        """
        cfg = self.config
        channels = cfg.channels

        # 合并时序与标签。
        # 关键：一条序列内 time 必须唯一，否则 merge(on="time") 会产生笛卡尔积
        # （2 条支路混在一起 -> 4 行/时间戳，16 条 -> 256 行）。调用方应先按
        # series_keys 分组（见 transform_multi_device）；这里做一层去重兜底。
        ts = device_timeseries[["time"] + channels]
        n_before = len(ts)
        ts = ts.drop_duplicates(subset=["time"], keep="first")
        if len(ts) != n_before:
            logger.warning(
                "序列 %s 内有 %d 个重复时间戳，已保留首次出现。"
                "这通常意味着调用方未按完整序列主键(site_id/device_id/branch_id)分组。",
                device_id or "(unknown)", n_before - len(ts),
            )

        labels_df = point_labels[["time", "label"]].drop_duplicates(
            subset=["time"], keep="first"
        )

        merged = ts.merge(labels_df, on="time", how="left")
        merged = merged.sort_values("time").reset_index(drop=True)

        # 标签统一成 float64 numpy 语义：
        # parquet 可能给出 pandas nullable 整型（Int16Dtype 等），np.issubdtype 无法
        # 解析这类扩展 dtype，会在 _aggregate_label 里抛 TypeError。转成 float64 后
        # 缺失值统一为 NaN，下游只需处理一种情况。
        merged["label"] = pd.to_numeric(merged["label"], errors="coerce").astype("float64")

        n_points = len(merged)
        if n_points < cfg.window_length:
            return (
                np.empty((0, cfg.window_length, len(channels)), dtype=np.float32),
                np.empty(0, dtype=np.int64),
                pd.DataFrame(columns=["sample_id", "t_start", "t_end", "purity", "device_id", "label_strategy"]),
            )

        samples: List[np.ndarray] = []
        labels: List[int] = []
        metas: List[dict] = []

        # sample_id 前缀：完整序列标识的稳定短哈希（跨进程/跨次运行一致）
        series_hash = hashlib.blake2b(
            (device_id or "unknown").encode("utf-8"), digest_size=6
        ).hexdigest()

        # @AI_GENERATED: 时间缺口切分（2026-08-04）
        # 原来直接 range(0, n_points-window+1, stride) 全序列滑窗，
        # 不检查相邻点时间间隔，导致跨缺口的假窗口（实测累计数据集 66.98% 跨缝）。
        # 修复：先按时间缺口切成连续段，只在段内滑窗。
        segments = self._split_by_time_gap(merged["time"], cfg.max_gap_multiplier)

        for seg_indices in segments:
            seg_len = len(seg_indices)
            if seg_len < cfg.window_length:
                # 该连续段太短，切不出完整窗口
                continue

            # 在段内滑窗；seg_start 是段内偏移，global_start 是全序列行号
            for seg_start in range(0, seg_len - cfg.window_length + 1, cfg.stride):
                global_start = seg_indices[seg_start]
                global_end = seg_indices[seg_start + cfg.window_length - 1] + 1
                window = merged.iloc[global_start:global_end]

                # 1. 覆盖率检查
                coverage = window[channels[0]].notna().mean()
                if coverage < cfg.min_coverage:
                    continue

                # 1b. 退化窗口过滤（常数/全零序列，见 SamplerConfig.min_std 说明）
                if cfg.min_std > 0:
                    first_ch = window[channels[0]].to_numpy(dtype=np.float64)
                    if not np.isfinite(first_ch).any() or np.nanstd(first_ch) < cfg.min_std:
                        continue

                # 2. 标签聚合
                result = self._aggregate_label(window["label"].values)
                if result is None:
                    continue  # 跳过该窗口

                label, purity = result

                # 3. 提取数值矩阵
                x = window[channels].values.astype(np.float32)  # [window_length, n_channels]
                samples.append(x)
                labels.append(label)

                t_start_val = window["time"].iloc[0]
                t_end_val = window["time"].iloc[-1]
                # sample_id 用全局行偏移保持跨段唯一性
                sample_id = f"tsc-{series_hash}-{global_start:06d}"

                metas.append({
                    "sample_id": sample_id,
                    "t_start": t_start_val,
                    "t_end": t_end_val,
                    "purity": round(purity, 4),
                    "device_id": device_id,
                    "label_strategy": cfg.label_strategy,
                })
        # @AI_GENERATED: end

        if not samples:
            return (
                np.empty((0, cfg.window_length, len(channels)), dtype=np.float32),
                np.empty(0, dtype=np.int64),
                pd.DataFrame(columns=["sample_id", "t_start", "t_end", "purity", "device_id", "label_strategy"]),
            )

        X = np.stack(samples, axis=0)  # [n_samples, window_length, n_channels]
        y = np.array(labels, dtype=np.int64)
        meta_df = pd.DataFrame(metas)

        return X, y, meta_df

    def _aggregate_label(self, window_labels: np.ndarray) -> Optional[Tuple[int, float]]:
        """
        按配置的策略聚合窗口内逐点标签为单一窗口级标签。

        Returns
        -------
        (label, purity) 或 None（表示该窗口应被丢弃）
        """
        cfg = self.config
        strategy = cfg.label_strategy

        # 去掉未标注点。transform() 已把 label 统一成 float64（缺失=NaN），
        # 但本方法也可能被独立调用，故这里做一次防御性转换。
        arr = np.asarray(window_labels, dtype="float64")
        valid_labels = arr[~np.isnan(arr)]

        if len(valid_labels) == 0:
            return None  # 全部未标注

        if strategy == "majority":
            return self._strategy_majority(valid_labels)
        elif strategy == "fault_priority":
            return self._strategy_fault_priority(valid_labels)
        elif strategy == "boundary_align":
            # boundary_align 的窗口位置调整在 transform 层面处理
            # 聚合逻辑退化为 majority
            return self._strategy_majority(valid_labels)
        else:
            logger.warning("未知标签策略 %s，退化为 majority", strategy)
            return self._strategy_majority(valid_labels)

    def _strategy_majority(self, valid_labels: np.ndarray) -> Optional[Tuple[int, float]]:
        """众数策略：取众数，纯度不足则丢弃。"""
        unique, counts = np.unique(valid_labels.astype(np.int64), return_counts=True)
        majority_idx = counts.argmax()
        majority_label = int(unique[majority_idx])
        purity = counts[majority_idx] / len(valid_labels)

        if purity < self.config.purity_threshold:
            return None

        return majority_label, purity

    def _strategy_fault_priority(self, valid_labels: np.ndarray) -> Optional[Tuple[int, float]]:
        """
        故障优先策略：只要故障点数 >= 阈值即标为该故障。

        如果多种故障共存，取点数最多的故障类型。
        如果故障点数不足阈值，则标为正常（如果正常点够多）或丢弃。
        """
        cfg = self.config
        min_fault_points = int(cfg.window_length * cfg.fault_priority_min_ratio)
        labels_int = valid_labels.astype(np.int64)

        # 统计各故障类型
        unique, counts = np.unique(labels_int, return_counts=True)
        fault_mask = unique != cfg.normal_label
        fault_labels = unique[fault_mask]
        fault_counts = counts[fault_mask]

        if len(fault_labels) > 0:
            max_fault_idx = fault_counts.argmax()
            if fault_counts[max_fault_idx] >= min_fault_points:
                fault_label = int(fault_labels[max_fault_idx])
                purity = fault_counts[max_fault_idx] / len(valid_labels)
                return fault_label, purity

        # 故障点不足阈值，检查正常点
        normal_count = counts[unique == cfg.normal_label]
        if len(normal_count) > 0 and normal_count[0] / len(valid_labels) >= cfg.purity_threshold:
            return cfg.normal_label, float(normal_count[0] / len(valid_labels))

        return None  # 丢弃

    def resolve_series_keys(self, data: pd.DataFrame) -> List[str]:
        """
        解析实际可用的序列主键列。

        取 config.series_keys 与 data 列的交集；若一个都不存在，退回 ["device_id"]
        并告警（此时结果可能包含跨支路混合窗口）。
        """
        keys = [k for k in self.config.series_keys if k in data.columns]
        if not keys:
            fallback = "device_id" if "device_id" in data.columns else None
            if fallback is None:
                raise ValueError(
                    f"数据中找不到任何序列主键列，config.series_keys={self.config.series_keys}，"
                    f"实际列={list(data.columns)}"
                )
            logger.warning(
                "数据中无 %s，退回按 %s 单列分组；若一个设备有多条支路，窗口可能跨物理序列混合。",
                self.config.series_keys, fallback,
            )
            keys = [fallback]
        return keys

    def transform_multi_device(
        self,
        data: pd.DataFrame,
        label_col: str = "label",
        series_keys: Optional[List[str]] = None,
    ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """
        批量对多序列数据切分。

        按 series_keys（默认 site_id + device_id + branch_id）分组，
        保证每组是一条连续的物理时序。

        Parameters
        ----------
        data : DataFrame
            含 time、series_keys、channels、label_col 列的完整数据集。
        label_col : str
            标签列名。
        series_keys : list[str], optional
            覆盖 config.series_keys。

        Returns
        -------
        X, y, meta — 所有序列的结果拼接。
            meta 含 series_id（完整序列主键拼接）与 device_id（用于 train/test 防泄漏分组）。
        """
        cfg = self.config
        keys = series_keys or self.resolve_series_keys(data)

        empty_meta_cols = [
            "sample_id", "t_start", "t_end", "purity",
            "device_id", "series_id", "label_strategy",
        ]

        all_X, all_y, all_meta = [], [], []

        for key_vals, grp in data.groupby(keys, sort=False):
            if not isinstance(key_vals, tuple):
                key_vals = (key_vals,)
            series_id = "|".join(str(v) for v in key_vals)

            grp_sorted = grp.sort_values("time").reset_index(drop=True)
            point_labels = grp_sorted[["time", label_col]].rename(columns={label_col: "label"})

            X, y, meta = self.transform(grp_sorted, point_labels, device_id=series_id)
            if len(X) == 0:
                continue

            meta = meta.copy()
            meta["series_id"] = series_id
            # device_id 单独保留：train/test 按设备分组防泄漏（比按支路更保守，
            # 因为同一设备的多条支路物理相关，不应被拆到不同集合）
            if "device_id" in keys:
                meta["device_id"] = str(key_vals[keys.index("device_id")])
            elif "device_id" in grp_sorted.columns:
                meta["device_id"] = str(grp_sorted["device_id"].iloc[0])
            else:
                meta["device_id"] = series_id

            all_X.append(X)
            all_y.append(y)
            all_meta.append(meta)

        if not all_X:
            return (
                np.empty((0, cfg.window_length, len(cfg.channels)), dtype=np.float32),
                np.empty(0, dtype=np.int64),
                pd.DataFrame(columns=empty_meta_cols),
            )

        return (
            np.concatenate(all_X, axis=0),
            np.concatenate(all_y, axis=0),
            pd.concat(all_meta, ignore_index=True),
        )
# @AI_GENERATED: end
