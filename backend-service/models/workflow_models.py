"""
算法模板相关的Pydantic模型
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ============ 基础类型定义 ============

class NodeType(str, Enum):
    """节点类型枚举"""
    FUNCTION = "function"
    MATRIX = "matrix"
    VISUALIZATION = "visualization"


class ExecutionStatus(str, Enum):
    """执行状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationSeverity(str, Enum):
    """验证严重程度枚举"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# ============ 算法模板结构模型 ============

class Position(BaseModel):
    """位置坐标"""
    x: float
    y: float


class Viewport(BaseModel):
    """视口配置"""
    x: float = 0
    y: float = 0
    zoom: float = 1


class Port(BaseModel):
    """端口定义"""
    id: str
    name: str
    type: str
    required: bool = False


class WorkflowNodeData(BaseModel):
    """算法模板节点数据"""
    label: str
    functionId: Optional[str] = None
    operation: Optional[str] = None
    chartType: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    inputs: List[Port] = Field(default_factory=list)
    outputs: List[Port] = Field(default_factory=list)
    icon: Optional[str] = None
    error: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class WorkflowNode(BaseModel):
    """算法模板节点"""
    id: str
    type: NodeType
    position: Position
    data: WorkflowNodeData


class WorkflowEdge(BaseModel):
    """算法模板边"""
    id: str
    source: str
    sourceHandle: str
    target: str
    targetHandle: str


class WorkflowMetadata(BaseModel):
    """算法模板元数据"""
    author: Optional[str] = None
    version: str = "1.0.0"
    tags: List[str] = Field(default_factory=list)
    isTemplate: bool = False


class WorkflowDefinition(BaseModel):
    """算法模板定义（完整结构）"""
    nodes: List[WorkflowNode] = Field(default_factory=list)
    edges: List[WorkflowEdge] = Field(default_factory=list)
    viewport: Optional[Viewport] = None
    metadata: Optional[WorkflowMetadata] = None


# ============ 算法模板CRUD模型 ============

class WorkflowCreate(BaseModel):
    """创建算法模板请求模型"""
    name: str = Field(..., min_length=1, max_length=255, description="算法模板名称")
    description: Optional[str] = Field(None, description="算法模板描述")
    workflow: WorkflowDefinition = Field(..., description="算法模板定义")


class WorkflowUpdate(BaseModel):
    """更新算法模板请求模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="算法模板名称")
    description: Optional[str] = Field(None, description="算法模板描述")
    workflow: Optional[WorkflowDefinition] = Field(None, description="算法模板定义")


class WorkflowResponse(BaseModel):
    """算法模板响应模型"""
    id: int
    name: str
    description: Optional[str]
    workflow: WorkflowDefinition
    user_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class WorkflowListItem(BaseModel):
    """算法模板列表项模型"""
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============ 验证模型 ============

class ValidationError(BaseModel):
    """验证错误模型"""
    type: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    severity: ValidationSeverity = Field(..., description="严重程度")
    nodeId: Optional[str] = Field(None, description="相关节点ID")
    edgeId: Optional[str] = Field(None, description="相关边ID")
    port: Optional[str] = Field(None, description="相关端口")
    suggestion: Optional[str] = Field(None, description="修复建议")


class ValidationResult(BaseModel):
    """验证结果模型"""
    valid: bool = Field(..., description="是否有效")
    errors: List[ValidationError] = Field(default_factory=list, description="错误列表")
    warnings: List[ValidationError] = Field(default_factory=list, description="警告列表")


# ============ 执行模型 ============

class NodeResult(BaseModel):
    """节点执行结果"""
    nodeId: str
    status: ExecutionStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    executionTime: float = 0
    startTime: Optional[str] = None


class ExecutionResult(BaseModel):
    """执行结果"""
    workflowId: str
    executionId: str
    status: ExecutionStatus
    startTime: str
    endTime: Optional[str] = None
    nodeResults: Dict[str, NodeResult] = Field(default_factory=dict)
    error: Optional[str] = None


class WorkflowExecutionCreate(BaseModel):
    """创建算法模板执行请求模型"""
    workflow_id: int = Field(..., description="算法模板ID")


class WorkflowExecutionResponse(BaseModel):
    """算法模板执行响应模型"""
    id: int
    workflow_id: int
    user_id: int
    status: ExecutionStatus
    start_time: datetime
    end_time: Optional[datetime]
    execution_data: Optional[ExecutionResult]
    error_message: Optional[str]
    
    class Config:
        from_attributes = True


# ============ 模板模型 ============

class TemplateParameter(BaseModel):
    """模板参数"""
    name: str
    description: str
    type: str
    defaultValue: Any
    moduleId: str
    parameterName: str


class WorkflowTemplate(BaseModel):
    """算法模板模板"""
    id: str
    name: str
    category: str
    description: str
    workflow: WorkflowDefinition
    documentation: str
    parameters: Optional[List[TemplateParameter]] = None
    previewImage: Optional[str] = None
    tags: Optional[List[str]] = None
    author: Optional[str] = None
    version: Optional[str] = None


class TemplateListItem(BaseModel):
    """模板列表项"""
    id: str
    name: str
    category: str
    description: str
    previewImage: Optional[str] = None
    tags: Optional[List[str]] = None

