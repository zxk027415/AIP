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
    设备三元组，每个设备独立记录"已预测到哪一时刻"。

    ``pv_prediction`` 任务每次触发时，对每台设备取
    ``(last_predicted_time, cutoff]`` 时间窗口内未预测的测量点（点粒度），
    不管这些点跨几天——积压的点下次自然补上，不需要任何额外逻辑。
    成功写入 ``PredictionRecord`` 后才推进游标（失败不推进，下次重试）。

    初始值：``2021-11-24T23:50:00``（与历史全局游标对齐，避免重复预测）。
    """

    __tablename__ = "device_prediction_cursor"

    # @AI_GENERATED: pv-fault-dual-path-serving 任务 2.2 —— slot + modeling_path 物理分区主键
    # slot — 槽位/产品线分区键；光伏产品线默认 pv_fault。将其放入主键，确保同一设备在
    # 不同产品槽位的游标互不覆盖；迁移脚本 20260816_add_dual_path_runtime_schema.py
    # 会先回填历史行为 pv_fault，再原子重建同顺序复合主键。
    slot: Mapped[str] = mapped_column(
        String(64), primary_key=True, nullable=False, default="pv_fault", server_default="pv_fault",
    )
    # modeling_path — 建模/检测路径标识，取 legacy_day / seq_annotation；与 slot 一起
    # 构成分区前缀，同一设备三元组的两条路径各占一行、互不覆盖。
    modeling_path: Mapped[str] = mapped_column(
        String(32), primary_key=True, nullable=False, default="legacy_day", server_default="legacy_day",
    )
    site_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    branch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # @AI_GENERATED: end
    # @AI_GENERATED: 点粒度游标 — 从 last_predicted_business_date(DATE) 改为 last_predicted_time(DATETIME)
    # 支撑"截止到设定时间点之前的点都诊断，后到的点下次补"逻辑
    last_predicted_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    # @AI_GENERATED: end
    # @AI_GENERATED: 双路径生产接入（pv-fault-dual-path-serving Req5.1，design.md Data Models §1
    # device_prediction_cursor）
    # cursor_semantics — 游标语义标记：本行 last_predicted_time 到底代表什么，
    # 避免消费方跨路径误用同一列的两种不同含义：
    #   - event_time_watermark          — Legacy 专用：Event_Time 消费水位（(cursor, watermark] 增量）
    #   - continuous_completion_frontier — Seq 专用：由 SeqDeviceDayLedger 派生的连续完成前沿摘要，
    #                                      仅供展示/缩小查询范围，不是"是否已处理"的权威真相
    # Legacy 默认取 event_time_watermark；Seq 写入时必须显式改写为 continuous_completion_frontier。
    cursor_semantics: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="event_time_watermark",
        server_default="event_time_watermark",
    )
    # @AI_GENERATED: end
    last_predicted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    model_version_id: Mapped[str] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )
    # @AI_GENERATED: 双路径生产接入（pv-fault-dual-path-serving Req5.1）
    # cursor_semantics 取值仅限两种语义标记，越界值一律拒绝写入，避免消费方按未知语义误读游标。
    __table_args__ = (
        CheckConstraint(
            "cursor_semantics IN ('event_time_watermark', 'continuous_completion_frontier')",
            name="ck_device_prediction_cursor_semantics",
        ),
    )
    # @AI_GENERATED: end


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

    ``slot``（双路径生产接入 pv-fault-dual-path-serving Req5.1/5.2，design.md
    Data Models §1 prediction_records）：产品线/槽位分区键，与 ``modeling_path``
    共同构成路径隔离维度；光伏产品线固定写 ``pv_fault``，历史行回填同值，
    不影响其他产品线复用本表结构时的默认取值。
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
        # @AI_GENERATED: 双路径生产接入（pv-fault-dual-path-serving Req5.2）
        # 按 modeling_path 分区检索预测记录：消费方据该标记唯一确定记录所属路径。
        # 旧索引不含 slot，继续保留供兼容查询，不删除、不改名。
        Index(
            "ix_prediction_records_path_device",
            "modeling_path", "site_id", "device_id", "branch_id", "business_date",
        ),
        # @AI_GENERATED: end
        # @AI_GENERATED: 双路径生产接入（pv-fault-dual-path-serving Req5.2，design.md Data Models §1
        # prediction_records：新增非空 slot 并建立 (slot, modeling_path, site_id, device_id,
        # branch_id, business_date) 索引）
        # 与上面 ix_prediction_records_path_device 并存：新索引补 slot 维度，
        # 供按产品线/槽位隔离查询；不废弃旧索引。
        Index(
            "ix_prediction_records_slot_path_device",
            "slot", "modeling_path", "site_id", "device_id", "branch_id", "business_date",
        ),
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
    # @AI_GENERATED: 双路径生产接入（pv-fault-dual-path-serving Req5.2）
    # modeling_path — 记录所属检测路径的非空标记（legacy_day / seq_annotation）；
    # 历史行由迁移脚本回填 legacy_day 后置非空。
    modeling_path: Mapped[str] = mapped_column(
        String(32), nullable=False, default="legacy_day", server_default="legacy_day",
    )
    # @AI_GENERATED: end
    # @AI_GENERATED: 双路径生产接入（pv-fault-dual-path-serving Req5.2，design.md Data Models §1
    # prediction_records：新增非空 slot）
    # slot — 产品线/槽位分区键，见类 docstring；光伏产品线固定写 pv_fault，
    # 历史行由迁移脚本回填同值后置非空，默认值仅用于兼容尚未迁移的写入路径。
    slot: Mapped[str] = mapped_column(
        String(64), nullable=False, default="pv_fault", server_default="pv_fault",
    )
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

# @AI_GENERATED: 双路径生产接入（pv-fault-dual-path-serving 任务 2.1，design.md Data Models §1
# 数据库表：seq_device_day_ledger / path_activation_epochs / path_activation_device_scopes /
# path_activation_lane_claims）
# 新增 4 张表，支撑 Req13（序列设备日记账）与 Req14（路径启用周期）：
#   - SeqDeviceDayLedger          — Seq 路径"是否处理过某个设备日"的唯一权威真相
#   - PathActivationEpoch         — 每次跨路径启用/重新启用建立的生产责任周期
#   - PathActivationDeviceScope   — 该周期内每台设备的生产责任起始日与切换点
#   - PathActivationLaneClaim     — 该周期内生产车道与历史回放车道的排他日期认领
class SeqDeviceDayLedger(Base):
    """序列设备日记账 — Seq（``seq_annotation``）路径判定"某个设备日是否已处理过"的唯一权威真相。

    **存什么**：以设备日为最小单位的状态机记录（``waiting_data``/``ready``/``running``/
    ``succeeded``/``failed``/``revision_pending``）、稳定输入指纹（``input_fingerprint``）、
    最新成功批次（``batch_id``）与修订链指向（``supersedes_batch_id``）、尝试次数与最近失败原因。

    **为何独立**：Legacy 路径用单点 ``Device_Cursor``（Event_Time 水位）即可表达"处理到哪"，
    但 Seq 路径需要"较早日期未完整不能阻塞较晚日期"（design.md 关键设计结论、Property 8/29），
    单点游标无法表达这种逐日独立状态；因此专设本表作为 Seq 的处理权威，
    ``device_prediction_cursor`` 在 Seq 侧只写派生的 ``continuous_completion_frontier`` 摘要，
    不能反向用于判定"是否已处理过某个设备日"（Property 32）。

    **分区维度**：复合主键 ``(slot, modeling_path, site_id, device_id, branch_id, business_date)``
    六元组——``slot``/``modeling_path`` 承载产品线与路径隔离（``modeling_path`` 当前固定为
    ``seq_annotation``，但保留该维度以防未来扩展），后四项是设备日唯一键。

    **路径/介质**：数据库表，与其它光伏表同库同 schema（``aip_algo_platform``）。
    """

    __tablename__ = "seq_device_day_ledger"
    __table_args__ = (
        CheckConstraint(
            "status IN ('waiting_data', 'ready', 'running', 'succeeded', 'failed', 'revision_pending')",
            name="ck_seq_device_day_ledger_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_seq_device_day_ledger_attempt_count_non_negative",
        ),
        Index(
            "ix_seq_device_day_ledger_status_business_date",
            "slot", "modeling_path", "status", "business_date",
        ),
    )

    # 六元组设备日唯一键
    slot: Mapped[str] = mapped_column(String(64), primary_key=True, default="pv_fault", server_default="pv_fault")
    modeling_path: Mapped[str] = mapped_column(
        String(32), primary_key=True, nullable=False, default="seq_annotation", server_default="seq_annotation",
    )
    site_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    branch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_date: Mapped[date] = mapped_column(Date, primary_key=True)

    # status — 六态状态机当前状态，见类 docstring 与 design.md 状态机图
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="waiting_data", server_default="waiting_data")
    # input_fingerprint — 该设备日全部 (event_time, value) 规范化后的 SHA-256，用于幂等与修订判定
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=True)
    # batch_id — 最新成功不可变审核批次标识
    batch_id: Mapped[str] = mapped_column(String(128), nullable=True)
    # supersedes_batch_id — 修订批次所取代的前一批次标识；首次批次为空
    supersedes_batch_id: Mapped[str] = mapped_column(String(128), nullable=True)
    # attempt_count — 实际处理失败次数，非负；成功/幂等跳过不增加
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # last_error — 最近一次可诊断失败原因
    last_error: Mapped[str] = mapped_column(String, nullable=True)
    # activation_epoch_id — 本记录所属的路径启用周期标识，关联 PathActivationEpoch
    activation_epoch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # processed_at — 最近一次状态推进的 UTC 时刻
    processed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )


class PathActivationEpoch(Base):
    """路径启用周期 — 每次跨路径启用或重新启用建立的生产责任边界事实。

    **存什么**：``activation_mode``（``cutover_only``/``recent_window``/``full_backfill``）、
    ``backfill_days``（recent_window 回看天数）、激活时刻、备注、引用的 Shadow ``comparison_id``
    与操作人；本表是周期级字段，逐设备边界在 ``PathActivationDeviceScope`` 另表存放。

    **为何独立**：切换路径不等于全量回放（design.md 关键设计结论）；必须有一个显式的
    "从这一刻起、这条路径对哪些设备负责"的边界记录，否则无法区分"本周期应处理但未处理"
    与"另一条路径值班期间、不属于本周期责任"的日期（Property 34）。

    **分区维度**：主键 ``activation_epoch_id``；周期归属通过 ``slot + modeling_path`` 字段表达，
    一个 Epoch 对应多台设备（在 ``PathActivationDeviceScope`` 展开）。

    **路径/介质**：数据库表；若部署改用文件介质，目录由部署配置决定，只持久化相对路径。
    """

    __tablename__ = "path_activation_epochs"
    __table_args__ = (
        CheckConstraint(
            "activation_mode IN ('cutover_only', 'recent_window', 'full_backfill')",
            name="ck_path_activation_epochs_mode",
        ),
        Index("ix_path_activation_epochs_slot_path", "slot", "modeling_path", "activated_at"),
    )

    activation_epoch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False, default="pv_fault", server_default="pv_fault")
    modeling_path: Mapped[str] = mapped_column(String(32), nullable=False)
    # activation_mode — 启用模式，见类 docstring 三种取值
    activation_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    # backfill_days — recent_window 模式下的回看天数；其他模式为空
    backfill_days: Mapped[int] = mapped_column(Integer, nullable=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    note: Mapped[str] = mapped_column(String(500), nullable=True)
    # comparison_id — 引用的 Cross-Path Shadow 报告标识，供跨路径切换审计追溯
    comparison_id: Mapped[str] = mapped_column(String(64), nullable=True)
    operator: Mapped[str] = mapped_column(String(128), nullable=True)


class PathActivationDeviceScope(Base):
    """路径启用周期设备范围 — 某个 Epoch 内单台设备的生产责任起始日与切换点。

    **存什么**：``activation_watermark``（建立本周期时该设备的数据水位）、
    ``effective_from_date``（本周期对该设备承担生产责任的起始日，无数据设备可空、
    首次到达后原子补齐）、``production_cutover_date``（仅 full_backfill 下生产在线车道
    开始接管的日期，其余模式与 effective_from_date 含义重合）。

    **为何独立**：生产责任边界必须按设备逐台判定，不能只在 Epoch 层存一个全局日期——
    不同设备到达节奏不同，"缺游标时的初始边界"必须精确到设备（Property 13、34）。

    **分区维度**：复合主键 ``(activation_epoch_id, site_id, device_id, branch_id)``，
    与所属 ``PathActivationEpoch`` 同事务创建。

    **路径/介质**：数据库表，与 ``PathActivationEpoch`` 同库同事务。
    """

    __tablename__ = "path_activation_device_scopes"

    activation_epoch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    branch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # activation_watermark — 建立本周期时该设备的数据水位（DataWatermark），用于推导启用模式公式
    activation_watermark: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    # effective_from_date — 本周期对该设备承担生产责任的起始日；无数据设备暂空，首次到达后原子补齐
    effective_from_date: Mapped[date] = mapped_column(Date, nullable=True)
    # production_cutover_date — full_backfill 下生产在线车道开始接管的日期（该日期之前交给 BackfillRunner）
    production_cutover_date: Mapped[date] = mapped_column(Date, nullable=True)


class PathActivationLaneClaim(Base):
    """路径启用周期执行车道认领 — 排他标记某个日期区间由生产车道还是历史回放车道处理。

    **存什么**：``lane``（``production``/``historical_backfill``）在
    ``[range_start, range_end)`` 半开区间上的认领状态（``claimed``/``running``/``succeeded``/
    ``failed``/``cancelled``）与关联的 ``backfill_task_id``；``range_end`` 为空表示生产车道
    的无穷上界。

    **为何独立**：full_backfill 场景下同一台设备同时存在"历史回放范围"与"生产在线范围"，
    若不显式排他认领，容易出现两个执行池重复处理同一日期或留出空档（Property 42、
    design.md §5 full_backfill 车道排他）；生产候选查询依赖本表排除
    ``historical_backfill`` 认领范围。

    **分区维度**：复合主键 ``(activation_epoch_id, site_id, device_id, branch_id, lane,
    range_start)``；historical/production 两段范围要求无交集、无空档。

    **路径/介质**：数据库表，与 ``PathActivationEpoch``/``PathActivationDeviceScope`` 同库同事务。
    """

    __tablename__ = "path_activation_lane_claims"
    __table_args__ = (
        CheckConstraint(
            "lane IN ('production', 'historical_backfill')",
            name="ck_path_activation_lane_claims_lane",
        ),
        CheckConstraint(
            "claim_status IN ('claimed', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_path_activation_lane_claims_status",
        ),
        Index(
            "ix_path_activation_lane_claims_lane_status",
            "activation_epoch_id", "lane", "claim_status",
        ),
    )

    activation_epoch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    branch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # lane — 执行车道：production（生产在线检测）或 historical_backfill（历史回放，见类 docstring）
    lane: Mapped[str] = mapped_column(String(32), primary_key=True)
    # range_start — 认领半开区间起点（含）
    range_start: Mapped[date] = mapped_column(Date, primary_key=True)
    # range_end — 认领半开区间终点（不含）；生产车道上界可空表示 +infinity
    range_end: Mapped[date] = mapped_column(Date, nullable=True)
    # claim_status — 认领状态，见类 docstring 五态取值
    claim_status: Mapped[str] = mapped_column(String(32), nullable=False, default="claimed", server_default="claimed")
    # backfill_task_id — 关联的历史回放任务标识；生产车道通常为空
    backfill_task_id: Mapped[str] = mapped_column(String(64), nullable=True)
# @AI_GENERATED: end
