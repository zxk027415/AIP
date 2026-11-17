# @AI_GENERATED
"""
accuracy_operations — 精度运营编排层包入口

导出核心组件：
  - AccuracyMonitor        : 精度监控组件，负责检测 production/shadow 形态退化并产出 AccuracyAlert
  - RCAOrchestrator        : 根因分析编排器，调度 operation_skill 子进程并产出 RCAReport
  - RecoveryArbitrator     : 恢复仲裁器，基于 RCA 结论与影子池状态决策恢复通道
  - AccuracyOperationsStore: 持久化 store，负责 alerts/rca/recovery 的 JSON 读写

注意：TrainingStrategyAdjuster（通道B）已从本轮实现范围移除。

子模块在后续任务中逐步创建；使用 try/except 延迟导入，保证包在
子模块尚未完成时也可正常 import（增量交付友好）。

References: Requirement 8.1
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# AccuracyMonitor — 精度监控组件（由 monitor.py 提供，任务 3.1 创建）
# ---------------------------------------------------------------------------
try:
    from services.accuracy_operations.monitor import AccuracyMonitor
except ImportError:
    AccuracyMonitor = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# RCAOrchestrator — 根因分析编排器（由 rca_orchestrator.py 提供，任务 4.2 创建）
# ---------------------------------------------------------------------------
try:
    from services.accuracy_operations.rca_orchestrator import RCAOrchestrator
except ImportError:
    RCAOrchestrator = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# RecoveryArbitrator — 恢复仲裁器（由 arbitrator.py 提供，任务 6.1 创建）
# ---------------------------------------------------------------------------
try:
    from services.accuracy_operations.arbitrator import RecoveryArbitrator
except ImportError:
    RecoveryArbitrator = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# AccuracyOperationsStore — 持久化 store（由 store.py 提供，任务 1.2 创建）
# ---------------------------------------------------------------------------
try:
    from services.accuracy_operations.store import AccuracyOperationsStore
except ImportError:
    AccuracyOperationsStore = None  # type: ignore[assignment,misc]

__all__ = [
    "AccuracyMonitor",
    "RCAOrchestrator",
    "RecoveryArbitrator",
    "AccuracyOperationsStore",
]
# @AI_GENERATED: end
