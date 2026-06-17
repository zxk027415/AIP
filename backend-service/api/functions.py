"""
函数库 API 路由
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from models.function import FunctionDefinition, Category
from services.function_library_service import get_function_library_service
from services.execution_service import ExecutionService
from services.matrix_service import MatrixService

router = APIRouter(prefix="/api/functions", tags=["functions"])


class FunctionExecutionRequest(BaseModel):
    """函数执行请求"""
    function_id: str
    parameters: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "function_id": "matrix_add",
                "parameters": {
                    "A": [[1, 2], [3, 4]],
                    "B": [[5, 6], [7, 8]]
                }
            }
        }


class FunctionExecutionResponse(BaseModel):
    """函数执行响应"""
    success: bool
    result: Any
    execution_time: Optional[float] = None
    error: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "result": [[6, 8], [10, 12]],
                "execution_time": 0.023
            }
        }


@router.get("/", response_model=List[FunctionDefinition], summary="获取所有函数")
async def get_all_functions():
    """
    获取函数库中的所有函数定义
    
    Returns:
        List[FunctionDefinition]: 所有函数定义列表
    """
    try:
        service = get_function_library_service()
        return service.get_all_functions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取函数列表失败: {str(e)}")


@router.get("/{function_id}", response_model=FunctionDefinition, summary="获取函数定义")
async def get_function(function_id: str):
    """
    根据ID获取函数定义
    
    Args:
        function_id: 函数ID
        
    Returns:
        FunctionDefinition: 函数定义
    """
    try:
        service = get_function_library_service()
        function = service.get_function(function_id)
        
        if function is None:
            raise HTTPException(status_code=404, detail=f"函数不存在: {function_id}")
        
        return function
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取函数失败: {str(e)}")


@router.get("/search/", response_model=List[FunctionDefinition], summary="搜索函数")
async def search_functions(
    q: Optional[str] = Query(None, description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类ID")
):
    """
    搜索函数
    
    Args:
        q: 搜索关键词（在名称和描述中搜索）
        category: 分类ID
        
    Returns:
        List[FunctionDefinition]: 匹配的函数列表
    """
    try:
        service = get_function_library_service()
        return service.search_functions(query=q, category=category)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索函数失败: {str(e)}")


@router.get("/category/{category_id}", response_model=List[FunctionDefinition], summary="获取分类下的函数")
async def get_functions_by_category(category_id: str):
    """
    获取指定分类下的所有函数
    
    Args:
        category_id: 分类ID
        
    Returns:
        List[FunctionDefinition]: 函数列表
    """
    try:
        service = get_function_library_service()
        
        # 验证分类是否存在
        category = service.get_category(category_id)
        if category is None:
            raise HTTPException(status_code=404, detail=f"分类不存在: {category_id}")
        
        return service.get_functions_by_category(category_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分类函数失败: {str(e)}")


@router.get("/categories/", response_model=List[Category], summary="获取所有分类")
async def get_categories():
    """
    获取所有算法分类
    
    Returns:
        List[Category]: 所有分类列表
    """
    try:
        service = get_function_library_service()
        return service.get_all_categories()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分类列表失败: {str(e)}")


@router.get("/categories/{category_id}", response_model=Category, summary="获取分类信息")
async def get_category(category_id: str):
    """
    根据ID获取分类信息
    
    Args:
        category_id: 分类ID
        
    Returns:
        Category: 分类信息
    """
    try:
        service = get_function_library_service()
        category = service.get_category(category_id)
        
        if category is None:
            raise HTTPException(status_code=404, detail=f"分类不存在: {category_id}")
        
        return category
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分类失败: {str(e)}")


# @AI_GENERATED: Kiro v1.0
@router.get("/stats/summary", summary="获取算法库统计摘要")
async def get_function_stats():
    """获取算法库的统计摘要：分类数、函数总数、各分类函数数"""
    try:
        service = get_function_library_service()
        categories = service.get_all_categories()
        functions = service.get_all_functions()

        category_stats = []
        for cat in categories:
            cat_funcs = [f for f in functions if f.category == cat.id]
            category_stats.append({
                "id": cat.id,
                "name": cat.name,
                "count": len(cat_funcs)
            })

        return {
            "total_categories": len(categories),
            "total_functions": len(functions),
            "categories": category_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")
# @AI_GENERATED: end


@router.post("/reload", summary="重新加载函数库")
async def reload_function_library():
    """
    重新加载函数库数据
    
    用于在修改函数库数据文件后刷新缓存
    
    Returns:
        dict: 操作结果
    """
    try:
        service = get_function_library_service()
        service.reload()
        return {"message": "函数库已重新加载", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新加载失败: {str(e)}")


@router.post("/execute", response_model=FunctionExecutionResponse, summary="执行函数")
async def execute_function(request: FunctionExecutionRequest):
    """
    执行函数
    
    Args:
        request: 函数执行请求，包含function_id和parameters
        
    Returns:
        FunctionExecutionResponse: 执行结果
    """
    import time
    
    try:
        start_time = time.time()
        
        # 获取函数库服务
        function_library = get_function_library_service()
        
        # 验证函数是否存在
        function_def = function_library.get_function(request.function_id)
        if function_def is None:
            raise HTTPException(status_code=404, detail=f"函数不存在: {request.function_id}")
        
        # 转换参数中的矩阵数据
        converted_params = {}
        for param_name, param_value in request.parameters.items():
            # 如果是二维数组，转换为Matrix对象
            if isinstance(param_value, list) and len(param_value) > 0 and isinstance(param_value[0], list):
                converted_params[param_name] = MatrixService.from_array(param_value)
            # 如果是一维数组，也转换为Matrix对象（向量）
            elif isinstance(param_value, list) and len(param_value) > 0:
                # 转换为列向量
                converted_params[param_name] = MatrixService.from_array([[v] for v in param_value])
            else:
                converted_params[param_name] = param_value
        
        # 创建执行服务
        execution_service = ExecutionService(
            function_library_service=function_library,
            matrix_service=MatrixService
        )
        
        # 执行函数
        node_data = {
            'functionId': request.function_id,
            'parameters': {}
        }
        
        result = execution_service._execute_function_node(node_data, converted_params)
        
        execution_time = time.time() - start_time
        
        return FunctionExecutionResponse(
            success=True,
            result=result,
            execution_time=round(execution_time, 4)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        return FunctionExecutionResponse(
            success=False,
            result=None,
            error=error_detail
        )
