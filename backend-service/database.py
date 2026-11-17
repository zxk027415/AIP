"""
数据库配置
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

# @AI_GENERATED
# 数据库连接串：优先读环境变量 DB_CONNECTION_URL（MySQL）；
# 未设置时降级到本地 SQLite，保证零配置也能启动。
# 生产/开发环境在 .env.local 或 .aip.local.env 中设置 DB_CONNECTION_URL。
_db_url_from_env = os.environ.get("DB_CONNECTION_URL", "").strip()
if _db_url_from_env:
    DATABASE_URL = _db_url_from_env
    # MySQL：不传 check_same_thread（SQLite 专用参数）
    _engine_kwargs: dict = {}
else:
    # 降级到本地 SQLite
    DATABASE_DIR = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(DATABASE_DIR, exist_ok=True)
    DATABASE_URL = f"sqlite:///{os.path.join(DATABASE_DIR, 'users.db')}"
    _engine_kwargs = {"connect_args": {"check_same_thread": False}}
# @AI_GENERATED: end

# 兜底：确保 SQLite 的 data 目录存在（MySQL 模式下也不报错）
_data_dir = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(_data_dir, exist_ok=True)

# 创建数据库引擎
engine = create_engine(DATABASE_URL, **_engine_kwargs)  # type: ignore[arg-type]

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()


class User(Base):
    """用户表模型"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    hashed_password = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    workflows = relationship("Workflow", back_populates="owner", cascade="all, delete-orphan")
    workflow_executions = relationship("WorkflowExecution", back_populates="user", cascade="all, delete-orphan")


class Workflow(Base):
    """算法模板表模型"""
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workflow_data = Column(Text, nullable=False)  # JSON格式的算法模板定义
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    owner = relationship("User", back_populates="workflows")
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowExecution(Base):
    """算法模板执行记录表模型"""
    __tablename__ = "workflow_executions"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)  # pending, running, completed, failed
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    execution_data = Column(Text, nullable=True)  # JSON格式的执行结果
    error_message = Column(Text, nullable=True)
    
    # 关系
    workflow = relationship("Workflow", back_populates="executions")
    user = relationship("User", back_populates="workflow_executions")


# 创建所有表
def init_db():
    """初始化数据库"""
    # 导入所有模型以确保它们被注册
    from models.service_status import ServiceStatus
    from models.algorithm import (
        AlgorithmCategory, AlgorithmFunction,
        AlgorithmVersion, AlgorithmAuditLog
    )
    # @AI_GENERATED: Kiro v1.0
    from models.workflow_agent_db import (
        WorkflowAgentTemplate, WorkflowAgentAuditLog,
        DomainConstraintRecord, BestPracticeRecord
    )
    from models.algo_template import WorkflowTemplate, Skill
    # @AI_GENERATED: end
    Base.metadata.create_all(bind=engine)


# 获取数据库会话
def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
