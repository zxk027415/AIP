"""
增强版算法模板服务
提供算法模板的 CRUD 操作和持久化功能
"""
import json
import os
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from models.workflow_models import (
    WorkflowDefinition,
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
    WorkflowListItem
)


class WorkflowEnhancedService:
    """增强版算法模板服务"""
    
    def __init__(self, storage_path: str = "backend/data/workflows_enhanced"):
        """
        初始化算法模板服务
        
        Args:
            storage_path: 算法模板存储路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def _get_workflow_path(self, workflow_id: str) -> Path:
        """获取算法模板文件路径"""
        return self.storage_path / f"{workflow_id}.json"
    
    def _generate_workflow_id(self) -> str:
        """生成唯一的算法模板ID"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        return f"workflow-{timestamp}"
    
    async def create_workflow(self, workflow_data: WorkflowCreate, user_id: int) -> WorkflowResponse:
        """
        创建新算法模板
        
        Args:
            workflow_data: 算法模板创建数据
            user_id: 用户ID
            
        Returns:
            WorkflowResponse: 创建的算法模板
        """
        workflow_id = self._generate_workflow_id()
        now = datetime.now()
        
        # 构建算法模板响应对象
        workflow = WorkflowResponse(
            id=workflow_id,
            name=workflow_data.name,
            description=workflow_data.description,
            workflow=workflow_data.workflow,
            user_id=user_id,
            created_at=now,
            updated_at=now
        )
        
        # 保存到文件
        self._save_to_file(workflow)
        
        return workflow
    
    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowResponse]:
        """
        获取算法模板详情
        
        Args:
            workflow_id: 算法模板ID
            
        Returns:
            Optional[WorkflowResponse]: 算法模板数据，不存在则返回None
        """
        file_path = self._get_workflow_path(workflow_id)
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 转换时间字符串为 datetime 对象
            data['created_at'] = datetime.fromisoformat(data['created_at'])
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
            
            return WorkflowResponse(**data)
        except Exception as e:
            print(f"Error loading workflow {workflow_id}: {e}")
            return None
    
    async def update_workflow(
        self, 
        workflow_id: str, 
        workflow_data: WorkflowUpdate,
        user_id: int
    ) -> Optional[WorkflowResponse]:
        """
        更新算法模板
        
        Args:
            workflow_id: 算法模板ID
            workflow_data: 更新数据
            user_id: 用户ID
            
        Returns:
            Optional[WorkflowResponse]: 更新后的算法模板，不存在则返回None
        """
        # 获取现有算法模板
        existing_workflow = await self.get_workflow(workflow_id)
        
        if existing_workflow is None:
            return None
        
        # 更新字段
        update_dict = workflow_data.dict(exclude_unset=True)
        
        for field, value in update_dict.items():
            setattr(existing_workflow, field, value)
        
        # 更新时间戳
        existing_workflow.updated_at = datetime.now()
        
        # 保存到文件
        self._save_to_file(existing_workflow)
        
        return existing_workflow
    
    async def delete_workflow(self, workflow_id: str) -> bool:
        """
        删除算法模板
        
        Args:
            workflow_id: 算法模板ID
            
        Returns:
            bool: 是否删除成功
        """
        file_path = self._get_workflow_path(workflow_id)
        
        if not file_path.exists():
            return False
        
        try:
            file_path.unlink()
            return True
        except Exception as e:
            print(f"Error deleting workflow {workflow_id}: {e}")
            return False
    
    async def list_workflows(self, user_id: Optional[int] = None) -> List[WorkflowListItem]:
        """
        列出算法模板
        
        Args:
            user_id: 用户ID（可选，用于过滤）
            
        Returns:
            List[WorkflowListItem]: 算法模板列表
        """
        workflows = []
        
        for file_path in self.storage_path.glob("workflow-*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 如果指定了用户ID，则过滤
                if user_id is not None and data.get('user_id') != user_id:
                    continue
                
                # 转换时间字符串
                data['created_at'] = datetime.fromisoformat(data['created_at'])
                data['updated_at'] = datetime.fromisoformat(data['updated_at'])
                
                workflow_item = WorkflowListItem(
                    id=data['id'],
                    name=data['name'],
                    description=data.get('description'),
                    created_at=data['created_at'],
                    updated_at=data['updated_at']
                )
                
                workflows.append(workflow_item)
            except Exception as e:
                print(f"Error loading workflow from {file_path}: {e}")
                continue
        
        # 按更新时间倒序排序
        workflows.sort(key=lambda w: w.updated_at, reverse=True)
        
        return workflows
    
    def _save_to_file(self, workflow: WorkflowResponse):
        """
        保存算法模板到文件
        
        Args:
            workflow: 算法模板对象
        """
        file_path = self._get_workflow_path(workflow.id)
        
        # 转换为字典并序列化时间
        data = workflow.dict()
        data['created_at'] = workflow.created_at.isoformat()
        data['updated_at'] = workflow.updated_at.isoformat()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# 创建全局服务实例
workflow_enhanced_service = WorkflowEnhancedService()
