"""
算法模板数据模型
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from .function import DataType


class Position(BaseModel):
    """位置坐标"""
    x: float
    y: float


class Port(BaseModel):
    """端口定义"""
    name: str
    type: DataType
    required: bool = True


class PortId(BaseModel):
    """端口ID"""
    module_id: str
    port_name: str


class ModuleInstance(BaseModel):
    """模块实例"""
    id: str = Field(..., description="模块实例ID")
    type: str = Field(..., description="模块类型（对应FunctionDefinition的id）")
    position: Position = Field(..., description="画布上的位置")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="参数值")
    inputs: List[Port] = Field(default_factory=list, description="输入端口")
    outputs: List[Port] = Field(default_factory=list, description="输出端口")


class Connection(BaseModel):
    """连接"""
    id: str = Field(..., description="连接ID")
    source: PortId = Field(..., description="源端口")
    target: PortId = Field(..., description="目标端口")


class WorkflowMetadata(BaseModel):
    """算法模板元数据"""
    author: Optional[str] = None
    version: str = "1.0.0"
    tags: List[str] = Field(default_factory=list)
    is_template: bool = False


class Workflow(BaseModel):
    """算法模板"""
    id: str = Field(..., description="算法模板ID")
    name: str = Field(..., description="算法模板名称")
    description: Optional[str] = Field(None, description="算法模板描述")
    modules: List[ModuleInstance] = Field(default_factory=list, description="模块列表")
    connections: List[Connection] = Field(default_factory=list, description="连接列表")
    metadata: WorkflowMetadata = Field(default_factory=WorkflowMetadata, description="元数据")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "workflow_001",
                "name": "矩阵计算示例",
                "description": "演示矩阵加法和乘法",
                "modules": [],
                "connections": [],
                "metadata": {
                    "version": "1.0.0",
                    "tags": ["example", "matrix"],
                    "is_template": False
                }
            }
        }
