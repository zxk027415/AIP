# @AI_GENERATED: Kiro v1.0
"""
算法运营系统 API
提供漂移检测、A/B测试、自动重训等功能的后端接口
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import random

router = APIRouter(prefix="/api/algorithm-ops", tags=["algorithm-ops"])


# ============ 枚举类型 ============

class DriftStatus(str, Enum):
    NORMAL = "normal"
    MILD = "mild"
    SEVERE = "severe"


class DriftType(str, Enum):
    DATA = "data"
    CONCEPT = "concept"
    BOTH = "both"


class ABTestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class ABTestResult(str, Enum):
    PENDING = "pending"
    A_WINS = "a_wins"
    B_WINS = "b_wins"
    NO_DIFFERENCE = "no_difference"


class RetrainStatus(str, Enum):
    QUEUED = "queued"
    TRAINING = "training"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


class RetrainType(str, Enum):
    INCREMENTAL = "incremental"
    FULL = "full"


class RetrainTrigger(str, Enum):
    DRIFT_DETECTED = "drift_detected"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    AB_TEST_RESULT = "ab_test_result"


# ============ 请求/响应模型 ============

class DriftDetectRequest(BaseModel):
    model_id: str
    check_data_drift: bool = True
    check_concept_drift: bool = True
    reference_window: str = "7d"


class DriftAnalyzeRequest(BaseModel):
    model_id: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ABTestCreateRequest(BaseModel):
    test_name: str
    model_a_id: str
    model_a_name: str
    model_b_id: str
    model_b_name: str
    traffic_split: int = Field(ge=5, le=95, default=30)
    scenario_id: str
    scenario_name: str
    duration_days: int = Field(ge=1, le=30, default=7)


class ABTestUpdateRequest(BaseModel):
    traffic_split: Optional[int] = Field(ge=5, le=95, default=None)
    status: Optional[ABTestStatus] = None


class RetrainCreateRequest(BaseModel):
    model_id: str
    model_name: str
    scenario_id: str
    scenario_name: str
    retrain_type: RetrainType = RetrainType.INCREMENTAL
    trigger: RetrainTrigger = RetrainTrigger.MANUAL
    auto_deploy: bool = False


class PromptExecuteRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = None
    model_id: Optional[str] = None
    scenario_id: Optional[str] = None
    time_range: Optional[str] = "7d"
    enabled_skills: Optional[List[str]] = None


def _is_english_language(language: Optional[str]) -> bool:
    if not language:
        return False
    return language.lower().startswith("en")


def _request_is_english(request: PromptExecuteRequest) -> bool:
    context = request.context or {}
    language = context.get("language") if isinstance(context, dict) else None
    return _is_english_language(language)


# ============ Mock 数据 ============

MOCK_MODELS = [
    {"model_id": "pv-power-001", "model_name": "光伏功率预测-LSTM", "scenario_id": "renewable-energy", "scenario_name": "新能源发电", "status": "severe", "drift_type": "both", "psi_score": 0.35, "accuracy_change": -12.5, "last_check_time": "2026-03-21 10:30:00", "alert_triggered": True},
    {"model_id": "wind-power-001", "model_name": "风电功率预测-XGBoost", "scenario_id": "renewable-energy", "scenario_name": "新能源发电", "status": "mild", "drift_type": "data", "psi_score": 0.18, "accuracy_change": -5.2, "last_check_time": "2026-03-21 10:25:00", "alert_triggered": False},
    {"model_id": "load-forecast-001", "model_name": "负荷预测-Transformer", "scenario_id": "power-grid", "scenario_name": "电网与微网", "status": "severe", "drift_type": "concept", "psi_score": 0.28, "accuracy_change": -15.8, "last_check_time": "2026-03-21 10:15:00", "alert_triggered": True},
    {"model_id": "defect-detect-001", "model_name": "晶圆缺陷检测-YOLO", "scenario_id": "semiconductor", "scenario_name": "半导体制造", "status": "mild", "drift_type": "data", "psi_score": 0.15, "accuracy_change": -3.8, "last_check_time": "2026-03-21 10:10:00", "alert_triggered": False},
    {"model_id": "quality-pred-001", "model_name": "质量预测-RF", "scenario_id": "steel-manufacturing", "scenario_name": "钢铁制造", "status": "normal", "drift_type": "data", "psi_score": 0.05, "accuracy_change": 0.5, "last_check_time": "2026-03-21 10:05:00", "alert_triggered": False},
]

MOCK_TESTS = [
    {"test_id": "ab-001", "test_name": "光伏预测 v2.1 vs v2.0", "model_a_id": "pv-v2.0", "model_a_name": "光伏预测-LSTM v2.0", "model_b_id": "pv-v2.1", "model_b_name": "光伏预测-LSTM v2.1", "traffic_split": 30, "start_time": "2026-03-18 10:00:00", "status": "running", "result": "pending", "scenario_id": "renewable-energy", "scenario_name": "新能源发电"},
    {"test_id": "ab-002", "test_name": "风电预测 v3.0 vs v2.5", "model_a_id": "wind-v2.5", "model_a_name": "风电预测-XGBoost v2.5", "model_b_id": "wind-v3.0", "model_b_name": "风电预测-XGBoost v3.0", "traffic_split": 50, "start_time": "2026-03-15 08:00:00", "status": "running", "result": "pending", "scenario_id": "renewable-energy", "scenario_name": "新能源发电"},
    {"test_id": "ab-003", "test_name": "负荷预测 Transformer vs LSTM", "model_a_id": "load-lstm", "model_a_name": "负荷预测-LSTM", "model_b_id": "load-trans", "model_b_name": "负荷预测-Transformer", "traffic_split": 20, "start_time": "2026-03-10 00:00:00", "end_time": "2026-03-17 00:00:00", "status": "completed", "result": "b_wins", "scenario_id": "power-grid", "scenario_name": "电网与微网"},
]

MOCK_TASKS = [
    {"task_id": "rt-001", "model_id": "pv-power-001", "model_name": "光伏功率预测-LSTM", "scenario_id": "renewable-energy", "scenario_name": "新能源发电", "retrain_type": "incremental", "trigger": "drift_detected", "status": "training", "created_at": "2026-03-21 09:00:00", "started_at": "2026-03-21 09:05:00", "progress": 65, "old_accuracy": 92.5},
    {"task_id": "rt-002", "model_id": "load-forecast-001", "model_name": "负荷预测-Transformer", "scenario_id": "power-grid", "scenario_name": "电网与微网", "retrain_type": "full", "trigger": "drift_detected", "status": "validating", "created_at": "2026-03-21 08:00:00", "started_at": "2026-03-21 08:10:00", "progress": 90, "old_accuracy": 88.2, "new_accuracy": 93.5, "improvement": 5.3},
    {"task_id": "rt-003", "model_id": "wind-power-001", "model_name": "风电功率预测-XGBoost", "scenario_id": "renewable-energy", "scenario_name": "新能源发电", "retrain_type": "incremental", "trigger": "scheduled", "status": "queued", "created_at": "2026-03-21 10:00:00", "progress": 0, "old_accuracy": 91.8},
]
# @AI_GENERATED: end


# @AI_GENERATED: Kiro v1.0
# ============ 漂移检测 API ============

@router.get("/drift/models")
async def get_drift_models(
    status: Optional[str] = Query(None, description="状态筛选: normal/mild/severe"),
    scenario_id: Optional[str] = Query(None, description="场景ID筛选")
):
    """获取模型漂移列表"""
    models = MOCK_MODELS.copy()
    if status and status != "all":
        models = [m for m in models if m["status"] == status]
    if scenario_id:
        models = [m for m in models if m["scenario_id"] == scenario_id]
    return {"models": models, "total": len(models)}


@router.get("/drift/stats")
async def get_drift_stats():
    """获取漂移监控统计"""
    return {
        "total_models": 45,
        "normal_count": 32,
        "mild_drift_count": 8,
        "severe_drift_count": 5,
        "retrain_triggered": 3
    }


@router.post("/drift/detect")
async def detect_drift(request: DriftDetectRequest):
    """执行漂移检测"""
    model = next((m for m in MOCK_MODELS if m["model_id"] == request.model_id), None)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    
    # 模拟检测结果
    psi_score = round(random.uniform(0.01, 0.4), 2)
    ks_score = round(random.uniform(0.01, 0.3), 2)
    js_divergence = round(random.uniform(0.01, 0.25), 2)
    
    status = "normal"
    if psi_score > 0.25 or ks_score > 0.2:
        status = "severe"
    elif psi_score > 0.1 or ks_score > 0.1:
        status = "mild"
    
    return {
        "model_id": request.model_id,
        "status": status,
        "psi_score": psi_score,
        "ks_score": ks_score,
        "js_divergence": js_divergence,
        "check_time": datetime.now().isoformat(),
        "feature_drifts": [
            {"feature": "辐照度", "psi": round(random.uniform(0.01, 0.5), 2)},
            {"feature": "温度", "psi": round(random.uniform(0.01, 0.3), 2)},
            {"feature": "湿度", "psi": round(random.uniform(0.01, 0.2), 2)},
            {"feature": "风速", "psi": round(random.uniform(0.01, 0.15), 2)},
        ]
    }


@router.post("/drift/analyze")
async def analyze_drift(request: DriftAnalyzeRequest):
    """分析漂移根因"""
    model = next((m for m in MOCK_MODELS if m["model_id"] == request.model_id), None)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    
    return {
        "model_id": request.model_id,
        "analysis_time": datetime.now().isoformat(),
        "root_causes": [
            {"cause": "辐照度传感器校准偏移", "confidence": 0.85, "impact": "high"},
            {"cause": "季节性数据分布变化", "confidence": 0.72, "impact": "medium"},
            {"cause": "新增光伏板类型", "confidence": 0.45, "impact": "low"},
        ],
        "recommendations": [
            "建议重新校准辐照度传感器",
            "考虑增加季节性特征",
            "收集新光伏板类型的训练数据"
        ],
        "accuracy_trend": [
            {"date": "2026-03-15", "accuracy": 94.5},
            {"date": "2026-03-16", "accuracy": 93.8},
            {"date": "2026-03-17", "accuracy": 92.1},
            {"date": "2026-03-18", "accuracy": 90.5},
            {"date": "2026-03-19", "accuracy": 88.2},
            {"date": "2026-03-20", "accuracy": 85.5},
            {"date": "2026-03-21", "accuracy": 82.0},
        ]
    }


@router.get("/drift/alerts")
async def get_drift_alerts(
    acknowledged: Optional[bool] = Query(None, description="是否已确认")
):
    """获取漂移告警列表"""
    alerts = [
        {"alert_id": "alert-001", "model_id": "pv-power-001", "model_name": "光伏功率预测-LSTM", "severity": "critical", "message": "PSI超过阈值0.25，当前值0.35", "created_at": "2026-03-21 10:30:00", "acknowledged": False},
        {"alert_id": "alert-002", "model_id": "load-forecast-001", "model_name": "负荷预测-Transformer", "severity": "critical", "message": "精度下降超过10%，当前下降15.8%", "created_at": "2026-03-21 10:15:00", "acknowledged": False},
        {"alert_id": "alert-003", "model_id": "wind-power-001", "model_name": "风电功率预测-XGBoost", "severity": "warning", "message": "检测到轻度数据漂移", "created_at": "2026-03-21 10:25:00", "acknowledged": True},
    ]
    if acknowledged is not None:
        alerts = [a for a in alerts if a["acknowledged"] == acknowledged]
    return {"alerts": alerts, "total": len(alerts)}


@router.put("/drift/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """确认告警"""
    return {"alert_id": alert_id, "acknowledged": True, "acknowledged_at": datetime.now().isoformat()}
# @AI_GENERATED: end


# @AI_GENERATED: Kiro v1.0
# ============ A/B 测试 API ============

@router.get("/abtest/tests")
async def get_ab_tests(
    status: Optional[str] = Query(None, description="状态筛选"),
    scenario_id: Optional[str] = Query(None, description="场景ID筛选")
):
    """获取A/B测试列表"""
    tests = MOCK_TESTS.copy()
    if status and status != "all":
        tests = [t for t in tests if t["status"] == status]
    if scenario_id:
        tests = [t for t in tests if t["scenario_id"] == scenario_id]
    return {"tests": tests, "total": len(tests)}


@router.get("/abtest/stats")
async def get_ab_test_stats():
    """获取A/B测试统计"""
    return {
        "total_tests": 22,
        "running_count": 5,
        "completed_count": 12,
        "a_wins_count": 4,
        "b_wins_count": 8
    }


@router.post("/abtest/tests")
async def create_ab_test(request: ABTestCreateRequest):
    """创建A/B测试"""
    test_id = f"ab-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {
        "test_id": test_id,
        "test_name": request.test_name,
        "model_a_id": request.model_a_id,
        "model_a_name": request.model_a_name,
        "model_b_id": request.model_b_id,
        "model_b_name": request.model_b_name,
        "traffic_split": request.traffic_split,
        "scenario_id": request.scenario_id,
        "scenario_name": request.scenario_name,
        "status": "pending",
        "result": "pending",
        "start_time": None,
        "created_at": datetime.now().isoformat()
    }


@router.get("/abtest/tests/{test_id}")
async def get_ab_test(test_id: str):
    """获取A/B测试详情"""
    test = next((t for t in MOCK_TESTS if t["test_id"] == test_id), None)
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")
    return test


@router.put("/abtest/tests/{test_id}")
async def update_ab_test(test_id: str, request: ABTestUpdateRequest):
    """更新A/B测试"""
    test = next((t for t in MOCK_TESTS if t["test_id"] == test_id), None)
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")
    
    if request.traffic_split is not None:
        test["traffic_split"] = request.traffic_split
    if request.status is not None:
        test["status"] = request.status.value
    
    return test


@router.post("/abtest/tests/{test_id}/start")
async def start_ab_test(test_id: str):
    """启动A/B测试"""
    return {
        "test_id": test_id,
        "status": "running",
        "start_time": datetime.now().isoformat()
    }


@router.post("/abtest/tests/{test_id}/pause")
async def pause_ab_test(test_id: str):
    """暂停A/B测试"""
    return {"test_id": test_id, "status": "paused"}


@router.post("/abtest/tests/{test_id}/stop")
async def stop_ab_test(test_id: str):
    """停止A/B测试"""
    return {
        "test_id": test_id,
        "status": "completed",
        "end_time": datetime.now().isoformat()
    }


@router.get("/abtest/tests/{test_id}/metrics")
async def get_ab_test_metrics(test_id: str):
    """获取A/B测试指标"""
    return {
        "test_id": test_id,
        "model_a": {
            "accuracy": 92.5,
            "latency_p50": 45,
            "latency_p99": 120,
            "error_rate": 0.5,
            "sample_count": 15000
        },
        "model_b": {
            "accuracy": 94.8,
            "latency_p50": 42,
            "latency_p99": 105,
            "error_rate": 0.3,
            "sample_count": 5000
        },
        "statistical_significance": 0.95,
        "confidence_interval": [1.8, 2.8],
        "recommendation": "b_wins",
        "recommendation_reason": "模型B在精度、延迟、错误率三项指标均优于模型A，置信度95%"
    }


@router.post("/abtest/tests/{test_id}/adopt")
async def adopt_ab_test_winner(test_id: str, winner: str = Query(..., description="获胜模型: a/b")):
    """采纳A/B测试获胜模型"""
    return {
        "test_id": test_id,
        "adopted_model": winner,
        "status": "completed",
        "result": f"{winner}_wins",
        "adopted_at": datetime.now().isoformat()
    }
# @AI_GENERATED: end


# @AI_GENERATED: Kiro v1.0
# ============ 自动重训 API ============

@router.get("/retrain/tasks")
async def get_retrain_tasks(
    status: Optional[str] = Query(None, description="状态筛选"),
    scenario_id: Optional[str] = Query(None, description="场景ID筛选")
):
    """获取重训任务列表"""
    tasks = MOCK_TASKS.copy()
    if status and status != "all":
        tasks = [t for t in tasks if t["status"] == status]
    if scenario_id:
        tasks = [t for t in tasks if t["scenario_id"] == scenario_id]
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/retrain/stats")
async def get_retrain_stats():
    """获取重训统计"""
    return {
        "total_tasks": 29,
        "queued_count": 8,
        "training_count": 2,
        "completed_count": 15,
        "failed_count": 1,
        "avg_improvement": 3.2
    }


@router.post("/retrain/tasks")
async def create_retrain_task(request: RetrainCreateRequest):
    """创建重训任务"""
    task_id = f"rt-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {
        "task_id": task_id,
        "model_id": request.model_id,
        "model_name": request.model_name,
        "scenario_id": request.scenario_id,
        "scenario_name": request.scenario_name,
        "retrain_type": request.retrain_type.value,
        "trigger": request.trigger.value,
        "auto_deploy": request.auto_deploy,
        "status": "queued",
        "progress": 0,
        "created_at": datetime.now().isoformat()
    }


@router.get("/retrain/tasks/{task_id}")
async def get_retrain_task(task_id: str):
    """获取重训任务详情"""
    task = next((t for t in MOCK_TASKS if t["task_id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/retrain/tasks/{task_id}/start")
async def start_retrain_task(task_id: str):
    """启动重训任务"""
    return {
        "task_id": task_id,
        "status": "training",
        "started_at": datetime.now().isoformat()
    }


@router.post("/retrain/tasks/{task_id}/cancel")
async def cancel_retrain_task(task_id: str):
    """取消重训任务"""
    return {
        "task_id": task_id,
        "status": "cancelled",
        "cancelled_at": datetime.now().isoformat()
    }


@router.get("/retrain/tasks/{task_id}/logs")
async def get_retrain_logs(task_id: str):
    """获取重训日志"""
    return {
        "task_id": task_id,
        "logs": [
            {"time": "09:05:00", "level": "info", "message": "开始训练 光伏功率预测-LSTM"},
            {"time": "09:05:01", "level": "info", "message": "加载数据: 15,000样本"},
            {"time": "09:05:05", "level": "info", "message": "数据预处理完成"},
            {"time": "09:10:00", "level": "info", "message": "Epoch 10/50, Loss: 0.125"},
            {"time": "09:15:00", "level": "info", "message": "Epoch 20/50, Loss: 0.082"},
            {"time": "09:20:00", "level": "info", "message": "Epoch 30/50, Loss: 0.052"},
            {"time": "09:25:00", "level": "info", "message": "Epoch 40/50, Loss: 0.038"},
            {"time": "09:30:00", "level": "info", "message": "训练中... Epoch 45/50"},
        ]
    }


@router.get("/retrain/tasks/{task_id}/metrics")
async def get_retrain_metrics(task_id: str):
    """获取重训指标"""
    return {
        "task_id": task_id,
        "training_loss": [0.5, 0.35, 0.25, 0.18, 0.12, 0.08, 0.05, 0.04, 0.035, 0.032],
        "validation_loss": [0.55, 0.38, 0.28, 0.20, 0.14, 0.10, 0.07, 0.055, 0.045, 0.040],
        "old_accuracy": 92.5,
        "new_accuracy": 95.8,
        "improvement": 3.3
    }


@router.post("/retrain/tasks/{task_id}/deploy")
async def deploy_retrained_model(task_id: str):
    """部署重训后的模型"""
    return {
        "task_id": task_id,
        "status": "deployed",
        "deployed_at": datetime.now().isoformat(),
        "deployment_id": f"deploy-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    }


@router.post("/retrain/evaluate")
async def evaluate_retrain_need(model_id: str = Query(..., description="模型ID")):
    """评估模型是否需要重训"""
    model = next((m for m in MOCK_MODELS if m["model_id"] == model_id), None)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    
    need_retrain = model["status"] in ["mild", "severe"]
    return {
        "model_id": model_id,
        "need_retrain": need_retrain,
        "reason": "检测到数据漂移" if need_retrain else "模型状态正常",
        "recommended_type": "full" if model["status"] == "severe" else "incremental",
        "estimated_duration": "2小时" if model["status"] == "severe" else "30分钟"
    }
# @AI_GENERATED: end


# @AI_GENERATED: Kiro v1.0
# ============ Prompt 执行 API (统一入口) ============

@router.post("/prompt/execute")
async def execute_prompt(request: PromptExecuteRequest):
    """执行自然语言 Prompt（统一入口）"""
    prompt = request.prompt.lower()
    use_english = _request_is_english(request)
    
    # 根据 prompt 内容路由到不同的处理逻辑
    if "漂移" in prompt or "诊断" in prompt or "drift" in prompt:
        return await _handle_drift_prompt(request, use_english)
    elif "a/b" in prompt or "测试" in prompt or "test" in prompt:
        return await _handle_abtest_prompt(request, use_english)
    elif "重训" in prompt or "训练" in prompt or "retrain" in prompt:
        return await _handle_retrain_prompt(request, use_english)
    elif "周报" in prompt or "报告" in prompt or "report" in prompt:
        return await _handle_report_prompt(request, use_english)
    else:
        return await _handle_general_prompt(request, use_english)


async def _handle_drift_prompt(request: PromptExecuteRequest, use_english: bool = False) -> Dict[str, Any]:
    """处理漂移相关的 Prompt"""
    severe_models = [m for m in MOCK_MODELS if m["status"] == "severe"]
    mild_models = [m for m in MOCK_MODELS if m["status"] == "mild"]
    
    response_text = "Drift diagnosis completed:\n\n" if use_english else "已完成模型漂移诊断：\n\n"
    
    if severe_models:
        response_text += f"🔴 Severe drift ({len(severe_models)}):\n" if use_english else f"🔴 严重漂移 ({len(severe_models)}个):\n"
        for m in severe_models:
            response_text += (
                f"- {m['model_name']}: PSI={m['psi_score']}, accuracy drop {abs(m['accuracy_change'])}%\n"
                if use_english
                else f"- {m['model_name']}: PSI={m['psi_score']}, 精度下降{abs(m['accuracy_change'])}%\n"
            )
    
    if mild_models:
        response_text += f"\n🟡 Mild drift ({len(mild_models)}):\n" if use_english else f"\n🟡 轻度漂移 ({len(mild_models)}个):\n"
        for m in mild_models:
            response_text += f"- {m['model_name']}\n"
    
    response_text += (
        "\nRecommendation: trigger auto-retraining for models with severe drift."
        if use_english
        else "\n建议：对严重漂移模型触发自动重训。"
    )
    
    return {
        "response": response_text,
        "type": "drift_analysis",
        "data": {
            "severe_models": severe_models,
            "mild_models": mild_models,
            "total_checked": len(MOCK_MODELS)
        },
        "actions": [
            {"label": "Trigger retraining" if use_english else "触发重训", "action": "retrain", "model_ids": [m["model_id"] for m in severe_models]},
            {"label": "View details" if use_english else "查看详情", "action": "view_details"}
        ]
    }


async def _handle_abtest_prompt(request: PromptExecuteRequest, use_english: bool = False) -> Dict[str, Any]:
    """处理 A/B 测试相关的 Prompt"""
    running_tests = [t for t in MOCK_TESTS if t["status"] == "running"]
    completed_tests = [t for t in MOCK_TESTS if t["status"] == "completed"]
    
    response_text = "Current A/B test status:\n\n" if use_english else "当前 A/B 测试状态：\n\n"
    
    # 模拟可结束的测试
    response_text += "✅ Can be ended:\n" if use_english else "✅ 可结束测试:\n"
    response_text += (
        "- PV Forecast v2.1 vs v2.0: reached 95% confidence, Model B improves accuracy by 2.3%, recommend adopting.\n"
        if use_english
        else "- 光伏预测 v2.1 vs v2.0: 已达95%置信度，B模型精度提升2.3%，建议采纳\n"
    )
    
    response_text += "\n⏳ Continue observing:\n" if use_english else "\n⏳ 继续观察:\n"
    response_text += (
        "- Wind Forecast v3.0 vs v2.5: insufficient sample size, recommend running for 3 more days."
        if use_english
        else "- 风电预测 v3.0 vs v2.5: 样本量不足，建议继续运行3天"
    )
    
    return {
        "response": response_text,
        "type": "abtest_analysis",
        "data": {
            "running_tests": running_tests,
            "completed_tests": completed_tests,
            "recommendations": [
                {"test_id": "ab-001", "action": "adopt_b", "confidence": 0.95},
                {"test_id": "ab-002", "action": "continue", "days_remaining": 3}
            ]
        },
        "actions": [
            {"label": "Adopt Model B" if use_english else "采纳B模型", "action": "adopt", "test_id": "ab-001", "winner": "b"},
            {"label": "Extend test" if use_english else "延长测试", "action": "extend", "test_id": "ab-002"}
        ]
    }


async def _handle_retrain_prompt(request: PromptExecuteRequest, use_english: bool = False) -> Dict[str, Any]:
    """处理重训相关的 Prompt"""
    training_tasks = [t for t in MOCK_TASKS if t["status"] == "training"]
    validating_tasks = [t for t in MOCK_TASKS if t["status"] == "validating"]
    queued_tasks = [t for t in MOCK_TASKS if t["status"] == "queued"]
    
    response_text = "Retraining tasks in progress:\n\n" if use_english else "重训任务执行中：\n\n"
    
    if training_tasks:
        response_text += f"🔄 Training ({len(training_tasks)}):\n" if use_english else f"🔄 训练中 ({len(training_tasks)}个):\n"
        for t in training_tasks:
            response_text += (
                f"- {t['model_name']}: progress {t['progress']}%, estimated completion in 30 minutes\n"
                if use_english
                else f"- {t['model_name']}: 进度{t['progress']}%，预计30分钟完成\n"
            )
    
    if validating_tasks:
        response_text += f"\n✅ Pending validation ({len(validating_tasks)}):\n" if use_english else f"\n✅ 待验证 ({len(validating_tasks)}个):\n"
        for t in validating_tasks:
            improvement = t.get('improvement', 0)
            response_text += (
                f"- {t['model_name']}: accuracy improves by {improvement}%, recommend validating via A/B test\n"
                if use_english
                else f"- {t['model_name']}: 精度提升{improvement}%，建议创建A/B测试验证\n"
            )
    
    if queued_tasks:
        response_text += f"\n⏳ Queued ({len(queued_tasks)}):\n" if use_english else f"\n⏳ 排队中 ({len(queued_tasks)}个):\n"
        for t in queued_tasks:
            response_text += f"- {t['model_name']}\n"
    
    return {
        "response": response_text,
        "type": "retrain_status",
        "data": {
            "training_tasks": training_tasks,
            "validating_tasks": validating_tasks,
            "queued_tasks": queued_tasks
        },
        "actions": [
            {"label": "Deploy validated models" if use_english else "部署验证完成的模型", "action": "deploy", "task_ids": [t["task_id"] for t in validating_tasks]},
            {"label": "Create A/B test" if use_english else "创建A/B测试", "action": "create_abtest"}
        ]
    }


async def _handle_report_prompt(request: PromptExecuteRequest, use_english: bool = False) -> Dict[str, Any]:
    """处理报告生成相关的 Prompt"""
    response_text = (
        """📊 Weekly Algorithm Operations Report

[Drift Monitoring]
- Monitored models: 45
- New drift cases: 5 (2 severe, 3 mild)
- Fixed: 3

[A/B Testing]
- Completed tests: 3
- New version wins: 2
- Average gain: 3.8%

[Auto Retraining]
- Completed retrains: 5
- Average accuracy gain: 3.2%

Recommendation: prioritize drift issues for PV and load forecasting models."""
        if use_english else
        """📊 本周算法运营周报

【漂移监控】
- 监控模型: 45个
- 新增漂移: 5个 (严重2, 轻度3)
- 已修复: 3个

【A/B测试】
- 完成测试: 3个
- 新版胜出: 2个
- 平均提升: 3.8%

【自动重训】
- 完成重训: 5个
- 平均精度提升: 3.2%

建议：优先处理光伏和负荷预测模型的漂移问题。"""
    )
    
    return {
        "response": response_text,
        "type": "weekly_report",
        "data": {
            "drift": {"total": 45, "new_drift": 5, "fixed": 3},
            "abtest": {"completed": 3, "new_version_wins": 2, "avg_improvement": 3.8},
            "retrain": {"completed": 5, "avg_improvement": 3.2}
        },
        "actions": [
            {"label": "Export PDF" if use_english else "导出PDF", "action": "export_pdf"},
            {"label": "Send Email" if use_english else "发送邮件", "action": "send_email"}
        ]
    }


async def _handle_general_prompt(request: PromptExecuteRequest, use_english: bool = False) -> Dict[str, Any]:
    """处理通用 Prompt"""
    response_text = (
        """Request received. Analyzing now...

I can help with:
1. Diagnosing model drift
2. Analyzing A/B test results
3. Managing auto-retraining tasks
4. Generating operations reports

Tell me what you want to do."""
        if use_english else
        """收到您的请求，正在分析中...

我可以帮您：
1. 诊断模型漂移状态
2. 分析 A/B 测试结果
3. 管理自动重训任务
4. 生成运营报告

请告诉我具体需要什么帮助？"""
    )
    
    return {
        "response": response_text,
        "type": "general",
        "data": {},
        "actions": [
            {"label": "Diagnose drift" if use_english else "诊断漂移", "action": "diagnose_drift"},
            {"label": "View A/B tests" if use_english else "查看A/B测试", "action": "view_abtest"},
            {"label": "View retraining tasks" if use_english else "查看重训任务", "action": "view_retrain"},
            {"label": "Generate report" if use_english else "生成周报", "action": "generate_report"}
        ]
    }


# ============ 技能管理 API ============

@router.get("/skills")
async def get_available_skills():
    """获取可用技能列表"""
    return {
        "skills": [
            {"id": "drift-detect", "name": "漂移检测", "description": "使用 PSI/KS/JS 检测数据漂移", "enabled": True},
            {"id": "root-cause", "name": "根因分析", "description": "智能分析精度下降的根本原因", "enabled": True},
            {"id": "ab-analyze", "name": "A/B分析", "description": "统计显著性检验和决策建议", "enabled": True},
            {"id": "retrain-eval", "name": "重训评估", "description": "评估模型是否需要重训", "enabled": False},
            {"id": "data-quality", "name": "数据质量", "description": "检查生产数据质量问题", "enabled": False},
            {"id": "report-gen", "name": "报告生成", "description": "自动生成运营分析报告", "enabled": True},
        ]
    }


@router.put("/skills/{skill_id}/toggle")
async def toggle_skill(skill_id: str, enabled: bool = Query(...)):
    """切换技能启用状态"""
    return {"skill_id": skill_id, "enabled": enabled}
# @AI_GENERATED: end
