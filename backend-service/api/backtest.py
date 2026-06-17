# @AI_GENERATED: Kiro v1.0
"""
算法回测系统 API
提供回测任务CRUD、执行引擎、运行管理、结果聚合等端点
"""
from fastapi import APIRouter, Query
from typing import Optional
import json, os, copy, random
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
BACKTEST_DIR = os.path.join(DATA_DIR, "backtest")

os.makedirs(BACKTEST_DIR, exist_ok=True)


def _tasks_path():
    return os.path.join(BACKTEST_DIR, "tasks.json")


def _runs_path(task_id: str):
    return os.path.join(BACKTEST_DIR, f"runs-{task_id}.json")


def _load_tasks() -> list:
    p = _tasks_path()
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_tasks(tasks: list):
    with open(_tasks_path(), "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def _load_runs(task_id: str) -> list:
    p = _runs_path(task_id)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_runs(task_id: str, runs: list):
    with open(_runs_path(task_id), "w", encoding="utf-8") as f:
        json.dump(runs, f, ensure_ascii=False, indent=2)


def _init_mock_data():
    """Initialize mock backtest tasks if none exist."""
    if os.path.exists(_tasks_path()):
        return
    now = datetime.now()
    tasks = [
        {
            "id": "bt-task-001",
            "name": "光伏发电预测算法对比",
            "description": "对比3种预测算法在5个光伏电站数据集上的表现",
            "scenario_id": "renewable-energy",
            "datasets": [
                {"id": "ds-001", "name": "光伏电站A-2025年数据"},
                {"id": "ds-002", "name": "光伏电站B-2025年数据"},
                {"id": "ds-003", "name": "光伏电站C-2024年数据"},
                {"id": "ds-004", "name": "光伏电站D-2025年数据"},
                {"id": "ds-005", "name": "光伏电站E-2024年数据"},
            ],
            "algorithms": [
                {"type": "template", "id": "pv_power_forecast", "name": "光伏发电功率预测"},
                {"type": "template", "id": "lstm_forecast", "name": "LSTM时序预测"},
                {"type": "workflow", "id": "wf-001", "name": "集成预测算法模板"},
            ],
            "metrics_config": {
                "primary_metric": "rmse",
                "metrics": ["rmse", "mae", "r2", "mape"],
                "thresholds": {"rmse": 0.05, "mae": 0.03},
            },
            "status": "completed",
            "created_by": "engineer_01",
            "created_at": (now - timedelta(days=3)).isoformat(),
            "started_at": (now - timedelta(days=3, hours=-1)).isoformat(),
            "completed_at": (now - timedelta(days=3, hours=-2)).isoformat(),
            "total_runs": 15,
            "completed_runs": 15,
            "failed_runs": 0,
        },
        {
            "id": "bt-task-002",
            "name": "负荷预测模型竞赛",
            "description": "10个负荷数据集×4个算法方案的竞争评估",
            "scenario_id": "grid-load-storage",
            "datasets": [
                {"id": "ds-101", "name": "华东电网-2025Q1"},
                {"id": "ds-102", "name": "华南电网-2025Q1"},
                {"id": "ds-103", "name": "华北电网-2024Q4"},
            ],
            "algorithms": [
                {"type": "template", "id": "load_forecast_lstm", "name": "LSTM负荷预测"},
                {"type": "template", "id": "load_forecast_xgb", "name": "XGBoost负荷预测"},
                {"type": "template", "id": "load_forecast_transformer", "name": "Transformer负荷预测"},
                {"type": "workflow", "id": "wf-load-ensemble", "name": "集成负荷预测算法模板"},
            ],
            "metrics_config": {
                "primary_metric": "rmse",
                "metrics": ["rmse", "mae", "r2"],
                "thresholds": {"rmse": 0.04},
            },
            "status": "running",
            "created_by": "engineer_02",
            "created_at": (now - timedelta(hours=5)).isoformat(),
            "started_at": (now - timedelta(hours=4)).isoformat(),
            "completed_at": None,
            "total_runs": 12,
            "completed_runs": 8,
            "failed_runs": 1,
        },
        {
            "id": "bt-task-003",
            "name": "故障诊断算法评估",
            "description": "工业设备故障诊断算法在不同设备数据集上的分类性能对比",
            "scenario_id": "industrial-manufacturing",
            "datasets": [
                {"id": "ds-201", "name": "电机振动数据集"},
                {"id": "ds-202", "name": "轴承温度数据集"},
            ],
            "algorithms": [
                {"type": "template", "id": "fault_svm", "name": "SVM故障分类"},
                {"type": "template", "id": "fault_rf", "name": "随机森林故障诊断"},
            ],
            "metrics_config": {
                "primary_metric": "f1",
                "metrics": ["f1", "precision", "recall", "accuracy"],
                "thresholds": {"f1": 0.85},
            },
            "status": "pending",
            "created_by": "engineer_01",
            "created_at": (now - timedelta(hours=1)).isoformat(),
            "started_at": None,
            "completed_at": None,
            "total_runs": 4,
            "completed_runs": 0,
            "failed_runs": 0,
        },
        {
            "id": "bt-task-004",
            "name": "碳排放预测模型验证",
            "description": "碳排放预测算法在多个园区数据集上的回测验证",
            "scenario_id": "carbon-management",
            "datasets": [
                {"id": "ds-301", "name": "工业园区A碳排放"},
                {"id": "ds-302", "name": "工业园区B碳排放"},
                {"id": "ds-303", "name": "商业园区C碳排放"},
            ],
            "algorithms": [
                {"type": "template", "id": "carbon_predict_lr", "name": "线性回归碳预测"},
                {"type": "template", "id": "carbon_predict_nn", "name": "神经网络碳预测"},
                {"type": "workflow", "id": "wf-carbon", "name": "碳排放综合预测流"},
            ],
            "metrics_config": {
                "primary_metric": "rmse",
                "metrics": ["rmse", "mae", "r2"],
                "thresholds": {"rmse": 0.06},
            },
            "status": "failed",
            "created_by": "admin",
            "created_at": (now - timedelta(days=1)).isoformat(),
            "started_at": (now - timedelta(days=1, hours=-0.5)).isoformat(),
            "completed_at": (now - timedelta(days=1, hours=-1)).isoformat(),
            "total_runs": 9,
            "completed_runs": 6,
            "failed_runs": 3,
        },
    ]
    _save_tasks(tasks)
    # Generate mock runs for completed task
    _generate_mock_runs(tasks[0])
    _generate_mock_runs_partial(tasks[1])


def _generate_mock_runs(task: dict):
    """Generate completed mock runs for a task."""
    runs = []
    base_time = datetime.fromisoformat(task["started_at"])
    idx = 0
    for ds in task["datasets"]:
        for alg in task["algorithms"]:
            idx += 1
            start = base_time + timedelta(minutes=idx * 2)
            end = start + timedelta(minutes=random.randint(3, 10))
            is_regression = task["metrics_config"]["primary_metric"] in ("rmse", "mae", "r2", "mape")
            if is_regression:
                result = {
                    "rmse": round(random.uniform(0.02, 0.06), 4),
                    "mae": round(random.uniform(0.015, 0.045), 4),
                    "r2": round(random.uniform(0.92, 0.98), 4),
                    "mape": round(random.uniform(1.5, 5.0), 2),
                }
            else:
                result = {
                    "f1": round(random.uniform(0.82, 0.97), 4),
                    "precision": round(random.uniform(0.85, 0.98), 4),
                    "recall": round(random.uniform(0.80, 0.96), 4),
                    "accuracy": round(random.uniform(0.88, 0.98), 4),
                }
            runs.append({
                "id": f"bt-run-{task['id']}-{idx:03d}",
                "task_id": task["id"],
                "dataset_id": ds["id"],
                "dataset_name": ds["name"],
                "algorithm_type": alg["type"],
                "algorithm_id": alg["id"],
                "algorithm_name": alg["name"],
                "status": "completed",
                "started_at": start.isoformat(),
                "completed_at": end.isoformat(),
                "execution_time_ms": int((end - start).total_seconds() * 1000),
                "result": result,
                "error_message": None,
            })
    _save_runs(task["id"], runs)


def _generate_mock_runs_partial(task: dict):
    """Generate partially completed mock runs (for running task)."""
    runs = []
    base_time = datetime.fromisoformat(task["started_at"])
    idx = 0
    total = task["total_runs"]
    completed = task["completed_runs"]
    failed = task["failed_runs"]
    for ds in task["datasets"]:
        for alg in task["algorithms"]:
            idx += 1
            start = base_time + timedelta(minutes=idx * 3)
            if idx <= completed:
                end = start + timedelta(minutes=random.randint(3, 8))
                status = "completed"
                result = {
                    "rmse": round(random.uniform(0.02, 0.06), 4),
                    "mae": round(random.uniform(0.015, 0.045), 4),
                    "r2": round(random.uniform(0.92, 0.98), 4),
                }
                err = None
            elif idx <= completed + failed:
                end = start + timedelta(minutes=1)
                status = "failed"
                result = None
                err = "Execution timeout: dataset too large"
            elif idx == completed + failed + 1:
                end = None
                status = "running"
                result = None
                err = None
            else:
                start = None
                end = None
                status = "pending"
                result = None
                err = None
            runs.append({
                "id": f"bt-run-{task['id']}-{idx:03d}",
                "task_id": task["id"],
                "dataset_id": ds["id"],
                "dataset_name": ds["name"],
                "algorithm_type": alg["type"],
                "algorithm_id": alg["id"],
                "algorithm_name": alg["name"],
                "status": status,
                "started_at": start.isoformat() if start else None,
                "completed_at": end.isoformat() if end else None,
                "execution_time_ms": int((end - start).total_seconds() * 1000) if start and end else None,
                "result": result,
                "error_message": err,
            })
    _save_runs(task["id"], runs)


# Initialize mock data on module load
_init_mock_data()


# ─── Task CRUD ───

@router.get("/stats")
async def backtest_stats():
    tasks = _load_tasks()
    running = sum(1 for t in tasks if t["status"] == "running")
    completed = sum(1 for t in tasks if t["status"] == "completed")
    scores = []
    for t in tasks:
        if t["status"] == "completed" and t["total_runs"] > 0:
            scores.append(t["completed_runs"] / t["total_runs"])
    return {
        "total_tasks": len(tasks),
        "running_tasks": running,
        "completed_tasks": completed,
        "avg_score": round(sum(scores) / len(scores), 3) if scores else 0,
    }


@router.get("/tasks")
async def list_tasks(
    scenario: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    tasks = _load_tasks()
    if scenario:
        tasks = [t for t in tasks if t["scenario_id"] == scenario]
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    tasks.sort(key=lambda t: t["created_at"], reverse=True)
    total = len(tasks)
    start = (page - 1) * page_size
    return {"total": total, "items": tasks[start : start + page_size]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"error": "Task not found"}
    return task


@router.post("/tasks")
async def create_task(body: dict):
    tasks = _load_tasks()
    now = datetime.now()
    datasets = body.get("datasets", [])
    algorithms = body.get("algorithms", [])
    task = {
        "id": f"bt-task-{now.strftime('%Y%m%d%H%M%S%f')[:20]}",
        "name": body.get("name", "未命名回测"),
        "description": body.get("description", ""),
        "scenario_id": body.get("scenario_id", ""),
        "datasets": datasets,
        "algorithms": algorithms,
        "metrics_config": body.get("metrics_config", {
            "primary_metric": "rmse",
            "metrics": ["rmse", "mae", "r2"],
            "thresholds": {},
        }),
        "status": "pending",
        "created_by": body.get("created_by", "user"),
        "created_at": now.isoformat(),
        "started_at": None,
        "completed_at": None,
        "total_runs": len(datasets) * len(algorithms),
        "completed_runs": 0,
        "failed_runs": 0,
    }
    tasks.append(task)
    _save_tasks(tasks)
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    tasks = _load_tasks()
    tasks = [t for t in tasks if t["id"] != task_id]
    _save_tasks(tasks)
    # Clean up runs file
    rp = _runs_path(task_id)
    if os.path.exists(rp):
        os.remove(rp)
    return {"success": True}


@router.post("/tasks/{task_id}/clone")
async def clone_task(task_id: str):
    tasks = _load_tasks()
    orig = next((t for t in tasks if t["id"] == task_id), None)
    if not orig:
        return {"error": "Task not found"}
    now = datetime.now()
    cloned = copy.deepcopy(orig)
    cloned["id"] = f"bt-task-{now.strftime('%Y%m%d%H%M%S%f')[:20]}"
    cloned["name"] = f"{orig['name']} (副本)"
    cloned["status"] = "pending"
    cloned["created_at"] = now.isoformat()
    cloned["started_at"] = None
    cloned["completed_at"] = None
    cloned["completed_runs"] = 0
    cloned["failed_runs"] = 0
    tasks.append(cloned)
    _save_tasks(tasks)
    return cloned


# ─── Execution ───

@router.post("/tasks/{task_id}/execute")
async def execute_task(task_id: str):
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"error": "Task not found"}
    if task["status"] not in ("pending", "paused"):
        return {"error": f"Cannot execute task in {task['status']} status"}
    now = datetime.now()
    task["status"] = "running"
    task["started_at"] = now.isoformat()
    # Generate runs
    runs = []
    idx = 0
    for ds in task["datasets"]:
        for alg in task["algorithms"]:
            idx += 1
            runs.append({
                "id": f"bt-run-{task_id}-{idx:03d}",
                "task_id": task_id,
                "dataset_id": ds["id"],
                "dataset_name": ds["name"],
                "algorithm_type": alg["type"],
                "algorithm_id": alg["id"],
                "algorithm_name": alg["name"],
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "execution_time_ms": None,
                "result": None,
                "error_message": None,
            })
    _save_runs(task_id, runs)
    # Simulate: complete some runs immediately (mock)
    _simulate_execution(task, runs)
    _save_tasks(tasks)
    _save_runs(task_id, runs)
    return {"success": True, "total_runs": len(runs)}


def _simulate_execution(task: dict, runs: list):
    """Mock simulation: complete all runs with random results."""
    now = datetime.now()
    completed = 0
    failed = 0
    primary = task["metrics_config"].get("primary_metric", "rmse")
    is_regression = primary in ("rmse", "mae", "r2", "mape")
    for i, run in enumerate(runs):
        start = now + timedelta(seconds=i * 30)
        if random.random() < 0.08:  # 8% failure rate
            run["status"] = "failed"
            run["started_at"] = start.isoformat()
            run["completed_at"] = (start + timedelta(seconds=5)).isoformat()
            run["execution_time_ms"] = 5000
            run["error_message"] = "Simulated execution error"
            failed += 1
        else:
            end = start + timedelta(seconds=random.randint(60, 600))
            run["status"] = "completed"
            run["started_at"] = start.isoformat()
            run["completed_at"] = end.isoformat()
            run["execution_time_ms"] = int((end - start).total_seconds() * 1000)
            if is_regression:
                run["result"] = {
                    "rmse": round(random.uniform(0.018, 0.065), 4),
                    "mae": round(random.uniform(0.012, 0.050), 4),
                    "r2": round(random.uniform(0.90, 0.985), 4),
                    "mape": round(random.uniform(1.2, 6.5), 2),
                }
            else:
                run["result"] = {
                    "f1": round(random.uniform(0.80, 0.97), 4),
                    "precision": round(random.uniform(0.82, 0.98), 4),
                    "recall": round(random.uniform(0.78, 0.96), 4),
                    "accuracy": round(random.uniform(0.85, 0.98), 4),
                }
            completed += 1
    task["completed_runs"] = completed
    task["failed_runs"] = failed
    task["status"] = "completed" if failed == 0 else "failed" if failed == len(runs) else "completed"
    task["completed_at"] = datetime.now().isoformat()


@router.put("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"error": "Task not found"}
    task["status"] = "paused"
    _save_tasks(tasks)
    return {"success": True}


@router.put("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"error": "Task not found"}
    task["status"] = "cancelled"
    task["completed_at"] = datetime.now().isoformat()
    _save_tasks(tasks)
    return {"success": True}


# ─── Runs ───

@router.get("/tasks/{task_id}/runs")
async def list_runs(task_id: str):
    runs = _load_runs(task_id)
    return {"runs": runs, "total": len(runs)}


@router.get("/tasks/{task_id}/runs/{run_id}")
async def get_run(task_id: str, run_id: str):
    runs = _load_runs(task_id)
    run = next((r for r in runs if r["id"] == run_id), None)
    if not run:
        return {"error": "Run not found"}
    return run


@router.post("/tasks/{task_id}/runs/{run_id}/retry")
async def retry_run(task_id: str, run_id: str):
    runs = _load_runs(task_id)
    run = next((r for r in runs if r["id"] == run_id), None)
    if not run:
        return {"error": "Run not found"}
    now = datetime.now()
    end = now + timedelta(seconds=random.randint(60, 300))
    run["status"] = "completed"
    run["started_at"] = now.isoformat()
    run["completed_at"] = end.isoformat()
    run["execution_time_ms"] = int((end - now).total_seconds() * 1000)
    run["result"] = {
        "rmse": round(random.uniform(0.02, 0.06), 4),
        "mae": round(random.uniform(0.015, 0.045), 4),
        "r2": round(random.uniform(0.92, 0.98), 4),
    }
    run["error_message"] = None
    _save_runs(task_id, runs)
    # Update task counts
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if task:
        task["completed_runs"] = sum(1 for r in runs if r["status"] == "completed")
        task["failed_runs"] = sum(1 for r in runs if r["status"] == "failed")
        _save_tasks(tasks)
    return {"success": True}


# ─── Results ───

@router.get("/tasks/{task_id}/results")
async def get_results(task_id: str):
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"error": "Task not found"}
    runs = _load_runs(task_id)
    completed_runs = [r for r in runs if r["status"] == "completed" and r.get("result")]
    if not completed_runs:
        return {"error": "No completed runs", "task_id": task_id, "matrix": None, "ranking": None, "statistics": None}

    primary = task["metrics_config"].get("primary_metric", "rmse")
    lower_is_better = primary in ("rmse", "mae", "mape")

    # Build matrix
    ds_ids = list(dict.fromkeys(r["dataset_id"] for r in runs))
    alg_ids = list(dict.fromkeys(r["algorithm_id"] for r in runs))
    ds_names = {r["dataset_id"]: r["dataset_name"] for r in runs}
    alg_names = {r["algorithm_id"]: r["algorithm_name"] for r in runs}

    results_map = {}
    for r in completed_runs:
        results_map.setdefault(r["dataset_id"], {})[r["algorithm_id"]] = r["result"]

    # Rank per dataset
    for ds_id in ds_ids:
        ds_results = results_map.get(ds_id, {})
        sorted_algs = sorted(
            ds_results.items(),
            key=lambda x: x[1].get(primary, 999) if lower_is_better else -x[1].get(primary, 0),
        )
        for rank, (alg_id, _) in enumerate(sorted_algs, 1):
            ds_results[alg_id]["rank"] = rank

    # Overall ranking
    alg_scores = {}
    for alg_id in alg_ids:
        vals = []
        for ds_id in ds_ids:
            v = results_map.get(ds_id, {}).get(alg_id, {}).get(primary)
            if v is not None:
                vals.append(v)
        if vals:
            alg_scores[alg_id] = sum(vals) / len(vals)
    sorted_overall = sorted(
        alg_scores.items(),
        key=lambda x: x[1] if lower_is_better else -x[1],
    )
    ranking = [
        {"algorithm_id": aid, "algorithm_name": alg_names.get(aid, aid), "avg_value": round(v, 4), "rank": i + 1}
        for i, (aid, v) in enumerate(sorted_overall)
    ]

    # Statistics
    statistics = {}
    for alg_id in alg_ids:
        statistics[alg_id] = {}
        for metric in task["metrics_config"].get("metrics", [primary]):
            vals = []
            for ds_id in ds_ids:
                v = results_map.get(ds_id, {}).get(alg_id, {}).get(metric)
                if v is not None:
                    vals.append(v)
            if vals:
                vals_sorted = sorted(vals)
                n = len(vals)
                statistics[alg_id][metric] = {
                    "mean": round(sum(vals) / n, 4),
                    "std": round((sum((v - sum(vals) / n) ** 2 for v in vals) / n) ** 0.5, 4),
                    "min": round(min(vals), 4),
                    "max": round(max(vals), 4),
                    "median": round(vals_sorted[n // 2], 4),
                }

    return {
        "task_id": task_id,
        "matrix": {
            "datasets": ds_ids,
            "algorithms": alg_ids,
            "dataset_names": ds_names,
            "algorithm_names": alg_names,
            "results": results_map,
        },
        "ranking": {"overall": ranking},
        "statistics": statistics,
    }


@router.get("/tasks/{task_id}/results/export")
async def export_results(task_id: str, format: str = Query("csv")):
    from fastapi.responses import PlainTextResponse
    result = await get_results(task_id)
    if "error" in result:
        return result
    matrix = result["matrix"]
    lines = ["Dataset," + ",".join(matrix["algorithm_names"].get(a, a) for a in matrix["algorithms"])]
    for ds_id in matrix["datasets"]:
        row = [matrix["dataset_names"].get(ds_id, ds_id)]
        for alg_id in matrix["algorithms"]:
            cell = matrix["results"].get(ds_id, {}).get(alg_id, {})
            primary = "rmse"
            row.append(str(cell.get(primary, "N/A")))
        lines.append(",".join(row))
    return PlainTextResponse("\n".join(lines), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=backtest-{task_id}.csv"})


# @AI_GENERATED: Kiro v1.0
# ─── 智能调度系统 ───

# 资源配额配置
RESOURCE_QUOTA = {
    "gpu_total": 8,
    "gpu_available": 8,
    "gpu_reserved": 0,
    "cpu_total": 64,
    "cpu_available": 64,
    "cpu_reserved": 0,
    "memory_total_gb": 256,
    "memory_available_gb": 256,
}

# 调度队列存储
SCHEDULE_QUEUE_PATH = os.path.join(BACKTEST_DIR, "schedule_queue.json")


def _load_schedule_queue() -> list:
    if os.path.exists(SCHEDULE_QUEUE_PATH):
        with open(SCHEDULE_QUEUE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_schedule_queue(queue: list):
    with open(SCHEDULE_QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def _estimate_task_resources(task: dict) -> dict:
    """根据任务规模估算资源需求"""
    total_runs = task.get("total_runs", 1)
    # 基于运行数量估算
    gpu_required = min(4, max(1, total_runs // 5))
    cpu_required = min(16, max(2, total_runs * 2))
    memory_required = min(64, max(4, total_runs * 2))
    # 估算时长（分钟）
    estimated_duration = total_runs * 5 + 10  # 每个运行约5分钟 + 10分钟开销
    return {
        "gpu_required": gpu_required,
        "cpu_required": cpu_required,
        "memory_required_gb": memory_required,
        "estimated_duration_minutes": estimated_duration,
    }


def _calculate_priority_score(schedule_config: dict) -> float:
    """计算任务优先级分数（用于排序）"""
    priority_weights = {"critical": 1000, "high": 100, "normal": 10, "low": 1}
    base_score = priority_weights.get(schedule_config.get("priority", "normal"), 10)
    
    # 如果有截止时间，根据紧迫程度调整分数
    deadline = schedule_config.get("deadline")
    if deadline:
        try:
            deadline_dt = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            now = datetime.now(deadline_dt.tzinfo) if deadline_dt.tzinfo else datetime.now()
            hours_until_deadline = (deadline_dt - now).total_seconds() / 3600
            if hours_until_deadline < 1:
                base_score *= 10  # 1小时内截止，大幅提升优先级
            elif hours_until_deadline < 4:
                base_score *= 5
            elif hours_until_deadline < 24:
                base_score *= 2
        except:
            pass
    
    return base_score


def _optimize_schedule(queue: list, quota: dict) -> dict:
    """优化调度顺序"""
    # 按优先级分数排序
    sorted_queue = sorted(
        queue,
        key=lambda x: _calculate_priority_score(x.get("schedule_config", {})),
        reverse=True
    )
    
    # 分配队列位置和预估时间
    current_time = datetime.now()
    gpu_timeline = 0  # GPU 释放时间偏移（分钟）
    
    deadline_violations = []
    total_time = 0
    
    for i, task in enumerate(sorted_queue):
        task["queue_position"] = i + 1
        config = task.get("schedule_config", {})
        duration = config.get("estimated_duration_minutes", 30)
        
        # 计算预估开始和结束时间
        start_offset = gpu_timeline
        end_offset = start_offset + duration
        
        task["scheduled_start"] = (current_time + timedelta(minutes=start_offset)).isoformat()
        task["scheduled_end"] = (current_time + timedelta(minutes=end_offset)).isoformat()
        
        # 检查是否违反截止时间
        deadline = config.get("deadline")
        if deadline:
            try:
                deadline_dt = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
                estimated_end = current_time + timedelta(minutes=end_offset)
                if deadline_dt.tzinfo:
                    estimated_end = estimated_end.replace(tzinfo=deadline_dt.tzinfo)
                if estimated_end > deadline_dt:
                    delay = (estimated_end - deadline_dt).total_seconds() / 60
                    deadline_violations.append({
                        "task_id": task["task_id"],
                        "task_name": task["task_name"],
                        "deadline": deadline,
                        "estimated_completion": task["scheduled_end"],
                        "delay_minutes": round(delay, 1),
                    })
            except:
                pass
        
        # 更新时间线（简化：假设任务串行执行）
        gpu_timeline = end_offset
        total_time = end_offset
    
    # 计算资源利用率
    running_tasks = [t for t in sorted_queue if t.get("status") == "running"]
    gpu_used = sum(t.get("resource_allocation", {}).get("gpu_allocated", 0) for t in running_tasks)
    cpu_used = sum(t.get("resource_allocation", {}).get("cpu_allocated", 0) for t in running_tasks)
    mem_used = sum(t.get("resource_allocation", {}).get("memory_allocated_gb", 0) for t in running_tasks)
    
    # 生成建议
    recommendations = []
    if len(deadline_violations) > 0:
        recommendations.append(f"有 {len(deadline_violations)} 个任务可能无法在截止时间前完成，建议提升优先级或增加资源配额")
    if len(sorted_queue) > 10:
        recommendations.append("队列任务较多，建议考虑增加计算资源或调整低优先级任务")
    if gpu_used / max(quota["gpu_total"], 1) > 0.9:
        recommendations.append("GPU 资源接近饱和，新任务可能需要等待")
    
    return {
        "optimized_order": sorted_queue,
        "total_estimated_time_minutes": total_time,
        "resource_utilization": {
            "gpu_utilization": round(gpu_used / max(quota["gpu_total"], 1) * 100, 1),
            "cpu_utilization": round(cpu_used / max(quota["cpu_total"], 1) * 100, 1),
            "memory_utilization": round(mem_used / max(quota["memory_total_gb"], 1) * 100, 1),
        },
        "deadline_violations": deadline_violations,
        "recommendations": recommendations,
    }


@router.get("/schedule/quota")
async def get_resource_quota():
    """获取当前资源配额"""
    queue = _load_schedule_queue()
    running = [t for t in queue if t.get("status") == "running"]
    
    gpu_used = sum(t.get("resource_allocation", {}).get("gpu_allocated", 0) for t in running)
    cpu_used = sum(t.get("resource_allocation", {}).get("cpu_allocated", 0) for t in running)
    mem_used = sum(t.get("resource_allocation", {}).get("memory_allocated_gb", 0) for t in running)
    
    return {
        "gpu_total": RESOURCE_QUOTA["gpu_total"],
        "gpu_available": RESOURCE_QUOTA["gpu_total"] - gpu_used,
        "gpu_reserved": gpu_used,
        "cpu_total": RESOURCE_QUOTA["cpu_total"],
        "cpu_available": RESOURCE_QUOTA["cpu_total"] - cpu_used,
        "cpu_reserved": cpu_used,
        "memory_total_gb": RESOURCE_QUOTA["memory_total_gb"],
        "memory_available_gb": RESOURCE_QUOTA["memory_total_gb"] - mem_used,
    }


@router.put("/schedule/quota")
async def update_resource_quota(body: dict):
    """更新资源配额"""
    global RESOURCE_QUOTA
    if "gpu_total" in body:
        RESOURCE_QUOTA["gpu_total"] = body["gpu_total"]
    if "cpu_total" in body:
        RESOURCE_QUOTA["cpu_total"] = body["cpu_total"]
    if "memory_total_gb" in body:
        RESOURCE_QUOTA["memory_total_gb"] = body["memory_total_gb"]
    return RESOURCE_QUOTA


@router.get("/schedule/queue")
async def get_schedule_queue():
    """获取调度队列"""
    queue = _load_schedule_queue()
    quota = await get_resource_quota()
    optimization = _optimize_schedule(queue, quota)
    return {
        "queue": optimization["optimized_order"],
        "total_tasks": len(queue),
        "running_tasks": len([t for t in queue if t.get("status") == "running"]),
        "queued_tasks": len([t for t in queue if t.get("status") == "queued"]),
        "optimization": optimization,
    }


@router.post("/schedule/tasks/{task_id}")
async def add_task_to_schedule(task_id: str, body: dict):
    """将任务添加到调度队列"""
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"error": "Task not found"}
    
    queue = _load_schedule_queue()
    
    # 检查是否已在队列中
    if any(t["task_id"] == task_id for t in queue):
        return {"error": "Task already in schedule queue"}
    
    # 估算资源需求
    estimated = _estimate_task_resources(task)
    
    # 构建调度配置
    schedule_config = {
        "priority": body.get("priority", "normal"),
        "deadline": body.get("deadline"),
        "estimated_duration_minutes": body.get("estimated_duration_minutes", estimated["estimated_duration_minutes"]),
        "gpu_required": body.get("gpu_required", estimated["gpu_required"]),
        "cpu_required": body.get("cpu_required", estimated["cpu_required"]),
        "memory_required_gb": body.get("memory_required_gb", estimated["memory_required_gb"]),
        "allow_preemption": body.get("allow_preemption", False),
        "max_retry": body.get("max_retry", 3),
    }
    
    scheduled_task = {
        "task_id": task_id,
        "task_name": task["name"],
        "task_type": "workflow",
        "schedule_config": schedule_config,
        "queue_position": len(queue) + 1,
        "status": "queued",
        "created_at": datetime.now().isoformat(),
    }
    
    queue.append(scheduled_task)
    _save_schedule_queue(queue)
    
    # 重新优化调度
    quota = await get_resource_quota()
    optimization = _optimize_schedule(queue, quota)
    _save_schedule_queue(optimization["optimized_order"])
    
    return {"success": True, "scheduled_task": scheduled_task, "optimization": optimization}


@router.put("/schedule/tasks/{task_id}")
async def update_task_schedule(task_id: str, body: dict):
    """更新任务调度配置"""
    queue = _load_schedule_queue()
    task = next((t for t in queue if t["task_id"] == task_id), None)
    if not task:
        return {"error": "Task not in schedule queue"}
    
    # 更新调度配置
    config = task.get("schedule_config", {})
    if "priority" in body:
        config["priority"] = body["priority"]
    if "deadline" in body:
        config["deadline"] = body["deadline"]
    if "estimated_duration_minutes" in body:
        config["estimated_duration_minutes"] = body["estimated_duration_minutes"]
    if "gpu_required" in body:
        config["gpu_required"] = body["gpu_required"]
    if "cpu_required" in body:
        config["cpu_required"] = body["cpu_required"]
    if "memory_required_gb" in body:
        config["memory_required_gb"] = body["memory_required_gb"]
    if "allow_preemption" in body:
        config["allow_preemption"] = body["allow_preemption"]
    
    task["schedule_config"] = config
    
    # 重新优化调度
    quota = await get_resource_quota()
    optimization = _optimize_schedule(queue, quota)
    _save_schedule_queue(optimization["optimized_order"])
    
    return {"success": True, "scheduled_task": task, "optimization": optimization}


@router.delete("/schedule/tasks/{task_id}")
async def remove_task_from_schedule(task_id: str):
    """从调度队列移除任务"""
    queue = _load_schedule_queue()
    queue = [t for t in queue if t["task_id"] != task_id]
    _save_schedule_queue(queue)
    return {"success": True}


@router.post("/schedule/optimize")
async def optimize_schedule():
    """手动触发调度优化"""
    queue = _load_schedule_queue()
    quota = await get_resource_quota()
    optimization = _optimize_schedule(queue, quota)
    _save_schedule_queue(optimization["optimized_order"])
    return optimization


@router.post("/schedule/tasks/{task_id}/start")
async def start_scheduled_task(task_id: str):
    """启动调度队列中的任务"""
    queue = _load_schedule_queue()
    task = next((t for t in queue if t["task_id"] == task_id), None)
    if not task:
        return {"error": "Task not in schedule queue"}
    
    if task["status"] != "queued":
        return {"error": f"Task is not in queued status, current: {task['status']}"}
    
    # 检查资源是否足够
    quota = await get_resource_quota()
    config = task.get("schedule_config", {})
    
    if config.get("gpu_required", 0) > quota["gpu_available"]:
        return {"error": "Insufficient GPU resources"}
    if config.get("cpu_required", 0) > quota["cpu_available"]:
        return {"error": "Insufficient CPU resources"}
    if config.get("memory_required_gb", 0) > quota["memory_available_gb"]:
        return {"error": "Insufficient memory resources"}
    
    # 分配资源
    task["status"] = "running"
    task["resource_allocation"] = {
        "gpu_allocated": config.get("gpu_required", 1),
        "cpu_allocated": config.get("cpu_required", 4),
        "memory_allocated_gb": config.get("memory_required_gb", 8),
    }
    task["started_at"] = datetime.now().isoformat()
    
    _save_schedule_queue(queue)
    
    # 同时启动实际的回测任务
    await execute_task(task_id)
    
    return {"success": True, "task": task}


@router.post("/schedule/tasks/{task_id}/complete")
async def complete_scheduled_task(task_id: str):
    """标记调度任务完成"""
    queue = _load_schedule_queue()
    task = next((t for t in queue if t["task_id"] == task_id), None)
    if not task:
        return {"error": "Task not in schedule queue"}
    
    task["status"] = "completed"
    task["completed_at"] = datetime.now().isoformat()
    task["resource_allocation"] = None  # 释放资源
    
    _save_schedule_queue(queue)
    return {"success": True}
# @AI_GENERATED: end
