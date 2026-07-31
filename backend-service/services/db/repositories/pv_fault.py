# -*- coding: utf-8 -*-
"""
services/db/repositories/pv_fault.py — 光伏故障诊断数据仓库

PVFaultRepository: 封装 pv_fault_diag 库下 4 张表的所有 CRUD 操作。

主要方法：
  - ingest_parquet        Parquet 批量导入 training_samples（INSERT IGNORE 去重）
  - insert_prediction_record   写入预测记录（含 confidence 范围校验）
  - insert_diagnosis_result    写入诊断结果
  - query_training_samples     多条件过滤查询训练样本
  - save_model_version         写入或更新模型版本元信息
  - get_model_version          按 ID 查询模型版本

Requirements: 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

# @AI_GENERATED: 未标注样本筛选需要显式 SQL OR 条件
from sqlalchemy import insert as sa_insert, or_, select
# @AI_GENERATED: end

from services.db.adapter import DBAdapter
from services.db.exceptions import IngestionError
from services.db.models.pv_fault import (
    DiagnosisResult,
    ModelVersion,
    PredictionRecord,
    TrainingSample,
)

logger = logging.getLogger(__name__)

# Parquet 导入必需列
_REQUIRED_COLUMNS = frozenset(
    {"time", "site_id", "device_id", "branch_id", "value", "i_cal", "label"}
)

# 每批 INSERT IGNORE 的行数上限，防止单条 SQL 过大
_BATCH_SIZE = 500


class PVFaultRepository:
    """
    光伏故障诊断数据仓库。

    所有操作通过 DBAdapter 获取同步 Session，在事务内完成写入/查询。

    用法示例：
        from services.db.config import DBConfig
        from services.db.adapter import DBAdapter
        from services.db.repositories.pv_fault import PVFaultRepository

        adapter = DBAdapter(DBConfig())
        repo = PVFaultRepository(adapter)
        result = repo.ingest_parquet("data/samples.parquet")
        print(result)   # {"inserted": 120, "skipped": 3}
    """

    def __init__(self, adapter: DBAdapter) -> None:
        self._adapter = adapter

    # ------------------------------------------------------------------
    # Parquet 批量导入
    # ------------------------------------------------------------------

    def ingest_parquet(self, file_path: str, *, batch_commit: bool = True) -> Dict[str, int]:
        """
        读取 Parquet 文件，按复合键 (time, site_id, device_id, branch_id) 去重，
        用 INSERT IGNORE 批量写入 training_samples。

        文件缺少必需列时抛 IngestionError（校验在写入前完成，不产生部分写入）。

        Args:
            file_path: Parquet 文件路径（相对或绝对路径均可）。
            batch_commit: 为 True 时每批独立 commit（防止远程 MySQL Lock wait
                timeout，幂等可重试）；为 False 时全量单事务（原子性，适合小文件）。

        Returns:
            {"inserted": n, "skipped": m}
              inserted — 实际插入的行数（新增）
              skipped  — 因复合键冲突被 IGNORE 的行数（重复）

        Raises:
            IngestionError: 文件不可读或缺少必需列。

        Requirements: 3.2, 3.3, 3.6
        """
        import pandas as pd

        # 1. 读取文件 —— 读取失败直接抛 IngestionError（无写入发生）
        try:
            df = pd.read_parquet(file_path)
        except Exception as exc:
            raise IngestionError(file_path) from exc

        # 2. 列校验 —— 在任何写入之前完成，确保"全失败"语义
        missing = _REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise IngestionError(file_path, missing_columns=sorted(missing))

        # 3. 只保留必需列，进行类型归一化
        df = df[list(_REQUIRED_COLUMNS)].copy()

        # time 列：统一转为无时区的 datetime（MySQL DateTime 不支持 tz-aware）
        df["time"] = pd.to_datetime(df["time"])
        if df["time"].dt.tz is not None:
            df["time"] = df["time"].dt.tz_convert("UTC").dt.tz_localize(None)

        # float/int 列：NaN → None（SQL NULL）
        df = df.where(pd.notnull(df), None)
        # @AI_GENERATED: pandas 浮点列会把 None 回写为 NaN；label 必须保留 SQL NULL 语义。
        df["label"] = df["label"].astype(object).where(df["label"].notna(), None)
        # @AI_GENERATED: end

        records = df.to_dict(orient="records")
        if not records:
            return {"inserted": 0, "skipped": 0}

        # 4. 分批 INSERT IGNORE
        total_inserted = 0
        n_batches = (len(records) + _BATCH_SIZE - 1) // _BATCH_SIZE

        if batch_commit:
            # @AI_GENERATED: 每批独立 session/commit，防止远程 MySQL Lock wait timeout。
            # INSERT IGNORE 幂等，中途失败可重跑、已成功的批次会被 skip。
            for i in range(0, len(records), _BATCH_SIZE):
                batch = records[i : i + _BATCH_SIZE]
                with self._adapter.get_sync_session() as session:
                    stmt = sa_insert(TrainingSample).prefix_with("IGNORE").values(batch)
                    result = session.execute(stmt)
                    total_inserted += result.rowcount
                if (i // _BATCH_SIZE) % 200 == 0:
                    logger.info(
                        "ingest_parquet progress: batch %d/%d inserted_so_far=%d",
                        i // _BATCH_SIZE + 1, n_batches, total_inserted,
                    )
            # @AI_GENERATED: end
        else:
            # 单事务（原子性，适合小文件或测试）
            with self._adapter.get_sync_session() as session:
                for i in range(0, len(records), _BATCH_SIZE):
                    batch = records[i : i + _BATCH_SIZE]
                    stmt = sa_insert(TrainingSample).prefix_with("IGNORE").values(batch)
                    result = session.execute(stmt)
                    total_inserted += result.rowcount

        skipped = len(records) - total_inserted
        logger.info(
            "ingest_parquet: file=%s total=%d inserted=%d skipped=%d batch_commit=%s",
            file_path,
            len(records),
            total_inserted,
            skipped,
            batch_commit,
        )
        return {"inserted": total_inserted, "skipped": skipped}

    # ------------------------------------------------------------------
    # 预测记录
    # ------------------------------------------------------------------

    def insert_prediction_record(self, record_data: dict) -> PredictionRecord:
        """
        写入预测记录。

        confidence 需在 [0.0, 1.0]，超出范围抛 ValueError（写入前校验）。

        Args:
            record_data: 与 PredictionRecord 列名对应的字典。

        Returns:
            已持久化、包含数据库生成 id 的 PredictionRecord 实例。

        Raises:
            ValueError: confidence 超出 [0.0, 1.0]。

        Requirements: 3.4
        """
        confidence = record_data.get("confidence")
        if confidence is not None and not (0.0 <= float(confidence) <= 1.0):
            raise ValueError(
                f"confidence 必须在 [0.0, 1.0] 范围内，当前值：{confidence}"
            )

        record = PredictionRecord(**record_data)
        with self._adapter.get_sync_session() as session:
            session.add(record)
            session.flush()
            session.refresh(record)
            # expire_on_commit=False 已在 adapter 设置，commit+close 后属性仍可访问
        return record

    # ------------------------------------------------------------------
    # 诊断结果
    # ------------------------------------------------------------------

    def insert_diagnosis_result(self, result_data: dict) -> DiagnosisResult:
        """
        写入诊断结果。

        Args:
            result_data: 与 DiagnosisResult 列名对应的字典。

        Returns:
            已持久化、包含数据库生成 id 的 DiagnosisResult 实例。

        Requirements: 3.4
        """
        result = DiagnosisResult(**result_data)
        with self._adapter.get_sync_session() as session:
            session.add(result)
            session.flush()
            session.refresh(result)
        return result

    # ------------------------------------------------------------------
    # 训练样本查询
    # ------------------------------------------------------------------

    def query_training_samples(
        self,
        site_id: Optional[str] = None,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
        labels: Optional[List[int]] = None,
    ) -> List[TrainingSample]:
        """
        按任意条件组合过滤查询 training_samples，结果按 time ASC 排序。

        Args:
            site_id:    站点 ID 精确匹配（None 表示不过滤）。
            time_start: 起始时间（含），None 表示不限。
            time_end:   结束时间（不含），None 表示不限。
            labels:     标签白名单列表，None 表示不过滤。

        Returns:
            符合条件的 TrainingSample 列表，按 time 升序排列。

        Requirements: 3.5
        """
        stmt = select(TrainingSample)
        if site_id is not None:
            stmt = stmt.where(TrainingSample.site_id == site_id)
        if time_start is not None:
            stmt = stmt.where(TrainingSample.time >= time_start)
        if time_end is not None:
            stmt = stmt.where(TrainingSample.time < time_end)
        if labels is not None:
            stmt = stmt.where(TrainingSample.label.in_(labels))
        stmt = stmt.order_by(TrainingSample.time.asc())

        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).scalars().all()
            # 在 session 关闭前将对象与 session 解绑，保留内存状态
            for row in rows:
                session.expunge(row)
        return list(rows)

    # @AI_GENERATED: 调度预测只读取未标注且尚未被成功批次消费的原始观测，供 pandas 快照为 CSV。
    def query_unlabeled_training_samples(
        self,
        after_time: Optional[datetime] = None,
    ) -> List[Dict[str, object]]:
        """读取 ``label IS NULL OR label < 0`` 的观测，按复合业务键稳定排序。

        ``after_time`` 是调度侧成功预测游标：传入后仅返回更晚的未标注观测，避免每日任务
        对同一批待审核数据重复推理。返回普通字典，调用方可直接构造 pandas CSV。
        """
        columns = (
            TrainingSample.time,
            TrainingSample.site_id,
            TrainingSample.device_id,
            TrainingSample.branch_id,
            TrainingSample.value,
            TrainingSample.i_cal,
            TrainingSample.label,
        )
        stmt = select(*columns).where(
            or_(TrainingSample.label.is_(None), TrainingSample.label < 0)
        )
        if after_time is not None:
            stmt = stmt.where(TrainingSample.time > after_time)
        stmt = stmt.order_by(
            TrainingSample.time.asc(),
            TrainingSample.site_id.asc(),
            TrainingSample.device_id.asc(),
            TrainingSample.branch_id.asc(),
            TrainingSample.id.asc(),
        )
        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).mappings().all()
        return [dict(row) for row in rows]
    # @AI_GENERATED: end

    # @AI_GENERATED: 逐点标签物化（LabelMaterializer）需要按设备三元组 + 时间范围
    # 精确取采样时刻集合；query_training_samples 只过滤 site_id，不够用，故新增。
    def query_sample_times(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: Optional[datetime] = None,
        t_end: Optional[datetime] = None,
    ) -> List[datetime]:
        """按设备三元组 + 半开区间 [t_start, t_end) 查真实存在的采样时刻。

        标签只能落在 training_samples 中真实存在的采样点上，供
        LabelMaterializer 物化前确定「哪些点需要判定标签」。

        Requirements: 4.1（design.md 组件 1 物化算法第 2 步）
        """
        stmt = select(TrainingSample.time).where(
            TrainingSample.site_id == site_id,
            TrainingSample.device_id == device_id,
            TrainingSample.branch_id == branch_id,
        )
        if t_start is not None:
            stmt = stmt.where(TrainingSample.time >= t_start)
        if t_end is not None:
            stmt = stmt.where(TrainingSample.time < t_end)
        stmt = stmt.order_by(TrainingSample.time.asc())

        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).scalars().all()
        return list(rows)
    # @AI_GENERATED: end

    # ------------------------------------------------------------------
    # 高水位查询
    # ------------------------------------------------------------------

    def get_high_watermark(self) -> Optional[datetime]:
        """
        返回 training_samples 表中最新的 time 值（高水位）。
        用于增量数据拉取，避免全表扫描。

        Returns:
            最新 time 值；表为空时返回 None。

        Requirements: 5.2
        """
        from sqlalchemy import func

        with self._adapter.get_sync_session() as session:
            result = session.query(func.max(TrainingSample.time)).scalar()
        return result

    # ------------------------------------------------------------------
    # 模型版本
    # ------------------------------------------------------------------

    def save_model_version(self, version_data: dict) -> ModelVersion:
        """
        写入或更新模型版本元信息（upsert 语义，主键相同时覆盖）。

        Args:
            version_data: 与 ModelVersion 列名对应的字典，必须包含 "id" 字段。

        Returns:
            已持久化的 ModelVersion 实例。

        Requirements: 3.4
        """
        version = ModelVersion(**version_data)
        with self._adapter.get_sync_session() as session:
            merged = session.merge(version)
            session.flush()
            session.refresh(merged)
            session.expunge(merged)
        return merged

    def get_model_version(self, version_id: str) -> Optional[ModelVersion]:
        """
        按 ID 查询模型版本，不存在时返回 None。

        Args:
            version_id: 模型版本主键 ID。

        Returns:
            ModelVersion 实例，或 None。

        Requirements: 3.4
        """
        with self._adapter.get_sync_session() as session:
            obj = session.get(ModelVersion, version_id)
            if obj is not None:
                session.expunge(obj)
        return obj

    # @AI_GENERATED: 候选训练数据分页与批量 ID 读取
    def query_training_sample_page(
        self,
        page: int = 1,
        page_size: int = 100,
        label_status: Optional[str] = None,
        site_id: Optional[str] = None,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """分页查询 training_samples，返回普通 dict 列表。

        label_status:
          - 'unlabeled': label IS NULL OR label < 0
          - 'labeled': label IS NOT NULL AND label >= 0
          - None: 不过滤
        page_size 最大 500。
        """
        from sqlalchemy import func

        page_size = max(1, min(int(page_size), 500))
        page = max(1, int(page))
        offset = (page - 1) * page_size

        columns = (
            TrainingSample.id,
            TrainingSample.time,
            TrainingSample.site_id,
            TrainingSample.device_id,
            TrainingSample.branch_id,
            TrainingSample.value,
            TrainingSample.i_cal,
            TrainingSample.label,
        )
        stmt = select(*columns)
        count_stmt = select(func.count(TrainingSample.id))

        if label_status == "unlabeled":
            condition = or_(TrainingSample.label.is_(None), TrainingSample.label < 0)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        elif label_status == "labeled":
            condition = TrainingSample.label.isnot(None) & (TrainingSample.label >= 0)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        if site_id is not None:
            stmt = stmt.where(TrainingSample.site_id == site_id)
            count_stmt = count_stmt.where(TrainingSample.site_id == site_id)
        if time_start is not None:
            stmt = stmt.where(TrainingSample.time >= time_start)
            count_stmt = count_stmt.where(TrainingSample.time >= time_start)
        if time_end is not None:
            stmt = stmt.where(TrainingSample.time < time_end)
            count_stmt = count_stmt.where(TrainingSample.time < time_end)

        stmt = stmt.order_by(
            TrainingSample.time.desc(),
            TrainingSample.site_id.asc(),
            TrainingSample.device_id.asc(),
            TrainingSample.id.desc(),
        ).offset(offset).limit(page_size)

        with self._adapter.get_sync_session() as session:
            total = session.execute(count_stmt).scalar() or 0
            rows = session.execute(stmt).mappings().all()

        return {
            "page": page,
            "page_size": page_size,
            "total": int(total),
            "items": [dict(row) for row in rows],
        }

    def query_training_samples_by_ids(self, ids: List[int]) -> List[Dict[str, object]]:
        """批量按主键 ID 读取样本，返回普通 dict。"""
        if not ids:
            return []
        ids = ids[:500]  # 最大 500
        columns = (
            TrainingSample.id,
            TrainingSample.time,
            TrainingSample.site_id,
            TrainingSample.device_id,
            TrainingSample.branch_id,
            TrainingSample.value,
            TrainingSample.i_cal,
            TrainingSample.label,
        )
        stmt = select(*columns).where(TrainingSample.id.in_(ids)).order_by(TrainingSample.time.asc())
        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).mappings().all()
        return [dict(row) for row in rows]
    # @AI_GENERATED: end
