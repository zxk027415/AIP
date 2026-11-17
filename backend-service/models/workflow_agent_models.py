# @AI_GENERATED: Kiro v1.0
"""
Workflow Agent 数据模型 — Pydantic 请求/响应模型
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


# ============ 通用枚举 ============

class SkillName(str, Enum):
    """Skill 名称枚举"""
    SCENARIO_MATCH = "scenario-match"
    ALGORITHM_COMPOSE = "algorithm-compose"
    WORKFLOW_GENERATE = "workflow-generate"
    WORKFLOW_VALIDATE = "workflow-validate"
    TEMPLATE_MANAGE = "template-manage"
    DOMAIN_CONSTRAINT = "domain-constraint"
    BEST_PRACTICE = "best-practice"
    CROSS_SCENARIO = "cross-scenario"


class UserRole(str, Enum):
    """用户角色枚举"""
    USER = "user"
    ENGINEER = "engineer"
    ADMIN = "admin"


class CombinationProfile(str, Enum):
    """算法组合方案类型"""
    HIGH_ACCURACY = "high-accuracy"
    LOW_LATENCY = "low-latency"
    BALANCED = "balanced"


class FindingSeverity(str, Enum):
    """验证发现严重程度"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FindingCategory(str, Enum):
    """验证发现分类"""
    STRUCTURAL = "structural"
    BUSINESS = "business"
    PARAMETER = "parameter"
    DATA_FLOW = "data_flow"


class TemplateVisibility(str, Enum):
    """模板可见性"""
    PRIVATE = "private"
    TEAM = "team"
    PUBLIC = "public"


class CompatibilityCategory(str, Enum):
    """迁移兼容性分类"""
    COMPATIBLE = "compatible"
    ADAPTABLE = "adaptable"
    INCOMPATIBLE = "incompatible"


# ============ 用户约束 ============

class UserConstraints(BaseModel):
    """用户约束条件"""
    data_volume: Optional[str] = None       # small|medium|large
    realtime_required: Optional[bool] = None
    accuracy_target: Optional[float] = None  # 0-100
    max_latency_ms: Optional[int] = None


# ============ Skill 上下文与编排 ============

class SkillContext(BaseModel):
    """Skill 执行上下文"""
    user_id: int
    username: str
    role: UserRole = UserRole.USER
    workflow_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SkillStep(BaseModel):
    """编排链中的一步"""
    skill_name: SkillName
    input_data: Dict[str, Any]
    depends_on: Optional[str] = None  # 依赖的上一步 skill_name


class SkillResult(BaseModel):
    """单个 Skill 执行结果"""
    skill_name: str
    status: str  # success|failed|skipped
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_duration_ms: int = 0


class ChainResult(BaseModel):
    """链式编排执行结果"""
    steps: List[SkillResult] = Field(default_factory=list)
    overall_status: str  # success|partial|failed
    total_duration_ms: int = 0


# ============ scenario-match 模型 ============

class ScenarioMatchRequest(BaseModel):
    """场景匹配请求"""
    description: str = Field(..., min_length=1, max_length=2000)
    language: str = "auto"  # auto|zh|en


class ScenarioMatchResult(BaseModel):
    """单个场景匹配结果"""
    scenario_id: str
    scenario_name: str
    confidence_score: int = Field(..., ge=0, le=100)
    rationale: str
    extracted_entities: Dict[str, str] = Field(default_factory=dict)


class ScenarioMatchResponse(BaseModel):
    """场景匹配响应"""
    matches: List[ScenarioMatchResult] = Field(default_factory=list)
    extracted_entities: Dict[str, str] = Field(default_factory=dict)
    processing_time_ms: int = 0


# ============ algorithm-compose 模型 ============

class AlgorithmRecommendation(BaseModel):
    """算法推荐"""
    algorithm_id: str
    algorithm_name: str
    confidence: int = Field(0, ge=0, le=100)
    rationale: str = ""
    source: str = "basic_module"  # basic_module|industry_template
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AlgorithmLayer(BaseModel):
    """算法层"""
    layer_name: str  # 数据接入层|数据处理层|算法模型层|评估输出层
    algorithms: List[AlgorithmRecommendation] = Field(default_factory=list)


class AlgorithmCombination(BaseModel):
    """算法组合方案（L3 竞争算法模板）"""
    combination_id: str
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    profile: CombinationProfile
    layers: List[AlgorithmLayer] = Field(default_factory=list)
    overall_confidence: float = Field(0, ge=0, le=100)
    description: str = ""


class AlgorithmComposeRequest(BaseModel):
    """算法组合推荐请求"""
    scenario_id: str
    template_id: Optional[str] = None  # 指定具体模板，不指定则返回场景级概览
    constraints: Optional[UserConstraints] = None


class AlgorithmComposeResponse(BaseModel):
    """算法组合推荐响应"""
    combinations: List[AlgorithmCombination] = Field(default_factory=list)
    scenario_id: str
    template_id: Optional[str] = None
    total_combinations: int = 0
    processing_time_ms: int = 0


# ============ workflow-generate 模型 ============

class WorkflowGenerateRequest(BaseModel):
    """算法模板生成请求"""
    combination: AlgorithmCombination
    scenario_id: str
    apply_domain_constraints: bool = True


class WorkflowGenerateResponse(BaseModel):
    """算法模板生成响应"""
    workflow: Dict[str, Any]  # WorkflowDefinition 序列化后的 dict
    generation_summary: str
    node_count: int = 0
    edge_count: int = 0
    processing_time_ms: int = 0


# ============ workflow-validate 模型 ============

class ValidationFinding(BaseModel):
    """验证发现"""
    severity: FindingSeverity
    category: FindingCategory
    message: str
    node_id: Optional[str] = None
    fix_suggestion: str = Field(..., min_length=1)
    auto_fixable: bool = False


class WorkflowValidateRequest(BaseModel):
    """算法模板验证请求"""
    workflow: Dict[str, Any]  # WorkflowDefinition 序列化后的 dict
    scenario_id: Optional[str] = None


class WorkflowValidateResponse(BaseModel):
    """算法模板验证响应"""
    structural_valid: bool = True
    structural_errors: List[Dict[str, Any]] = Field(default_factory=list)
    business_findings: List[ValidationFinding] = Field(default_factory=list)
    readiness_score: int = Field(0, ge=0, le=100)
    auto_fix_available: bool = False


# ============ template-manage 模型 ============

class TemplateCreateRequest(BaseModel):
    """模板创建请求"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    scenario_id: Optional[str] = None
    category: Optional[str] = None  # 预测|诊断|优化|监控
    tags: List[str] = Field(default_factory=list)
    visibility: TemplateVisibility = TemplateVisibility.PRIVATE
    workflow_data: Dict[str, Any] = Field(...)


class TemplateSearchParams(BaseModel):
    """模板搜索参数"""
    name: Optional[str] = None
    scenario_id: Optional[str] = None
    tags: Optional[List[str]] = None
    creator_id: Optional[int] = None
    visibility: Optional[TemplateVisibility] = None
    page: int = 1
    page_size: int = 20


# ============ domain-constraint 模型 ============

class DomainConstraintQuery(BaseModel):
    """业务约束查询"""
    scenario_id: str
    include_custom: bool = True


class DomainConstraintCreate(BaseModel):
    """自定义约束创建"""
    scenario_id: str
    constraint_key: str
    constraint_type: str  # range|enum|threshold
    constraint_value: Dict[str, Any]
    description: Optional[str] = None
    project_id: Optional[str] = None


# ============ best-practice 模型 ============

class BestPracticeQuery(BaseModel):
    """最佳实践查询"""
    scenario_id: str
    limit: int = 10


class BestPracticeContribute(BaseModel):
    """用户贡献最佳实践"""
    scenario_id: str
    title: str
    description: Optional[str] = None
    algorithm_combination: Dict[str, Any]
    key_parameters: Dict[str, Any] = Field(default_factory=dict)
    achieved_metrics: Dict[str, Any] = Field(default_factory=dict)
    applicability_notes: Optional[str] = None


# ============ cross-scenario 模型 ============

class CrossScenarioRequest(BaseModel):
    """跨场景迁移请求"""
    source_scenario_id: str
    target_scenario_id: str
    source_workflow: Dict[str, Any]


class MigrationAlgorithmReport(BaseModel):
    """迁移算法分类报告"""
    algorithm_id: str
    algorithm_name: str
    category: CompatibilityCategory
    reason: str
    replacement_id: Optional[str] = None  # incompatible 时的替换算法


class MigrationReport(BaseModel):
    """迁移报告"""
    source_scenario_id: str
    target_scenario_id: str
    confidence_score: int = Field(0, ge=0, le=100)
    algorithm_reports: List[MigrationAlgorithmReport] = Field(default_factory=list)
    migrated_workflow: Optional[Dict[str, Any]] = None
    changes_highlighted: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ============ Skill 状态与审计 ============

class SkillStatus(BaseModel):
    """Skill 状态"""
    skill_name: str
    available: bool = True
    recent_execution_count: int = 0
    avg_execution_time_ms: float = 0
    error_rate: float = 0


class AuditLogEntry(BaseModel):
    """审计日志条目"""
    id: int
    timestamp: str
    user_id: int
    skill_name: str
    action: str
    workflow_id: Optional[str] = None
    status: str
    execution_duration_ms: Optional[int] = None
    error_message: Optional[str] = None


class AuditLogQuery(BaseModel):
    """审计日志查询"""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    user_id: Optional[int] = None
    skill_name: Optional[str] = None
    workflow_id: Optional[str] = None
    page: int = 1
    page_size: int = 50

# @AI_GENERATED: end
