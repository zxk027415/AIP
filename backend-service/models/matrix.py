"""
矩阵数据模型
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class Matrix(BaseModel):
    """矩阵模型"""
    rows: int = Field(..., gt=0, description="行数")
    cols: int = Field(..., gt=0, description="列数")
    data: List[List[float]] = Field(..., description="矩阵数据")

    class Config:
        json_schema_extra = {
            "example": {
                "rows": 2,
                "cols": 2,
                "data": [[1.0, 2.0], [3.0, 4.0]]
            }
        }


class LUDecomposition(BaseModel):
    """LU分解结果"""
    L: Matrix = Field(..., description="下三角矩阵")
    U: Matrix = Field(..., description="上三角矩阵")
    P: Matrix = Field(..., description="置换矩阵")


class QRDecomposition(BaseModel):
    """QR分解结果"""
    Q: Matrix = Field(..., description="正交矩阵")
    R: Matrix = Field(..., description="上三角矩阵")


class SVDDecomposition(BaseModel):
    """SVD分解结果"""
    U: Matrix = Field(..., description="左奇异向量矩阵")
    S: Matrix = Field(..., description="奇异值对角矩阵")
    V: Matrix = Field(..., description="右奇异向量矩阵")


class EigenDecomposition(BaseModel):
    """特征值分解结果"""
    values: List[float] = Field(..., description="特征值列表")
    vectors: Matrix = Field(..., description="特征向量矩阵")
