# @AI_GENERATED: Kiro v1.0
"""
算法工作流模板 API
提供工作流模板的 CRUD 接口（使用数据库）
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from database import get_db
from models.algo_template import WorkflowTemplate as WorkflowTemplateModel

router = APIRouter(prefix="/api/workflow-templates", tags=["algo-template-workflow"])


class WorkflowTemplateResponse(BaseModel):
    """工作流模板响应"""
    id: str
    name: str
    description: Optional[str] = None
    scenario_id: Optional[str] = None
    scenario_name: Optional[str] = None
    category: Optional[str] = None
    status: str = "draft"
    version: str = "v1.0.0"
    author: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    published_at: Optional[str] = None
    node_count: int = 0
    edge_count: int = 0
    usage_count: int = 0
    star_count: int = 0
    tags: List[str] = []
    is_starred: bool = False


class CreateTemplateRequest(BaseModel):
    """创建模板请求"""
    name: str
    description: str
    scenario_id: str
    scenario_name: str
    category: str
    tags: List[str] = []


class UpdateTemplateRequest(BaseModel):
    """更新模板请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    scenario_id: Optional[str] = None
    scenario_name: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    version: Optional[str] = None
    tags: Optional[List[str]] = None


@router.get("/list")
async def list_templates(
    status: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取工作流模板列表"""
    query = db.query(WorkflowTemplateModel)
    
    # 筛选
    if status:
        query = query.filter(WorkflowTemplateModel.status == status)
    if category:
        query = query.filter(WorkflowTemplateModel.category == category)
    
    templates = query.all()
    
    # 统计（全部数据）
    all_templates = db.query(WorkflowTemplateModel).all()
    stats = {
        "total": len(all_templates),
        "published": len([t for t in all_templates if t.status == "published"]),
        "testing": len([t for t in all_templates if t.status == "testing"]),
        "developing": len([t for t in all_templates if t.status == "developing"]),
        "draft": len([t for t in all_templates if t.status == "draft"]),
    }
    
    return {
        "total": len(templates),
        "templates": [t.to_dict() for t in templates],
        "stats": stats,
    }


@router.get("/{template_id}")
async def get_template(template_id: str, db: Session = Depends(get_db)):
    """获取单个模板详情"""
    template = db.query(WorkflowTemplateModel).filter(
        WorkflowTemplateModel.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 '{template_id}' 不存在")
    
    return template.to_dict()


@router.post("/create")
async def create_template(request: CreateTemplateRequest, db: Session = Depends(get_db)):
    """创建新模板"""
    import uuid
    template_id = f"tpl-{uuid.uuid4().hex[:8]}"
    now = datetime.now()
    
    new_template = WorkflowTemplateModel(
        id=template_id,
        name=request.name,
        description=request.description,
        scenario_id=request.scenario_id,
        scenario_name=request.scenario_name,
        category=request.category,
        status="draft",
        version="v0.1.0",
        author="system",
        tags=request.tags,
        created_at=now,
        updated_at=now,
    )
    
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    
    return {
        "success": True,
        "template_id": template_id,
        "message": f"模板 '{request.name}' 创建成功",
    }


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    request: UpdateTemplateRequest,
    db: Session = Depends(get_db)
):
    """更新模板"""
    template = db.query(WorkflowTemplateModel).filter(
        WorkflowTemplateModel.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 '{template_id}' 不存在")
    
    # 更新字段
    if request.name is not None:
        template.name = request.name
    if request.description is not None:
        template.description = request.description
    if request.scenario_id is not None:
        template.scenario_id = request.scenario_id
    if request.scenario_name is not None:
        template.scenario_name = request.scenario_name
    if request.category is not None:
        template.category = request.category
    if request.status is not None:
        template.status = request.status
        # 如果状态变为 published，记录发布时间
        if request.status == "published" and not template.published_at:
            template.published_at = datetime.now()
    if request.version is not None:
        template.version = request.version
    if request.tags is not None:
        template.tags = request.tags
    
    template.updated_at = datetime.now()
    
    db.commit()
    db.refresh(template)
    
    return {
        "success": True,
        "message": f"模板 '{template.name}' 更新成功",
        "template": template.to_dict(),
    }


@router.put("/{template_id}/star")
async def toggle_star(template_id: str, db: Session = Depends(get_db)):
    """切换收藏状态"""
    template = db.query(WorkflowTemplateModel).filter(
        WorkflowTemplateModel.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 '{template_id}' 不存在")
    
    template.is_starred = not template.is_starred
    template.star_count = (template.star_count or 0) + (1 if template.is_starred else -1)
    template.updated_at = datetime.now()
    
    db.commit()
    
    return {"success": True, "is_starred": template.is_starred}


@router.delete("/{template_id}")
async def delete_template(template_id: str, db: Session = Depends(get_db)):
    """删除模板"""
    template = db.query(WorkflowTemplateModel).filter(
        WorkflowTemplateModel.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 '{template_id}' 不存在")
    
    name = template.name
    db.delete(template)
    db.commit()
    
    return {"success": True, "message": f"模板 '{name}' 已删除"}
# @AI_GENERATED: end
