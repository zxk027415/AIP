# -*- coding: utf-8 -*-
"""
services/db/models/pv_fault.py — 光伏故障诊断 ORM 模型

定义 aip_algo_platform 库下的 4 张光伏故障诊断相关表。
原设计使用独立 schema `pv_fault_diag`；现统一迁入 aip_algo_platform，
去掉 schema= 参数，降低部署权限要求。

Requirements: 3.1, 3.2, 3.4, 3.5
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BIGINT,
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# schema 统一到 aip_algo_platform，不再跨库
_SCHEMA = None


class TrainingSample(Base):
    """标注训练样本 — 存储光伏支路的时序测量值及人工标注的故障标签。

    ``data_source`` 区分数据来源（需求：按日滚动预测生产表结构设计）：
      - ``mock``       — 模拟喂数据（``PvFaultMockFeeder`` 及历史迁移脚本写入）
      - ``production`` — 真实生产采集管道写入（尚未接入，预留）
    这是逻辑隔离（同一张表、同一套读写代码），不是物理隔离：训练/预测复用同一份
    测量事实源，只按 ``data_source`` 区分"这一行数据的来源"，与"是否有标签"
    （由 ``point_labels`` 判定）是两个独立维度。历史遗留行统一回填为 ``mock``
    （见迁移脚本），确保 ``production`` 严格只包含未来真实接入的数据。
    """

    __tablename__ = "training_samples"
    __table_args__ = (
        UniqueConstraint(
            "time", "site_id", "device_id", "branch_id",
            name="uq_training_samples_composite_key",
        ),
        Index("ix_training_samples_site_time_label", "site_id", "time", "label"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    site_id: Mapped[str] = mapped_column(String(128), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    branch_id: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=True)
    i_cal: Mapped[float] = mapped_column(Float, nullable=True)
    label: Mapped[int] = mapped_column(Integer, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)
    # @AI_GENERATED: 按日滚动预测生产表结构设计 — 数据来源标记，见类 docstring
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="mock", server_default="mock",
    )
    # @AI_GENERATED: end


# @AI_GENERATED
class PointLabel(Base):
    """逐点标签 — 光伏故障逐点标签重构（point-label-segment-redesign）的标签唯一事实来源。

    每行对应一个采样点的生效标签，由 LabelMaterializer 从 LabelOp 物化产生。
    不含任何测量数值列（测量值仍在 TrainingSample）。

    对应设计文档 `.kiro/specs/pv-fault-label-segment-redesign/design.md` 数据模型第一节。
    """

    __tablename__ = "point_labels"
    __table_args__ = (
        Index("ix_point_labels_op_id", "op_id"),
    )

    site_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    branch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    time: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    label_id: Mapped[int] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    op_id: Mapped[str] = mapped_column(String(16), nullable=False)
    label_space_version: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class LabelOp(Base):
    """标注操作日志 — 记录每一次标注动作（人工框选、审核裁决、聚类确认、批量导入、伪标签）。

    是撤销与审计的唯一单元；撤销只迁移 status，不物理删除。
    对应设计文档数据模型第二节。
    """

    __tablename__ = "label_ops"
    __table_args__ = (
        Index("ix_label_ops_device_range", "site_id", "device_id", "branch_id", "t_start", "t_end"),
        Index("ix_label_ops_source_status", "source", "status"),
    )

    op_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(128), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    branch_id: Mapped[str] = mapped_column(String(128), nullable=False)
    t_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    t_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    label_id: Mapped[int] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    reviewer: Mapped[str] = mapped_column(String(128), nullable=True)
    source_ref: Mapped[str] = mapped_column(String(256), nullable=True)
    rest_of_day_policy: Mapped[str] = mapped_column(String(16), nullable=True)
    parent_op_id: Mapped[str] = mapped_column(String(16), nullable=True)
    label_space_version: Mapped[str] = mapped_column(String(64), nullable=False)
    migration_batch_id: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
# @AI_GENERATED: end


# @AI_GENERATED: 按日滚动预测生产表结构设计（.kiro/specs/pv-fault-timeseries-diagnosis 关联讨论）
# 新增 3 张表：设备-天完整性判定、按设备预测游标、mock 分批错峰释放计划。
class MeasurementIngestionDaily(Base):
    """设备-天数据完整性判定表 — 支撑"按日滚动预测"的核心前置条件。

    每行代表一个 (site_id, device_id, branch_id, business_date) 的到达进度。
    每次原始测量写入 ``training_samples`` 后，同步更新对应行的 ``point_count``；
    当 ``point_count`` 达到 ``expected_point_count`` 的完整性阈值比例时，
    置 ``is_complete=True``，记录 ``completed_at``。

    预测任务（``pv_prediction``）只应处理 ``is_complete=True`` 的设备-天，
    避免对当天未到齐的数据切样本、算出偏差的日内统计特征。

    与 mock/生产的关系：本表的写入方与 ``training_samples`` 完全对称——
    不管是 mock feeder 还是未来真实采集管道写入测量值，都走同一段
    完整性追踪逻辑（``IngestionTrackerRepository``），代码不区分数据来源。
    """

    __tablename__ = "measurement_ingestion_daily"
    __table_args__ = (
        Index("ix_ingestion_daily_complete", "site_id", "is_complete", "business_date"),
    )

    site_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    branch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_date: Mapped[date] = mapped_column(Date, primary_key=True)
    point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=288)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )


class DevicePredictionCursor(Base):
    """按设备维度的预测游标 — 替代全局单点游标（``prediction_cursor.json``）。

    真实生产环境下不同设备的数据到达节奏互不同步，用一个全局游标会导致
    "先到齐的设备要等最慢的设备"或"漏预测晚到设备"。本表把游标粒度下沉到
    设备三元组，每个设备独立记录"已预测到哪一天"。

    ``pv_prediction`` 任务对每个 ``is_complete=True`` 且
    ``business_date > last_predicted_business_date`` 的设备-天执行预测，
    成功写入 ``PredictionRecord`` 后才推进本表（失败不推进，下次重试）。
    """

    __tablename__ = "device_prediction_cursor"

    site_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    branch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_predicted_business_date: Mapped[date] = mapped_column(Date, nullable=True)
    last_predicted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    model_version_id: Mapped[str] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )


class PvMockReleaseSchedule(Base):
    """Mock 喂数据错峰释放计划 — mock 专用，生产环境不需要本表。

    每个业务日开始时一次性生成：把当天设备清单分配到若干释放批次
    （``planned_batch_index``），并按约定比例随机标记部分设备延迟
    （``delay_ticks`` > 0）或当天缺失（``is_dropped=True``），用来在测试环境
    复现真实场景下"设备异步到达、偶发延迟/缺失"的特性。

    真实数据不需要"计划"到达（它自己就会到），所以本表只被
    ``PvFaultMockFeeder`` 读写，不出现在预测/训练任何读取路径中。
    """

    __tablename__ = "pv_mock_release_schedule"
    __table_args__ = (
        Index("ix_mock_release_date_batch", "business_date", "planned_batch_index"),
    )

    business_date: Mapped[date] = mapped_column(Date, primary_key=True)
    site_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    branch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    planned_batch_index: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_ticks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_dropped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    released_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
# @AI_GENERATED: end


class ModelVersion(Base):
    """模型版本元信息 — 记录每个训练产物的版本标签、样本量、标签空间版本和存储路径。"""

    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_tag: Mapped[str] = mapped_column(String(128), nullable=True)
    training_sample_count: Mapped[int] = mapped_column(Integer, nullable=True)
    label_space_version: Mapped[str] = mapped_column(String(64), nullable=True)
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)


class PredictionRecord(Base):
    """预测记录 — 保存每次故障诊断推理的输入特征、预测标签、置信度和关联模型版本。

    ``business_date``/``sample_id``（按日滚动预测生产表结构设计新增）：
      - ``business_date`` — 这次预测对应哪一天，支撑按业务日审计和去重查询
      - ``sample_id``      — 对应 ``SampleBuilder``/``InferenceSampleGenerator``
                              生成的样本键（如 ``2026-08-04#day``），
                              把预测结果与训练快照的样本粒度对齐，便于审核溯源
    两列均可为空，兼容历史遗留预测记录（未回填）。
    """

    __tablename__ = "prediction_records"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_prediction_records_confidence",
        ),
        # @AI_GENERATED: 按日滚动预测生产表结构设计
        Index("ix_prediction_records_device_business_date", "site_id", "device_id", "branch_id", "business_date"),
        # @AI_GENERATED: end
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    model_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("model_versions.id"),
        nullable=True,
    )
    site_id: Mapped[str] = mapped_column(String(128), nullable=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=True)
    branch_id: Mapped[str] = mapped_column(String(128), nullable=True)
    input_feature_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    predicted_label: Mapped[int] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)
    # @AI_GENERATED: 按日滚动预测生产表结构设计 — 见类 docstring
    business_date: Mapped[date] = mapped_column(Date, nullable=True)
    sample_id: Mapped[str] = mapped_column(String(128), nullable=True)
    # @AI_GENERATED: end


class DiagnosisResult(Base):
    """诊断结果 — 关联预测记录，记录具体的故障类型名称和严重程度。"""

    __tablename__ = "diagnosis_results"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    prediction_record_id: Mapped[int] = mapped_column(
        BIGINT,
        ForeignKey("prediction_records.id"),
        nullable=True,
    )
    fault_type_name: Mapped[str] = mapped_column(String(128), nullable=True)
    severity: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)
