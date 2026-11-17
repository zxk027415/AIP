"""
版本控制API
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List

from models.version import (
    WorkflowVersion,
    WorkflowBranch,
    VersionCompareResult,
    CreateVersionRequest,
    RestoreVersionRequest,
    CreateBranchRequest,
)
from services.version_service import version_service
from api.auth import get_current_user


router = APIRouter(prefix="/api/versions", tags=["versions"])


@router.post("/", response_model=WorkflowVersion)
async def create_version(
    request: CreateVersionRequest,
    current_user: dict = Depends(get_current_user)
):
    """创建新版本"""
    try:
        return version_service.create_version(request, current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workflow_id}", response_model=List[WorkflowVersion])
async def get_versions(
    workflow_id: str,
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """获取版本历史"""
    return version_service.get_versions(workflow_id, limit)


@router.get("/{workflow_id}/{version}", response_model=WorkflowVersion)
async def get_version(
    workflow_id: str,
    version: int,
    current_user: dict = Depends(get_current_user)
):
    """获取指定版本"""
    result = version_service.get_version(workflow_id, version)
    if not result:
        raise HTTPException(status_code=404, detail="版本不存在")
    return result


@router.post("/restore", response_model=WorkflowVersion)
async def restore_version(
    request: RestoreVersionRequest,
    current_user: dict = Depends(get_current_user)
):
    """恢复到指定版本"""
    try:
        return version_service.restore_version(request, current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workflow_id}/compare/{from_version}/{to_version}", response_model=VersionCompareResult)
async def compare_versions(
    workflow_id: str,
    from_version: int,
    to_version: int,
    current_user: dict = Depends(get_current_user)
):
    """比较两个版本"""
    try:
        return version_service.compare_versions(workflow_id, from_version, to_version)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== 分支API ==========

@router.post("/branches", response_model=WorkflowBranch)
async def create_branch(
    request: CreateBranchRequest,
    current_user: dict = Depends(get_current_user)
):
    """创建分支"""
    try:
        return version_service.create_branch(request, current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/branches/{workflow_id}", response_model=List[WorkflowBranch])
async def get_branches(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """获取分支列表"""
    return version_service.get_branches(workflow_id)


@router.delete("/branches/{workflow_id}/{branch_id}")
async def delete_branch(
    workflow_id: str,
    branch_id: str,
    current_user: dict = Depends(get_current_user)
):
    """删除分支"""
    success = version_service.delete_branch(workflow_id, branch_id)
    if not success:
        raise HTTPException(status_code=404, detail="分支不存在")
    return {"message": "分支已删除"}


@router.post("/cleanup/{workflow_id}")
async def cleanup_versions(
    workflow_id: str,
    keep_count: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """清理旧版本"""
    removed_count = version_service.cleanup_old_versions(workflow_id, keep_count)
    return {"message": f"已清理 {removed_count} 个旧版本"}
