# @AI_GENERATED: Kiro v1.0
"""
算法模板数据模型
包含工作流模板和 Skills 的 SQLAlchemy 模型
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    ForeignKey, JSON, Index, Float
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class WorkflowTemplate(Base):
    """工作流模板表"""
    __tablename__ = "workflow_templates"

    id = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    scenario_id = Column(String(50), nullable=True, index=True)
    scenario_name = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True, index=True)
    status = Column(String(20), default="draft", index=True)  # draft/developing/testing/published
    version = Column(String(20), default="v1.0.0")
    author = Column(String(100), nullable=True)
    
    # 模板内容
    node_count = Column(Integer, default=0)
    edge_count = Column(Integer, default=0)
    workflow_data = Column(JSON, nullable=True)  # 完整的工作流定义
    
    # 统计信息
    usage_count = Column(Integer, default=0)
    star_count = Column(Integer, default=0)
    is_starred = Column(Boolean, default=False)
    
    # 标签
    tags = Column(JSON, nullable=True)  # ["LSTM", "时序预测"]
    
    # 时间戳
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    published_at = Column(DateTime, nullable=True)
    
    # 关系
    skills = relationship("Skill", back_populates="source_template", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_wf_tpl_scenario", "scenario_id"),
        Index("idx_wf_tpl_status", "status"),
        Index("idx_wf_tpl_category", "category"),
    )

    def __repr__(self):
        return f"<WorkflowTemplate(id='{self.id}', name='{self.name}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "category": self.category,
            "status": self.status,
            "version": self.version,
            "author": self.author,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "usage_count": self.usage_count,
            "star_count": self.star_count,
            "is_starred": self.is_starred,
            "tags": self.tags or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }


class Skill(Base):
    """Skill 表（打包后的算法模板）"""
    __tablename__ = "skills"

    id = Column(String(50), primary_key=True)
    skill_name = Column(String(200), nullable=False)
    skill_version = Column(String(20), default="1.0.0")
    description = Column(Text, nullable=True)
    
    # 来源模板
    source_template_id = Column(String(50), ForeignKey("workflow_templates.id"), nullable=True)
    source_template_name = Column(String(200), nullable=True)
    source_template_version = Column(String(20), nullable=True)
    
    # 训练配置
    training_enabled = Column(Boolean, default=True)
    training_min_samples = Column(Integer, default=30)
    training_default_epochs = Column(Integer, default=80)
    training_default_batch_size = Column(Integer, default=32)
    
    # 资源配置
    resource_cpu = Column(String(20), default="2")
    resource_memory = Column(String(20), default="4Gi")
    resource_gpu = Column(String(20), default="optional")  # none/optional/required
    resource_timeout = Column(Integer, default=300)  # 秒
    
    # 状态
    status = Column(String(20), default="packaged", index=True)  # packaged/training/ready/deployed
    
    # 时间戳
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_by = Column(String(50), default="system")
    
    # 关系
    source_template = relationship("WorkflowTemplate", back_populates="skills")

    __table_args__ = (
        Index("idx_skill_status", "status"),
        Index("idx_skill_template", "source_template_id"),
    )

    def __repr__(self):
        return f"<Skill(id='{self.id}', name='{self.skill_name}')>"

    def to_dict(self):
        return {
            "skill_id": self.id,
            "skill_name": self.skill_name,
            "skill_version": self.skill_version,
            "description": self.description,
            "source_template_id": self.source_template_id,
            "source_template_name": self.source_template_name,
            "source_template_version": self.source_template_version,
            "training_config": {
                "enabled": self.training_enabled,
                "min_samples": self.training_min_samples,
                "default_epochs": self.training_default_epochs,
                "default_batch_size": self.training_default_batch_size,
            },
            "resource_config": {
                "cpu": self.resource_cpu,
                "memory": self.resource_memory,
                "gpu": self.resource_gpu,
                "timeout_seconds": self.resource_timeout,
            },
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
        }
# @AI_GENERATED: end
