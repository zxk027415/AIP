"""
版本控制服务
"""
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4

from models.version import (
    WorkflowVersion,
    WorkflowDiff,
    WorkflowBranch,
    VersionCompareResult,
    CreateVersionRequest,
    RestoreVersionRequest,
    CreateBranchRequest,
)


class VersionService:
    """版本控制服务"""
    
    def __init__(self):
        # 模拟数据库存储
        self.versions: Dict[str, List[WorkflowVersion]] = {}
        self.diffs: Dict[str, List[WorkflowDiff]] = {}
        self.branches: Dict[str, List[WorkflowBranch]] = {}
    
    def create_version(self, request: CreateVersionRequest, user_id: str) -> WorkflowVersion:
        """创建新版本"""
        workflow_id = request.workflow_id
        
        # 获取当前版本号
        versions = self.versions.get(workflow_id, [])
        next_version = len(versions) + 1
        
        # 创建版本
        version = WorkflowVersion(
            id=str(uuid4()),
            workflow_id=workflow_id,
            version=next_version,
            name=request.name,
            description=request.description,
            data=request.data,
            created_by=user_id,
            created_at=datetime.now(),
            is_current=True,
            tags=request.tags,
        )
        
        # 如果有上一个版本，计算差异（在添加新版本之前）
        if len(versions) > 0:
            prev_version = versions[-1]
            diff = self._calculate_diff(prev_version, version)
            if workflow_id not in self.diffs:
                self.diffs[workflow_id] = []
            self.diffs[workflow_id].append(diff)
        
        # 将之前的版本标记为非当前版本
        for v in versions:
            v.is_current = False
        
        # 保存版本
        if workflow_id not in self.versions:
            self.versions[workflow_id] = []
        self.versions[workflow_id].append(version)
        
        return version
    
    def get_versions(self, workflow_id: str, limit: int = 50) -> List[WorkflowVersion]:
        """获取版本历史"""
        versions = self.versions.get(workflow_id, [])
        return sorted(versions, key=lambda v: v.version, reverse=True)[:limit]
    
    def get_version(self, workflow_id: str, version: int) -> Optional[WorkflowVersion]:
        """获取指定版本"""
        versions = self.versions.get(workflow_id, [])
        for v in versions:
            if v.version == version:
                return v
        return None
    
    def restore_version(self, request: RestoreVersionRequest, user_id: str) -> WorkflowVersion:
        """恢复到指定版本"""
        # 获取要恢复的版本
        version_to_restore = self.get_version(request.workflow_id, request.version)
        if not version_to_restore:
            raise ValueError(f"版本 {request.version} 不存在")
        
        # 创建新版本（基于要恢复的版本）
        new_version_request = CreateVersionRequest(
            workflow_id=request.workflow_id,
            name=f"恢复到版本 {request.version}",
            description=f"从版本 {request.version} 恢复",
            data=version_to_restore.data,
            tags=["restored"],
        )
        
        return self.create_version(new_version_request, user_id)
    
    def compare_versions(
        self,
        workflow_id: str,
        from_version: int,
        to_version: int
    ) -> VersionCompareResult:
        """比较两个版本"""
        v1 = self.get_version(workflow_id, from_version)
        v2 = self.get_version(workflow_id, to_version)
        
        if not v1 or not v2:
            raise ValueError("版本不存在")
        
        return self._compare_workflow_data(v1.data, v2.data, from_version, to_version)
    
    def _calculate_diff(
        self,
        from_version: WorkflowVersion,
        to_version: WorkflowVersion
    ) -> WorkflowDiff:
        """计算版本差异"""
        diff_data = self._compare_workflow_data(
            from_version.data,
            to_version.data,
            from_version.version,
            to_version.version
        )
        
        return WorkflowDiff(
            id=str(uuid4()),
            workflow_id=from_version.workflow_id,
            from_version=from_version.version,
            to_version=to_version.version,
            diff_data=diff_data.dict(),
            created_at=datetime.now(),
        )
    
    def _compare_workflow_data(
        self,
        data1: Dict[str, Any],
        data2: Dict[str, Any],
        from_version: int,
        to_version: int
    ) -> VersionCompareResult:
        """比较算法模板数据"""
        nodes1 = {n['id']: n for n in data1.get('nodes', [])}
        nodes2 = {n['id']: n for n in data2.get('nodes', [])}
        edges1 = {e['id']: e for e in data1.get('edges', [])}
        edges2 = {e['id']: e for e in data2.get('edges', [])}
        
        # 比较节点
        nodes_added = [n for nid, n in nodes2.items() if nid not in nodes1]
        nodes_removed = [n for nid, n in nodes1.items() if nid not in nodes2]
        nodes_modified = []
        
        for nid in set(nodes1.keys()) & set(nodes2.keys()):
            if json.dumps(nodes1[nid], sort_keys=True) != json.dumps(nodes2[nid], sort_keys=True):
                nodes_modified.append({
                    'id': nid,
                    'old': nodes1[nid],
                    'new': nodes2[nid],
                })
        
        # 比较边
        edges_added = [e for eid, e in edges2.items() if eid not in edges1]
        edges_removed = [e for eid, e in edges1.items() if eid not in edges2]
        edges_modified = []
        
        for eid in set(edges1.keys()) & set(edges2.keys()):
            if json.dumps(edges1[eid], sort_keys=True) != json.dumps(edges2[eid], sort_keys=True):
                edges_modified.append({
                    'id': eid,
                    'old': edges1[eid],
                    'new': edges2[eid],
                })
        
        return VersionCompareResult(
            from_version=from_version,
            to_version=to_version,
            nodes_added=nodes_added,
            nodes_removed=nodes_removed,
            nodes_modified=nodes_modified,
            edges_added=edges_added,
            edges_removed=edges_removed,
            edges_modified=edges_modified,
        )
    
    # ========== 分支功能 ==========
    
    def create_branch(self, request: CreateBranchRequest, user_id: str) -> WorkflowBranch:
        """创建分支"""
        workflow_id = request.workflow_id
        
        # 验证基础版本存在
        base_version = self.get_version(workflow_id, request.base_version)
        if not base_version:
            raise ValueError(f"基础版本 {request.base_version} 不存在")
        
        # 创建分支
        branch = WorkflowBranch(
            id=str(uuid4()),
            workflow_id=workflow_id,
            name=request.name,
            description=request.description,
            base_version=request.base_version,
            current_version=request.base_version,
            created_by=user_id,
            created_at=datetime.now(),
            is_active=True,
        )
        
        if workflow_id not in self.branches:
            self.branches[workflow_id] = []
        self.branches[workflow_id].append(branch)
        
        return branch
    
    def get_branches(self, workflow_id: str) -> List[WorkflowBranch]:
        """获取分支列表"""
        return self.branches.get(workflow_id, [])
    
    def get_branch(self, workflow_id: str, branch_id: str) -> Optional[WorkflowBranch]:
        """获取指定分支"""
        branches = self.branches.get(workflow_id, [])
        for b in branches:
            if b.id == branch_id:
                return b
        return None
    
    def delete_branch(self, workflow_id: str, branch_id: str) -> bool:
        """删除分支"""
        branches = self.branches.get(workflow_id, [])
        for i, b in enumerate(branches):
            if b.id == branch_id:
                branches.pop(i)
                return True
        return False
    
    def cleanup_old_versions(self, workflow_id: str, keep_count: int = 50) -> int:
        """清理旧版本（保留最近的N个）"""
        versions = self.versions.get(workflow_id, [])
        if len(versions) <= keep_count:
            return 0
        
        # 按版本号排序
        sorted_versions = sorted(versions, key=lambda v: v.version, reverse=True)
        
        # 保留最近的版本
        to_keep = sorted_versions[:keep_count]
        to_remove = sorted_versions[keep_count:]
        
        self.versions[workflow_id] = to_keep
        
        return len(to_remove)


# 全局服务实例
version_service = VersionService()
