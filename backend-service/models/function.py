"""
函数定义数据模型
"""
from typing import List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field


class DataType(str, Enum):
    """数据类型枚举"""
    NUMBER = "NUMBER"
    MATRIX = "MATRIX"
    VECTOR = "VECTOR"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    ARRAY = "ARRAY"
    OBJECT = "OBJECT"
    DATAFRAME = "DATAFRAME"  # 时序数据框
    MODEL = "MODEL"  # 机器学习模型
    ANY = "ANY"


class TypeConstraint(BaseModel):
    """类型约束"""
    type: DataType
    dimensions: Optional[List[int]] = Field(None, description="矩阵/向量维度约束")
    range: Optional[tuple[float, float]] = Field(None, description="数值范围约束")
    pattern: Optional[str] = Field(None, description="字符串模式约束")


class ParameterDefinition(BaseModel):
    """参数定义"""
    name: str = Field(..., description="参数名称")
    type: DataType = Field(..., description="参数类型")
    required: bool = Field(True, description="是否必需")
    default_value: Optional[Any] = Field(None, description="默认值")
    constraints: Optional[List[TypeConstraint]] = Field(None, description="类型约束")
    description: Optional[str] = Field(None, description="参数描述")


class FunctionDefinition(BaseModel):
    """函数定义"""
    id: str = Field(..., description="函数ID")
    name: str = Field(..., description="函数名称")
    category: str = Field(..., description="所属分类")
    description: str = Field(..., description="函数描述")
    parameters: List[ParameterDefinition] = Field(default_factory=list, description="参数列表")
    return_type: DataType = Field(..., description="返回类型")
    examples: List[str] = Field(default_factory=list, description="使用示例")
    implementation: Optional[str] = Field(None, description="函数实现代码")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "matrix_add",
                "name": "矩阵加法",
                "category": "linear_algebra",
                "description": "计算两个矩阵的和",
                "parameters": [
                    {"name": "A", "type": "MATRIX", "required": True},
                    {"name": "B", "type": "MATRIX", "required": True}
                ],
                "return_type": "MATRIX",
                "examples": ["A + B"]
            }
        }


class Category(BaseModel):
    """分类"""
    id: str = Field(..., description="分类ID")
    name: str = Field(..., description="分类名称")
    description: str = Field(..., description="分类描述")
    subcategories: Optional[List['Category']] = Field(None, description="子分类")
