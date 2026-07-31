# -*- coding: utf-8 -*-
"""待标注队列：未覆盖或 label_id=NULL 的采样点聚合。"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from services.db.repositories.point_label import PointLabelRepository
from services.db.repositories.pv_fault import PVFaultRepository

SAMPLING_SECONDS = 300

# 内存缓存：source_coverage 结果 + 过期时间（TTL 秒）
_COVERAGE_CACHE: Dict[str, Any] = {}
_COVERAGE_CACHE_TS: float = 0.0
_COVERAGE_CACHE_TTL: float = 120.0  # 2 分钟


def _group_consecutive_times(times: List[datetime]) -> List[tuple]:
    if not times:
        return []
    ordered = sorted(times)
    segments: List[tuple] = []
    seg_start = ordered[0]
    prev = ordered[0]
    for current in ordered[1:]:
        if (current - prev).total_seconds() <= SAMPLING_SECONDS:
            prev = current
            continue
        segments.append((seg_start, prev))
        seg_start = current
        prev = current
    segments.append((seg_start, prev))
    return segments


class PendingLabelQueueService:
    def __init__(self, point_repo: PointLabelRepository, sample_repo: PVFaultRepository) -> None:
        self._labels = point_repo
        self._samples = sample_repo

    def list_queue(
        self,
        *,
        site_id: Optional[str] = None,
        device_id: Optional[str] = None,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
        min_points: int = 1,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """待标注队列：用 SQL 聚合替代逐设备 Python 循环。

        性能优化：原实现对每个设备做 Python 级 query_points，1130 设备
        × 51ms RTT = 阻塞 ~60s。改为一条 LEFT JOIN + GROUP BY SQL，<2s。
        """
        from sqlalchemy import func, text

        from services.db.models.pv_fault import PointLabel, TrainingSample

        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))
        min_points = max(1, int(min_points))

        adapter = self._labels._adapter

        # 构造条件
        conditions = []
        params: Dict[str, Any] = {"min_pts": min_points}
        if site_id:
            conditions.append("ts.site_id = :site_id")
            params["site_id"] = site_id
        if device_id:
            conditions.append("ts.device_id = :device_id")
            params["device_id"] = device_id
        if time_start:
            conditions.append("ts.time >= :t_start")
            params["t_start"] = time_start
        if time_end:
            conditions.append("ts.time < :t_end")
            params["t_end"] = time_end

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # 未标注点 = training_samples 中没有对应 point_labels 行（或 label_id IS NULL）
        sql = text(f"""
            SELECT ts.site_id, ts.device_id, ts.branch_id,
                   COUNT(*) AS unknown_count,
                   MIN(ts.time) AS t_start,
                   MAX(ts.time) AS t_end
            FROM training_samples ts
            LEFT JOIN point_labels pl
              ON ts.site_id=pl.site_id AND ts.device_id=pl.device_id
              AND ts.branch_id=pl.branch_id AND ts.time=pl.time
            WHERE (pl.label_id IS NULL OR pl.site_id IS NULL)
              AND {where_clause}
            GROUP BY ts.site_id, ts.device_id, ts.branch_id
            HAVING COUNT(*) >= :min_pts
            ORDER BY unknown_count DESC
        """)

        with adapter.get_sync_session() as session:
            rows = session.execute(sql, params).fetchall()
            # 总 unknown 点数（跨分页）
            total_unknown = sum(int(r[3]) for r in rows)

        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        items = [
            {
                "site_id": str(r[0]),
                "device_id": str(r[1]),
                "branch_id": str(r[2]),
                "point_count": int(r[3]),
                "t_start": r[4].isoformat(sep=" ") if r[4] else None,
                "t_end": (r[5] + timedelta(seconds=SAMPLING_SECONDS)).isoformat(sep=" ") if r[5] else None,
            }
            for r in rows[start:end]
        ]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "unknown_point_count": total_unknown,
            "items": items,
        }

    def source_coverage(self) -> Dict[str, Any]:
        """各 source 覆盖点数与占比（运营面板）。

        带 2 分钟 TTL 内存缓存，避免重复慢查询。
        """
        global _COVERAGE_CACHE, _COVERAGE_CACHE_TS
        now = time.time()
        if _COVERAGE_CACHE and (now - _COVERAGE_CACHE_TS) < _COVERAGE_CACHE_TTL:
            return _COVERAGE_CACHE

        result = self._source_coverage_uncached()
        _COVERAGE_CACHE = result
        _COVERAGE_CACHE_TS = now
        return result

    def _source_coverage_uncached(self) -> Dict[str, Any]:
        """实际执行 SQL 聚合的 source_coverage。"""
        from sqlalchemy import func, select, text

        from services.db.models.pv_fault import PointLabel, TrainingSample

        adapter = self._labels._adapter

        with adapter.get_sync_session() as session:
            # 1. training_samples 总点数
            total_points = session.execute(
                select(func.count()).select_from(TrainingSample)
            ).scalar() or 0

            # 2. point_labels 按 source 聚合（只算 label_id IS NOT NULL 的）
            source_rows = session.execute(
                select(PointLabel.source, func.count()).where(
                    PointLabel.label_id.isnot(None)
                ).group_by(PointLabel.source)
            ).fetchall()
            source_points = {str(row[0]): int(row[1]) for row in source_rows}
            labeled_points = sum(source_points.values())

            # 3. label_ops active 按 source 聚合
            ops_rows = session.execute(text(
                "SELECT source, COUNT(*) FROM label_ops WHERE status='active' GROUP BY source"
            )).fetchall()
            by_source_ops = {str(row[0]): int(row[1]) for row in ops_rows}

            # 4. 未标注点数 = 总点数 - 已标注点数（避免逐设备循环）
            unknown_points = total_points - labeled_points

            # 5. Top 未标注设备（用单条 SQL）
            top_sql = text("""
                SELECT CONCAT(ts.site_id,'|',ts.device_id,'|',ts.branch_id) AS device_key,
                       COUNT(*) AS unknown_count
                FROM training_samples ts
                LEFT JOIN point_labels pl
                  ON ts.site_id=pl.site_id AND ts.device_id=pl.device_id
                  AND ts.branch_id=pl.branch_id AND ts.time=pl.time
                WHERE pl.label_id IS NULL OR pl.site_id IS NULL
                GROUP BY ts.site_id, ts.device_id, ts.branch_id
                ORDER BY unknown_count DESC
                LIMIT 10
            """)
            top_rows = session.execute(top_sql).fetchall()
            top_devices = [
                {"device_key": str(row[0]), "unknown_point_count": int(row[1])}
                for row in top_rows
            ]

        return {
            "total_measurement_points": total_points,
            "labeled_points": labeled_points,
            "unknown_points": unknown_points,
            "coverage_ratio": round(labeled_points / total_points, 4) if total_points else 0.0,
            "active_ops_by_source": by_source_ops,
            "labeled_points_by_source": source_points,
            "top_unknown_devices": top_devices,
        }
