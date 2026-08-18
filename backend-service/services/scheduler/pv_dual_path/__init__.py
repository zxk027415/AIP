# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
services/scheduler/pv_dual_path — 光伏故障诊断双路径生产接入包

本包承载 spec `pv-fault-dual-path-serving` 的双路径调度相关组件。
当前已落地：
  - config.DualPathConfig — 完整性闸门相关的可配阈值（completeness_ratio /
    expected_point_count），支持配置文件 + 环境变量覆盖 + 越界回退默认。
  - watermark.DataWatermarkService — 设备数据到达水位（两条策略共用的时间进度基准）。
  - completeness_gate.CompletenessGate / GateDecision — 显式完整性闸门（只读判定 +
    seq 严格 / legacy 宽松放行）。
  - strategy_base.DetectionStrategy / CycleContext / CycleResult — 检测策略抽象与运行契约
    （两条路径的统一接口 + 可断言的输入/输出）。
  - scheduler.DualPathScheduler — 双路径分派器：读生产路径指针 → 校验 → 按 modeling_path
    分派到对应检测策略 → 落账运行状态；不含检测逻辑。
  - path_isolation.PathIsolationRegistry — 按 (slot, modeling_path) 分区访问游标 / 预测记录 /
    审核批次的约定层：缺分区回退初始水位、分区写隔离、写失败不产生部分写、批次原子落盘、
    审计布尔严格。PartitionWriteError 为其分区写失败异常。
  - legacy_day_strategy.LegacyDayStrategy — 传统按天检测策略（legacy_day）：事件时间游标
    `(cursor, watermark]`、按设备独立取点、自然日分组不跨日拼接、按参与检测点最大 Event_Time
    分设备推进游标（>= 旧值）、无效 Event_Time 点拒收、不以 CompletenessGate 为前置。

后续任务将陆续加入 SeqDailyStrategy / ShadowCompareRunner 等组件。
"""

from .completeness_gate import CompletenessGate, GateDecision
from .config import DualPathConfig, load_dual_path_config
from .legacy_day_strategy import LegacyDayStrategy
from .path_isolation import PartitionWriteError, PathIsolationRegistry
from .scheduler import DualPathScheduler
from .seq_daily_strategy import SeqDailyStrategy
from .strategy_base import CycleContext, CycleResult, DetectionStrategy
from .watermark import DataWatermarkService

__all__ = [
    "DualPathConfig",
    "load_dual_path_config",
    "DataWatermarkService",
    "CompletenessGate",
    "GateDecision",
    "DetectionStrategy",
    "CycleContext",
    "CycleResult",
    "DualPathScheduler",
    "LegacyDayStrategy",
    "PathIsolationRegistry",
    "PartitionWriteError",
    "SeqDailyStrategy",
]
# @AI_GENERATED: end
