"""
执行相关数据模型
"""
from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field


class ExecutionState(str, Enum):
    """执行状态枚举"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExecutionError(BaseModel):
    """执行错误"""
    module_id: str = Field(..., description="模块ID")
    message: str = Field(..., description="错误消息")
    stack_trace: Optional[str] = Field(None, description="堆栈跟踪")


class ExecutionResult(BaseModel):
    """执行结果"""
    success: bool = Field(..., description="是否成功")
    outputs: Dict[str, Any] = Field(default_factory=dict, description="输出结果")
    errors: Optional[List[ExecutionError]] = Field(None, description="错误列表")
    execution_time: float = Field(..., description="执行时间（秒）")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "outputs": {
                    "result": [[5.0, 7.0], [9.0, 11.0]]
                },
                "errors": None,
                "execution_time": 0.123
            }
        }


class ExecutionStatus(BaseModel):
    """执行状态"""
    execution_id: str = Field(..., description="执行ID")
    state: ExecutionState = Field(..., description="执行状态")
    progress: float = Field(0.0, ge=0.0, le=100.0, description="进度（0-100）")
    current_module: Optional[str] = Field(None, description="当前执行的模块ID")
