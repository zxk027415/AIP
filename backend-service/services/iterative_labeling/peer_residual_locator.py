# -*- coding: utf-8 -*-
"""
services/iterative_labeling/peer_residual_locator.py — 同期对标故障段候选生成

本模块只根据天标签和同期残差提出子天候选边界，不写数据库、不生成生效点真值，
也不生成“候选段以外即正常”的 K4 伴生操作。候选必须进入独立审核流程；只有批准后
才允许以 ``peer_residual`` 来源写入点路径，并通过 ``source_candidate_id`` 追溯。

**核心方法 —— 同期对标（peer comparison）**：
同一电站同一时刻的所有设备受相同辐照/天气影响，正常设备的功率形态应彼此相似。
取该时刻站内所有序列的**中位数**作为基准（中位数对少数异常值鲁棒，只要故障设备
不过半就代表"正常水平"），残差 = 该设备值 / 基准值。

    残差 ≈ 1.0  → 与同期设备一致，正常
    残差 < 0.7  → 明显低于同期，疑似故障
    残差 < 0.3  → 远低于同期，重度故障

天气影响会被中位数一起吸收（云来了所有设备同降，基准也降，残差不变），
因此残差能区分「天气导致的普降」与「单台设备的真实故障」——这是纯阈值法做不到的。

**为什么需要它**：实测 `point_labels` 中 99.96% 的设备-天只有单一标签（天级广播），
子天标注仅 2 条 `human_range` 操作 / 293 点，不足以训练任何逐点模型。

设计依据：与用户确认的分层筛选方案（2026-08-04）。
"""

# @AI_GENERATED
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: 采样间隔（秒）。与 sample_columns.SAMPLING_INTERVAL_SECONDS 保持一致。
SAMPLING_INTERVAL_SECONDS = 300

#: 正常标签编码（与 point_label_service.NORMAL_LABEL_ID 一致）
NORMAL_LABEL_ID = 0

#: 候选算法合同版本；参与稳定 candidate ID，算法变化时必须升级。
ALGORITHM_VERSION = "peer_residual_v1"


@dataclass
class LocatorConfig:
    """同期对标定位器配置（可序列化，随结果一起落盘便于复现）。"""

    # ---- 对照组（peer group）约束 ----
    min_peer_series: int = 5
    """算基准所需的最少同站点同期序列数。低于此值该 (站点,日期) 整体跳过。

    实测：99.5% 的设备-天满足 >=5，中位对照组大小 47 条序列。
    对照组太小时中位数不代表"正常水平"（万一那几台都坏了）。
    """

    # ---- 白天时段（夜间残差无意义：0/0） ----
    daylight_start_hour: int = 7
    daylight_end_hour: int = 17
    """白天时段 [start, end)。夜间所有设备出力均为 0，残差退化为 0/0。"""

    min_peer_baseline: float = 1.0
    """基准值下限。基准低于此值的时刻整体跳过（清晨/傍晚/阴天，信噪比太低）。"""

    # ---- 残差阈值 ----
    residual_fault_threshold: float = 0.7
    """残差低于此值判为疑似故障点。0.7 = 比同期设备低 30% 以上。"""

    residual_high_conf_threshold: float = 0.5
    """残差低于此值判为高置信故障点。用于区分「直接落库」与「送人工/LLM 复核」。"""

    # ---- 段（segment）约束 ----
    min_segment_points: int = 6
    """候选段最少连续点数。6 点 × 5min = 30 分钟，滤掉瞬时抖动。"""

    max_gap_points_to_merge: int = 3
    """两个候选段之间的间隔 <= 此点数时合并为一段（容忍短暂恢复）。"""

    min_valid_daylight_points: int = 60
    """该设备-天白天有效点数下限（60 点 = 5 小时）。数据太少不做定位。"""

    # ---- 跳过规则 ----
    skip_labels: Tuple[int, ...] = (0, 2)
    """不做定位的标签。
    0 = 正常（无故障段可定位）；
    2 = 实测日内变异系数 CV≈0（p50=0.000，仅 8.4% 的天 CV>0.3），
        属"整天持续"型故障，没有"故障开始的那个点"，强行定位无意义。
    """

    min_label_days: int = 10
    """标签的总天数下限。少于此值的稀有类（实测 label 9/10/16 各 1/6/4 天）跳过，
    自动定位的收益不足以抵消引入错误标签的风险。
    """

    max_fault_ratio: float = 0.95
    """故障点占白天比例上限。超过此值说明"整天都是故障"，
    没有子天边界信息，不产出候选段（保留原天级标签即可）。
    """

    min_fault_ratio: float = 0.02
    """故障点占白天比例下限。低于此值多为噪声抖动，不产出。"""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["skip_labels"] = list(self.skip_labels)
        return d


@dataclass
class FaultSegment:
    """一个候选故障段。"""

    site_id: str
    device_id: str
    branch_id: str
    date: str
    label: int
    """继承自该设备-天的天级标签（定位不改变故障类型，只确定时间边界）。"""

    t_start: datetime
    t_end: datetime
    """段边界，半开区间 [t_start, t_end)。t_end 已含最后一点的采样间隔。"""

    n_points: int
    mean_residual: float
    """段内平均残差。越小说明偏离同期设备越远、越可能是真故障。"""

    min_residual: float
    confidence: str
    """high（mean_residual < high_conf_threshold）/ medium。"""

    peer_count: int
    """算基准时的对照组序列数，用于审计（对照组越大基准越可信）。"""

    fault_ratio: float
    """该设备-天白天的故障点占比。"""

    source_candidate_id: str = field(init=False)
    proposed_label_id: int = field(init=False)
    review_status: str = field(default="pending", init=False)
    algorithm_version: str = field(default=ALGORITHM_VERSION, init=False)

    def __post_init__(self) -> None:
        self.proposed_label_id = int(self.label)
        identity = "|".join(
            (
                self.algorithm_version,
                str(self.site_id),
                str(self.device_id),
                str(self.branch_id),
                self.t_start.isoformat(),
                self.t_end.isoformat(),
                str(self.proposed_label_id),
            )
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        self.source_candidate_id = f"prc-{digest}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["t_start"] = self.t_start.isoformat()
        d["t_end"] = self.t_end.isoformat()
        return d


class PeerResidualLocator:
    """
    同期对标故障段定位器。

    用法::

        locator = PeerResidualLocator(LocatorConfig())
        segments, report = locator.locate(df)   # df 需含 site_id/device_id/branch_id/time/value/label

    只做计算与产出候选段，**不写数据库**。调用方只能导出候选并送人工审核，
    不得把候选或段外互补区间直接写成生效点标签。
    """

    def __init__(self, config: Optional[LocatorConfig] = None):
        self.config = config or LocatorConfig()

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def locate(
        self, data: pd.DataFrame, value_col: str = "value"
    ) -> Tuple[List[FaultSegment], Dict[str, Any]]:
        """
        对整个数据集做同期对标定位。

        Parameters
        ----------
        data : DataFrame
            须含 site_id / device_id / branch_id / time / value / label 列。
        value_col : str
            用于对标的功率列。

        Returns
        -------
        (segments, report)
            segments —— 候选故障段列表
            report   —— 统计报告（各阶段跳过原因与计数，便于审计）
        """
        cfg = self.config
        df = data.copy()
        df["time"] = pd.to_datetime(df["time"])
        df["_date"] = df["time"].dt.date

        stats: Dict[str, int] = {
            "device_days_total": 0,
            "skipped_label_in_skiplist": 0,
            "skipped_rare_label": 0,
            "skipped_small_peer_group": 0,
            "skipped_few_daylight_points": 0,
            "skipped_no_segment": 0,
            "skipped_fault_ratio_out_of_range": 0,
            "located": 0,
        }

        # 稀有标签统计（按设备-天计数，不是按行）
        label_day_counts = (
            df.groupby(["site_id", "device_id", "branch_id", "_date"])["label"]
            .first()
            .value_counts()
            .to_dict()
        )
        rare_labels = {
            int(lbl)
            for lbl, cnt in label_day_counts.items()
            if pd.notna(lbl) and cnt < cfg.min_label_days
        }
        if rare_labels:
            logger.info("稀有标签（天数 < %d）将跳过: %s", cfg.min_label_days, sorted(rare_labels))

        segments: List[FaultSegment] = []

        # 按 (站点, 日期) 分组 —— 对照组的作用域
        for (site_id, date), site_day in df.groupby(["site_id", "_date"], sort=False):
            baseline, peer_count = self._compute_peer_baseline(site_day, value_col)
            if baseline is None:
                n_dd = site_day.groupby(["device_id", "branch_id"]).ngroups
                stats["device_days_total"] += n_dd
                stats["skipped_small_peer_group"] += n_dd
                continue

            for (device_id, branch_id), series in site_day.groupby(
                ["device_id", "branch_id"], sort=False
            ):
                stats["device_days_total"] += 1

                label = series["label"].dropna()
                if label.empty:
                    stats["skipped_label_in_skiplist"] += 1
                    continue
                label_val = int(label.iloc[0])

                if label_val in cfg.skip_labels:
                    stats["skipped_label_in_skiplist"] += 1
                    continue
                if label_val in rare_labels:
                    stats["skipped_rare_label"] += 1
                    continue

                seg_list, skip_reason = self._locate_one_series(
                    series, baseline, peer_count,
                    site_id=str(site_id), device_id=str(device_id),
                    branch_id=str(branch_id), date=str(date), label=label_val,
                    value_col=value_col,
                )
                if skip_reason:
                    stats[skip_reason] = stats.get(skip_reason, 0) + 1
                    continue

                segments.extend(seg_list)
                stats["located"] += 1

        report = {
            "config": cfg.to_dict(),
            "stats": stats,
            "n_segments": len(segments),
            "n_high_confidence": sum(1 for s in segments if s.confidence == "high"),
            "n_medium_confidence": sum(1 for s in segments if s.confidence == "medium"),
            "generated_at": datetime.utcnow().isoformat(),
        }
        return segments, report

    # ------------------------------------------------------------------
    # 第 1 层：同期基准
    # ------------------------------------------------------------------

    def _compute_peer_baseline(
        self, site_day: pd.DataFrame, value_col: str
    ) -> Tuple[Optional[pd.Series], int]:
        """
        计算某站点某天各时刻的基准曲线（同期所有序列的中位数）。

        Returns
        -------
        (baseline, peer_count)
            baseline —— index 为 time、值为该时刻中位数的 Series；对照组不足时为 None
            peer_count —— 参与计算的序列数

        Notes
        -----
        用中位数而非均值：若 50 台里有 10 台同时故障，均值会被拉低导致基准偏低，
        正常设备残差反而 >1、故障设备残差看起来"没那么坏"。中位数只要故障设备
        不过半就仍代表正常水平（鲁棒统计）。
        """
        cfg = self.config
        peer_count = site_day.groupby(["device_id", "branch_id"]).ngroups
        if peer_count < cfg.min_peer_series:
            return None, peer_count

        hours = site_day["time"].dt.hour
        daylight = site_day[
            (hours >= cfg.daylight_start_hour) & (hours < cfg.daylight_end_hour)
        ]
        if daylight.empty:
            return None, peer_count

        baseline = daylight.groupby("time")[value_col].median()
        # 基准过低的时刻置 NaN（清晨/傍晚/阴天，信噪比不足，残差不可信）
        baseline = baseline.where(baseline >= cfg.min_peer_baseline)
        if baseline.notna().sum() < cfg.min_valid_daylight_points:
            return None, peer_count
        return baseline, peer_count

    # ------------------------------------------------------------------
    # 第 2 层：残差 + 候选段
    # ------------------------------------------------------------------

    def _locate_one_series(
        self,
        series: pd.DataFrame,
        baseline: pd.Series,
        peer_count: int,
        *,
        site_id: str,
        device_id: str,
        branch_id: str,
        date: str,
        label: int,
        value_col: str,
    ) -> Tuple[List[FaultSegment], Optional[str]]:
        """对单条设备-天序列算残差并提取候选故障段。"""
        cfg = self.config

        s = series.sort_values("time")
        hours = s["time"].dt.hour
        s = s[(hours >= cfg.daylight_start_hour) & (hours < cfg.daylight_end_hour)]
        if len(s) < cfg.min_valid_daylight_points:
            return [], "skipped_few_daylight_points"

        # 对齐基准并算残差
        base_aligned = s["time"].map(baseline)
        residual = s[value_col].to_numpy(dtype=float) / base_aligned.to_numpy(dtype=float)
        times = s["time"].to_numpy()

        valid = np.isfinite(residual)
        if valid.sum() < cfg.min_valid_daylight_points:
            return [], "skipped_few_daylight_points"

        # 疑似故障点掩码（NaN 视为非故障，避免缺测被当成异常）
        is_fault = np.zeros(len(residual), dtype=bool)
        is_fault[valid] = residual[valid] < cfg.residual_fault_threshold

        fault_ratio = float(is_fault.sum() / valid.sum())
        if not (cfg.min_fault_ratio <= fault_ratio <= cfg.max_fault_ratio):
            # 太少 = 噪声；太多 = 整天故障，无子天边界信息
            return [], "skipped_fault_ratio_out_of_range"

        runs = self._extract_runs(is_fault)
        runs = self._merge_close_runs(runs, cfg.max_gap_points_to_merge)
        runs = [(a, b) for a, b in runs if (b - a) >= cfg.min_segment_points]
        if not runs:
            return [], "skipped_no_segment"

        out: List[FaultSegment] = []
        for start_i, end_i in runs:
            seg_res = residual[start_i:end_i]
            seg_res = seg_res[np.isfinite(seg_res)]
            if seg_res.size == 0:
                continue
            mean_res = float(seg_res.mean())
            t_start = pd.Timestamp(times[start_i]).to_pydatetime()
            # 半开区间：末点 + 一个采样间隔
            t_end = pd.Timestamp(times[end_i - 1]).to_pydatetime() + timedelta(
                seconds=SAMPLING_INTERVAL_SECONDS
            )
            out.append(FaultSegment(
                site_id=site_id, device_id=device_id, branch_id=branch_id,
                date=date, label=label,
                t_start=t_start, t_end=t_end,
                n_points=int(end_i - start_i),
                mean_residual=round(mean_res, 4),
                min_residual=round(float(seg_res.min()), 4),
                confidence="high" if mean_res < cfg.residual_high_conf_threshold else "medium",
                peer_count=peer_count,
                fault_ratio=round(fault_ratio, 4),
            ))
        if not out:
            return [], "skipped_no_segment"
        return out, None

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_runs(mask: np.ndarray) -> List[Tuple[int, int]]:
        """把布尔掩码里连续 True 的区间提成 [start, end) 索引对。"""
        if not mask.any():
            return []
        # 用差分找边界，避免逐点 Python 循环
        padded = np.concatenate(([False], mask, [False]))
        diff = np.diff(padded.astype(np.int8))
        starts = np.flatnonzero(diff == 1)
        ends = np.flatnonzero(diff == -1)
        return list(zip(starts.tolist(), ends.tolist()))

    @staticmethod
    def _merge_close_runs(
        runs: List[Tuple[int, int]], max_gap: int
    ) -> List[Tuple[int, int]]:
        """合并间隔 <= max_gap 的相邻区间（容忍故障期间的短暂恢复）。"""
        if not runs:
            return []
        merged = [list(runs[0])]
        for start, end in runs[1:]:
            if start - merged[-1][1] <= max_gap:
                merged[-1][1] = end
            else:
                merged.append([start, end])
        return [(a, b) for a, b in merged]


def segments_to_dataframe(segments: List[FaultSegment]) -> pd.DataFrame:
    """把候选段列表转成 DataFrame，便于导出 CSV / 人工抽查。"""
    if not segments:
        return pd.DataFrame(columns=[
            "source_candidate_id", "site_id", "device_id", "branch_id", "date",
            "proposed_label_id", "label", "t_start", "t_end", "n_points",
            "mean_residual", "min_residual", "confidence", "review_status",
            "algorithm_version", "peer_count", "fault_ratio",
        ])
    return pd.DataFrame([s.to_dict() for s in segments])
# @AI_GENERATED: end
