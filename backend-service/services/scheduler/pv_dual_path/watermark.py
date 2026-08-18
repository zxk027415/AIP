# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/scheduler/pv_dual_path/watermark.py — 设备数据到达水位（Data_Watermark）

DataWatermarkService 计算某设备三元组已入库数据点的最大 Event_Time（事件时间/业务时间），
作为双路径检测的统一时间进度基准：两条策略都按「数据到达」推进，不看墙钟（Processing_Time）。

- device_watermark(site_id, device_id, branch_id) -> Optional[datetime]
    该设备已入库数据点的最大 Event_Time；无数据返回 None。
    主口径：MAX(training_samples.time)，限定 data_source in (mock, production)。
    回退/交叉校验：measurement_ingestion_daily 的 MAX(business_date)（当主口径缺失时用它兜底，
    避免完整性表已登记但样本表尚未可查导致水位偏空）。
- device_watermark_date(site_id, device_id, branch_id) -> Optional[date]
    上者所在自然日，作为「数据今天」基准（Seq_Daily_Strategy 用其判定「只检测水位前完整整天」）。

对应设计：.kiro/specs/pv-fault-dual-path-serving/design.md §2 DataWatermarkService。
需求：1.8（两条策略共用 Data_Watermark、不用墙钟）、2.9（Legacy 以已到达数据为窗口上限）、
3.1（Seq 以 Data_Watermark 所在自然日为「数据今天」基准）。

依赖注入：构造函数接收一个已初始化的 DBAdapter（复用 IngestionTrackerRepository 的 session 用法），
不在本类内部新建连接池，便于测试与复用。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select

from services.db.adapter import DBAdapter
from services.db.models.pv_fault import MeasurementIngestionDaily, TrainingSample

logger = logging.getLogger(__name__)

#: 计入水位的数据来源：mock 回放 + 真实生产采集（预留）。两者都是「已到达的观测事实」。
_WATERMARK_DATA_SOURCES = ("mock", "production")


class DataWatermarkService:
    """设备数据到达水位服务 —— 双路径共用的时间进度基准。"""

    def __init__(self, adapter: DBAdapter) -> None:
        self._adapter = adapter

    # ------------------------------------------------------------------
    # 设备级数据到达水位
    # ------------------------------------------------------------------

    def device_watermark(
        self, site_id: str, device_id: str, branch_id: str,
    ) -> Optional[datetime]:
        """返回该设备三元组已入库数据点的最大 Event_Time；无数据返回 None。

        计算顺序：
          1. 主口径：MAX(training_samples.time)，限定 data_source in (mock, production)。
          2. 回退/交叉校验：若主口径为空，用 measurement_ingestion_daily 的
             MAX(business_date) 作为兜底（转成该自然日起始时刻 00:00:00，
             精确 Event_Time 未知时以自然日粒度提供水位，仅用于「数据今天」判定）。
          3. 两者都无 → None。
        """
        with self._adapter.get_sync_session() as session:
            sample_max = session.execute(
                select(func.max(TrainingSample.time)).where(
                    TrainingSample.site_id == site_id,
                    TrainingSample.device_id == device_id,
                    TrainingSample.branch_id == branch_id,
                    TrainingSample.data_source.in_(_WATERMARK_DATA_SOURCES),
                )
            ).scalar_one_or_none()

            if sample_max is not None:
                return sample_max

            # 回退：完整性表最大业务日。转成该自然日的起始时刻（00:00:00），
            # 精确 Event_Time 未知时以自然日粒度提供水位，供 date 级判定使用。
            fallback_date = session.execute(
                select(func.max(MeasurementIngestionDaily.business_date)).where(
                    MeasurementIngestionDaily.site_id == site_id,
                    MeasurementIngestionDaily.device_id == device_id,
                    MeasurementIngestionDaily.branch_id == branch_id,
                )
            ).scalar_one_or_none()

        if fallback_date is not None:
            logger.debug(
                "watermark: 设备(%s,%s,%s) 无 training_samples，回退 measurement_ingestion_daily "
                "最大业务日 %s",
                site_id, device_id, branch_id, fallback_date,
            )
            return datetime(fallback_date.year, fallback_date.month, fallback_date.day)
        return None

    def device_watermark_date(
        self, site_id: str, device_id: str, branch_id: str,
    ) -> Optional[date]:
        """返回设备数据到达水位所在的自然日；无数据返回 None。

        Seq_Daily_Strategy 以此作为「数据今天」基准：仅检测 Event_Time 自然日
        严格早于该日期的整天数据（Req3.1）。
        """
        watermark = self.device_watermark(site_id, device_id, branch_id)
        if watermark is None:
            return None
        return watermark.date()
# @AI_GENERATED: end
