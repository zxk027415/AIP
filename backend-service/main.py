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
# @AI_GENERATED
from api.precision_ops import router as precision_ops_router  # 精度运营路由
# @AI_GENERATED: end
from api.scheduler import router as scheduler_router, set_scheduler_engine

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

    # @AI_GENERATED
    # 数据库连通性校验 — 在初始化 DBAdapter 之前主动校验配置和连通性。
    # 依赖 services/db/connectivity_validator.py（返回结构化 ValidationResult）。
    # 行为契约：
    #   - status == 'config_error' 且 fatal_on_missing_vars=True → 抛 RuntimeError，
    #     阻止服务以半配置状态启动（Requirement 8.6 "启动阶段立即报错并列出所有缺失的变量名"）。
    #   - status == 'skipped'（DB_ENABLED=false）→ 打印 info 后继续，走文件存储。
    #   - status == 'unhealthy'（连接失败）→ 打印 warning 后继续，其他端点仍可服务。
    # 与运行时 /api/system/db-health 端点解耦：本处是启动阶段一次性校验，
    # /db-health 端点由 UI/探针按需实时轮询（api/system.py::get_db_health）。
    # Requirements: 8.4, 8.6
    try:
        from services.db.connectivity_validator import validate_at_startup

        _db_validation = validate_at_startup(fatal_on_missing_vars=True)
        if _db_validation.status == "healthy":
            print(
                "✓ DB 连通性校验通过："
                f"engine={_db_validation.engine} "
                f"latency={_db_validation.latency_ms}ms "
                f"url={_db_validation.connection_url_masked}"
            )
        elif _db_validation.status == "unhealthy":
            print(
                "⚠ DB 连通性异常但继续启动："
                f"error_type={_db_validation.error_type} "
                f"message={_db_validation.message} "
                f"url={_db_validation.connection_url_masked}"
            )
        else:
            # skipped：DB_ENABLED=false，或其它非致命状态
            print(
                f"ℹ DB 连通性校验：status={_db_validation.status} "
                f"message={_db_validation.message}"
            )
    except RuntimeError:
        # config_error 且 fatal_on_missing_vars=True — 直接抛出，让 uvicorn 报错
        # 并展示 validate_at_startup 生成的中文错误信息（含缺失变量名列表）
        raise
    except Exception as _db_val_exc:  # noqa: BLE001 — 兜底：验证器自身异常不阻断启动
        print(f"DB 连通性校验遇到未预期异常（非致命，继续启动）：{_db_val_exc}")
    # @AI_GENERATED: end

    # DB 层和调度器初始化（DB_ENABLED 控制是否真正连接）
    try:
        from services.db.config import DBConfig
        from services.db.adapter import DBAdapter
        from services.scheduler.engine import SchedulerEngine
        from services.scheduler.tasks.load_forecast_tasks import (
            make_data_pull_task, make_daily_rolling_task, make_accuracy_backfill_task
        )
        from services.scheduler.tasks.pv_fault_tasks import (
            make_pv_data_pull_task, make_pv_prediction_task
        )
        from services.precision_ops.production_registry import ProductionRegistry
        from services.precision_ops.version_registry import VersionRegistry
        from services.precision_ops.config_manager import ConfigManager
        from services.db.datasources.local_db_mock import (
            LocalDbMockDataSource,
            build_default_mock_feeder,
        )
        from services.db.repositories.load_forecast import LoadForecastRepository
        from services.db.repositories.pv_fault import PVFaultRepository

        _db_cfg = DBConfig()
        _db_adapter = DBAdapter(_db_cfg)
        _lf_repo = LoadForecastRepository(_db_adapter)
        from services.precision_ops._db_helper import set_lf_repo
        set_lf_repo(_lf_repo)
        _pv_repo = PVFaultRepository(_db_adapter)
        _mock_feeder = build_default_mock_feeder(_db_adapter)
        _mock_feeder.ensure_tables()
        _mock_source = LocalDbMockDataSource(_db_adapter)

        _sched_engine = SchedulerEngine()
        # @AI_GENERATED: mock_data_feed — 模拟公司生产库每天新增 96 行数据（独立于平台拉取）
        _sched_engine.register_task(
            "mock_data_feed",
            _mock_feeder.feed_next_batch,
            "0 0 * * *", "load_forecast"  # 默认每天 0:00 喂一批（比 lf_data_pull 早 1 小时）
        )
        # @AI_GENERATED: end
        _sched_engine.register_task(
            "lf_data_pull",
            make_data_pull_task(
                _mock_source,
                _lf_repo,
                "default",
            ),
            _db_cfg.sched_lf_pull_cron, "load_forecast"
        )
        # @AI_GENERATED: 改用新版 make_daily_rolling_task（严格 gap-1-day + slot config 读训练窗口）
        from services.deployment.store import DeploymentSlotStore as _SlotStore
        _slot_store_instance = _SlotStore()
        _sched_engine.register_task(
            "lf_daily_rolling",
            make_daily_rolling_task(
                _lf_repo,
                "default",
                station_id=_mock_feeder.station_id,
                feature_name=_mock_feeder.feature_name,
                slot_store=_slot_store_instance,
                production_registry=ProductionRegistry(),
                version_registry=VersionRegistry(),
            ),
            _db_cfg.sched_lf_predict_cron, "load_forecast"
        )
        # @AI_GENERATED: end
        _sched_engine.register_task(
            "lf_backfill",
            make_accuracy_backfill_task(
                _lf_repo,
                "default",
                station_id=_mock_feeder.station_id,
                feature_name=_mock_feeder.feature_name,
                slot_store=_slot_store_instance,
            ),
            _db_cfg.sched_lf_backfill_cron, "load_forecast"
        )
        _sched_engine.register_task(
            "pv_data_pull", make_pv_data_pull_task(_mock_source, _pv_repo),
            _db_cfg.sched_pv_pull_cron, "pv_fault"
        )
        _sched_engine.register_task(
            "pv_prediction", make_pv_prediction_task(_pv_repo, "models/pv_fault.pkl"),
            _db_cfg.sched_pv_predict_cron, "pv_fault"
        )
        set_scheduler_engine(_sched_engine)
        app._db_adapter = _db_adapter  # store for shutdown
        print("✓ DBAdapter 和 SchedulerEngine 初始化完成")

        # @AI_GENERATED: 阶段 3 — 启动时预置 tasks.json 种子（幂等，已存在则不覆盖）
        _seed_scheduler_tasks(_db_cfg)
        # @AI_GENERATED: end
    except Exception as e:
        print(f"DBAdapter/SchedulerEngine 初始化失败（非致命）: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        if hasattr(app, '_db_adapter') and app._db_adapter:
            app._db_adapter.dispose()
            print("✓ DBAdapter 已关闭")
    except Exception as e:
        print(f"DBAdapter 关闭失败: {e}")


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
# @AI_GENERATED
app.include_router(precision_ops_router)  # 精度运营路由
# @AI_GENERATED: end
app.include_router(scheduler_router)  # 调度器状态路由

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

# @AI_GENERATED: 阶段 3 — 启动时预置 tasks.json 种子函数
def _seed_scheduler_tasks(db_cfg) -> None:
    """
    启动时把 5 条默认 cron 任务写入 tasks.json（幂等，已存在则不覆盖）。

    以 tasks.json 为运行时唯一真源：
      - 初次启动时 tasks.json 不存在 → 全部写入
      - 后续启动时 tasks.json 已有记录 → 保留用户改过的 cron_expr，不覆盖

    默认 5 条任务（cron 表达式来自 configs/db.yaml）：
      lf_data_pull      — 负荷预测数据拉取
      lf_daily_rolling  — 负荷预测每日滚动训练+预测
      lf_accuracy_backfill — 负荷预测精度回填
      pv_data_pull      — 光伏故障数据拉取
      pv_prediction     — 光伏故障预测
    """
    try:
        from services.deployment.scheduler_store import SchedulerStore
        from services.deployment.scheduler_models import ScheduledTask

        store = SchedulerStore()
        now = __import__('datetime').datetime.now().isoformat()

        _DEFAULT_TASKS = [
            {
                "task_id": "mock_data_feed",
                "name": "模拟喂数据 — 公司生产库每天新增 96 行",
                "pipeline": "load_forecast",
                "schedule_type": "cron",
                "cron_expr": "0 0 * * *",
                "slot": "default",
            },
            {
                "task_id": "lf_data_pull",
                "name": "负荷预测 — 数据拉取（从公司库拉到平台库）",
                "pipeline": "load_forecast",
                "schedule_type": "cron",
                "cron_expr": getattr(db_cfg, "sched_lf_pull_cron", "0 1 * * *"),
                "slot": "default",
            },
            {
                "task_id": "lf_daily_rolling",
                "name": "负荷预测 — 每日滚动训练+预测（gap-1-day，预测 T+1）",
                "pipeline": "load_forecast",
                "schedule_type": "cron",
                "cron_expr": getattr(db_cfg, "sched_lf_predict_cron", "30 1 * * *"),
                "slot": "default",
            },
            {
                "task_id": "lf_accuracy_backfill",
                "name": "负荷预测 — 精度回填（用 T 真值补 T-1 预测精度）",
                "pipeline": "load_forecast",
                "schedule_type": "cron",
                "cron_expr": getattr(db_cfg, "sched_lf_backfill_cron", "0 4 * * *"),
                "slot": "default",
            },
            {
                "task_id": "pv_data_pull",
                "name": "光伏故障 — 数据拉取",
                "pipeline": "pv_fault",
                "schedule_type": "cron",
                "cron_expr": getattr(db_cfg, "sched_pv_pull_cron", "0 2 * * *"),
                "slot": "default",
            },
            {
                "task_id": "pv_prediction",
                "name": "光伏故障 — 预测",
                "pipeline": "pv_fault",
                "schedule_type": "cron",
                "cron_expr": getattr(db_cfg, "sched_pv_predict_cron", "30 2 * * *"),
                "slot": "default",
            },
        ]

        seeded = 0
        for defaults in _DEFAULT_TASKS:
            # 已存在则跳过（不覆盖用户改过的 cron_expr）
            if store.get_task(defaults["task_id"]) is not None:
                continue
            try:
                task = ScheduledTask(
                    **defaults,
                    trigger_time="02:00",
                    status="stopped",
                    retry_on_failure=True,
                    max_retries=3,
                    created_at=now,
                    updated_at=now,
                )
                store.upsert_task(task)
                seeded += 1
            except Exception as _e:
                print(f"  seed task {defaults['task_id']} 失败（跳过）: {_e}")

        if seeded > 0:
            print(f"✓ tasks.json 种子写入：{seeded} 条新任务")
        else:
            print("✓ tasks.json 已有种子，无需重新写入")

    except Exception as e:
        print(f"tasks.json 种子写入失败（非致命）: {e}")
# @AI_GENERATED: end

    # @AI_GENERATED: Phase 1 双写 — B' 类静态配置文件 → MySQL 镜像同步
    # 三份 Git-tracked 权威配置文件（search_space_registry / feature_recipes / production_workflow_registry）
    # 按 SHA-256 幂等同步到 DB，供后续跨机器统一读。
    # 失败降级 warning（非致命），不阻塞其他 startup 步骤。
    try:
        from services.db.repositories.registry_sync import sync_all_from_files
        _sync_summary = sync_all_from_files()
        if isinstance(_sync_summary, dict) and _sync_summary.get("error"):
            print(f"⚠ 静态配置 sync 失败（非致命）: {_sync_summary['error']}")
        else:
            for _table_name, _stats in (_sync_summary or {}).items():
                if not isinstance(_stats, dict):
                    continue
                print(
                    f"✓ 静态配置 sync [{_table_name}]: "
                    f"scanned={_stats.get('scanned', 0)} "
                    f"upserted={_stats.get('upserted', 0)} "
                    f"unchanged={_stats.get('unchanged', 0)} "
                    f"errors={len(_stats.get('errors', []))}"
                )
    except Exception as _sync_exc:
        print(f"静态配置 sync 遇到未预期异常（非致命）: {_sync_exc}")
    # @AI_GENERATED: end
