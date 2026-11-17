"""
算法模板API路由

提供算法模板的CRUD操作和执行功能
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import json
from datetime import datetime

from database import get_db, Workflow, WorkflowExecution, User
from models.workflow_models import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
    WorkflowListItem,
    WorkflowExecutionResponse,
    ValidationResult,
    WorkflowDefinition
)
from services.validation_service import ValidationService
from services.execution_service import ExecutionService
from services.function_library_service import get_function_library_service
from services.matrix_service import MatrixService


router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def get_current_user(db: Session = Depends(get_db)) -> User:
    """
    获取当前用户（临时实现）
    TODO: 实现真正的JWT认证
    """
    # 临时返回第一个用户
    user = db.query(User).first()
    if not user:
        raise HTTPException(status_code=401, detail="未找到用户")
    return user


@router.post("/", response_model=WorkflowResponse)
def create_workflow(
    workflow_data: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建工作流
    
    Args:
        workflow_data: 工作流创建数据
        db: 数据库会话
        current_user: 当前用户
        
    Returns:
        WorkflowResponse: 创建的工作流
    """
    # 将WorkflowDefinition转换为JSON字符串
    workflow_json = workflow_data.workflow.model_dump()
    
    workflow = Workflow(
        name=workflow_data.name,
        description=workflow_data.description,
        user_id=current_user.id,
        workflow_data=json.dumps(workflow_json)
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    
    # 构造响应
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        workflow=workflow_data.workflow,
        user_id=workflow.user_id,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at
    )


@router.get("/", response_model=List[WorkflowListItem])
def list_workflows(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取用户的工作流列表
    
    Args:
        db: 数据库会话
        current_user: 当前用户
        
    Returns:
        List[WorkflowListItem]: 工作流列表
    """
    workflows = db.query(Workflow).filter(
        Workflow.user_id == current_user.id
    ).order_by(Workflow.updated_at.desc()).all()
    
    return [
        WorkflowListItem(
            id=w.id,
            name=w.name,
            description=w.description,
            created_at=w.created_at,
            updated_at=w.updated_at
        )
        for w in workflows
    ]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取工作流详情
    
    Args:
        workflow_id: 工作流ID
        db: 数据库会话
        current_user: 当前用户
        
    Returns:
        WorkflowResponse: 工作流详情
    """
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == current_user.id
    ).first()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="算法模板不存在")
    
    # 解析算法模板数据
    workflow_dict = json.loads(workflow.workflow_data)
    workflow_def = WorkflowDefinition(**workflow_dict)
    
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        workflow=workflow_def,
        user_id=workflow.user_id,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at
    )


@router.put("/{workflow_id}")
def update_workflow(
    workflow_id: int,
    workflow_data: WorkflowUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    更新工作流
    
    Args:
        workflow_id: 工作流ID
        workflow_data: 更新数据
        db: 数据库会话
        current_user: 当前用户
        
    Returns:
        dict: 成功消息
    """
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == current_user.id
    ).first()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")
    
    # 更新字段
    if workflow_data.name is not None:
        workflow.name = workflow_data.name
    if workflow_data.description is not None:
        workflow.description = workflow_data.description
    if workflow_data.workflow is not None:
        workflow_json = workflow_data.workflow.model_dump()
        workflow.workflow_data = json.dumps(workflow_json)
    
    workflow.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "算法模板更新成功", "id": workflow_id}


@router.delete("/{workflow_id}")
def delete_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    删除工作流
    
    Args:
        workflow_id: 工作流ID
        db: 数据库会话
        current_user: 当前用户
        
    Returns:
        dict: 成功消息
    """
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == current_user.id
    ).first()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="算法模板不存在")
    
    db.delete(workflow)
    db.commit()
    
    return {"message": "算法模板删除成功", "id": workflow_id}


@router.post("/{workflow_id}/validate", response_model=ValidationResult)
def validate_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    验证工作流
    
    Args:
        workflow_id: 工作流ID
        db: 数据库会话
        current_user: 当前用户
        
    Returns:
        ValidationResult: 验证结果
    """
    # 获取工作流
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == current_user.id
    ).first()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="算法模板不存在")
    
    # 解析算法模板数据
    workflow_data = json.loads(workflow.workflow_data)
    
    # 验证算法模板
    validation_service = ValidationService()
    is_valid, issues = validation_service.validate_workflow(workflow_data)
    
    # 分离错误和警告
    errors = [issue for issue in issues if issue.get('severity') == 'error']
    warnings = [issue for issue in issues if issue.get('severity') == 'warning']
    
    return ValidationResult(
        valid=is_valid,
        errors=errors,
        warnings=warnings
    )


@router.post("/{workflow_id}/execute", response_model=WorkflowExecutionResponse)
def execute_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    执行工作流
    
    Args:
        workflow_id: 工作流ID
        db: 数据库会话
        current_user: 当前用户
        
    Returns:
        WorkflowExecutionResponse: 执行结果
    """
    # 1. 获取工作流
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == current_user.id
    ).first()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="算法模板不存在")
    
    # 2. 解析算法模板数据
    workflow_data = json.loads(workflow.workflow_data)
    
    # 3. 验证算法模板
    validation_service = ValidationService()
    is_valid, errors = validation_service.validate_workflow(workflow_data)
    
    if not is_valid:
        error_list = [e for e in errors if e.get('severity') == 'error']
        raise HTTPException(
            status_code=400,
            detail={
                "message": "算法模板验证失败",
                "errors": error_list
            }
        )
    
    # 4. 创建执行记录
    execution = WorkflowExecution(
        workflow_id=workflow_id,
        user_id=current_user.id,
        status='pending'
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    
    # 5. 执行算法模板
    function_library = get_function_library_service()
    matrix_service = MatrixService()
    execution_service = ExecutionService(function_library, matrix_service)
    
    try:
        result = execution_service.execute_workflow(workflow_data, current_user.id)
        
        # 6. 更新执行记录
        execution.status = result['status']
        execution.execution_data = json.dumps(result)
        execution.end_time = datetime.utcnow()
        
        if result['status'] == 'failed':
            execution.error_message = result.get('error')
        
        db.commit()
        db.refresh(execution)
        
        return WorkflowExecutionResponse(
            id=execution.id,
            workflow_id=execution.workflow_id,
            user_id=execution.user_id,
            status=execution.status,
            start_time=execution.start_time,
            end_time=execution.end_time,
            execution_data=result,
            error_message=execution.error_message
        )
        
    except Exception as e:
        execution.status = 'failed'
        execution.error_message = str(e)
        execution.end_time = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/", response_model=List[WorkflowExecutionResponse])
def list_executions(
    workflow_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取执行历史列表
    
    Args:
        workflow_id: 可选的工作流ID过滤
        db: 数据库会话
        current_user: 当前用户
        
    Returns:
        List[WorkflowExecutionResponse]: 执行历史列表
    """
    query = db.query(WorkflowExecution).filter(
        WorkflowExecution.user_id == current_user.id
    )
    
    if workflow_id:
        query = query.filter(WorkflowExecution.workflow_id == workflow_id)
    
    executions = query.order_by(WorkflowExecution.start_time.desc()).all()
    
    results = []
    for execution in executions:
        execution_data = None
        if execution.execution_data:
            execution_data = json.loads(execution.execution_data)
        
        results.append(WorkflowExecutionResponse(
            id=execution.id,
            workflow_id=execution.workflow_id,
            user_id=execution.user_id,
            status=execution.status,
            start_time=execution.start_time,
            end_time=execution.end_time,
            execution_data=execution_data,
            error_message=execution.error_message
        ))
    
    return results


@router.get("/executions/{execution_id}", response_model=WorkflowExecutionResponse)
def get_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取执行详情
    
    Args:
        execution_id: 执行ID
        db: 数据库会话
        current_user: 当前用户
        
    Returns:
        WorkflowExecutionResponse: 执行详情
    """
    execution = db.query(WorkflowExecution).filter(
        WorkflowExecution.id == execution_id,
        WorkflowExecution.user_id == current_user.id
    ).first()
    
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    
    execution_data = None
    if execution.execution_data:
        execution_data = json.loads(execution.execution_data)
    
    return WorkflowExecutionResponse(
        id=execution.id,
        workflow_id=execution.workflow_id,
        user_id=execution.user_id,
        status=execution.status,
        start_time=execution.start_time,
        end_time=execution.end_time,
        execution_data=execution_data,
        error_message=execution.error_message
    )
