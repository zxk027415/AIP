from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
import time
import traceback
import os
from pathlib import Path

# 自动加载 .env.local（确保 GLM 等环境变量无论启动方式都能生效）
from dotenv import load_dotenv
_env_local = Path(__file__).resolve().parent / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local, override=False)

import numpy as np

# NumPy compatibility shim for older third-party libraries (e.g. bayes_opt)
# that still access removed aliases in NumPy 2.x.
if not hasattr(np, "float"):
    np.float = float  # type: ignore[attr-defined]
if not hasattr(np, "int"):
    np.int = int  # type: ignore[attr-defined]

# 导入 API 路由
from api.matrix import router as matrix_router
from api.functions import router as functions_router
from api.auth import router as auth_router
from api.workflows import router as workflows_router
from api.workflows_enhanced import router as workflows_enhanced_router
from api.templates import router as templates_router
from api.system import router as system_router
from api.algorithm_test import router as algorithm_test_router
from api.upload import router as upload_router
from api.industry import router as industry_router
# @AI_GENERATED: Kiro v1.0
from api.workflow_agent import router as workflow_agent_router
from api.algorithm_solutions import router as algorithm_solutions_router
from api.backtest import router as backtest_router
from api.deployment import router as deployment_router
from api.algorithm_ops import router as algorithm_ops_router
from api.algo_template_skill import router as algo_template_skill_router
from api.algo_template_workflow import router as algo_template_workflow_router
# @AI_GENERATED: Kiro v1.0
from api.algorithm_agent import router as algorithm_agent_router
from api.llm_config import router as llm_config_router
# @AI_GENERATED: end
# @AI_GENERATED
from api.load_forecast import router as load_forecast_router
# @AI_GENERATED: end
# @AI_GENERATED
from api.iterative_labeling import router as iterative_labeling_router
# @AI_GENERATED: end

# 导入数据库初始化
from database import init_db

# 记录服务启动时间
SERVER_START_TIME = time.time()
SERVER_START_DATETIME = datetime.now()

app = FastAPI(
    title="工业AI算法平台 API",
    description="提供矩阵计算、算法模板执行、AI算法库等功能的后端 API",
    version="0.2.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite 开发服务器
        "http://localhost:3000",  # 备用端口
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# @AI_GENERATED: Kiro v1.0
# 全局异常处理器 - 确保错误响应也包含 CORS 头并打印详细错误
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    error_detail = traceback.format_exc()
    print(f"❌ 全局异常捕获:")
    print(f"   路径: {request.url.path}")
    print(f"   方法: {request.method}")
    print(f"   异常类型: {type(exc).__name__}")
    print(f"   异常信息: {str(exc)}")
    print(f"   详细堆栈:\n{error_detail}")
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{type(exc).__name__}: {str(exc)}",
            "path": request.url.path,
        },
        headers={
            "Access-Control-Allow-Origin": "http://localhost:5173",
            "Access-Control-Allow-Credentials": "true",
        }
    )
# @AI_GENERATED: end

# 初始化数据库
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库并记录服务状态"""
    from database import SessionLocal
    from models.service_status import ServiceStatus
    from datetime import datetime
    
    init_db()
    print("数据库初始化完成")
    
    # 记录后端服务启动
    try:
        db = SessionLocal()
        # 将之前的后端服务记录设为非活动
        db.query(ServiceStatus).filter(
            ServiceStatus.service_name == "backend",
            ServiceStatus.is_active == True
        ).update({"is_active": False})
        
        # 创建新的后端服务记录
        backend_status = ServiceStatus(
            service_name="backend",
            service_type="api",
            status="running",
            start_time=datetime.now(),
            last_check_time=datetime.now(),
            is_active=True,
            version="0.2.0",
            host="localhost",
            port=8080
        )
        db.add(backend_status)
        db.commit()
        print(f"✓ 后端服务状态已记录到数据库: {backend_status.start_time}")
        db.close()
    except Exception as e:
        print(f"记录后端服务状态失败: {e}")

    # AutoResearch：服务重启后将磁盘上仍为 running/waiting_review 的 run 标记为 interrupted
    try:
        from services.autoresearch_run_store import AutoResearchRunStore
        _store = AutoResearchRunStore()
        marked = _store.scan_and_mark_interrupted()
        if marked:
            print(f"✓ AutoResearch：已将 {len(marked)} 个中断 run 标记为 interrupted: {marked}")
        else:
            print("✓ AutoResearch：无需标记中断 run")
    except Exception as e:
        print(f"AutoResearch interrupted 标记失败: {e}")

    # AutoResearch Job Queue：标记心跳超时的 worker job
    try:
        from services.autoresearch_job_queue import mark_dead_workers
        dead = mark_dead_workers()
        if dead:
            print(f"✓ AutoResearch Job Queue：已标记 {len(dead)} 个死亡 worker: {dead}")
        else:
            print("✓ AutoResearch Job Queue：无死亡 worker")
    except Exception as e:
        print(f"AutoResearch Job Queue 检查失败: {e}")

# 注册路由
# 注意：更具体的路由要先注册，避免被通用路由拦截
app.include_router(auth_router, prefix="/api")
# @AI_GENERATED: Kiro v1.0
app.include_router(workflow_agent_router)  # Workflow Agent 路由 - 优先注册
# @AI_GENERATED: end
app.include_router(system_router)  # 系统监控路由 - 提前注册
app.include_router(matrix_router)
app.include_router(functions_router)
app.include_router(workflows_enhanced_router)  # 先注册增强版算法模板路由
app.include_router(workflows_router)  # 再注册普通算法模板路由
app.include_router(templates_router)
app.include_router(algorithm_test_router)
app.include_router(upload_router)
app.include_router(industry_router)
app.include_router(algorithm_solutions_router)
app.include_router(backtest_router)
app.include_router(deployment_router)
app.include_router(algorithm_ops_router)
app.include_router(algo_template_skill_router)
app.include_router(algo_template_workflow_router)
# @AI_GENERATED: Kiro v1.0
app.include_router(algorithm_agent_router)  # Algorithm Agent 路由
app.include_router(llm_config_router)  # LLM 配置路由
# @AI_GENERATED: end
# @AI_GENERATED
app.include_router(load_forecast_router)  # 负荷预测路由
# @AI_GENERATED: end
# @AI_GENERATED
app.include_router(iterative_labeling_router)  # 光伏故障迭代标注闭环路由
# @AI_GENERATED: end

print("已注册的路由:")
for route in app.routes:
    if hasattr(route, 'path'):
        print(f"  {route.path}")

@app.get("/")
async def root():
    return {"message": "工业AI算法平台 API", "version": "0.2.0"}

@app.get("/api/health")
async def health_check():
    """健康检查接口，返回服务状态和运行时间（从数据库读取）"""
    from database import SessionLocal
    from models.service_status import ServiceStatus
    from sqlalchemy import desc
    
    try:
        db = SessionLocal()
        # 从数据库读取后端服务状态
        backend_status = db.query(ServiceStatus).filter(
            ServiceStatus.service_name == "backend",
            ServiceStatus.is_active == True
        ).order_by(desc(ServiceStatus.start_time)).first()
        
        if backend_status:
            uptime_seconds = int((datetime.now() - backend_status.start_time).total_seconds())
            start_time = backend_status.start_time.isoformat()
        else:
            # 降级方案：使用内存中的启动时间
            uptime_seconds = int(time.time() - SERVER_START_TIME)
            start_time = SERVER_START_DATETIME.isoformat()
        
        db.close()
        
        return {
            "status": "healthy",
            "version": "0.2.0",
            "uptime_seconds": uptime_seconds,
            "start_time": start_time,
            "current_time": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error in health check: {e}")
        # 降级方案：使用内存中的启动时间
        current_time = time.time()
        uptime_seconds = int(current_time - SERVER_START_TIME)
        
        return {
            "status": "healthy",
            "version": "0.2.0",
            "uptime_seconds": uptime_seconds,
            "start_time": SERVER_START_DATETIME.isoformat(),
            "current_time": datetime.now().isoformat()
        }
