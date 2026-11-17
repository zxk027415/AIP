# @AI_GENERATED: Kiro v1.0
"""
Workflow Agent 数据库 ORM 模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from datetime import datetime
from database import Base


class WorkflowAgentTemplate(Base):
    """Workflow Agent 增强模板表"""
    __tablename__ = "workflow_agent_templates"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scenario_id = Column(String(64), nullable=True, index=True)
    category = Column(String(64), nullable=True)
    tags = Column(Text, nullable=True)  # JSON array
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    visibility = Column(String(20), default="private")
    workflow_data = Column(Text, nullable=False)  # JSON: WorkflowDefinition
    version = Column(Integer, default=1)
    parent_version_id = Column(String(64), nullable=True)
    load_count = Column(Integer, default=0)
    fork_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkflowAgentAuditLog(Base):
    """Workflow Agent 审计日志表"""
    __tablename__ = "workflow_agent_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_name = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    workflow_id = Column(String(64), nullable=True, index=True)
    template_id = Column(String(64), nullable=True)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    execution_duration_ms = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)


class DomainConstraintRecord(Base):
    """业务约束记录表（用户自定义约束）"""
    __tablename__ = "domain_constraint_overrides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scenario_id = Column(String(64), nullable=False, index=True)
    constraint_key = Column(String(128), nullable=False)
    constraint_type = Column(String(32), nullable=False)
    constraint_value = Column(Text, nullable=False)  # JSON
    description = Column(Text, nullable=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(String(64), nullable=True)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


class BestPracticeRecord(Base):
    """最佳实践记录表"""
    __tablename__ = "best_practices"

    id = Column(String(64), primary_key=True)
    scenario_id = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    algorithm_combination = Column(Text, nullable=False)  # JSON
    key_parameters = Column(Text, nullable=True)  # JSON
    achieved_metrics = Column(Text, nullable=True)  # JSON
    applicability_notes = Column(Text, nullable=True)
    contributor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    effectiveness_rating = Column(Integer, default=0)
    version = Column(Integer, default=1)
    is_system = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
# @AI_GENERATED: end
