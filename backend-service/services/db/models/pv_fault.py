# -*- coding: utf-8 -*-
"""
services/db/models/pv_fault.py — 光伏故障诊断 ORM 模型

定义 aip_algo_platform 库下的 4 张光伏故障诊断相关表。
原设计使用独立 schema `pv_fault_diag`；现统一迁入 aip_algo_platform，
去掉 schema= 参数，降低部署权限要求。

Requirements: 3.1, 3.2, 3.4, 3.5
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BIGINT,
    JSON,
    CheckConstraint,
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
    """标注训练样本 — 存储光伏支路的时序测量值及人工标注的故障标签。"""

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
    """预测记录 — 保存每次故障诊断推理的输入特征、预测标签、置信度和关联模型版本。"""

    __tablename__ = "prediction_records"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_prediction_records_confidence",
        ),
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
