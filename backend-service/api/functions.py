"""
函数库 API 路由
"""
import os
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from models.function import FunctionDefinition, Category
from services.function_library_service import get_function_library_service
from services.execution_service import ExecutionService
from services.matrix_service import MatrixService

router = APIRouter(prefix="/api/functions", tags=["functions"])

# @AI_GENERATED
# operator_backends/ 目录的绝对路径（相对于本文件计算，与 workflows_enhanced.py 约定一致）
# __file__ = backend-service/api/functions.py
# dirname(__file__)     = backend-service/api/
# dirname(dirname(...)) = backend-service/
_OPERATOR_BACKENDS_DIR: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "services",
    "operator_backends",
)

# 模块级懒初始化路由器；首次调用 _ensure_router() 时自动 auto_discover
_operator_router: Optional[Any] = None  # type: ignore[assignment]


def _ensure_router() -> Any:
    """
    惰性初始化 OperatorRouter 并完成自动发现。
    首次调用时扫描 operator_backends/ 目录注册所有算子；后续调用复用缓存实例。

    Returns:
        OperatorRouter: 已完成自动发现的路由器实例。
    """
    global _operator_router
    if _operator_router is None:
        from services.operator_execution.router import OperatorRouter
        _operator_router = OperatorRouter()
        _operator_router.auto_discover(_OPERATOR_BACKENDS_DIR)
    return _operator_router


class BackendStatusResponse(BaseModel):
    """算子后端注册状态响应体"""
    total_registered: int        # 已注册算子总数
    registered_operators: List[str]  # 已注册算子 ID 列表（按字母排序）
    # verified_operators — 5 层测试 + 真实数据 e2e 均已覆盖且当前已注册的算子 ID
    verified_operators: List[str] = []
    total_verified: int = 0  # verified_operators 数量

    class Config:
        json_schema_extra = {
            "example": {
                "total_registered": 3,
                "registered_operators": ["load_csv", "load_parquet", "min_max_scale"],
                "verified_operators": ["load_csv", "min_max_scale"],
                "total_verified": 2,
            }
        }
# @AI_GENERATED: end


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


# @AI_GENERATED
@router.get("/backend-status", response_model=BackendStatusResponse, summary="查询已注册算子后端状态")
async def get_backend_status():
    """
    返回所有已在 operator_backends/ 目录中发现并注册的算子 ID 列表。

    用于前端展示徽标：
    - registered_operators：有真实后端实现 → 「可执行」
    - verified_operators：通过六重测试（L1–L6）→ 「已验证」
      （覆盖源：services.operator_test_coverage.six_layer_passed）

    Returns:
        BackendStatusResponse:
            - total_registered / registered_operators
            - total_verified / verified_operators
    """
    try:
        from services.operator_verification import filter_verified_registered

        r = _ensure_router()
        ids = r.list_operators()
        verified = filter_verified_registered(ids)
        return BackendStatusResponse(
            total_registered=len(ids),
            registered_operators=sorted(ids),
            verified_operators=verified,
            total_verified=len(verified),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取算子后端状态失败: {str(e)}")
# @AI_GENERATED: end


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


# @AI_GENERATED: operator source code endpoint
class OperatorSourceResponse(BaseModel):
    """算子源码响应体"""
    operator_id: str
    source_code: str          # 文件完整源码
    key_snippet: str          # execute() 函数片段（约 80 行以内）
    file_path: str            # 相对于 backend-service/ 的路径
    available: bool           # 是否存在对应后端文件

    class Config:
        json_schema_extra = {
            "example": {
                "operator_id": "load_csv",
                "source_code": "# @AI_GENERATED\n...",
                "key_snippet": "def execute(params, inputs):\n    ...",
                "file_path": "services/operator_backends/load_csv.py",
                "available": True,
            }
        }


@router.get("/{function_id}/source", response_model=OperatorSourceResponse, summary="获取算子源码")
async def get_operator_source(function_id: str):
    """
    返回指定算子对应的 operator_backends/{function_id}.py 源码内容。

    - source_code：完整文件内容
    - key_snippet：仅 execute() 函数体（方便前端高亮展示）
    - file_path：相对于 backend-service/ 的相对路径
    - available：后端文件是否存在（不存在时 source_code / key_snippet 均为空字符串）
    """
    import re

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    operator_file = os.path.join(
        backend_dir, "services", "operator_backends", f"{function_id}.py"
    )
    rel_path = os.path.join("services", "operator_backends", f"{function_id}.py")

    if not os.path.isfile(operator_file):
        return OperatorSourceResponse(
            operator_id=function_id,
            source_code="",
            key_snippet="",
            file_path=rel_path,
            available=False,
        )

    try:
        with open(operator_file, "r", encoding="utf-8") as f:
            source_code = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取算子源码失败: {str(e)}")

    # 提取 execute() 函数片段
    # 策略：找到 "def execute(" 所在行，截取到下一个顶层 def/class 之前（最多 120 行）
    lines = source_code.splitlines()
    execute_start = None
    for idx, line in enumerate(lines):
        if re.match(r"^def execute\s*\(", line):
            execute_start = idx
            break

    if execute_start is not None:
        snippet_lines = []
        for line in lines[execute_start:]:
            snippet_lines.append(line)
            if len(snippet_lines) > 120:
                break
            # 遇到下一个顶层 def/class（非首行）就停止
            if len(snippet_lines) > 1 and re.match(r"^(def |class )", line):
                snippet_lines.pop()  # 去掉触发结束的那行
                break
        key_snippet = "\n".join(snippet_lines)
    else:
        # 没有 execute()，回退到前 80 行
        key_snippet = "\n".join(lines[:80])

    return OperatorSourceResponse(
        operator_id=function_id,
        source_code=source_code,
        key_snippet=key_snippet,
        file_path=rel_path,
        available=True,
    )
# @AI_GENERATED: end


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
