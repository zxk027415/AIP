# @AI_GENERATED: Kiro v1.0
"""
算法模板合理性验证 Skill — 结构验证（复用 WorkflowValidator）+ 业务验证
"""
import time
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from models.workflow_agent_models import (
    FindingCategory,
    FindingSeverity,
    SkillContext,
    ValidationFinding,
    WorkflowValidateRequest,
    WorkflowValidateResponse,
)
from models.workflow_models import WorkflowDefinition
from services.workflow_validator import WorkflowValidator
from services.workflow_agent.skills.base_skill import BaseSkill

logger = logging.getLogger(__name__)


def _structural_validate(workflow_dict: Dict[str, Any]) -> tuple:
    """调用已有 WorkflowValidator 进行结构验证"""
    try:
        wf = WorkflowDefinition(**workflow_dict)
        validator = WorkflowValidator(wf)
        result = validator.validate()
        errors = []
        for e in result.errors:
            errors.append(e.model_dump() if hasattr(e, "model_dump") else {"message": str(e)})
        for w in result.warnings:
            errors.append(w.model_dump() if hasattr(w, "model_dump") else {"message": str(w)})
        return result.valid, errors
    except Exception as e:
        logger.error(f"结构验证异常: {e}")
        return False, [{"message": f"结构验证异常: {str(e)}"}]


def _business_validate(
    workflow_dict: Dict[str, Any], scenario_id: Optional[str]
) -> List[ValidationFinding]:
    """业务层验证"""
    findings: List[ValidationFinding] = []
    nodes = workflow_dict.get("nodes", [])
    edges = workflow_dict.get("edges", [])

    if not nodes:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            category=FindingCategory.STRUCTURAL,
            message="算法模板不包含任何节点",
            fix_suggestion="请添加至少一个算法节点",
        ))
        return findings

    # 检查孤立节点（无入边也无出边）
    node_ids = {n["id"] for n in nodes}
    connected = set()
    for e in edges:
        connected.add(e.get("source"))
        connected.add(e.get("target"))
    isolated = node_ids - connected
    if len(nodes) > 1:
        for nid in isolated:
            findings.append(ValidationFinding(
                severity=FindingSeverity.WARNING,
                category=FindingCategory.DATA_FLOW,
                message=f"节点 {nid} 未与其他节点连接",
                node_id=nid,
                fix_suggestion="将该节点连接到数据流中，或移除该节点",
            ))

    # 检查终端节点（无出边）
    sources = {e.get("source") for e in edges}
    terminal_nodes = node_ids - sources
    if not terminal_nodes and nodes:
        findings.append(ValidationFinding(
            severity=FindingSeverity.WARNING,
            category=FindingCategory.DATA_FLOW,
            message="算法模板没有终端输出节点",
            fix_suggestion="确保至少有一个节点作为最终输出",
        ))

    # 场景特定验证
    if scenario_id:
        findings.extend(_scenario_specific_validate(nodes, scenario_id))

    return findings


PREDICTION_KEYWORDS = ["forecast", "predict", "预测", "lstm", "arima", "gru", "xgboost"]
PREDICTION_SCENARIOS = [
    "renewable-energy", "energy-storage", "power-grid",
    "building-campus", "port-logistics", "carbon-management",
]


def _scenario_specific_validate(
    nodes: List[Dict], scenario_id: str
) -> List[ValidationFinding]:
    """场景特定的业务规则验证"""
    findings: List[ValidationFinding] = []

    if scenario_id in PREDICTION_SCENARIOS:
        has_prediction = any(
            any(kw in (n.get("data", {}).get("functionId", "") or "").lower()
                or kw in (n.get("data", {}).get("label", "") or "").lower()
                for kw in PREDICTION_KEYWORDS)
            for n in nodes
        )
        if not has_prediction:
            findings.append(ValidationFinding(
                severity=FindingSeverity.WARNING,
                category=FindingCategory.BUSINESS,
                message=f"场景 {scenario_id} 为预测类场景，但算法模板中未检测到预测模型节点",
                fix_suggestion="建议添加 LSTM、ARIMA 或 XGBoost 等预测模型节点",
            ))

    return findings


def _compute_readiness(
    structural_valid: bool, findings: List[ValidationFinding]
) -> int:
    """计算就绪度分数"""
    if not structural_valid:
        return 0
    score = 100
    for f in findings:
        if f.severity == FindingSeverity.ERROR:
            score -= 30
        elif f.severity == FindingSeverity.WARNING:
            score -= 10
        elif f.severity == FindingSeverity.INFO:
            score -= 2
    return max(0, min(100, score))


class WorkflowValidateSkill(BaseSkill):
    """算法模板合理性验证 Skill"""

    skill_name = "workflow-validate"
    required_role = "user"

    async def validate_input(self, request: BaseModel) -> None:
        if isinstance(request, WorkflowValidateRequest):
            if not request.workflow:
                raise ValueError("workflow 不能为空")

    async def execute(
        self, request: BaseModel, context: SkillContext
    ) -> WorkflowValidateResponse:
        if not isinstance(request, WorkflowValidateRequest):
            raise ValueError("请求类型错误，期望 WorkflowValidateRequest")

        start = time.time()

        # 1. 结构验证（复用已有 WorkflowValidator）
        structural_valid, structural_errors = _structural_validate(request.workflow)

        # 2. 业务验证
        business_findings = _business_validate(request.workflow, request.scenario_id)

        # 3. 就绪度
        readiness = _compute_readiness(structural_valid, business_findings)
        auto_fix = any(f.auto_fixable for f in business_findings)

        return WorkflowValidateResponse(
            structural_valid=structural_valid,
            structural_errors=structural_errors,
            business_findings=business_findings,
            readiness_score=readiness,
            auto_fix_available=auto_fix,
        )
# @AI_GENERATED: end
