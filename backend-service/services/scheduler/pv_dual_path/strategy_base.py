# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/scheduler/pv_dual_path/strategy_base.py — 检测策略抽象与运行契约

本模块定义双路径调度的**统一策略接口**与其输入/输出契约，是 DualPathScheduler（双路径
分派器）与两条具体策略（LegacyDayStrategy / SeqDailyStrategy）之间的边界：

  - CycleContext（本轮检测上下文，frozen）—— 分派器构造后注入策略的只读输入。
  - CycleResult（本轮检测结果，frozen）—— 策略回传给分派器的可断言输出，落 prediction_last_run
    供前端/审计（Req1.5），其条数字段可用于守恒断言（Req1.6 / Req1.7）。
  - DetectionStrategy（检测策略协议）—— 两条路径共同实现的最小接口，run_cycle 输入
    CycleContext、输出 CycleResult。

对应设计：.kiro/specs/pv-fault-dual-path-serving/design.md §1 DetectionStrategy 抽象 +
DualPathScheduler。
需求：1.5（分派结果可审计/前端展示）、1.6 / 1.7（本轮检测/顺延条数可断言、非负确定）。

说明：CycleContext.watermark 的类型是 DataWatermarkService，但为避免与 watermark 模块
形成循环导入，这里使用 TYPE_CHECKING 前置引用（运行期以字符串前置注解表达）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    # 仅供类型检查/IDE，运行期不导入，避免 watermark <-> strategy_base 循环导入。
    from services.scheduler.pv_dual_path.watermark import DataWatermarkService


@dataclass(frozen=True)
class CycleContext:
    """一轮检测的只读上下文，由 DualPathScheduler 构造后注入策略（不可变）。

    字段（英文名 — 中文含义）：
      - slot          — 槽位（默认 "pv_fault"），与 modeling_path 组合成分区键。
      - modeling_path — 本轮生效路径：legacy_day（传统按天） / seq_annotation（全天序列）。
      - champion_model_ref — 本轮路径当前 Champion 工件引用；调度器不得猜测默认模型。
      - activation_epoch_id — 本轮适用的 PathActivationEpoch 标识；缺失则跳过本轮。
      - model_ref     — 兼容旧字段，值与 champion_model_ref 相同。
      - watermark     — 共用的数据到达水位服务（时间进度基准，两条路径都不看墙钟）。
      - started_at    — 本轮启动墙钟时刻，仅用于审计时间戳，不参与任何窗口判定。
    """

    slot: str
    modeling_path: str
    watermark: "DataWatermarkService"
    started_at: datetime
    champion_model_ref: str = ""
    activation_epoch_id: str = ""
    model_ref: str = ""

    def __post_init__(self) -> None:
        champion = str(self.champion_model_ref or self.model_ref or "").strip()
        object.__setattr__(self, "champion_model_ref", champion)
        object.__setattr__(self, "model_ref", champion)


@dataclass(frozen=True)
class CycleResult:
    """一轮检测的结果契约，策略回传给分派器（不可变、可断言）。

    字段（英文名 — 中文含义）：
      - modeling_path    — 实际分派到的路径取值（审计/前端展示，Req1.5）。
      - strategy_name    — 目标策略类名（如 "LegacyDayStrategy"），便于审计/排错。
      - window_start     — 本轮数据时间下界（Event_Time ISO 字符串），无数据为 None。
      - window_end       — 本轮数据时间上界（由 Data_Watermark 界定，Event_Time ISO），无数据为 None。
      - points_detected  — 本轮实际参与检测的数据条数（非负、确定，Req1.6）。
      - points_deferred  — 顺延到下一轮的数据条数（非负、确定，Req1.7）。
      - devices_processed — 本轮处理的设备三元组数。
      - batch_ids        — 生成的审核批次 ID 列表（可多批）。
      - review_ids       — 生成的审核会话 ID 列表。
      - status           — 本轮状态：success（成功） / skipped（跳过） / failed（失败）。
      - skipped_reason   — 跳过/失败的可诊断原因（如 invalid_modeling_path）；正常为 None。
    """

    modeling_path: str
    strategy_name: str
    window_start: Optional[str]
    window_end: Optional[str]
    points_detected: int
    points_deferred: int
    devices_processed: int
    batch_ids: List[str]
    review_ids: List[str]
    status: str
    skipped_reason: Optional[str] = None
    backlog_remaining: int = 0
    batched_backlog: bool = False
    invalid_max_device_days_per_cycle: bool = False


@runtime_checkable
class DetectionStrategy(Protocol):
    """检测策略协议 —— 两条路径（LegacyDayStrategy / SeqDailyStrategy）共同实现的最小接口。

    属性：
      - name — 策略名称（用于审计/日志/CycleResult.strategy_name）。

    方法：
      - run_cycle(ctx) — 输入本轮 CycleContext，执行一轮检测，输出可断言的 CycleResult。
    """

    name: str

    def run_cycle(self, ctx: CycleContext) -> CycleResult:
        """执行一轮检测：读分区游标 → 取窗口数据 → 检测 → 写记录/批次 → 推进游标，
        返回本轮 CycleResult。"""
        ...
# @AI_GENERATED: end
