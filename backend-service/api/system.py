"""
系统监控 API
提供系统性能指标和统计数据
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db, User, Workflow
from models.service_status import ServiceStatus
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
import os

# @AI_GENERATED
# 数据库连通性验证器 — 用于 GET /api/system/db-health 端点
# 依赖：services/db/connectivity_validator.py（任务 12.1 已实现，返回结构化 ValidationResult）
from services.db.connectivity_validator import DBConnectivityValidator
# @AI_GENERATED: end

# 尝试导入psutil，如果失败则使用模拟数据
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not installed, using mock data for system metrics")

router = APIRouter(prefix="/api/system", tags=["system"])


class ServiceStatusCreate(BaseModel):
    """服务状态创建模型"""
    service_name: str
    service_type: str
    status: str
    version: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None


@router.get("/test")
async def test_route():
    """测试路由是否工作"""
    return {"message": "System API is working!"}


@router.get("/metrics")
async def get_system_metrics():
    """
    获取系统性能指标
    """
    if not PSUTIL_AVAILABLE:
        return {
            "cpu_percent": 45.0,
            "memory": {"percent": 62.0, "used_gb": 8.5, "total_gb": 16.0, "available_gb": 7.5},
            "disk": {"percent": 38.0, "used_gb": 150.0, "total_gb": 500.0, "free_gb": 350.0},
            "network": {"bytes_sent": 1024000, "bytes_recv": 2048000, "mb_sent": 1.0, "mb_recv": 2.0}
        }
    
    try:
        import platform
        # 使用非阻塞方式获取CPU使用率（interval=None 返回上次调用后的平均值）
        # 首次调用返回0，后续调用返回实际值
        cpu_percent = psutil.cpu_percent(interval=0)
        memory = psutil.virtual_memory()
        disk_path = 'C:\\' if platform.system() == 'Windows' else '/'
        disk = psutil.disk_usage(disk_path)
        net_io = psutil.net_io_counters()
        
        return {
            "cpu_percent": round(cpu_percent, 1),
            "memory": {
                "percent": round(memory.percent, 1),
                "used_gb": round(memory.used / (1024**3), 2),
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2)
            },
            "disk": {
                "percent": round(disk.percent, 1),
                "used_gb": round(disk.used / (1024**3), 2),
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2)
            },
            "network": {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "mb_sent": round(net_io.bytes_sent / (1024**2), 2),
                "mb_recv": round(net_io.bytes_recv / (1024**2), 2)
            }
        }
    except Exception as e:
        print(f"Error: {e}")
        return {
            "cpu_percent": 0,
            "memory": {"percent": 0, "used_gb": 0, "total_gb": 0, "available_gb": 0},
            "disk": {"percent": 0, "used_gb": 0, "total_gb": 0, "free_gb": 0},
            "network": {"bytes_sent": 0, "bytes_recv": 0, "mb_sent": 0, "mb_recv": 0}
        }


@router.get("/statistics")
async def get_statistics(db: Session = Depends(get_db)):
    """获取系统统计数据"""
    try:
        total_users = db.query(User).count()
        total_workflows = db.query(Workflow).count()
        
        return {
            "total_users": total_users,
            "active_users": 0,
            "total_workflows": total_workflows,
            "today_executions": 0
        }
    except Exception as e:
        print(f"Error: {e}")
        return {
            "total_users": 0,
            "active_users": 0,
            "total_workflows": 0,
            "today_executions": 0
        }


@router.get("/database-info")
async def get_database_info():
    """获取数据库信息"""
    try:
        db_path = "data/users.db"
        
        if os.path.exists(db_path):
            db_size_mb = round(os.path.getsize(db_path) / (1024**2), 2)
        else:
            db_size_mb = 0
        
        return {
            "size_mb": db_size_mb,
            "table_count": 5,
            "type": "SQLite",
            "path": db_path
        }
    except Exception as e:
        print(f"Error: {e}")
        return {
            "size_mb": 0,
            "table_count": 0,
            "type": "SQLite",
            "path": "data/users.db"
        }


@router.post("/service-status")
async def record_service_status(
    data: ServiceStatusCreate,
    db: Session = Depends(get_db)
):
    """
    记录服务启动状态
    
    参数:
    - service_name: 服务名称 (frontend, backend, database)
    - service_type: 服务类型 (web, api, db)
    - status: 状态 (running, stopped, error)
    - version: 服务版本
    - host: 主机地址
    - port: 端口号
    """
    try:
        # 将之前的同名服务记录设为非活动
        db.query(ServiceStatus).filter(
            ServiceStatus.service_name == data.service_name,
            ServiceStatus.is_active == True
        ).update({"is_active": False})
        
        # 创建新的服务状态记录
        service_status = ServiceStatus(
            service_name=data.service_name,
            service_type=data.service_type,
            status=data.status,
            start_time=datetime.now(),
            last_check_time=datetime.now(),
            is_active=True,
            version=data.version,
            host=data.host,
            port=data.port
        )
        
        db.add(service_status)
        db.commit()
        db.refresh(service_status)
        
        return {
            "success": True,
            "message": f"服务状态已记录: {data.service_name}",
            "service_id": service_status.id,
            "start_time": service_status.start_time.isoformat()
        }
    except Exception as e:
        db.rollback()
        print(f"Error recording service status: {e}")
        return {
            "success": False,
            "message": f"记录服务状态失败: {str(e)}"
        }


@router.get("/service-status/{service_name}")
async def get_service_status(service_name: str, db: Session = Depends(get_db)):
    """
    获取指定服务的最新状态
    
    参数:
    - service_name: 服务名称 (frontend, backend, database)
    """
    try:
        # 查询最新的活动记录
        service_status = db.query(ServiceStatus).filter(
            ServiceStatus.service_name == service_name,
            ServiceStatus.is_active == True
        ).order_by(desc(ServiceStatus.start_time)).first()
        
        if not service_status:
            return {
                "found": False,
                "message": f"未找到服务记录: {service_name}"
            }
        
        # 计算运行时间
        uptime_seconds = int((datetime.now() - service_status.start_time).total_seconds())
        
        return {
            "found": True,
            "service_name": service_status.service_name,
            "service_type": service_status.service_type,
            "status": service_status.status,
            "start_time": service_status.start_time.isoformat(),
            "uptime_seconds": uptime_seconds,
            "version": service_status.version,
            "host": service_status.host,
            "port": service_status.port,
            "last_check_time": service_status.last_check_time.isoformat()
        }
    except Exception as e:
        print(f"Error getting service status: {e}")
        return {
            "found": False,
            "message": f"查询服务状态失败: {str(e)}"
        }


@router.get("/service-status")
async def get_all_service_status(db: Session = Depends(get_db)):
    """获取所有服务的最新状态"""
    try:
        services = ["frontend", "backend", "database"]
        result = {}
        
        for service_name in services:
            service_status = db.query(ServiceStatus).filter(
                ServiceStatus.service_name == service_name,
                ServiceStatus.is_active == True
            ).order_by(desc(ServiceStatus.start_time)).first()
            
            if service_status:
                uptime_seconds = int((datetime.now() - service_status.start_time).total_seconds())
                result[service_name] = {
                    "status": service_status.status,
                    "start_time": service_status.start_time.isoformat(),
                    "uptime_seconds": uptime_seconds,
                    "version": service_status.version,
                    "host": service_status.host,
                    "port": service_status.port
                }
            else:
                result[service_name] = {
                    "status": "unknown",
                    "start_time": None,
                    "uptime_seconds": 0
                }
        
        return result
    except Exception as e:
        print(f"Error getting all service status: {e}")
        return {
            "error": f"查询服务状态失败: {str(e)}"
        }


# @AI_GENERATED
@router.get("/db-health", summary="数据库连通性健康检查")
async def get_db_health():
    """
    数据库连通性健康检查（GET /api/system/db-health）— 供前端"系统健康"面板与
    运维探针（human-readable + machine-readable）消费。

    行为矩阵：
      - ``DB_ENABLED=false``            → 200 + ``status='skipped'``（跳过连接验证）
      - 必需环境变量缺失               → 200 + ``status='config_error'``，
                                          附 ``missing_vars`` 列表（如 ``["DB_CONNECTION_URL"]``）
      - 连接失败                       → 200 + ``status='unhealthy'``，
                                          ``error_type`` ∈ {``connection_timeout``,
                                          ``auth_failure``, ``database_not_found``, ``unknown``}
      - 连接成功                       → 200 + ``status='healthy'``，
                                          附 ``latency_ms``（探测耗时，毫秒）与
                                          ``connection_url_masked``（密码脱敏后的连接串）

    重要约定：
      - 本端点**不抛出异常**：所有失败均被 ``DBConnectivityValidator`` 内部分类为
        ValidationResult；上层健康探针应基于响应体 ``status`` 字段决策，**不要**
        依赖 HTTP 状态码判断数据库是否可用。
      - 与主入口 ``main.py`` 的启动阶段致命校验解耦：本端点是"运行时探针"，
        启动阶段的强制报错由 ``validate_at_startup(fatal_on_missing_vars=True)`` 负责。

    响应字段（``ValidationResult.to_dict()``）：
      - ``status`` — 状态：healthy / unhealthy / config_error / skipped
      - ``error_type`` — 错误类型枚举，成功或跳过时为 None
      - ``message`` — 面向 UI/日志的中文可读消息
      - ``missing_vars`` — 缺失的必需环境变量名列表（仅 config_error 时非空）
      - ``latency_ms`` — SELECT 1 探测耗时（毫秒），仅 healthy 时填充
      - ``engine`` — 数据库引擎（如 "mysql"），非 config_error 时填充
      - ``connection_url_masked`` — 已脱敏（密码替换为 ``***``）的连接串

    Requirements: 8.4, 8.5, 8.6
    """
    result = DBConnectivityValidator().validate_config()
    return result.to_dict()
# @AI_GENERATED: end
