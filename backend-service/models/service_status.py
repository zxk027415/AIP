"""
服务状态模型
记录服务启动时间和状态
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from database import Base

class ServiceStatus(Base):
    """服务状态表"""
    __tablename__ = "service_status"
    
    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String(100), index=True, nullable=False)  # 服务名称：frontend, backend, database
    service_type = Column(String(50), nullable=False)  # 服务类型：web, api, db
    status = Column(String(50), nullable=False)  # 状态：running, stopped, error
    start_time = Column(DateTime, nullable=False)  # 启动时间
    last_check_time = Column(DateTime, default=func.now(), onupdate=func.now())  # 最后检查时间
    is_active = Column(Boolean, default=True)  # 是否为当前活动记录
    version = Column(String(100), nullable=True)  # 服务版本
    host = Column(String(255), nullable=True)  # 主机地址
    port = Column(Integer, nullable=True)  # 端口号
    
    def __repr__(self):
        return f"<ServiceStatus(service_name='{self.service_name}', status='{self.status}', start_time='{self.start_time}')>"
