"""
模板API路由
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from api.auth import get_current_user
from services.template_service import get_template_service

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("/", response_model=List[dict])
async def list_templates(current_user: dict = Depends(get_current_user)):
    """
    获取模板列表
    """
    template_service = get_template_service()
    templates = template_service.get_all_templates()
    return templates


@router.get("/{template_id}", response_model=dict)
async def get_template(template_id: str, current_user: dict = Depends(get_current_user)):
    """
    获取指定模板详情
    """
    template_service = get_template_service()
    template = template_service.get_template(template_id)
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    return template


