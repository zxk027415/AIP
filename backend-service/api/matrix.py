"""
矩阵计算 API 路由
"""
from fastapi import APIRouter, HTTPException
from typing import List
from pydantic import BaseModel, Field

from models.matrix import Matrix, LUDecomposition, QRDecomposition, SVDDecomposition, EigenDecomposition
from services.matrix_service import MatrixService

router = APIRouter(prefix="/api/matrix", tags=["matrix"])


# 请求模型
class MatrixCreateRequest(BaseModel):
    """创建矩阵请求"""
    rows: int = Field(..., gt=0, description="行数")
    cols: int = Field(..., gt=0, description="列数")
    initial_value: float = Field(0.0, description="初始值")


class MatrixFromArrayRequest(BaseModel):
    """从数组创建矩阵请求"""
    data: List[List[float]] = Field(..., description="二维数组数据")


class MatrixOperationRequest(BaseModel):
    """矩阵运算请求"""
    operation: str = Field(..., description="运算类型: add, subtract, multiply, transpose, inverse")
    matrix_a: Matrix = Field(..., description="矩阵 A")
    matrix_b: Matrix = Field(None, description="矩阵 B（二元运算需要）")


class MatrixElementRequest(BaseModel):
    """矩阵元素操作请求"""
    matrix: Matrix = Field(..., description="矩阵")
    row: int = Field(..., ge=0, description="行索引")
    col: int = Field(..., ge=0, description="列索引")
    value: float = Field(None, description="新值（set操作需要）")


class MatrixDecompositionRequest(BaseModel):
    """矩阵分解请求"""
    decomposition_type: str = Field(..., description="分解类型: lu, qr, svd, eigen")
    matrix: Matrix = Field(..., description="矩阵")


# API 端点
@router.post("/create", response_model=Matrix, summary="创建矩阵")
async def create_matrix(request: MatrixCreateRequest):
    """
    创建指定维度的矩阵
    
    - **rows**: 行数
    - **cols**: 列数
    - **initial_value**: 初始值（默认为0）
    """
    try:
        return MatrixService.create(request.rows, request.cols, request.initial_value)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/from-array", response_model=Matrix, summary="从数组创建矩阵")
async def create_matrix_from_array(request: MatrixFromArrayRequest):
    """
    从二维数组创建矩阵
    
    - **data**: 二维数组数据
    """
    try:
        return MatrixService.from_array(request.data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/operation", response_model=Matrix, summary="矩阵运算")
async def matrix_operation(request: MatrixOperationRequest):
    """
    执行矩阵运算
    
    - **operation**: 运算类型
      - add: 加法
      - subtract: 减法
      - multiply: 乘法
      - transpose: 转置
      - inverse: 求逆
    - **matrix_a**: 矩阵 A
    - **matrix_b**: 矩阵 B（二元运算需要）
    """
    try:
        if request.operation == "add":
            if not request.matrix_b:
                raise ValueError("加法运算需要两个矩阵")
            return MatrixService.add(request.matrix_a, request.matrix_b)
        
        elif request.operation == "subtract":
            if not request.matrix_b:
                raise ValueError("减法运算需要两个矩阵")
            return MatrixService.subtract(request.matrix_a, request.matrix_b)
        
        elif request.operation == "multiply":
            if not request.matrix_b:
                raise ValueError("乘法运算需要两个矩阵")
            return MatrixService.multiply(request.matrix_a, request.matrix_b)
        
        elif request.operation == "transpose":
            return MatrixService.transpose(request.matrix_a)
        
        elif request.operation == "inverse":
            return MatrixService.inverse(request.matrix_a)
        
        else:
            raise ValueError(f"不支持的运算类型: {request.operation}")
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"运算失败: {str(e)}")


@router.post("/get-element", response_model=float, summary="获取矩阵元素")
async def get_matrix_element(request: MatrixElementRequest):
    """
    获取矩阵指定位置的元素
    
    - **matrix**: 矩阵
    - **row**: 行索引（从0开始）
    - **col**: 列索引（从0开始）
    """
    try:
        return MatrixService.get(request.matrix, request.row, request.col)
    except IndexError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-element", response_model=Matrix, summary="设置矩阵元素")
async def set_matrix_element(request: MatrixElementRequest):
    """
    设置矩阵指定位置的元素
    
    - **matrix**: 矩阵
    - **row**: 行索引（从0开始）
    - **col**: 列索引（从0开始）
    - **value**: 新值
    """
    if request.value is None:
        raise HTTPException(status_code=400, detail="必须提供value参数")
    
    try:
        return MatrixService.set(request.matrix, request.row, request.col, request.value)
    except IndexError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decomposition/lu", response_model=LUDecomposition, summary="LU分解")
async def lu_decomposition(request: MatrixDecompositionRequest):
    """
    LU 分解
    
    将矩阵 A 分解为 P*A = L*U
    - L: 下三角矩阵
    - U: 上三角矩阵
    - P: 置换矩阵
    """
    try:
        return MatrixService.lu_decomposition(request.matrix)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LU分解失败: {str(e)}")


@router.post("/decomposition/qr", response_model=QRDecomposition, summary="QR分解")
async def qr_decomposition(request: MatrixDecompositionRequest):
    """
    QR 分解
    
    将矩阵 A 分解为 A = Q*R
    - Q: 正交矩阵
    - R: 上三角矩阵
    """
    try:
        return MatrixService.qr_decomposition(request.matrix)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QR分解失败: {str(e)}")


@router.post("/decomposition/svd", response_model=SVDDecomposition, summary="SVD分解")
async def svd_decomposition(request: MatrixDecompositionRequest):
    """
    SVD 分解（奇异值分解）
    
    将矩阵 A 分解为 A = U*S*V^T
    - U: 左奇异向量矩阵
    - S: 奇异值对角矩阵
    - V: 右奇异向量矩阵
    """
    try:
        return MatrixService.svd_decomposition(request.matrix)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SVD分解失败: {str(e)}")


@router.post("/decomposition/eigen", response_model=EigenDecomposition, summary="特征值分解")
async def eigen_decomposition(request: MatrixDecompositionRequest):
    """
    特征值分解
    
    计算矩阵的特征值和特征向量
    - values: 特征值列表
    - vectors: 特征向量矩阵
    """
    try:
        return MatrixService.eigen_decomposition(request.matrix)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"特征值分解失败: {str(e)}")
