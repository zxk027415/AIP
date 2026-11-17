# @AI_GENERATED: Kiro v1.0
"""
算法模板 Skill 打包 API
提供模板打包为 Skill 的接口（使用数据库）
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
from sqlalchemy.orm import Session

from database import get_db
from models.algo_template import Skill as SkillModel

router = APIRouter(prefix="/api/skills", tags=["template-skill"])


class TrainingConfig(BaseModel):
    """训练配置"""
    enabled: bool = True
    min_samples: int = 30
    default_epochs: int = 80
    default_batch_size: int = 32


class ResourceConfig(BaseModel):
    """资源配置"""
    cpu: str = "2"
    memory: str = "4Gi"
    gpu: str = "optional"
    timeout_seconds: int = 300


class SkillPackageRequest(BaseModel):
    """Skill 打包请求"""
    template_id: str
    template_name: str
    template_version: str
    skill_name: str
    skill_version: str
    description: Optional[str] = ""
    training_config: TrainingConfig
    resource_config: ResourceConfig


class UpdateSkillRequest(BaseModel):
    """更新 Skill 请求"""
    skill_name: Optional[str] = None
    skill_version: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    training_config: Optional[TrainingConfig] = None
    resource_config: Optional[ResourceConfig] = None


@router.post("/package")
async def package_template(request: SkillPackageRequest, db: Session = Depends(get_db)):
    """将算法模板打包为 Skill"""
    # 检查是否已存在同名同版本的 Skill
    existing = db.query(SkillModel).filter(
        SkillModel.skill_name == request.skill_name,
        SkillModel.skill_version == request.skill_version
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{request.skill_name}' v{request.skill_version} 已存在"
        )
    
    # 生成 Skill ID
    skill_id = f"skill-{uuid.uuid4().hex[:8]}"
    now = datetime.now()
    
    # 创建 Skill 记录
    new_skill = SkillModel(
        id=skill_id,
        skill_name=request.skill_name,
        skill_version=request.skill_version,
        description=request.description,
        source_template_id=request.template_id,
        source_template_name=request.template_name,
        source_template_version=request.template_version,
        training_enabled=request.training_config.enabled,
        training_min_samples=request.training_config.min_samples,
        training_default_epochs=request.training_config.default_epochs,
        training_default_batch_size=request.training_config.default_batch_size,
        resource_cpu=request.resource_config.cpu,
        resource_memory=request.resource_config.memory,
        resource_gpu=request.resource_config.gpu,
        resource_timeout=request.resource_config.timeout_seconds,
        status="packaged",
        created_at=now,
        updated_at=now,
        created_by="system"
    )
    
    db.add(new_skill)
    db.commit()
    db.refresh(new_skill)
    
    return {
        "success": True,
        "skill_id": skill_id,
        "message": f"Skill '{request.skill_name}' 打包成功"
    }


@router.get("/list")
async def list_skills(db: Session = Depends(get_db)):
    """获取所有已打包的 Skills"""
    skills = db.query(SkillModel).all()
    return {
        "total": len(skills),
        "skills": [s.to_dict() for s in skills]
    }


@router.get("/{skill_id}")
async def get_skill(skill_id: str, db: Session = Depends(get_db)):
    """获取单个 Skill 详情"""
    skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' 不存在")
    
    return skill.to_dict()


@router.put("/{skill_id}")
async def update_skill(
    skill_id: str,
    request: UpdateSkillRequest,
    db: Session = Depends(get_db)
):
    """更新 Skill"""
    skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' 不存在")
    
    # 更新字段
    if request.skill_name is not None:
        skill.skill_name = request.skill_name
    if request.skill_version is not None:
        skill.skill_version = request.skill_version
    if request.description is not None:
        skill.description = request.description
    if request.status is not None:
        skill.status = request.status
    
    # 更新训练配置
    if request.training_config is not None:
        skill.training_enabled = request.training_config.enabled
        skill.training_min_samples = request.training_config.min_samples
        skill.training_default_epochs = request.training_config.default_epochs
        skill.training_default_batch_size = request.training_config.default_batch_size
    
    # 更新资源配置
    if request.resource_config is not None:
        skill.resource_cpu = request.resource_config.cpu
        skill.resource_memory = request.resource_config.memory
        skill.resource_gpu = request.resource_config.gpu
        skill.resource_timeout = request.resource_config.timeout_seconds
    
    skill.updated_at = datetime.now()
    
    db.commit()
    db.refresh(skill)
    
    return {
        "success": True,
        "message": f"Skill '{skill.skill_name}' 更新成功",
        "skill": skill.to_dict(),
    }


@router.delete("/{skill_id}")
async def delete_skill(skill_id: str, db: Session = Depends(get_db)):
    """删除 Skill"""
    skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' 不存在")
    
    name = skill.skill_name
    db.delete(skill)
    db.commit()
    
    return {"success": True, "message": f"Skill '{name}' 已删除"}
# @AI_GENERATED: end
