# -*- coding: utf-8 -*-
"""
services/scheduler/tasks/pv_fault_tasks.py — 光伏故障诊断调度任务

提供两个任务工厂函数：

  make_pv_data_pull_task(station_source, pv_repo)
    → 返回 pv_data_pull_task()，负责按高水位拉取 PV 传感器数据并写入数据库。
    每次执行最多处理 10,000 条记录（需求 5.2）。
    数据源不可达（DataSourceError）时记录 WARNING，跳过本次，不影响下次调度（需求 5.5）。

  make_pv_prediction_task(pv_repo, model_ref)
    → 返回 pv_prediction_task()，负责加载故障诊断模型并执行推理（当前为 stub）。
    模型文件缺失时记录 WARNING + ERROR 通知事件，跳过本次周期（需求 5.6）。

Requirements: 5.2, 5.3, 5.5, 5.6
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Callable

from services.db.datasources.base import DataSourceError, StationDataSource
from services.db.repositories.pv_fault import PVFaultRepository

logger = logging.getLogger(__name__)

# 每次拉取处理的最大记录数（需求 5.2）
_MAX_RECORDS_PER_PULL = 10_000


def make_pv_data_pull_task(
    station_source: StationDataSource,
    pv_repo: PVFaultRepository,
) -> Callable[[], None]:
    """
    工厂函数：创建 PV 数据拉取任务。

    Args:
        station_source: 站点数据源实例，提供 pull_latest() 接口。
                        station_source — 抽象数据源，实现 StationDataSource ABC。
        pv_repo:        光伏故障诊断数据仓库实例。
                        pv_repo — PVFaultRepository，负责写入 training_samples 表。

    Returns:
        pv_data_pull_task — 无参可调用对象，供 SchedulerEngine 注册。
    """

    # 闭包变量：跟踪本任务实例累计失败次数（需求 5.1，独立失败计数）
    failure_count: int = 0

    def pv_data_pull_task() -> None:
        """
        PV 传感器数据拉取任务（每次调度执行一次）。

        流程：
          1. 查询 pv_repo 中最新的 training_sample.time，作为高水位（since_timestamp）。
             若无历史数据，则以 epoch 起点作为起始时间（拉取全量）。
          2. 调用 station_source.pull_latest(station_id, since_timestamp) 拉取新记录。
          3. 截取前 10,000 条（需求 5.2），转换为 training_sample 格式写入数据库。
          4. 数据源不可达时（DataSourceError）记录 WARNING，更新失败计数，跳过。

        Requirements: 5.2, 5.5
        """
        nonlocal failure_count

        # 1. 确定高水位：取数据库中最新 time；无数据时从 epoch 开始
        hw = pv_repo.get_high_watermark()
        since_ts = hw if hw is not None else datetime(1970, 1, 1)

        # 2. 拉取新记录（数据源不可达时 WARNING + 跳过）
        try:
            records = station_source.pull_latest(
                station_id="pv",
                since_timestamp=since_ts,
            )
        except DataSourceError as exc:
            failure_count += 1
            logger.warning(
                "pv_data_pull_task: 数据源不可达，跳过本次拉取（累计失败 %d 次）: %s",
                failure_count,
                exc,
            )
            return

        if not records:
            logger.info("pv_data_pull_task: 无新记录，跳过本次写入。since=%s", since_ts)
            return

        # 3. 批量上限 10,000 条（需求 5.2）
        batch = records[:_MAX_RECORDS_PER_PULL]
        logger.info(
            "pv_data_pull_task: 拉取 %d 条（数据源共 %d 条），写入数据库。",
            len(batch),
            len(records),
        )

        # 4. 转换为 training_sample 格式，使用 INSERT IGNORE 语义写入
        #    直接调用 PVFaultRepository.insert_prediction_record 是错的；
        #    training_samples 写入通过 ingest_parquet 或批量 INSERT IGNORE。
        #    此处逐条构造 dict 后批量写入（INSERT IGNORE 由 ingest_parquet 底层保证）。
        import pandas as pd

        rows = []
        for rec in batch:
            rows.append(
                {
                    "time": rec.timestamp.replace(tzinfo=None)
                    if rec.timestamp.tzinfo is not None
                    else rec.timestamp,
                    "site_id": rec.station_id,
                    "device_id": rec.feature_name,  # feature_name 作为 device_id 占位
                    "branch_id": "default",
                    "value": rec.value,
                    "i_cal": 0.0,
                    "label": -1,  # 未标注
                }
            )

        import tempfile

        fd, tmp_path = tempfile.mkstemp(suffix=".parquet")
        os.close(fd)  # 关闭文件描述符，pandas 会单独打开写入
        try:
            pd.DataFrame(rows).to_parquet(tmp_path, index=False)
            result = pv_repo.ingest_parquet(tmp_path)
            logger.info(
                "pv_data_pull_task: 写入完成 inserted=%d skipped=%d",
                result["inserted"],
                result["skipped"],
            )
        except Exception as exc:
            failure_count += 1
            logger.error(
                "pv_data_pull_task: 写入数据库失败（累计失败 %d 次）: %s",
                failure_count,
                exc,
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    return pv_data_pull_task


def make_pv_prediction_task(
    pv_repo: PVFaultRepository,
    model_ref: str,
) -> Callable[[], None]:
    """
    工厂函数：创建 PV 故障预测任务（当前为 stub 实现）。

    Args:
        pv_repo:   光伏故障诊断数据仓库实例（预留给后续实际推理逻辑）。
                   pv_repo — PVFaultRepository，供推理结果写入。
        model_ref: 故障诊断模型文件路径（字符串）。
                   model_ref — 模型文件路径，缺失时触发 MODEL_UNAVAILABLE 通知。

    Returns:
        pv_prediction_task — 无参可调用对象，供 SchedulerEngine 注册。
    """

    def pv_prediction_task() -> None:
        """
        PV 故障预测任务（stub）。

        流程：
          1. 检查 model_ref 文件是否存在。
          2. 文件不存在：记录 WARNING，emit MODEL_UNAVAILABLE 通知，跳过本周期（需求 5.6）。
          3. 文件存在：记录 INFO，占位（实际推理逻辑待后续实现）。

        Requirements: 5.3, 5.6
        """
        if not os.path.exists(model_ref):
            # 模型缺失：记录警告 + 通知事件，跳过本周期（需求 5.6）
            logger.warning("PV fault model not found: %s", model_ref)
            logger.error("MODEL_UNAVAILABLE: %s", model_ref)
            return

        # 模型存在：占位 stub，实际推理逻辑留给后续迭代（需求 5.3）
        logger.info("pv_prediction_task triggered, model=%s", model_ref)

    return pv_prediction_task
