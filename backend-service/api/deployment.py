# @AI_GENERATED: Kiro v1.0
"""
算法部署上线系统 API
提供部署任务CRUD、服务管理、监控指标、告警规则等端点
"""
from fastapi import APIRouter, Query
from typing import Optional
import json, os, copy, random, math
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/deployment", tags=["deployment"])

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DEPLOY_DIR = os.path.join(DATA_DIR, "deployment")
os.makedirs(DEPLOY_DIR, exist_ok=True)


def _tasks_path():
    return os.path.join(DEPLOY_DIR, "tasks.json")


def _services_path():
    return os.path.join(DEPLOY_DIR, "services.json")


def _alerts_path():
    return os.path.join(DEPLOY_DIR, "alerts.json")


def _load_json(path: str) -> list:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _init_mock_data():
    """Initialize mock deployment data if none exist."""
    if os.path.exists(_tasks_path()):
        return
    now = datetime.now()
    tasks = [
        {
            "id": "deploy-task-001",
            "name": "负荷预测LSTM模型部署",
            "description": "部署回测排名第一的LSTM预测模型到生产环境",
            "scenario": "load-forecasting",
            "source_type": "template",
            "source_id": "lstm_forecast",
            "source_name": "LSTM时序预测",
            "backtest_task_id": "bt-task-001",
            "backtest_rank": 1,
            "deploy_config": {
                "cpu": "2核", "memory": "4GB", "gpu": "无",
                "replicas": 2, "endpoint": "/api/predict/load-forecast",
                "timeout_ms": 5000, "env_vars": {"MODEL_VERSION": "v1.2"}
            },
            "release_strategy": {
                "type": "canary", "canary_percent": 20,
                "auto_promote": True, "promote_after_minutes": 30
            },
            "status": "running",
            "created_at": (now - timedelta(days=5)).isoformat(),
            "updated_at": (now - timedelta(days=1)).isoformat(),
        },
        {
            "id": "deploy-task-002",
            "name": "光伏发电预测集成模型",
            "description": "部署集成预测算法模板用于光伏发电功率预测",
            "scenario": "pv-power-forecast",
            "source_type": "workflow",
            "source_id": "wf-pv-ensemble",
            "source_name": "光伏集成预测算法模板",
            "backtest_task_id": "bt-task-002",
            "backtest_rank": 1,
            "deploy_config": {
                "cpu": "4核", "memory": "8GB", "gpu": "1×T4",
                "replicas": 3, "endpoint": "/api/predict/pv-power",
                "timeout_ms": 10000, "env_vars": {"MODEL_VERSION": "v2.0"}
            },
            "release_strategy": {
                "type": "blue-green", "canary_percent": 0,
                "auto_promote": False, "promote_after_minutes": 0
            },
            "status": "running",
            "created_at": (now - timedelta(days=3)).isoformat(),
            "updated_at": (now - timedelta(hours=6)).isoformat(),
        },
        {
            "id": "deploy-task-003",
            "name": "故障诊断XGBoost模型",
            "description": "部署设备故障诊断分类模型",
            "scenario": "fault-diagnosis",
            "source_type": "template",
            "source_id": "xgboost_classifier",
            "source_name": "XGBoost故障分类",
            "backtest_task_id": None,
            "backtest_rank": None,
            "deploy_config": {
                "cpu": "2核", "memory": "4GB", "gpu": "无",
                "replicas": 1, "endpoint": "/api/predict/fault-diagnosis",
                "timeout_ms": 3000, "env_vars": {}
            },
            "release_strategy": {
                "type": "full", "canary_percent": 0,
                "auto_promote": False, "promote_after_minutes": 0
            },
            "status": "stopped",
            "created_at": (now - timedelta(days=10)).isoformat(),
            "updated_at": (now - timedelta(days=7)).isoformat(),
        },
        {
            "id": "deploy-task-004",
            "name": "电价预测模型部署",
            "description": "部署电力市场价格预测模型",
            "scenario": "price-forecasting",
            "source_type": "template",
            "source_id": "price_forecast_v1",
            "source_name": "电价预测模型v1",
            "backtest_task_id": None,
            "backtest_rank": None,
            "deploy_config": {
                "cpu": "1核", "memory": "2GB", "gpu": "无",
                "replicas": 1, "endpoint": "/api/predict/price",
                "timeout_ms": 5000, "env_vars": {}
            },
            "release_strategy": {
                "type": "full", "canary_percent": 0,
                "auto_promote": False, "promote_after_minutes": 0
            },
            "status": "draft",
            "created_at": (now - timedelta(hours=2)).isoformat(),
            "updated_at": (now - timedelta(hours=2)).isoformat(),
        },
    ]
    _save_json(_tasks_path(), tasks)

    # Mock services for running tasks
    services = [
        {
            "id": "svc-001",
            "task_id": "deploy-task-001",
            "name": "负荷预测LSTM服务",
            "endpoint": "http://localhost:8080/api/predict/load-forecast",
            "version": "v1.2",
            "replicas": {"desired": 2, "running": 2, "ready": 2},
            "health": "healthy",
            "qps": 45.2,
            "avg_latency_ms": 128,
            "error_rate": 0.02,
            "uptime": "5d 3h 20m",
            "created_at": (now - timedelta(days=5)).isoformat(),
            "versions": [
                {"version": "v1.0", "published_at": (now - timedelta(days=10)).isoformat(), "status": "inactive"},
                {"version": "v1.1", "published_at": (now - timedelta(days=7)).isoformat(), "status": "inactive"},
                {"version": "v1.2", "published_at": (now - timedelta(days=5)).isoformat(), "status": "active"},
            ],
        },
        {
            "id": "svc-002",
            "task_id": "deploy-task-002",
            "name": "光伏发电预测服务",
            "endpoint": "http://localhost:8080/api/predict/pv-power",
            "version": "v2.0",
            "replicas": {"desired": 3, "running": 3, "ready": 2},
            "health": "warning",
            "qps": 120.5,
            "avg_latency_ms": 256,
            "error_rate": 0.05,
            "uptime": "3d 0h 15m",
            "created_at": (now - timedelta(days=3)).isoformat(),
            "versions": [
                {"version": "v1.0", "published_at": (now - timedelta(days=8)).isoformat(), "status": "inactive"},
                {"version": "v2.0", "published_at": (now - timedelta(days=3)).isoformat(), "status": "active"},
            ],
        },
        {
            "id": "svc-003",
            "task_id": "deploy-task-003",
            "name": "故障诊断服务",
            "endpoint": "http://localhost:8080/api/predict/fault-diagnosis",
            "version": "v1.0",
            "replicas": {"desired": 1, "running": 0, "ready": 0},
            "health": "stopped",
            "qps": 0,
            "avg_latency_ms": 0,
            "error_rate": 0,
            "uptime": "0",
            "created_at": (now - timedelta(days=10)).isoformat(),
            "versions": [
                {"version": "v1.0", "published_at": (now - timedelta(days=10)).isoformat(), "status": "inactive"},
            ],
        },
    ]
    _save_json(_services_path(), services)

    # Mock alert rules and history
    alerts = {
        "rules": [
            {"id": "rule-001", "service_id": "svc-001", "metric_name": "latency_p99", "operator": "gt", "threshold": 500, "severity": "warning", "enabled": True},
            {"id": "rule-002", "service_id": "svc-001", "metric_name": "error_rate", "operator": "gt", "threshold": 0.05, "severity": "critical", "enabled": True},
            {"id": "rule-003", "service_id": "svc-002", "metric_name": "cpu_usage", "operator": "gt", "threshold": 80, "severity": "warning", "enabled": True},
            {"id": "rule-004", "service_id": "svc-002", "metric_name": "error_rate", "operator": "gt", "threshold": 0.05, "severity": "critical", "enabled": True},
        ],
        "history": [
            {"id": "alert-001", "rule_id": "rule-003", "service_id": "svc-002", "metric_name": "cpu_usage", "triggered_value": 85.3, "severity": "warning", "status": "recovered", "triggered_at": (now - timedelta(hours=12)).isoformat(), "recovered_at": (now - timedelta(hours=11)).isoformat()},
            {"id": "alert-002", "rule_id": "rule-004", "service_id": "svc-002", "metric_name": "error_rate", "triggered_value": 0.068, "severity": "critical", "status": "triggered", "triggered_at": (now - timedelta(hours=2)).isoformat(), "recovered_at": None},
        ],
    }
    _save_json(_alerts_path(), alerts)


_init_mock_data()


# ==================== 部署任务 API ====================

@router.get("/stats")
async def get_deployment_stats():
    """全局部署统计"""
    tasks = _load_json(_tasks_path())
    services = _load_json(_services_path())
    running = [s for s in services if s["health"] != "stopped"]
    stopped = [s for s in services if s["health"] == "stopped"]
    health_scores = [100 if s["health"] == "healthy" else 80 if s["health"] == "warning" else 50 if s["health"] == "unhealthy" else 0 for s in services]
    avg_health = round(sum(health_scores) / len(health_scores), 1) if health_scores else 0
    return {
        "total_deployments": len(tasks),
        "running_services": len(running),
        "stopped_services": len(stopped),
        "avg_health_score": avg_health,
    }


@router.post("/tasks")
async def create_task(body: dict):
    """创建部署任务"""
    tasks = _load_json(_tasks_path())
    now = datetime.now()
    task_id = f"deploy-task-{now.strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"
    task = {
        "id": task_id,
        "name": body.get("name", ""),
        "description": body.get("description", ""),
        "scenario": body.get("scenario", ""),
        "source_type": body.get("source_type", "template"),
        "source_id": body.get("source_id", ""),
        "source_name": body.get("source_name", ""),
        "backtest_task_id": body.get("backtest_task_id"),
        "backtest_rank": body.get("backtest_rank"),
        "deploy_config": body.get("deploy_config", {}),
        "release_strategy": body.get("release_strategy", {"type": "full"}),
        "status": "draft",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    tasks.append(task)
    _save_json(_tasks_path(), tasks)
    return task


@router.get("/tasks")
async def list_tasks(
    scenario: Optional[str] = None,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取部署任务列表"""
    tasks = _load_json(_tasks_path())
    if scenario:
        tasks = [t for t in tasks if t.get("scenario") == scenario]
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    if source_type:
        tasks = [t for t in tasks if t.get("source_type") == source_type]
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    total = len(tasks)
    start = (page - 1) * page_size
    return {"total": total, "items": tasks[start:start + page_size]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取部署任务详情"""
    tasks = _load_json(_tasks_path())
    for t in tasks:
        if t["id"] == task_id:
            return t
    return {"error": "Task not found"}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除部署任务"""
    tasks = _load_json(_tasks_path())
    tasks = [t for t in tasks if t["id"] != task_id]
    _save_json(_tasks_path(), tasks)
    return {"success": True}


@router.post("/tasks/{task_id}/clone")
async def clone_task(task_id: str):
    """克隆部署任务"""
    tasks = _load_json(_tasks_path())
    source = None
    for t in tasks:
        if t["id"] == task_id:
            source = t
            break
    if not source:
        return {"error": "Task not found"}
    now = datetime.now()
    cloned = copy.deepcopy(source)
    cloned["id"] = f"deploy-task-{now.strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"
    cloned["name"] = f"{source['name']} (副本)"
    cloned["status"] = "draft"
    cloned["created_at"] = now.isoformat()
    cloned["updated_at"] = now.isoformat()
    tasks.append(cloned)
    _save_json(_tasks_path(), tasks)
    return cloned


@router.post("/tasks/{task_id}/deploy")
async def deploy_task(task_id: str):
    """执行部署，生成服务实例"""
    tasks = _load_json(_tasks_path())
    services = _load_json(_services_path())
    task = None
    for t in tasks:
        if t["id"] == task_id:
            task = t
            break
    if not task:
        return {"error": "Task not found"}
    now = datetime.now()
    task["status"] = "running"
    task["updated_at"] = now.isoformat()
    _save_json(_tasks_path(), tasks)

    svc_id = f"svc-{now.strftime('%Y%m%d%H%M%S')}-{random.randint(100,999)}"
    cfg = task.get("deploy_config", {})
    svc = {
        "id": svc_id,
        "task_id": task_id,
        "name": task["name"].replace("部署", "服务") if "部署" in task["name"] else task["name"] + " 服务",
        "endpoint": f"http://localhost:8080{cfg.get('endpoint', '/api/predict/unknown')}",
        "version": "v1.0",
        "replicas": {"desired": cfg.get("replicas", 1), "running": cfg.get("replicas", 1), "ready": cfg.get("replicas", 1)},
        "health": "healthy",
        "qps": round(random.uniform(10, 100), 1),
        "avg_latency_ms": round(random.uniform(50, 300), 0),
        "error_rate": round(random.uniform(0, 0.05), 3),
        "uptime": "0d 0h 0m",
        "created_at": now.isoformat(),
        "versions": [{"version": "v1.0", "published_at": now.isoformat(), "status": "active"}],
    }
    services.append(svc)
    _save_json(_services_path(), services)
    return {"success": True, "service_id": svc_id}


# ==================== 服务管理 API ====================

@router.get("/services")
async def list_services():
    """获取服务列表"""
    return _load_json(_services_path())


@router.get("/services/{svc_id}")
async def get_service(svc_id: str):
    """获取服务详情"""
    services = _load_json(_services_path())
    for s in services:
        if s["id"] == svc_id:
            return s
    return {"error": "Service not found"}


@router.post("/services/{svc_id}/start")
async def start_service(svc_id: str):
    """启动服务"""
    services = _load_json(_services_path())
    for s in services:
        if s["id"] == svc_id:
            s["health"] = "healthy"
            desired = s["replicas"]["desired"]
            s["replicas"]["running"] = desired
            s["replicas"]["ready"] = desired
            s["qps"] = round(random.uniform(10, 80), 1)
            s["avg_latency_ms"] = round(random.uniform(50, 200), 0)
            s["error_rate"] = round(random.uniform(0, 0.03), 3)
            _save_json(_services_path(), services)
            return {"success": True}
    return {"error": "Service not found"}


@router.post("/services/{svc_id}/stop")
async def stop_service(svc_id: str):
    """停止服务"""
    services = _load_json(_services_path())
    for s in services:
        if s["id"] == svc_id:
            s["health"] = "stopped"
            s["replicas"]["running"] = 0
            s["replicas"]["ready"] = 0
            s["qps"] = 0
            s["avg_latency_ms"] = 0
            s["error_rate"] = 0
            s["uptime"] = "0"
            _save_json(_services_path(), services)
            return {"success": True}
    return {"error": "Service not found"}


@router.post("/services/{svc_id}/restart")
async def restart_service(svc_id: str):
    """重启服务"""
    services = _load_json(_services_path())
    for s in services:
        if s["id"] == svc_id:
            s["health"] = "healthy"
            desired = s["replicas"]["desired"]
            s["replicas"]["running"] = desired
            s["replicas"]["ready"] = desired
            s["qps"] = round(random.uniform(10, 80), 1)
            s["avg_latency_ms"] = round(random.uniform(50, 200), 0)
            s["error_rate"] = round(random.uniform(0, 0.02), 3)
            _save_json(_services_path(), services)
            return {"success": True}
    return {"error": "Service not found"}


@router.put("/services/{svc_id}/scale")
async def scale_service(svc_id: str, body: dict):
    """扩缩容"""
    services = _load_json(_services_path())
    target = body.get("replicas", 1)
    for s in services:
        if s["id"] == svc_id:
            s["replicas"]["desired"] = target
            s["replicas"]["running"] = target
            s["replicas"]["ready"] = target
            _save_json(_services_path(), services)
            return {"success": True}
    return {"error": "Service not found"}


@router.post("/services/{svc_id}/rollback")
async def rollback_service(svc_id: str, body: dict):
    """回滚到指定版本"""
    services = _load_json(_services_path())
    target_version = body.get("version", "")
    for s in services:
        if s["id"] == svc_id:
            for v in s.get("versions", []):
                v["status"] = "active" if v["version"] == target_version else "inactive"
            s["version"] = target_version
            _save_json(_services_path(), services)
            return {"success": True}
    return {"error": "Service not found"}


@router.get("/services/{svc_id}/versions")
async def get_service_versions(svc_id: str):
    """获取版本历史"""
    services = _load_json(_services_path())
    for s in services:
        if s["id"] == svc_id:
            return s.get("versions", [])
    return []


@router.put("/services/{svc_id}/canary")
async def update_canary(svc_id: str, body: dict):
    """调整灰度比例"""
    # Mock: just return success
    return {"success": True, "canary_percent": body.get("canary_percent", 0)}


# ==================== 服务监控 API ====================

@router.get("/services/{svc_id}/metrics")
async def get_service_metrics(svc_id: str, time_range: str = Query("1h")):
    """获取服务指标时序数据"""
    hours_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
    hours = hours_map.get(time_range, 1)
    points = min(hours * 6, 200)  # ~10min intervals
    now = datetime.now()
    data = []
    for i in range(points):
        ts = now - timedelta(minutes=(points - i) * (hours * 60 / points))
        data.append({
            "timestamp": ts.isoformat(),
            "qps": round(random.uniform(20, 150) + 10 * math.sin(i / 10), 1),
            "latency_p50": round(random.uniform(50, 120), 1),
            "latency_p90": round(random.uniform(100, 250), 1),
            "latency_p95": round(random.uniform(150, 350), 1),
            "latency_p99": round(random.uniform(200, 500), 1),
            "error_rate": round(max(0, random.gauss(0.02, 0.015)), 4),
            "cpu_usage": round(random.uniform(30, 75) + 10 * math.sin(i / 8), 1),
            "memory_usage": round(random.uniform(40, 70), 1),
            "gpu_usage": round(random.uniform(0, 60), 1),
        })
    return data


@router.get("/services/{svc_id}/logs")
async def get_service_logs(svc_id: str, page: int = 1, page_size: int = 50):
    """获取访问日志"""
    now = datetime.now()
    statuses = [200, 200, 200, 200, 200, 200, 200, 200, 400, 500]
    logs = []
    for i in range(page_size):
        ts = now - timedelta(seconds=i * random.randint(1, 10))
        status = random.choice(statuses)
        logs.append({
            "timestamp": ts.isoformat(),
            "request_id": f"req-{random.randint(100000, 999999)}",
            "input_summary": f"输入数据: {random.choice(['负荷数据', '气象数据', '历史功率', '设备参数'])} ({random.randint(10, 500)} 条)",
            "output_summary": f"预测结果: {random.choice(['24h预测', '48h预测', '故障概率', '功率曲线'])}",
            "latency_ms": round(random.uniform(50, 500), 0),
            "status_code": status,
        })
    return {"total": 200, "items": logs}


# ==================== 告警 API ====================

@router.get("/alerts/rules")
async def list_alert_rules():
    """获取告警规则列表"""
    alerts = _load_json(_alerts_path())
    return alerts.get("rules", []) if isinstance(alerts, dict) else []


@router.post("/alerts/rules")
async def create_alert_rule(body: dict):
    """创建告警规则"""
    alerts = _load_json(_alerts_path())
    if not isinstance(alerts, dict):
        alerts = {"rules": [], "history": []}
    rule = {
        "id": f"rule-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100,999)}",
        "service_id": body.get("service_id", ""),
        "metric_name": body.get("metric_name", ""),
        "operator": body.get("operator", "gt"),
        "threshold": body.get("threshold", 0),
        "severity": body.get("severity", "warning"),
        "enabled": body.get("enabled", True),
    }
    alerts["rules"].append(rule)
    _save_json(_alerts_path(), alerts)
    return rule


@router.put("/alerts/rules/{rule_id}")
async def update_alert_rule(rule_id: str, body: dict):
    """更新告警规则"""
    alerts = _load_json(_alerts_path())
    if not isinstance(alerts, dict):
        return {"error": "No alerts data"}
    for r in alerts.get("rules", []):
        if r["id"] == rule_id:
            for k in ["metric_name", "operator", "threshold", "severity", "enabled"]:
                if k in body:
                    r[k] = body[k]
            _save_json(_alerts_path(), alerts)
            return r
    return {"error": "Rule not found"}


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """删除告警规则"""
    alerts = _load_json(_alerts_path())
    if not isinstance(alerts, dict):
        return {"error": "No alerts data"}
    alerts["rules"] = [r for r in alerts.get("rules", []) if r["id"] != rule_id]
    _save_json(_alerts_path(), alerts)
    return {"success": True}


@router.get("/alerts/history")
async def list_alert_history(service_id: Optional[str] = None):
    """获取告警历史"""
    alerts = _load_json(_alerts_path())
    history = alerts.get("history", []) if isinstance(alerts, dict) else []
    if service_id:
        history = [h for h in history if h.get("service_id") == service_id]
    return history
# @AI_GENERATED: end
