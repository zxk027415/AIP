# @AI_GENERATED: Kiro v1.0
"""
Algorithm Agent API
算法全生命周期管理 Agent 接口
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Callable, Awaitable, Tuple
from datetime import datetime
import uuid
import asyncio
import re
import json
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/algorithm", tags=["Algorithm Agent"])

# ============ 数据模型 ============

class SessionContext(BaseModel):
    selected_algorithm: Optional[Dict[str, Any]] = None
    selected_skill: Optional[str] = None
    current_model: Optional[str] = None
    experiment_ids: Optional[List[str]] = None
    active_ab_test: Optional[str] = None
    agent_type: Optional[str] = None  # Agent 类型: curator, sandbox, onboarding, operation
    language: Optional[str] = None  # 当前会话语言，如 zh-CN / en-US
    # 运营分析：显式指定要解读的模板 id（高于「最近执行」）
    workflow_id: Optional[str] = None
    template_id: Optional[str] = None
    # 最近一次在编辑器里启动的流水线/回测对应的模板 id（前端写入 + 本会话回写）
    last_executed_workflow_id: Optional[str] = None
    preselected_template: Optional[Dict[str, Any]] = None
    backtest_start_date: Optional[str] = None
    backtest_end_date: Optional[str] = None
    trigger_backtest_after_retrain: Optional[bool] = None
    trigger_backtest_after_tuning: Optional[bool] = None

class AgentMessage(BaseModel):
    id: str
    role: str  # user, assistant, system
    content: str
    timestamp: str
    skill: Optional[str] = None
    skill_result: Optional[Dict[str, Any]] = None
    reasoning_content: Optional[str] = None

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    context: Optional[SessionContext] = None
    use_llm: Optional[bool] = True  # 是否使用 LLM

class ChatResponse(BaseModel):
    session_id: str
    message: AgentMessage
    suggested_actions: Optional[List[Dict[str, Any]]] = None
    context_update: Optional[Dict[str, Any]] = None
    llm_used: Optional[bool] = False  # 是否使用了 LLM

class AlgorithmRecommendRequest(BaseModel):
    description: str
    data_characteristics: Optional[Dict[str, Any]] = None
    business_objective: Optional[str] = None

class TrainingRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    skill_id: str
    model_type: str
    parameters: Optional[Dict[str, Any]] = None
    data_config: Optional[Dict[str, Any]] = None

class DriftDetectRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str
    reference_data: Optional[str] = None
    current_data: Optional[str] = None

class ABTestConfig(BaseModel):
    model_config = {"protected_namespaces": ()}
    name: str
    control_model_id: str
    treatment_model_id: str
    traffic_split: int
    duration_hours: int
    metrics: List[str]

# ============ 内存存储 ============

sessions: Dict[str, Dict[str, Any]] = {}

# ============ 对话接口 ============

# @AI_GENERATED: Kiro v1.0
# Function Calling 模式下，LLM 会自动决定是否调用工具
# 不再需要关键词强制规则，但保留作为降级方案
FORCE_RULE_RESPONSE_KEYWORDS = [
    # 当 LLM 不支持 Function Calling 时的降级关键词
    # 目前保留为空，让 LLM 自动处理
]

def should_use_rule_response(message: str) -> bool:
    """检查是否应该强制使用规则响应（降级方案）"""
    # Function Calling 模式下，让 LLM 自动决定
    # 只有在 LLM 不可用时才会降级到规则响应
    return False


def is_english_language(language: Optional[str]) -> bool:
    """是否英文会话"""
    if not language:
        return False
    return language.lower().startswith("en")
# @AI_GENERATED: end

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """发送对话消息"""
    # 获取或创建会话
    session_id = request.session_id or str(uuid.uuid4())
    
    if session_id not in sessions:
        sessions[session_id] = {
            "id": session_id,
            "messages": [],
            "context": {},
            "created_at": datetime.now().isoformat(),
        }
    
    session = sessions[session_id]
    
    # 合并请求中的 context
    if request.context:
        session["context"].update(request.context.dict(exclude_none=True))
    
    # 添加用户消息
    user_msg = {
        "id": f"user-{datetime.now().timestamp()}",
        "role": "user",
        "content": request.message,
        "timestamp": datetime.now().isoformat(),
    }
    session["messages"].append(user_msg)
    
    # @AI_GENERATED: Kiro v1.0
    # 检查是否需要强制使用规则响应（模板查询等需要返回格式化数据的场景）
    force_rule = should_use_rule_response(request.message)
    
    # 尝试使用 LLM 生成响应
    llm_used = False
    if request.use_llm and not force_rule:
        llm_response = await generate_llm_response(request.message, session)
        if llm_response:
            response_content = llm_response
            skill_name = None
            if session.get("context", {}).get("agent_type") == "operation":
                suggested_actions = session.get("context", {}).get("last_operation_suggested_actions") or get_suggested_actions_for_message(
                    request.message,
                    session.get("context", {}).get("agent_type"),
                )
            else:
                suggested_actions = get_suggested_actions_for_message(
                    request.message,
                    session.get("context", {}).get("agent_type"),
                )
            context_update = {}
            llm_used = True
        else:
            # LLM 不可用，使用规则响应
            response_content, skill_name, suggested_actions, context_update = generate_response(
                request.message, 
                session.get("context", {})
            )
    else:
        # 不使用 LLM 或强制使用规则响应
        response_content, skill_name, suggested_actions, context_update = generate_response(
            request.message, 
            session.get("context", {})
        )
    # @AI_GENERATED: end
    
    # 更新会话 context
    if context_update:
        session["context"].update(context_update)
    
    _op_rc = None
    if session.get("context", {}).get("agent_type") == "operation":
        _op_rc = session.get("context", {}).get("last_model_reasoning")
    assistant_msg = AgentMessage(
        id=f"assistant-{datetime.now().timestamp()}",
        role="assistant",
        content=response_content,
        timestamp=datetime.now().isoformat(),
        skill=skill_name if not llm_used else None,
        reasoning_content=_op_rc,
    )
    session["messages"].append(assistant_msg.model_dump())
    
    return ChatResponse(
        session_id=session_id,
        message=assistant_msg,
        suggested_actions=suggested_actions,
        context_update=context_update if context_update else None,
        llm_used=llm_used,
    )

# @AI_GENERATED: Kiro v1.0
from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话消息"""

    # 获取或创建会话
    session_id = request.session_id or str(uuid.uuid4())
    
    if session_id not in sessions:
        sessions[session_id] = {
            "id": session_id,
            "messages": [],
            "context": {},
            "created_at": datetime.now().isoformat(),
        }
    
    session = sessions[session_id]
    
    # 合并请求中的 context
    if request.context:
        session["context"].update(request.context.dict(exclude_none=True))
    
    # 添加用户消息
    user_msg = {
        "id": f"user-{datetime.now().timestamp()}",
        "role": "user",
        "content": request.message,
        "timestamp": datetime.now().isoformat(),
    }
    session["messages"].append(user_msg)
    
    # 检查是否需要强制使用规则响应
    force_rule = should_use_rule_response(request.message)
    
    async def generate():
        import sys
        import os
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        
        from services.llm_service import get_llm_service
        
        full_content = ""
        llm_used = False
        suggested_actions = []
        
        try:
            # 获取 agent_type 与 language
            agent_type = session.get("context", {}).get("agent_type")
            language = session.get("context", {}).get("language")
            
            # 对于 curator agent，中文会话使用 Master Agent 架构（非流式，直接返回完整响应）
            # 英文会话走通用 LLM 路径，确保与前端国际化切换一致
            if agent_type == "curator" and request.use_llm and not force_rule and not is_english_language(language):
                from services.curator_agent import get_curator_master_agent
                
                master_agent = get_curator_master_agent()
                
                # 构建上下文，包含对话历史
                context = session.get("context", {}).copy()
                context["conversation_history"] = session.get("messages", [])[-10:]
                
                print(f"[Curator Master Agent Stream] 处理消息: {request.message[:50]}...")
                print(f"[Curator Master Agent Stream] 对话历史: {len(context.get('conversation_history', []))} 条消息")
                result = await master_agent.process(request.message, context)
                
                intent = result.get("intent", {})
                print(f"[Curator Master Agent Stream] 意图: {intent.get('primary_intent')} (置信度: {intent.get('confidence', 0):.2f})")
                
                full_content = result.get("response", "")
                suggested_actions = result.get("suggested_actions", [])
                llm_used = True
                
                # 发送开始事件
                yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"
                
                # 一次性发送完整内容（Master Agent 不支持流式）
                yield f"data: {json.dumps({'type': 'chunk', 'content': full_content})}\n\n"
                
            # 运营 agent：Master + Sub-Agent（强制预读取、混合打分路由、依赖补全）
            elif agent_type == "operation" and request.use_llm and not force_rule:
                yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"
                progress_queue: asyncio.Queue[str] = asyncio.Queue()

                async def _op_progress_enqueue(msg: str):
                    await progress_queue.put(msg)

                op_task = asyncio.create_task(
                    _generate_operation_response(
                        request.message,
                        session,
                        on_progress=_op_progress_enqueue,
                    )
                )
                while True:
                    if op_task.done() and progress_queue.empty():
                        break
                    try:
                        progress_msg = await asyncio.wait_for(progress_queue.get(), timeout=0.15)
                        progress_payload = {
                            "type": "reasoning_chunk",
                            "content": "- " + str(progress_msg) + "\n",
                        }
                        yield f"data: {json.dumps(progress_payload, ensure_ascii=False)}\n\n"
                    except asyncio.TimeoutError:
                        continue
                op_result = await op_task
                if op_result:
                    reasoning = op_result.get("reasoning")
                    if reasoning:
                        yield f"data: {json.dumps({'type': 'reasoning', 'content': reasoning}, ensure_ascii=False)}\n\n"
                    # 明确给前端一个“思考结束 -> 开始输出结果”的过渡，避免观感上结果抢跑
                    yield f"data: {json.dumps({'type': 'reasoning_progress', 'message': '思考完成，正在组织最终答复...'}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.2)
                    full_content = op_result.get("response", "")
                    if full_content:
                        yield f"data: {json.dumps({'type': 'chunk', 'content': full_content}, ensure_ascii=False)}\n\n"
                    llm_used = True

            # 其他 agent 类型使用 LLM 流式输出
            elif request.use_llm and not force_rule:
                llm_service = await get_llm_service()
                if llm_service:
                    # 构建消息
                    system_prompt = get_system_prompt(agent_type, language)
                    messages = [
                        {"role": "system", "content": system_prompt}
                    ]
                    history = session.get("messages", [])[-10:]
                    for msg in history:
                        if msg["role"] in ["user", "assistant"]:
                            messages.append({
                                "role": msg["role"],
                                "content": msg["content"]
                            })
                    messages.append({"role": "user", "content": request.message})
                    
                    # 发送开始事件
                    yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"
                    
                    # 流式输出
                    async for chunk in llm_service.chat_stream(messages):
                        full_content += chunk
                        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                    
                    llm_used = True
        except Exception as e:
            print(f"[Algorithm Agent Stream] LLM 调用失败: {e}")
            import traceback
            print(traceback.format_exc())
        
        # 如果 LLM 失败、未启用或强制使用规则响应，使用规则响应
        if not llm_used:
            response_content, skill_name, suggested_actions, context_update = generate_response(
                request.message, 
                session.get("context", {})
            )
            full_content = response_content
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'content': full_content})}\n\n"
        
        # 保存助手消息（运营 Agent 附思考/工具轨迹，便于历史回放）
        assistant_msg: Dict[str, Any] = {
            "id": f"assistant-{datetime.now().timestamp()}",
            "role": "assistant",
            "content": full_content,
            "timestamp": datetime.now().isoformat(),
        }
        if session.get("context", {}).get("agent_type") == "operation":
            r = session.get("context", {}).get("last_model_reasoning")
            if r:
                assistant_msg["reasoning_content"] = r
        session["messages"].append(assistant_msg)
        
        # 发送完成事件
        if session.get("context", {}).get("agent_type") == "operation":
            suggested_actions = session.get("context", {}).get("last_operation_suggested_actions") or get_suggested_actions_for_message(
                request.message,
                session.get("context", {}).get("agent_type"),
            )
        else:
            suggested_actions = get_suggested_actions_for_message(
                request.message,
                session.get("context", {}).get("agent_type"),
            )
        done_payload = {
            "type": "done",
            "llm_used": llm_used,
            "suggested_actions": suggested_actions,
        }
        if session.get("context", {}).get("agent_type") == "operation":
            done_payload["operation_observability"] = session.get("context", {}).get("last_operation_observability")
        yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
# @AI_GENERATED: end

@router.get("/sessions")
async def get_sessions():
    """获取会话列表"""
    return [
        {
            "id": s["id"],
            "title": s["messages"][0]["content"][:50] if s["messages"] else "新会话",
            "updated_at": s["messages"][-1]["timestamp"] if s["messages"] else s["created_at"],
        }
        for s in sessions.values()
    ]

@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    if session_id in sessions:
        del sessions[session_id]
    return {"status": "ok"}

# ============ Skills 接口 ============

@router.post("/skills/algorithm-recommend")
async def recommend_algorithm(request: AlgorithmRecommendRequest):
    """
    算法推荐 - 完整实现
    集成 Workflow Agent 场景匹配 + 算法库查询 (1054 个算法)
    """
    # @AI_GENERATED: Kiro v1.0
    from backend.services.algorithm_recommend_service import get_algorithm_recommend_service
    
    service = get_algorithm_recommend_service()
    
    try:
        result = await service.recommend(
            description=request.description,
            data_characteristics=request.data_characteristics,
            business_objective=request.business_objective,
            max_results=10,
        )
        return result
    except Exception as e:
        # 降级到简单推荐
        logger.warning(f"完整推荐失败，降级到简单推荐: {e}")
        return await _fallback_recommend(request)
    # @AI_GENERATED: end


async def _fallback_recommend(request: AlgorithmRecommendRequest):
    """降级推荐 - 简单关键词匹配"""
    # @AI_GENERATED: Kiro v1.0
    skills_path = os.path.join(os.path.dirname(__file__), "../data/skills/packaged_skills.json")
    skills = []
    if os.path.exists(skills_path):
        with open(skills_path, "r", encoding="utf-8") as f:
            skills = json.load(f)
    
    recommendations = []
    desc_lower = request.description.lower()
    
    for skill in skills:
        score = 0
        name_lower = skill.get("name", "").lower()
        skill_desc = skill.get("description", "").lower()
        
        keywords = ["光伏", "pv", "solar", "功率", "预测", "forecast", "负荷", "load"]
        for kw in keywords:
            if kw in desc_lower:
                if kw in name_lower:
                    score += 30
                if kw in skill_desc:
                    score += 20
        
        if score > 0:
            recommendations.append({
                "algorithm_id": skill.get("id"),
                "algorithm_name": skill.get("name"),
                "category": skill.get("category", "预测"),
                "score": min(score, 100),
                "rationale": f"基于关键词匹配推荐",
                "source": "industry_template",
            })
    
    if not recommendations:
        recommendations = [
            {
                "algorithm_id": "pv-power-forecast",
                "algorithm_name": "光伏发电功率预测",
                "category": "时序预测",
                "score": 85,
                "rationale": "适用于基于气象数据的功率预测场景",
                "source": "industry_template",
            },
        ]
    
    return {
        "recommendations": sorted(recommendations, key=lambda x: x["score"], reverse=True)[:5],
        "matched_scenarios": [],
        "total_algorithms_searched": len(skills),
        "processing_time_ms": 50,
    }
    # @AI_GENERATED: end

@router.post("/skills/param-config")
async def config_params(algorithm_id: str, preset: str = "standard"):
    """参数配置"""
    # 返回默认参数配置
    return {
        "algorithm_id": algorithm_id,
        "parameters": [
            {"name": "learning_rate", "type": "float", "default": 0.01, "min": 0.0001, "max": 1.0, "description": "学习率"},
            {"name": "epochs", "type": "int", "default": 100, "min": 10, "max": 1000, "description": "训练轮数"},
            {"name": "batch_size", "type": "int", "default": 32, "min": 8, "max": 256, "description": "批次大小"},
        ],
        "recommended_config": {
            "learning_rate": 0.01,
            "epochs": 100,
            "batch_size": 32,
        },
        "presets": {
            "quick": {"epochs": 50, "batch_size": 64},
            "standard": {"epochs": 100, "batch_size": 32},
            "high_accuracy": {"epochs": 200, "batch_size": 16},
        },
    }

@router.post("/skills/training-pipeline/start")
async def start_training(request: TrainingRequest):
    """启动训练"""
    task_id = f"train-{uuid.uuid4().hex[:8]}"
    return {"task_id": task_id}

@router.get("/skills/training-pipeline/{task_id}/progress")
async def get_training_progress(task_id: str):
    """获取训练进度"""
    return {
        "stage": "training",
        "progress": 75,
        "current_epoch": 75,
        "total_epochs": 100,
        "metrics": {"loss": 0.023, "val_loss": 0.028},
    }

@router.get("/skills/training-pipeline/{task_id}/result")
async def get_training_result(task_id: str):
    """获取训练结果"""
    return {
        "task_id": task_id,
        "status": "success",
        "metrics": {
            "train": {"mape": 0.065, "rmse": 120.5, "r2": 0.985},
            "val": {"mape": 0.072, "rmse": 125.3, "r2": 0.982},
            "test": {"mape": 0.077, "rmse": 124.5, "r2": 0.984},
        },
        "training_time_s": 12.5,
    }

@router.post("/skills/drift-detect")
async def detect_drift(request: DriftDetectRequest):
    """漂移检测"""
    return {
        "model_id": request.model_id,
        "data_drift": {
            "detected": True,
            "psi_score": 0.15,
            "drifted_features": ["temperature_forecast", "cloud_cover_forecast"],
        },
        "concept_drift": {
            "detected": False,
            "metric_degradation": 0.032,
            "trend": "stable",
        },
        "recommendation": "检测到轻度数据漂移，建议在未来 7 天内进行增量重训",
        "alert_level": "warning",
    }

@router.post("/skills/ab-test/create")
async def create_ab_test(config: ABTestConfig):
    """创建 A/B 测试"""
    test_id = f"ab-{uuid.uuid4().hex[:8]}"
    return {
        "test_id": test_id,
        "status": "running",
        "control_metrics": {},
        "treatment_metrics": {},
        "sample_size": {"control": 0, "treatment": 0},
    }

@router.get("/skills/ab-test/{test_id}")
async def get_ab_test_result(test_id: str):
    """获取 A/B 测试结果"""
    return {
        "test_id": test_id,
        "status": "running",
        "control_metrics": {"mape": 0.082, "rmse": 130.2},
        "treatment_metrics": {"mape": 0.075, "rmse": 122.5},
        "p_value": 0.03,
        "is_significant": True,
        "recommendation": "adopt",
        "sample_size": {"control": 1200, "treatment": 300},
    }

@router.post("/skills/retrain-trigger/execute")
async def trigger_retrain(model_id: str, reason: str = "manual"):
    """触发重训"""
    return {
        "task_id": f"retrain-{uuid.uuid4().hex[:8]}",
        "trigger_reason": reason,
        "training_type": "incremental",
        "old_metrics": {"mape": 0.082, "r2": 0.978},
        "new_metrics": {"mape": 0.075, "r2": 0.984},
        "improvement": {"mape": -0.007, "r2": 0.006},
        "deployed": False,
    }

@router.get("/quick-commands")
async def get_quick_commands(phase: str = None):
    """获取快捷指令"""
    commands = {
        "research": [
            {"label": "推荐算法", "prompt": "根据我的数据特征推荐合适的算法"},
            {"label": "配置参数", "prompt": "为选定的算法推荐最优参数配置"},
            {"label": "开始训练", "prompt": "使用推荐配置开始模型训练"},
            {"label": "对比实验", "prompt": "对比最近几次实验的结果"},
        ],
        "release": [
            {"label": "代码审查", "prompt": "对当前模型进行代码质量审查"},
            {"label": "性能测试", "prompt": "执行性能基准测试"},
            {"label": "发布版本", "prompt": "准备发布新版本"},
        ],
        "operation": [
            {"label": "漂移检测", "prompt": "检测当前模型是否存在漂移"},
            {"label": "创建A/B测试", "prompt": "创建新旧模型的A/B测试"},
            {"label": "触发重训", "prompt": "评估是否需要重训"},
        ],
    }
    
    if phase and phase in commands:
        return commands[phase]
    
    # 返回所有
    all_commands = []
    for cmds in commands.values():
        all_commands.extend(cmds)
    return all_commands

# ============ 场景细化知识库 ============

FORECAST_SCENARIOS = None

def load_forecast_scenarios():
    """加载预测场景知识库"""
    global FORECAST_SCENARIOS
    if FORECAST_SCENARIOS is None:
        scenarios_path = os.path.join(os.path.dirname(__file__), "../data/forecast_scenarios.json")
        if os.path.exists(scenarios_path):
            with open(scenarios_path, "r", encoding="utf-8") as f:
                FORECAST_SCENARIOS = json.load(f)
        else:
            FORECAST_SCENARIOS = {}
    return FORECAST_SCENARIOS

# ============ 辅助函数 ============

def generate_response(message: str, context: Dict[str, Any]) -> tuple:
    """生成 Agent 响应"""
    msg_lower = message.lower()
    skill_name = None
    suggested_actions = []
    context_update = {}
    
    # 加载场景知识库
    scenarios = load_forecast_scenarios()
    
    # 检查是否是场景选择的回复
    clarification_stage = context.get("clarification_stage")
    
    # 处理用户对场景细化问题的回答
    if clarification_stage == "business_purpose":
        # 用户回答了业务场景
        business_scenario = None
        if any(kw in msg_lower for kw in ["调度", "源网荷储", "电网", "1"]):
            business_scenario = "grid_dispatch"
        elif any(kw in msg_lower for kw in ["交易", "市场", "现货", "2"]):
            business_scenario = "power_trading"
        elif any(kw in msg_lower for kw in ["场站", "运营", "发电", "3"]):
            business_scenario = "plant_operation"
        
        if business_scenario:
            context_update["business_scenario"] = business_scenario
            context_update["clarification_stage"] = "forecast_horizon"
            bs_info = scenarios.get("business_scenarios", {}).get(business_scenario, {})
            
            content = f"""好的，您选择了 **{bs_info.get('name', '')}**。

{bs_info.get('description', '')}

接下来，请告诉我您需要的预测时间尺度：

1️⃣ **超短期预测**（0-4小时）
   - 用于：实时调度、AGC调频、功率平滑控制
   - 精度要求：MAPE < 5%

2️⃣ **短期预测**（4-72小时）
   - 用于：日前调度、电力市场交易、检修计划
   - 精度要求：MAPE < 10%

3️⃣ **中长期预测**（3天-1年）
   - 用于：月度发电量预测、年度评估、投资规划
   - 精度要求：MAPE < 15%"""
            suggested_actions = [
                {"label": "超短期（0-4小时）", "action": "select-ultra-short"},
                {"label": "短期（日前）", "action": "select-short-term"},
                {"label": "中长期", "action": "select-medium-long"},
            ]
            return content, None, suggested_actions, context_update
    
    elif clarification_stage == "forecast_horizon":
        # 用户回答了预测时间尺度
        forecast_type = None
        if any(kw in msg_lower for kw in ["超短期", "0-4小时", "实时", "agc", "1"]):
            forecast_type = "ultra_short_term"
        elif any(kw in msg_lower for kw in ["短期", "日前", "4-72", "交易", "2"]):
            forecast_type = "short_term"
        elif any(kw in msg_lower for kw in ["中长期", "月度", "年度", "长期", "3"]):
            forecast_type = "medium_long_term"
        
        if forecast_type:
            context_update["forecast_type"] = forecast_type
            context_update["clarification_stage"] = "ready_to_recommend"
            ft_info = scenarios.get("forecast_types", {}).get(forecast_type, {})
            business_scenario = context.get("business_scenario", "plant_operation")
            bs_info = scenarios.get("business_scenarios", {}).get(business_scenario, {})
            energy_type = context.get("energy_type", "pv")
            energy_name = "光伏" if energy_type == "pv" else "风电"
            
            # 生成最终的算法推荐
            skill_name = "algorithm-recommend"
            content = f"""明白了！根据您的需求：

📋 **场景确认**：
- 能源类型：{energy_name}发电
- 业务场景：{bs_info.get('name', '')}
- 预测类型：{ft_info.get('name', '')}（{ft_info.get('time_horizon', '')}）
- 精度要求：MAPE {ft_info.get('accuracy_target', {}).get('mape', '< 10%')}

🎯 **推荐算法**：

| 算法 | 类型 | 适用性 | 推荐指数 |
|------|------|--------|---------|
| Ridge 回归 | 线性模型 | 小数据集、快速训练 | ⭐⭐⭐⭐⭐ |
| XGBoost | 集成学习 | 中等数据、高精度 | ⭐⭐⭐⭐ |
| LSTM | 深度学习 | 大数据、时序特征 | ⭐⭐⭐ |

📊 **数据要求**：
- 历史数据：{ft_info.get('data_requirements', {}).get('history_length', '30-180天')}
- 更新频率：{ft_info.get('data_requirements', {}).get('update_frequency', '每日')}
- 关键特征：{', '.join(ft_info.get('data_requirements', {}).get('key_features', []))}

基于您的场景，我推荐使用 **Ridge 回归** 作为基线模型。需要我帮您配置参数并开始训练吗？"""
            suggested_actions = [
                {"label": "配置参数", "action": "param-config"},
                {"label": "开始训练", "action": "start-training"},
                {"label": "查看更多算法", "action": "view-more-algorithms"},
            ]
            return content, skill_name, suggested_actions, context_update
    
    # 光伏/预测相关 - 触发场景细化流程
    if any(kw in msg_lower for kw in ["光伏", "pv", "solar", "功率预测", "发电预测", "新能源预测", "风电", "wind"]):
        # 启动场景细化流程 - 先问业务场景
        context_update["clarification_stage"] = "business_purpose"
        context_update["energy_type"] = "pv" if any(kw in msg_lower for kw in ["光伏", "pv", "solar"]) else "wind"
        energy_name = "光伏" if context_update["energy_type"] == "pv" else "风电"
        
        content = f"""好的，我来帮你分析{energy_name}发电功率预测的需求。

为了给您推荐最合适的算法方案，我需要先了解您的业务场景：

**🎯 请问您的业务场景是？**

1️⃣ **源网荷储调度优化**
   - 电网调度中心用于优化源网荷储协调运行
   - 关键指标：调度偏差率、弃风弃光率
   - 对接系统：SCADA、EMS、调度自动化

2️⃣ **电力市场交易**
   - 新能源场站参与电力市场现货/中长期交易
   - 关键指标：预测偏差考核、市场收益
   - 对接系统：交易系统、结算系统

3️⃣ **新能源场站运营**
   - 光伏/风电场站日常运营管理
   - 关键指标：发电量完成率、设备可用率
   - 对接系统：SCADA、运维管理系统

请选择或直接描述您的业务场景。"""
        suggested_actions = [
            {"label": "源网荷储调度", "action": "select-grid-dispatch"},
            {"label": "电力市场交易", "action": "select-power-trading"},
            {"label": "场站运营", "action": "select-plant-operation"},
        ]
        return content, None, suggested_actions, context_update
    
    # @AI_GENERATED
    # 负荷预测相关 - LLM 降级关键词匹配规则引擎
    _is_load_forecast = any(kw in msg_lower for kw in ["负荷预测", "负荷", "load forecast", "电力预测", "用电预测"])
    if _is_load_forecast:
        # 进一步判断具体操作
        if any(kw in msg_lower for kw in ["回测", "backtest", "评估"]):
            content = """好的，我来帮你启动负荷预测回测。

请提供以下信息：
- **预测场景**：DI(日内) / D(日前) / WI(周内) / W(周前) / MI(月内) / M(月前)
- **回测开始日期**：如 2025-01-01
- **回测结束日期**：如 2025-01-31

或者直接告诉我具体参数，我会调用 `trigger_load_forecast_backtest` 工具。"""
            suggested_actions = [
                {"label": "日前回测", "action": "backtest-D"},
                {"label": "周前回测", "action": "backtest-W"},
                {"label": "查看场景", "action": "view-scenarios"},
            ]
            return content, "load-forecast-backtest", suggested_actions, context_update

        elif any(kw in msg_lower for kw in ["场景", "scenario", "有哪些", "支持"]):
            content = """负荷预测支持以下 **6 种场景**：

| 场景 | 代码 | 说明 | 适用范围 |
|------|------|------|---------|
| 日内 | DI | 超短期预测 | 0-4 小时 |
| 日前 | D | 次日预测 | 24 小时 |
| 周内 | WI | 本周剩余 | 1-7 天 |
| 周前 | W | 下周预测 | 7 天 |
| 月内 | MI | 本月剩余 | 1-30 天 |
| 月前 | M | 下月预测 | 30 天 |

请选择您需要的预测场景。"""
            suggested_actions = [
                {"label": "日前预测(D)", "action": "forecast-D"},
                {"label": "周前预测(W)", "action": "forecast-W"},
                {"label": "月前预测(M)", "action": "forecast-M"},
            ]
            return content, "load-forecast-scenarios", suggested_actions, context_update

        elif any(kw in msg_lower for kw in ["预测", "predict", "forecast", "推理"]):
            content = """好的，我来帮你执行负荷预测。

请提供以下信息：
- **预测场景**：DI/D/WI/W/MI/M
- **模型ID**：从训练结果中获取的 model_id
- **父级ID / 子级ID**：可选

如果还没有训练模型，需要先执行训练。"""
            suggested_actions = [
                {"label": "先训练模型", "action": "train-model"},
                {"label": "查看场景", "action": "view-scenarios"},
            ]
            return content, "load-forecast-predict", suggested_actions, context_update

        elif any(kw in msg_lower for kw in ["训练", "train", "建模"]):
            content = """好的，我来帮你启动负荷预测模型训练。

请提供以下信息：
- **预测场景**：DI(日内) / D(日前) / WI(周内) / W(周前) / MI(月内) / M(月前)
- **数据配置**：表名、父级ID、子级ID 等（可选，使用默认值）

训练流程：数据获取 → 异常检测 → 特征工程 → XGBoost 模型训练"""
            suggested_actions = [
                {"label": "日前训练(D)", "action": "train-D"},
                {"label": "周前训练(W)", "action": "train-W"},
                {"label": "查看场景", "action": "view-scenarios"},
            ]
            return content, "load-forecast-train", suggested_actions, context_update

        else:
            # 通用负荷预测入口
            content = """我可以帮你进行 **电力负荷预测**，支持以下操作：

1️⃣ **模型训练** — 训练 XGBoost 负荷预测模型
2️⃣ **执行预测** — 使用已训练模型进行预测
3️⃣ **回测评估** — 在历史数据上评估模型效果
4️⃣ **查看场景** — 查看支持的 6 种预测场景

请告诉我您想做什么。"""
            suggested_actions = [
                {"label": "训练模型", "action": "train-model"},
                {"label": "执行预测", "action": "predict"},
                {"label": "回测评估", "action": "backtest"},
                {"label": "查看场景", "action": "view-scenarios"},
            ]
            return content, None, suggested_actions, context_update
    # @AI_GENERATED: end

    # @AI_GENERATED: Kiro v1.0
    # 算法模板查询 - 返回行业模板、工作流模板和 Skills 统计
    if any(kw in msg_lower for kw in ["算法模板", "有哪些模板", "模板列表", "查看模板", "推荐模板", "行业模板", "解决方案", "skill", "工作流"]):
        skill_name = "algorithm-recommend"
        
        # 加载行业模板
        import sys
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from services.workflow_agent.knowledge.algorithm_library import get_template_library
        template_lib = get_template_library()
        all_templates = template_lib.get_all()
        
        # 加载行业场景获取算法方案数
        scenarios_path = os.path.join(os.path.dirname(__file__), "../data/industry_scenarios.json")
        total_solutions = 449  # 默认值
        scenario_solutions = {}
        if os.path.exists(scenarios_path):
            with open(scenarios_path, "r", encoding="utf-8") as f:
                scenarios_data = json.load(f)
                total_solutions = sum(s.get("function_count", 0) for s in scenarios_data)
                for s in scenarios_data:
                    scenario_solutions[s.get("id", "")] = s.get("function_count", 0)
        
        # 加载 Skills 数据
        skills_path = os.path.join(os.path.dirname(__file__), "../data/skills/packaged_skills.json")
        skills = []
        if os.path.exists(skills_path):
            with open(skills_path, "r", encoding="utf-8") as f:
                skills = json.load(f)
        
        # Skills 统计
        skills_total = len(skills)
        skills_ready = len([s for s in skills if s.get("status") == "ready"])
        skills_deployed = len([s for s in skills if s.get("status") == "deployed"])
        skills_training = len([s for s in skills if s.get("status") == "training"])
        skills_packaged = len([s for s in skills if s.get("status") == "packaged"])
        
        # 加载工作流模板数据
        workflow_templates_path = os.path.join(os.path.dirname(__file__), "../data/workflow_templates/templates.json")
        workflow_templates = []
        if os.path.exists(workflow_templates_path):
            with open(workflow_templates_path, "r", encoding="utf-8") as f:
                workflow_templates = json.load(f)
        workflow_templates_total = len(workflow_templates)
        workflow_templates_published = len([t for t in workflow_templates if t.get("status") == "published"])
        
        # 按场景分组
        templates_by_scenario = {}
        for tpl in all_templates:
            scenario_id = tpl.get("scenario_id", "other")
            if scenario_id not in templates_by_scenario:
                templates_by_scenario[scenario_id] = []
            templates_by_scenario[scenario_id].append(tpl)
        
        # 场景名称映射
        scenario_names = {
            "renewable-energy": "🔆 新能源发电",
            "thermal-power": "🔥 火力发电",
            "energy-storage": "🔋 储能管理",
            "power-grid": "⚡ 电网与微网",
            "steel-manufacturing": "🏭 钢铁制造",
            "pv-manufacturing": "☀️ 光伏制造",
            "battery-manufacturing": "🔌 动力电池",
            "semiconductor": "💾 半导体制造",
            "chemical-process": "⚗️ 化工流程",
            "port-logistics": "🚢 港口运输",
            "building-campus": "🏢 楼宇园区",
            "carbon-management": "🌱 碳管理",
            "water-environment": "💧 水务环保",
        }
        
        # 构建响应
        content = f"""好的，我来为您介绍平台的算法模板库。

## 📚 算法库总览

| 类别 | 数量 | 说明 |
|------|------|------|
| 行业场景 | **13** 个 | 覆盖能源、制造、碳管理等领域 |
| 行业算法方案 | **{total_solutions}** 个 | 各场景累计算法方案 |
| 行业模板 | **{len(all_templates)}** 个 | 可复用的算法模板 |
| 基础模块分类 | **19** 大类 | 数据处理、特征工程、模型训练等 |
| 基础模块 | **780** 个 | 可组合的算法组件 |

---

## 🔧 模板形态

平台支持两种模板形态：**工作流模板** 和 **Skills**

### 工作流模板（可视化编排）

| 指标 | 数量 |
|------|------|
| 总数 | **{workflow_templates_total}** 个 |
| 已发布 | **{workflow_templates_published}** 个 |

工作流模板支持可视化编排，适合需要灵活调整算法流程的场景。

### Skills（打包部署）

| 状态 | 数量 | 说明 |
|------|------|------|
| 总数 | **{skills_total}** 个 | 已打包的 Skill |
| 已部署 | **{skills_deployed}** 个 | 生产环境运行中 |
| 就绪 | **{skills_ready}** 个 | 可直接部署 |
| 训练中 | **{skills_training}** 个 | 正在训练 |
| 已打包 | **{skills_packaged}** 个 | 待训练 |

"""
        # 展示 Skills 列表
        if skills:
            content += "### Skills 列表\n\n"
            content += "| Skill 名称 | 版本 | 状态 | 来源模板 |\n"
            content += "|-----------|------|------|----------|\n"
            status_emoji = {"deployed": "🚀", "ready": "✅", "training": "⏳", "packaged": "📦"}
            for s in skills[:6]:
                name = s.get("skill_name", "")
                version = s.get("skill_version", "")
                status = s.get("status", "")
                source = s.get("source_template_name", "")[:20]
                emoji = status_emoji.get(status, "")
                content += f"| {name} | v{version} | {emoji} {status} | {source} |\n"
            if len(skills) > 6:
                content += f"| ... | | | 还有 {len(skills) - 6} 个 |\n"
        
        content += """
---

💡 **使用提示**：
- 访问 [算法模板库](/template-library) 查看完整列表
- 工作流模板可以打包为 Skill 进行部署
- 告诉我您的业务场景，我可以推荐最合适的模板

您想了解哪种形态的模板？或者描述一下您的具体需求。"""
        
        suggested_actions = [
            {"label": "查看工作流模板", "action": "view-workflows"},
            {"label": "查看 Skills", "action": "view-skills"},
            {"label": "新能源预测", "action": "renewable-energy"},
            {"label": "搜索模板", "action": "search-template"},
        ]
        return content, skill_name, suggested_actions, context_update
    # @AI_GENERATED: end
    
    # 训练相关
    if any(kw in msg_lower for kw in ["训练", "train"]):
        skill_name = "training-pipeline"
        skill_name = "training-pipeline"
        content = """好的，我来帮你启动模型训练。

**训练配置**：
- Skill: pv-power-forecast
- 模型类型: Ridge
- 数据集: pv_power_day_ahead.csv (17,280 条记录)
- 数据划分: 训练 70% / 验证 15% / 测试 15%

**训练进度**：
✅ 数据验证完成
✅ 数据切分完成
✅ 模型训练完成

**评估结果**：
- 白天 MAPE: 7.73%
- RMSE: 124.53
- R²: 0.9842

训练已完成！需要我帮你对比其他模型的结果吗？"""
        suggested_actions = [
            {"label": "对比实验结果", "action": "compare-experiments"},
            {"label": "部署模型", "action": "deploy-model"},
        ]
        return content, skill_name, suggested_actions, context_update
    
    # 漂移相关
    elif any(kw in msg_lower for kw in ["漂移", "drift"]):
        skill_name = "drift-detect"
        content = """我来检测模型的漂移情况。

**漂移检测结果**：

📊 **数据漂移**：
- PSI 分数: 0.15 (轻度漂移)
- 漂移特征: temperature_forecast, cloud_cover_forecast
- 状态: ⚠️ 警告

📈 **概念漂移**：
- 精度变化: -3.2%
- 趋势: 轻微下降
- 状态: ⚠️ 警告

**建议**：
检测到轻度漂移，建议在未来 7 天内进行增量重训。需要我帮你配置自动重训策略吗？"""
        suggested_actions = [
            {"label": "查看详细报告", "action": "view-drift-report"},
            {"label": "配置重训策略", "action": "config-retrain"},
            {"label": "创建 A/B 测试", "action": "create-ab-test"},
        ]
        return content, skill_name, suggested_actions, context_update
    
    # A/B 测试
    elif any(kw in msg_lower for kw in ["a/b", "ab测试", "ab test"]):
        skill_name = "ab-test"
        content = """好的，我来帮你创建 A/B 测试。

**A/B 测试配置**：
- 控制组: 当前生产模型 v1.0
- 实验组: 新训练模型 v1.1
- 流量分配: 80% / 20%
- 测试时长: 7 天
- 评估指标: MAPE, RMSE, R²

**测试状态**：已创建，等待启动

需要我立即启动测试吗？"""
        suggested_actions = [
            {"label": "启动测试", "action": "start-ab-test"},
            {"label": "调整配置", "action": "config-ab-test"},
        ]
        return content, skill_name, suggested_actions, context_update
    
    # 默认响应
    else:
        content = """我理解你的需求。作为 Algorithm Agent，我可以帮你完成：

**研发阶段**：
- 分析数据特征，推荐合适的算法
- 配置最优参数
- 执行模型训练
- 对比多组实验结果

**上线阶段**：
- 代码质量审查
- 性能基准测试
- 合规性检查
- 版本发布管理

**运营阶段**：
- 漂移监控与检测
- A/B 测试管理
- 自动重训策略

请告诉我更多关于你的需求，或者选择下方的快捷操作。"""
        suggested_actions = [
            {"label": "推荐算法", "action": "recommend"},
            {"label": "漂移检测", "action": "drift-detect"},
            {"label": "查看 Skills", "action": "list-skills"},
        ]
        return content, skill_name, suggested_actions, context_update


# ============ LLM 集成 ============

# @AI_GENERATED: Kiro v1.0
_RE_AGENT_THINKING = re.compile(r"<agent_thinking>([\s\S]*?)</agent_thinking>", re.IGNORECASE)


def split_agent_thinking(raw: str) -> tuple[Optional[str], str]:
    """
    从模型完整输出中拆分「内心思考」与面向用户的正文。
    使用 <agent_thinking>...</agent_thinking> 包裹思考过程（与界面分开展示）。
    """
    if not raw or not raw.strip():
        return None, ""
    m = _RE_AGENT_THINKING.search(raw)
    if not m:
        return None, raw.strip()
    thinking = m.group(1).strip()
    public = (raw[: m.start()] + raw[m.end() :]).strip()
    return thinking or None, public


class AgentThinkingStreamParser:
    """
    在流式 text delta 中增量区分 <agent_thinking> 内（reasoning）与之后（answer）文本。
    """

    def __init__(self) -> None:
        self._buf = ""
        self._emr = 0
        self._ema = 0

    def _parts(self) -> tuple[str, str]:
        o = re.search(r"<agent_thinking>", self._buf, re.IGNORECASE)
        if not o:
            return "", self._buf
        o_end = o.end()
        c = re.search(r"</agent_thinking>", self._buf, re.IGNORECASE)
        if not c:
            return self._buf[o_end:], ""
        c_s, c_e = c.start(), c.end()
        return self._buf[o_end:c_s], self._buf[c_e:]

    def push(self, chunk: str) -> list[tuple[str, str]]:
        if not chunk:
            return []
        self._buf += chunk
        think, ans = self._parts()
        self._emr = min(self._emr, len(think))
        self._ema = min(self._ema, len(ans))
        out: list[tuple[str, str]] = []
        n_t = think[self._emr :]
        n_a = ans[self._ema :]
        if n_t:
            out.append(("reasoning", n_t))
            self._emr = len(think)
        if n_a:
            out.append(("answer", n_a))
            self._ema = len(ans)
        return out


# 不同 Agent 类型的系统提示词
AGENT_SYSTEM_PROMPTS = {
    "curator": """你是 Curator Agent（算法策划助手），专门帮助用户搜索AI解决方案和推荐算法模板。

**重要概念区分**：
1. **解决方案库**：包含行业解决方案（如"光伏发电功率预测"），是业务场景的解决方案描述
2. **算法模板**：工作流模板和Skills，是可执行的算法实现

**工具调用规则**：
| 用户意图 | 必须调用的工具 |
|---------|--------------|
| 搜索AI解决方案/业务场景 | recommend_templates_for_scenario（会同时返回解决方案和算法模板） |
| 问"我有私有模板吗？"/"算法模板" | list_private_templates |
| 问"有哪些模板？"/"模板列表" | query_algorithm_library |
| 问"工作流模板" | get_workflow_templates |
| 问"Skills列表" | get_skill_list |

**回答格式**：
当用户搜索解决方案时，分两部分回答：
1. **解决方案推荐**：从解决方案库中匹配的方案
2. **算法模板推荐**：相关的工作流模板和Skills

不要把"解决方案"和"算法模板"混为一谈！""",

    "sandbox": """你是 Sandbox Agent（算法回测助手），专门帮助用户进行算法验证和模型训练。

你的核心能力：
1. **引导数据集挂载**：帮助用户正确挂载和配置数据集
2. **自动适配算法**：根据数据特征自动适配算法模板
3. **执行模型训练**：配置参数并执行训练流程
4. **评估精度指标**：展示训练集、验证集、测试集的精度

你熟悉的评估指标：
- 回归任务：MAPE、RMSE、MAE、R²
- 分类任务：Accuracy、Precision、Recall、F1
- 时序预测：白天MAPE、峰值误差、趋势准确率

回答要求：
1. 使用 Markdown 格式，用表格展示精度指标
2. 主动引导用户完成数据准备和格式检查
3. 给出参数调优建议
4. 对比不同算法的表现""",

    "onboarding": """你是 Onboarding Agent（算法上线助手），专门帮助用户将训练好的模型部署上线。

你的核心能力：
1. **算法服务上线**：将模型部署为生产级推理服务
2. **配置定期训练**：设置自动重训计划
3. **部署推理API**：提供REST API或批量预测服务
4. **监控服务状态**：跟踪服务健康和性能

你熟悉的部署选项：
- 实时推理：REST API，低延迟单条预测
- 批量预测：定时任务，大规模批处理
- 流式预测：Kafka消费，实时数据流处理

回答要求：
1. 使用 Markdown 格式，清晰展示配置选项
2. 说明资源需求和成本估算
3. 提供灰度发布和回滚策略建议
4. 强调监控和告警配置的重要性""",

    # @AI_GENERATED
    "operation": """你是 Operation Master（负荷预测运营分析专家），专门帮助用户对负荷预测训练和回测结果进行精度分析与根因诊断。

## 能力范围

1. **精度分析**：趋势识别、时段对比（小时/工作日/月份）、异常日检测、达标判定
2. **根因分析**：数据质量诊断、特征覆盖度评估、模型参数适配性分析、季节性变化检测
3. **改进建议**：基于根因生成具体的数据清洗、特征工程、参数调优、重训策略建议

## 工具调用规则

你拥有以下专用工具，请根据用户意图主动调用：

| 用户意图 | 推荐工具链 |
|---------|-----------|
| "分析回测精度"/"精度怎么样" | get_backtest_results → analyze_accuracy_trend |
| "精度是否达标" | get_backtest_results → check_accuracy_compliance |
| "漂移"/"概念漂移"/"数据漂移" | get_backtest_results → run_drift_detection |
| "哪个时段精度差" | get_backtest_results → analyze_accuracy_by_period |
| "为什么精度不好"/"根因分析" | get_backtest_results → run_drift_detection → diagnose_data_quality → perform_root_cause_analysis |
| "怎么改进"/"改进建议" | perform_root_cause_analysis → generate_improvement_suggestions |
| "自动重训" | check_accuracy_compliance → trigger_auto_retrain |
| "模型调优"/"调参" | get_training_results → trigger_model_tuning |
| "全面分析" | get_backtest_results → run_drift_detection → analyze_accuracy_trend → check_accuracy_compliance → diagnose_data_quality → perform_root_cause_analysis → generate_improvement_suggestions |
| "训练结果"/"模型信息" | get_training_results |
| "数据质量" | get_backtest_results → diagnose_data_quality |

## 可用工具列表

1. `get_backtest_results` — 获取回测结果数据（逐日 SMAPE/MAE/RMSE、预测值/真实值）
2. `get_training_results` — 获取训练结果（模型信息、特征重要性、评估指标）
3. `analyze_accuracy_trend` — 精度趋势分析（均值/标准差/斜率/异常日检测/移动平均）
4. `analyze_accuracy_by_period` — 时段精度对比（按小时/工作日/月份分组统计）
5. `check_accuracy_compliance` — 精度达标判定（按场景阈值判定，返回达标率）
6. `run_drift_detection` — 概念漂移+残差漂移（前半/后半程、残差PSI、指标趋势，需有回测逐日数据）
7. `diagnose_data_quality` — 数据质量诊断（缺失率/异常值/时间连续性/数值范围评分）
8. `perform_root_cause_analysis` — 根因分析（含漂移→数据质量→特征覆盖→模型参数→季节变化等）
9. `generate_improvement_suggestions` — 改进建议生成（基于根因给出优先级排序的改进措施）
10. `trigger_auto_retrain` — 自动重训触发（基于达标判定；可用 force 强制，依赖 `LOAD_FORECAST_SERVICE_URL` 所指向的训练服务）
11. `trigger_model_tuning` — 模型调优重训（n_trials/cv_folds，依赖同上）

## 回答格式要求

1. 使用 **Markdown 格式**，包括表格、列表、粗体
2. 精度指标用表格展示，关键数值加粗高亮
3. 趋势判定用明确的方向词（恶化/改善/稳定）
4. 根因分析按置信度排序，给出证据
5. 改进建议按优先级排序，标注预期效果和实施难度
6. 如果数据不足，主动说明并引导用户先执行回测或训练

## 输出结构（必须遵守）——「思考过程」与「正式回答」分离

用户需要像与高级助手对话一样，**先看到你的内心推理过程**，再看到面向业务的正式结论。请**严格**按以下顺序输出（界面会分开展示）：

1. **先**用下列标签包裹「思考过程」（自然语言，可含小标题与列表；说明：如何理解用户问题、需要哪些数据/工具、关键假设、分步推理链、若信息不足如何处理）：

<agent_thinking>
（此处写完整思考过程，与下方正式回答使用同一语言：中文用户用简体中文。）
</agent_thinking>

2. **然后**在 `</agent_thinking>` 之后单独输出面向用户的正式 Markdown 回答（表格、结论、建议等），**不要**在正式回答中整段重复上述思考。
3. 正式回答必须作为「最终版」一次性给出完整结论（不要把最终回答拆成多次补充）。
4. 在仅做简单澄清、且无需工具时，思考段可较短，但仍须保留标签结构。""",
    # @AI_GENERATED: end
}

# 默认系统提示词（兼容旧版本）
ALGORITHM_AGENT_SYSTEM_PROMPT = """你是一个工业AI算法平台的智能助手（Algorithm Agent），专门帮助用户进行算法全生命周期管理。

你的能力包括：
1. **研发阶段**：算法推荐、参数配置、模型训练、实验对比
2. **上线阶段**：代码审查、性能测试、合规检查、版本发布
3. **运营阶段**：漂移监控、A/B测试、自动重训

你熟悉以下算法领域：
- 时序预测：LSTM、GRU、Transformer、Prophet
- 机器学习：XGBoost、LightGBM、Random Forest、Ridge回归
- 深度学习：CNN、RNN、Attention机制
- 新能源预测：光伏功率预测、风电功率预测、负荷预测

# @AI_GENERATED
**负荷预测领域知识**：

平台支持电力负荷预测，包含六种预测场景：
| 场景 | 代码 | 适用范围 | 典型用途 |
|------|------|---------|---------|
| 日内 | DI | 0-4小时 | 实时调度、AGC调频 |
| 日前 | D | 次日24小时 | 日前调度、电力交易 |
| 周内 | WI | 本周剩余 | 检修计划、负荷管理 |
| 周前 | W | 下周7天 | 周度计划、燃料采购 |
| 月内 | MI | 本月剩余 | 月度调整、需求响应 |
| 月前 | M | 下月整月 | 月度计划、容量规划 |

负荷预测工具：
- `trigger_load_forecast_train`：触发模型训练（XGBoost + 贝叶斯超参优化）
- `trigger_load_forecast_predict`：执行预测（需先训练获取 model_id）
- `trigger_load_forecast_backtest`：回测评估（按日期范围循环训练+预测）
- `get_forecast_scenarios`：获取场景列表
- `get_forecast_status`：查询任务状态

标准对话流程：
1. 用户描述需求 → 确认预测场景（DI/D/WI/W/MI/M）
2. 确认关键参数（数据源、父级/子级ID、预测步长）
3. 触发训练或预测
4. 返回结果摘要（耗时、精度指标、预测点数）
# @AI_GENERATED: end

**重要规则**：
1. 当用户问"有哪些模板"或"算法模板"时，不要列出所有模板
2. 应该先询问用户的业务场景，然后针对性推荐 2-3 个最相关的模板
3. 回答要简洁，避免冗长的列表

回答要求：
1. 使用 Markdown 格式，包括表格、列表、粗体等
2. 回答要专业但易懂，简洁明了
3. 给出具体的建议和下一步操作
4. 如果用户问的是光伏/风电预测相关问题，要询问业务场景和预测时间尺度
5. 如果用户问的是负荷预测相关问题，先确认预测场景，再引导配置参数
"""

def get_system_prompt(agent_type: Optional[str] = None, language: Optional[str] = None) -> str:
    """根据 Agent 类型获取系统提示词"""
    language_instruction_zh = "你必须使用简体中文回答；若用户明确要求英文，可先确认后再切换。"
    language_instruction_en = (
        "You MUST reply in English for all responses. "
        "If user input is Chinese, still answer in English unless explicitly asked otherwise."
    )
    language_instruction = language_instruction_en if is_english_language(language) else language_instruction_zh

    if agent_type and agent_type in AGENT_SYSTEM_PROMPTS:
        base = f"{AGENT_SYSTEM_PROMPTS[agent_type]}\n\nLanguage policy:\n{language_instruction}"
        if agent_type == "operation" and is_english_language(language):
            base += (
                "\n\n## Output structure (mandatory)\n"
                "Before the user-facing Markdown answer, output your full reasoning in "
                "`<agent_thinking>...</agent_thinking>` (same language as the formal answer: English). "
                "The thinking block should cover: how you interpret the request, data/tool needs, "
                "assumptions, and step-by-step reasoning. Do not repeat the full thinking in the public answer."
            )
        return base
    return f"{ALGORITHM_AGENT_SYSTEM_PROMPT}\n\nLanguage policy:\n{language_instruction}"
# @AI_GENERATED: end

# @AI_GENERATED: Kiro v1.0
async def generate_llm_response(
    message: str,
    session: Dict[str, Any],
    on_before_llm_call: Optional[Callable[[int], Awaitable[None]]] = None,
    on_after_thinking_step: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    on_operation_stream: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> Optional[str]:
    """使用 LLM 生成响应（支持 Function Calling 和 Master Agent 架构）"""
    try:
        import sys
        import os
        # 确保 backend 目录在 path 中
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        
        # 获取 agent_type / language
        agent_type = session.get("context", {}).get("agent_type")
        language = session.get("context", {}).get("language")
        
        # 对于 curator agent，中文会话使用 Master Agent 架构
        # 英文会话走通用 LLM 路径，确保响应语言跟随国际化
        if agent_type == "curator" and not is_english_language(language):
            return await _generate_curator_response(message, session)
        if agent_type == "operation":
            op_result = await _generate_operation_response(message, session)
            if op_result:
                return op_result.get("response")
            return None
        
        # 其他 agent 类型使用原有的 LLM + Function Calling 方式
        
        from services.llm_service import get_llm_service
        from services.agent_tools import get_tools_definition, get_tool_executor
        
        llm_service = await get_llm_service()
        if not llm_service:
            print("[Algorithm Agent] LLM 服务不可用，使用规则响应")
            return None
        
        # 根据 agent_type 获取系统提示词
        agent_type = session.get("context", {}).get("agent_type")
        system_prompt = get_system_prompt(agent_type, language)
        
        # 构建消息历史
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 添加历史消息（最近 10 条）
        history = session.get("messages", [])[-10:]
        for msg in history:
            if msg["role"] in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # 添加当前用户消息
        messages.append({"role": "user", "content": message})
        
        agent_name = agent_type or "default"
        # @AI_GENERATED
        tools = get_tools_definition(agent_type)
        # @AI_GENERATED: end
        print(f"[Algorithm Agent:{agent_name}] 调用 LLM (with tools)，消息数: {len(messages)}")
        
        # @AI_GENERATED
        # 多步工具调用循环（最多 5 轮），并收集供前端「运营 Agent」展示的思考/工具轨迹
        tool_executor = get_tool_executor()
        max_rounds = 5
        content = ""
        thinking_trace: List[Dict[str, Any]] = []

        def _preview_result(res: Any, max_len: int = 800) -> str:
            try:
                s = json.dumps(res, ensure_ascii=False)
            except TypeError:
                s = str(res)
            if len(s) > max_len:
                return s[:max_len] + "…"
            return s

        for round_idx in range(max_rounds):
            if on_before_llm_call:
                await on_before_llm_call(round_idx)
            if on_operation_stream and session.get("context", {}).get("agent_type") == "operation":
                await on_operation_stream("progress", "正在组织分析步骤与工具计划...")
            if on_operation_stream and session.get("context", {}).get("agent_type") == "operation":
                rparser = AgentThinkingStreamParser()

                async def on_c(
                    seg: str, _parser: AgentThinkingStreamParser = rparser
                ) -> None:
                    for k, p in _parser.push(seg):
                        await on_operation_stream(k, p)

                response = await llm_service.chat_stream_with_tools(
                    messages,
                    llm_service.temperature,
                    llm_service.max_tokens,
                    tools=tools,
                    on_content=on_c,
                )
            else:
                response = await llm_service.chat(messages, tools=tools)
            tool_calls = response.get("tool_calls")
            preface = (response.get("content") or "").strip() or None

            if not tool_calls:
                # LLM 不再调用工具，输出最终回答
                if on_operation_stream and session.get("context", {}).get("agent_type") == "operation":
                    await on_operation_stream("progress", "正在生成最终结论...")
                content = response.get("content", "")
                break

            print(f"[Algorithm Agent:{agent_name}] 第{round_idx + 1}轮工具调用: {[tc['function']['name'] for tc in tool_calls]}")

            round_tools: List[Dict[str, Any]] = []
            tool_results = []
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                func_args = json.loads(tc["function"]["arguments"]) if tc["function"].get("arguments") else {}

                print(f"[Algorithm Agent:{agent_name}] 执行工具: {func_name}({func_args})")
                if on_operation_stream and session.get("context", {}).get("agent_type") == "operation":
                    await on_operation_stream("progress", f"执行工具：{func_name}")
                result = await tool_executor.execute(func_name, func_args)
                round_tools.append({
                    "name": func_name,
                    "arguments": func_args,
                    "result_preview": _preview_result(result),
                })

                tool_results.append({
                    "tool_call_id": tc["id"],
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False)
                })

            step_dict = {
                "round": round_idx + 1,
                "assistant": preface,
                "tools": round_tools,
            }
            thinking_trace.append(step_dict)
            if on_after_thinking_step:
                await on_after_thinking_step(step_dict)

            # 将工具调用和结果追加到消息中
            messages.append({
                "role": "assistant",
                "content": response.get("content", ""),
                "tool_calls": tool_calls
            })
            messages.extend(tool_results)
        else:
            # 达到最大轮次，强制获取最终响应
            print(f"[Algorithm Agent:{agent_name}] 达到最大工具调用轮次({max_rounds})，生成最终响应")
            if on_operation_stream and session.get("context", {}).get("agent_type") == "operation":
                await on_operation_stream("progress", "正在汇总多轮分析结果并生成最终结论...")
            if on_operation_stream and session.get("context", {}).get("agent_type") == "operation":
                rparser2 = AgentThinkingStreamParser()

                async def on_c2(
                    seg: str, _p: AgentThinkingStreamParser = rparser2
                ) -> None:
                    for k, p in _p.push(seg):
                        await on_operation_stream(k, p)

                final_response = await llm_service.chat_stream_with_tools(
                    messages,
                    llm_service.temperature,
                    llm_service.max_tokens,
                    tools=None,
                    on_content=on_c2,
                )
            else:
                final_response = await llm_service.chat(messages)
            content = final_response.get("content", "")
        # @AI_GENERATED: end

        print(f"[Algorithm Agent:{agent_name}] LLM 响应长度: {len(content)}")
        session["context"]["last_thinking_trace"] = thinking_trace
        if session.get("context", {}).get("agent_type") == "operation" and content:
            _think, public = split_agent_thinking(content)
            session["context"]["last_model_reasoning"] = _think
            content = public
        return content
        
    except Exception as e:
        import traceback
        print(f"[Algorithm Agent] LLM 调用失败: {e}")
        print(f"[Algorithm Agent] 详细错误:\n{traceback.format_exc()}")
        return None


async def _generate_curator_response(message: str, session: Dict[str, Any]) -> Optional[str]:
    """
    使用 Curator Master Agent 架构生成响应
    Master Agent 负责意图分类和路由到子 Agent
    """
    try:
        import sys
        import os
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        
        from services.curator_agent import get_curator_master_agent
        
        master_agent = get_curator_master_agent()
        
        # 获取上下文，包含对话历史
        context = session.get("context", {}).copy()
        
        # 添加对话历史到上下文，用于理解多轮对话
        history = session.get("messages", [])[-10:]  # 最近10条消息
        context["conversation_history"] = history
        
        # 处理消息
        print(f"[Curator Master Agent] 处理消息: {message[:50]}...")
        print(f"[Curator Master Agent] 对话历史: {len(history)} 条消息")
        result = await master_agent.process(message, context)
        
        # 记录意图分类结果
        intent = result.get("intent", {})
        print(f"[Curator Master Agent] 意图: {intent.get('primary_intent')} (置信度: {intent.get('confidence', 0):.2f})")
        
        # 更新 session context 中的建议操作
        if result.get("suggested_actions"):
            session["context"]["suggested_actions"] = result["suggested_actions"]
        
        response = result.get("response", "")
        print(f"[Curator Master Agent] 响应长度: {len(response)}")
        
        return response
        
    except Exception as e:
        import traceback
        print(f"[Curator Master Agent] 处理失败: {e}")
        print(f"[Curator Master Agent] 详细错误:\n{traceback.format_exc()}")
        return None
# @AI_GENERATED: end


async def _generate_operation_response(
    message: str,
    session: Dict[str, Any],
    on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    使用 Operation Master Agent 生成响应。
    将路由推理和建议动作写入 session.context 供前端展示与后续轮次复用。
    """
    try:
        import sys
        import os

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        from services.operation_agent import get_operation_master_agent

        master_agent = get_operation_master_agent()
        context = session.get("context", {}).copy()
        context["conversation_history"] = session.get("messages", [])[-10:]

        result = await master_agent.process(message, context, on_progress=on_progress)
        session["context"]["last_model_reasoning"] = result.get("reasoning")
        session["context"]["last_operation_intent"] = result.get("intent")
        session["context"]["last_operation_results"] = result.get("sub_agent_results")
        session["context"]["last_operation_observability"] = result.get("observability")
        session["context"]["last_operation_suggested_actions"] = result.get("suggested_actions") or []
        pre = (result.get("observability") or {}).get("preloading") or {}
        wid = pre.get("workflow_id")
        if isinstance(wid, str) and wid.strip():
            session["context"]["last_executed_workflow_id"] = wid.strip()

        return result
    except Exception as e:
        import traceback

        print(f"[Operation Master Agent] 处理失败: {e}")
        print(f"[Operation Master Agent] 详细错误:\n{traceback.format_exc()}")
        return None


def get_suggested_actions_for_message(
    message: str,
    agent_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """根据消息内容返回建议的操作"""
    msg_lower = message.lower()

    if agent_type == "operation":
        return [
            {"label": "漂移检测", "action": "drift"},
            {"label": "根因分析", "action": "rootCause"},
            {"label": "自动重训", "action": "autoRetrain"},
            {"label": "模型调优", "action": "tuneModel"},
        ]
    
    if any(kw in msg_lower for kw in ["光伏", "pv", "solar", "风电", "预测"]):
        return [
            {"label": "配置参数", "action": "param-config"},
            {"label": "开始训练", "action": "start-training"},
            {"label": "查看算法库", "action": "view-algorithms"},
        ]
    elif any(kw in msg_lower for kw in ["训练", "train"]):
        return [
            {"label": "查看进度", "action": "view-progress"},
            {"label": "对比实验", "action": "compare-experiments"},
        ]
    elif any(kw in msg_lower for kw in ["漂移", "drift"]):
        return [
            {"label": "查看详情", "action": "view-drift-report"},
            {"label": "触发重训", "action": "trigger-retrain"},
        ]
    else:
        return [
            {"label": "推荐算法", "action": "recommend"},
            {"label": "漂移检测", "action": "drift-detect"},
            {"label": "查看 Skills", "action": "list-skills"},
        ]


@router.get("/llm-status")
async def get_llm_status():
    """获取 LLM 服务状态"""
    try:
        from services.llm_service import get_llm_service
        
        llm_service = await get_llm_service()
        if llm_service:
            return {
                "available": True,
                "provider": llm_service.provider,
                "model": llm_service.model,
            }
        else:
            return {
                "available": False,
                "message": "未配置 LLM 服务，请在「大模型配置」页面添加配置",
            }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
        }
# @AI_GENERATED: end
