# @AI_GENERATED: Kiro v1.0
"""
跨场景迁移 Skill — 分析源/目标场景兼容性并生成迁移算法模板
"""
import time
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from models.workflow_agent_models import (
    CrossScenarioRequest,
    MigrationAlgorithmReport,
    MigrationReport,
    CompatibilityCategory,
    SkillContext,
)
from services.workflow_agent.skills.base_skill import BaseSkill
from services.workflow_agent.knowledge.algorithm_library import (
    get_algorithm_library,
)
from services.workflow_agent.knowledge.domain_constraints import (
    get_domain_constraints_library,
)

logger = logging.getLogger(__name__)

# 算法分类标签：用于判断跨场景兼容性
# 通用算法（所有场景兼容）
UNIVERSAL_ALGORITHMS = {
    "load_csv", "load_timeseries_db", "load_api", "load_mqtt",
    "load_opcua", "load_modbus", "load_database",
    "handle_missing", "detect_outliers", "resample_timeseries",
    "normalize_features", "extract_time_features",
    "create_lag_features", "extract_statistical_features",
    "rmse_metric", "mape_metric", "mae_metric",
    "f1_score", "r2_score", "accuracy_score", "confusion_matrix",
}

# 时序预测类算法（预测场景间可迁移）
TIMESERIES_ALGORITHMS = {
    "arima_forecast", "lstm_forecast", "xgboost_forecast",
}

# 分类类算法（分类场景间可迁移）
CLASSIFICATION_ALGORITHMS = {
    "svm_classifier", "random_forest_classifier",
    "isolation_forest_anomaly",
}


class CrossScenarioSkill(BaseSkill):
    """跨场景迁移 Skill"""

    skill_name = "cross-scenario"
    required_role = "engineer"

    async def validate_input(self, request: BaseModel) -> None:
        if isinstance(request, CrossScenarioRequest):
            if not request.source_scenario_id.strip():
                raise ValueError("source_scenario_id 不能为空")
            if not request.target_scenario_id.strip():
                raise ValueError("target_scenario_id 不能为空")
            if request.source_scenario_id == request.target_scenario_id:
                raise ValueError("源场景和目标场景不能相同")

    async def execute(
        self, request: BaseModel, context: SkillContext
    ) -> MigrationReport:
        if not isinstance(request, CrossScenarioRequest):
            raise ValueError("请求类型错误，期望 CrossScenarioRequest")

        start = time.time()
        base_lib = get_algorithm_library()
        constraints_lib = get_domain_constraints_library()

        # 提取源算法模板中的所有算法节点ID
        source_wf = request.source_workflow
        nodes = source_wf.get("nodes", [])
        algo_ids = []
        for node in nodes:
            data = node.get("data", {})
            func_id = data.get("functionId") or data.get("function_id") or ""
            if func_id:
                algo_ids.append(func_id)

        if not algo_ids:
            return MigrationReport(
                source_scenario_id=request.source_scenario_id,
                target_scenario_id=request.target_scenario_id,
                confidence_score=0,
                warnings=["源算法模板中未找到算法节点"],
            )

        # 分类每个算法的兼容性
        reports: List[MigrationAlgorithmReport] = []
        compatible_count = 0
        adaptable_count = 0
        incompatible_count = 0

        for aid in algo_ids:
            fn = base_lib.get_by_id(aid)
            name = fn["name"] if fn else aid

            if aid in UNIVERSAL_ALGORITHMS:
                reports.append(MigrationAlgorithmReport(
                    algorithm_id=aid,
                    algorithm_name=name,
                    category=CompatibilityCategory.COMPATIBLE,
                    reason="通用算法，所有场景兼容",
                ))
                compatible_count += 1
            elif aid in TIMESERIES_ALGORITHMS or aid in CLASSIFICATION_ALGORITHMS:
                reports.append(MigrationAlgorithmReport(
                    algorithm_id=aid,
                    algorithm_name=name,
                    category=CompatibilityCategory.ADAPTABLE,
                    reason="算法可复用，需调整参数适配目标场景",
                ))
                adaptable_count += 1
            else:
                reports.append(MigrationAlgorithmReport(
                    algorithm_id=aid,
                    algorithm_name=name,
                    category=CompatibilityCategory.INCOMPATIBLE,
                    reason="场景专用算法，需替换",
                    replacement_id=None,
                ))
                incompatible_count += 1

        # 计算迁移置信度
        total = len(algo_ids)
        confidence = int(
            (compatible_count * 100 + adaptable_count * 60) / total
        ) if total > 0 else 0
        confidence = min(confidence, 100)

        # 高亮变更
        changes = [
            r.algorithm_id for r in reports
            if r.category != CompatibilityCategory.COMPATIBLE
        ]

        warnings: List[str] = []
        if confidence < 50:
            warnings.append(
                f"迁移置信度仅 {confidence}%，建议从目标场景重新构建算法模板"
            )

        # 生成迁移后的算法模板（简单复制，标记变更）
        migrated = dict(source_wf)

        return MigrationReport(
            source_scenario_id=request.source_scenario_id,
            target_scenario_id=request.target_scenario_id,
            confidence_score=confidence,
            algorithm_reports=reports,
            migrated_workflow=migrated,
            changes_highlighted=changes,
            warnings=warnings,
        )
# @AI_GENERATED: end
