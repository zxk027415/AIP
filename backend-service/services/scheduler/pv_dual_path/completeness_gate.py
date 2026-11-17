# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/scheduler/pv_dual_path/completeness_gate.py — 显式完整性闸门（Completeness_Gate）

CompletenessGate（完整性闸门）在 IngestionTrackerRepository（设备-天完整性数据仓库）之上
做一层**只读**判定：给定设备三元组 + 业务日，回答「这一天数据到齐了没」以及「当前生效路径
是否放行检测」。它是 seq_annotation（全天序列路径）严格门控与 legacy_day（传统按天路径）
宽松放行的共同入口。

职责边界（重要）：
  - 本类只做**只读判定**，不写 measurement_ingestion_daily、不推进任何游标（Req4.7）。
  - 首达完整幂等（首次达阈值写 UTC completed_at、后续不重写，Req4.6）由
    IngestionTrackerRepository.record_arrival() 的 newly_complete 分支保证，本类不重复实现，
    仅在只读读取时透传该状态。

判定口径：
  - is_complete ⇔ point_count / expected_point_count >= config.completeness_ratio（Req4.1）。
  - 阈值 completeness_ratio 与默认 expected_point_count 越界回退默认（0.9 / 288）已由
    DualPathConfig（load_dual_path_config）在构造前保证（Req4.2 / Req4.5），本类直接信任。
  - 缺 point_count 或 expected_point_count（记录不存在，或字段为空/非正）→ 判未达标
    （is_complete=False）+ error 标识，且不修改现有行（Req4.7）。

路径放行语义（admissible_for_path）：
  - seq_annotation → 实测点数达到训练侧占用门槛（默认 173/288≈60%）即放行。
    光伏白天完整日通常约 200 行，达不到 288×90%；若仍用 is_complete=90%/288，
    喂数后点级路径永远不会检测。90% 完整只作为充分条件保留。
  - legacy_day     → 恒放行，允许对未完整当天的已到达点做增量检测（Req4.4，宽松）。

对应设计：.kiro/specs/pv-fault-dual-path-serving/design.md §4 CompletenessGate + DualPathConfig。
需求：4.1 / 4.3 / 4.4 / 4.6 / 4.7。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from services.db.repositories.ingestion_tracker import IngestionTrackerRepository
from services.iterative_labeling.seq_annotation.grid_align import MIN_OCCUPIED_SLOTS
from services.scheduler.pv_dual_path.config import DualPathConfig

logger = logging.getLogger(__name__)

#: 合法建模路径取值，与 modeling_path 分区维度一致。
_LEGACY_DAY = "legacy_day"
_SEQ_ANNOTATION = "seq_annotation"


@dataclass(frozen=True)
class GateDecision:
    """完整性闸门的单次只读判定结果（不可变）。

    字段（英文名 — 中文含义）：
      - is_complete            — 是否达到完整性阈值（ratio >= config.completeness_ratio）。
      - ratio                  — 实测完成比例 point_count / expected_point_count；
                                 无法计算（缺字段/expected 非正）时为 0.0。
      - point_count            — 该设备-天已到达点数；缺失时为 0。
      - expected_point_count   — 该设备-天理论应有点数；缺失时为 0。
      - error                  — 数据缺失/不可判定时的可诊断标识（Req4.7）；正常判定为 None。
    """

    is_complete: bool
    ratio: float
    point_count: int
    expected_point_count: int
    error: Optional[str] = None


class CompletenessGate:
    """基于 measurement_ingestion_daily 的显式完整性闸门（只读判定 + 按路径放行）。"""

    def __init__(
        self,
        tracker: IngestionTrackerRepository,
        config: DualPathConfig,
    ) -> None:
        """
        Args:
            tracker: 设备-天完整性数据仓库，本类只调用其只读方法 query_device_day()。
            config:  双路径可配阈值；应经 load_dual_path_config() 构造，
                     completeness_ratio / expected_point_count 已保证合法（越界已回退默认）。
        """
        self._tracker = tracker
        self._config = config

    # ------------------------------------------------------------------
    # 只读完整性判定（Req4.1 / Req4.7）
    # ------------------------------------------------------------------

    def evaluate(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        business_date: date,
    ) -> GateDecision:
        """只读判定某设备-天是否达到完整性阈值。

        判定：point_count / expected_point_count >= config.completeness_ratio → is_complete。
        缺失/不可判定（记录不存在、point_count 或 expected_point_count 为空/非正）→
        is_complete=False + error，且不修改 measurement_ingestion_daily 现有行（Req4.7）。
        """
        row = self._tracker.query_device_day(site_id, device_id, branch_id, business_date)

        if row is None:
            return GateDecision(
                is_complete=False,
                ratio=0.0,
                point_count=0,
                expected_point_count=0,
                error="missing_ingestion_row",
            )

        point_count = row.get("point_count")
        expected_point_count = row.get("expected_point_count")

        # 缺 point_count / expected_point_count → 未达标 + 可诊断错误（Req4.7）。
        if point_count is None or expected_point_count is None:
            return GateDecision(
                is_complete=False,
                ratio=0.0,
                point_count=int(point_count or 0),
                expected_point_count=int(expected_point_count or 0),
                error="missing_point_count_fields",
            )

        point_count = int(point_count)
        expected_point_count = int(expected_point_count)

        # expected_point_count 非正无法计算比例 → 未达标 + 可诊断错误（Req4.7）。
        if expected_point_count <= 0:
            return GateDecision(
                is_complete=False,
                ratio=0.0,
                point_count=point_count,
                expected_point_count=expected_point_count,
                error="invalid_expected_point_count",
            )

        ratio = point_count / expected_point_count
        is_complete = ratio >= self._config.completeness_ratio
        return GateDecision(
            is_complete=is_complete,
            ratio=ratio,
            point_count=point_count,
            expected_point_count=expected_point_count,
            error=None,
        )

    # ------------------------------------------------------------------
    # 按路径放行（Req4.3 严格 / Req4.4 宽松）
    # ------------------------------------------------------------------

    def admissible_for_path(self, decision: GateDecision, modeling_path: str) -> bool:
        """按当前生效路径判断该设备-天是否可被检测。

        - seq_annotation → 实测点数达到训练占用门槛（173/288）或 is_complete 为真。
        - legacy_day     → 恒放行（宽松，允许未完整当天的增量检测，Req4.4）。
        - 其他取值       → 视为非法路径，不放行（保守拒绝，交由上游分派器处理）。
        """
        if modeling_path == _SEQ_ANNOTATION:
            if bool(decision.is_complete):
                return True
            return int(decision.point_count or 0) >= int(MIN_OCCUPIED_SLOTS)
        if modeling_path == _LEGACY_DAY:
            return True
        logger.warning(
            "completeness_gate: 未知 modeling_path=%r，保守不放行。", modeling_path,
        )
        return False
# @AI_GENERATED: end
