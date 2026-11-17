# @AI_GENERATED: Kiro v1.0
"""
算法库管理数据模型
包含算法分类、算法函数、版本历史和审计日志的SQLAlchemy模型
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class AlgorithmCategory(Base):
    """算法分类表"""
    __tablename__ = "algorithm_categories"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(String(50), ForeignKey("algorithm_categories.id"), nullable=True)
    icon = Column(String(50), nullable=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    parent = relationship("AlgorithmCategory", remote_side=[id], backref="children")
    functions = relationship("AlgorithmFunction", back_populates="category_rel", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AlgorithmCategory(id='{self.id}', name='{self.name}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_id": self.parent_id,
            "icon": self.icon,
            "display_order": self.display_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AlgorithmFunction(Base):
    """算法函数表"""
    __tablename__ = "algorithm_functions"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    category_id = Column(String(50), ForeignKey("algorithm_categories.id"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    parameters = Column(JSON, nullable=False)
    return_type = Column(String(20), nullable=False)
    examples = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)  # SQLite不支持ARRAY，用JSON代替
    status = Column(String(20), default="published", index=True)  # draft/published/deprecated
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # 关系
    category_rel = relationship("AlgorithmCategory", back_populates="functions")
    versions = relationship("AlgorithmVersion", back_populates="function_rel", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_functions_name", "name"),
    )

    def __repr__(self):
        return f"<AlgorithmFunction(id='{self.id}', name='{self.name}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category_id": self.category_id,
            "description": self.description,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "examples": self.examples,
            "tags": self.tags,
            "status": self.status,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }

    def to_legacy_dict(self):
        """转换为兼容functions.json的格式"""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category_id,
            "description": self.description,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "examples": self.examples or [],
        }


class AlgorithmVersion(Base):
    """算法版本历史表"""
    __tablename__ = "algorithm_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    function_id = Column(String(50), ForeignKey("algorithm_functions.id"), nullable=False)
    version = Column(Integer, nullable=False)
    data_snapshot = Column(JSON, nullable=False)
    change_description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    # 关系
    function_rel = relationship("AlgorithmFunction", back_populates="versions")

    __table_args__ = (
        Index("idx_versions_function", "function_id", "version"),
    )

    def __repr__(self):
        return f"<AlgorithmVersion(function_id='{self.function_id}', version={self.version})>"

    def to_dict(self):
        return {
            "id": self.id,
            "function_id": self.function_id,
            "version": self.version,
            "data_snapshot": self.data_snapshot,
            "change_description": self.change_description,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AlgorithmAuditLog(Base):
    """算法审计日志表"""
    __tablename__ = "algorithm_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False)  # create/update/delete/publish/deprecate/rollback
    object_type = Column(String(20), nullable=False)  # category/function
    object_id = Column(String(50), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    data_before = Column(JSON, nullable=True)
    data_after = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_audit_user", "user_id", "created_at"),
        Index("idx_audit_object", "object_type", "object_id", "created_at"),
        Index("idx_audit_action", "action", "created_at"),
    )

    def __repr__(self):
        return f"<AlgorithmAuditLog(action='{self.action}', object_type='{self.object_type}', object_id='{self.object_id}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "ip_address": self.ip_address,
            "data_before": self.data_before,
            "data_after": self.data_after,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
# @AI_GENERATED: end
