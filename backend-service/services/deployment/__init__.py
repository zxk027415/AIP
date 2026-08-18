# @AI_GENERATED
"""
services/deployment — 算法部署服务层

职责：
  - 管理部署槽位（slot）：每个 slot 维护一个 Production_Model + 多个 Shadow_Model
  - 记录模型切换事件（append-only 审计日志）
  - 复用系统已有的 slot（槽位）分区概念，与 version_registry、candidate_pool、
    prediction_result、accuracy_metric 等表的 slot 列对齐

子模块：
  - models           — DeploymentSlot / ModelVersion / SwitchEvent Pydantic 数据模型
  - store            — JSON 文件读写（slots.json / switch_log.json）
  - rolling_window   — 滚动训练窗口计算器（Gap-One-Day，T-1 训练，T+1 预测）
  - switch_decision  — 切换决策引擎（资格检测 / 执行切换 / 回滚）
"""

from services.deployment.models import (
    DeploymentSlot,
    ModelVersion,
    SwitchEvent,
)
from services.deployment.rolling_window import (
    TrainingWindow,
    compute_training_window,
)
from services.deployment.store import (
    DeploymentSlotStore,
    SwitchEventLog,
    sort_shadow_models_by_accuracy,
)
from services.deployment.pv_read_adapter import (
    DeploymentSlotView,
    PVDeploymentReadAdapter,
    PvFaultRegistryReadOnlyError,
)
from services.deployment.switch_decision import (
    SwitchDecisionEngine,
    SwitchDecisionError,
    SwitchEligibility,
)

__all__ = [
    "DeploymentSlot",
    "ModelVersion",
    "SwitchEvent",
    "DeploymentSlotStore",
    "SwitchEventLog",
    "sort_shadow_models_by_accuracy",
    "TrainingWindow",
    "compute_training_window",
    "SwitchDecisionEngine",
    "SwitchDecisionError",
    "SwitchEligibility",
    "PVDeploymentReadAdapter",
    "DeploymentSlotView",
    "PvFaultRegistryReadOnlyError",
]
# @AI_GENERATED: end
