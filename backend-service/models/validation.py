"""
验证相关数据模型
"""
from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class ErrorType(str, Enum):
    """错误类型枚举"""
    MISSING_INPUT = "MISSING_INPUT"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    INVALID_OPERATION = "INVALID_OPERATION"


class ValidationError(BaseModel):
    """验证错误"""
    module_id: Optional[str] = Field(None, description="模块ID")
    connection_id: Optional[str] = Field(None, description="连接ID")
    message: str = Field(..., description="错误消息")
    type: ErrorType = Field(..., description="错误类型")


class ValidationWarning(BaseModel):
    """验证警告"""
    module_id: Optional[str] = Field(None, description="模块ID")
    connection_id: Optional[str] = Field(None, description="连接ID")
    message: str = Field(..., description="警告消息")


class ValidationResult(BaseModel):
    """验证结果"""
    valid: bool = Field(..., description="是否有效")
    errors: List[ValidationError] = Field(default_factory=list, description="错误列表")
    warnings: List[ValidationWarning] = Field(default_factory=list, description="警告列表")

    class Config:
        json_schema_extra = {
            "example": {
                "valid": False,
                "errors": [
                    {
                        "module_id": "module_001",
                        "message": "缺少必需的输入参数",
                        "type": "MISSING_INPUT"
                    }
                ],
                "warnings": []
            }
        }
