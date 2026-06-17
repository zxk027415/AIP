"""
算法模板版本模型
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class WorkflowVersion(BaseModel):
    """算法模板版本"""
    id: str
    workflow_id: str
    version: int
    name: str
    description: Optional[str] = None
    data: Dict[str, Any]  # 算法模板数据（nodes, edges等）
    created_by: str
    created_at: datetime = Field(default_factory=datetime.now)
    is_current: bool = False
    tags: List[str] = Field(default_factory=list)


class WorkflowDiff(BaseModel):
    """算法模板差异"""
    id: str
    workflow_id: str
    from_version: int
    to_version: int
    diff_data: Dict[str, Any]  # 差异数据
    created_at: datetime = Field(default_factory=datetime.now)


class WorkflowBranch(BaseModel):
    """算法模板分支"""
    id: str
    workflow_id: str
    name: str
    description: Optional[str] = None
    base_version: int
    current_version: int
    created_by: str
    created_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = True


class VersionCompareResult(BaseModel):
    """版本比较结果"""
    from_version: int
    to_version: int
    nodes_added: List[Dict[str, Any]] = Field(default_factory=list)
    nodes_removed: List[Dict[str, Any]] = Field(default_factory=list)
    nodes_modified: List[Dict[str, Any]] = Field(default_factory=list)
    edges_added: List[Dict[str, Any]] = Field(default_factory=list)
    edges_removed: List[Dict[str, Any]] = Field(default_factory=list)
    edges_modified: List[Dict[str, Any]] = Field(default_factory=list)


class CreateVersionRequest(BaseModel):
    """创建版本请求"""
    workflow_id: str
    name: str
    description: Optional[str] = None
    data: Dict[str, Any]
    tags: List[str] = Field(default_factory=list)


class RestoreVersionRequest(BaseModel):
    """恢复版本请求"""
    workflow_id: str
    version: int


class CreateBranchRequest(BaseModel):
    """创建分支请求"""
    workflow_id: str
    name: str
    description: Optional[str] = None
    base_version: int
