# @AI_GENERATED: Kiro v1.0
"""
LLM API 配置管理接口
支持多种大模型提供商的配置管理
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, Literal
from datetime import datetime
import uuid
import json
import os

router = APIRouter(prefix="/llm", tags=["LLM Config"])

# ============ 数据模型 ============

class LLMConfigCreate(BaseModel):
    credential_name: str           # 凭据名称
    display_name: str              # 模型显示名称
    provider: str                  # openai, azure, anthropic, deepseek, qwen, zhipu, custom
    api_key: str
    api_base: str                  # API endpoint URL
    model: str                     # API endpoint 中的模型名称
    completion_mode: Literal["chat", "completion"] = "chat"
    context_length: int = 64000    # 模型上下文长度
    max_tokens: int = 64000        # 最大 token 上限
    temperature: Optional[float] = 0.7
    is_default: bool = False
    is_enabled: bool = True

class LLMConfigUpdate(BaseModel):
    credential_name: Optional[str] = None
    display_name: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    model: Optional[str] = None
    completion_mode: Optional[Literal["chat", "completion"]] = None
    context_length: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    is_default: Optional[bool] = None
    is_enabled: Optional[bool] = None

class LLMTestRequest(BaseModel):
    config_id: str
    prompt: Optional[str] = "你好，请简单介绍一下你自己。"

# ============ 提供商信息 ============

PROVIDERS = {
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "description": "OpenAI GPT 系列模型",
        "defaultApiBase": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"],
        "requiresApiBase": False,
    },
    "azure": {
        "id": "azure",
        "name": "Azure OpenAI",
        "description": "微软 Azure 托管的 OpenAI 服务",
        "defaultApiBase": "",
        "models": ["gpt-4o", "gpt-4", "gpt-35-turbo"],
        "requiresApiBase": True,
    },
    "anthropic": {
        "id": "anthropic",
        "name": "Anthropic",
        "description": "Anthropic Claude 系列模型",
        "defaultApiBase": "https://api.anthropic.com",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
        "requiresApiBase": False,
    },
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "description": "DeepSeek 深度求索大模型",
        "defaultApiBase": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-coder", "deepseek-v3"],
        "requiresApiBase": False,
    },
    "qwen": {
        "id": "qwen",
        "name": "通义千问",
        "description": "阿里云通义千问大模型",
        "defaultApiBase": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
        "requiresApiBase": False,
    },
    "zhipu": {
        "id": "zhipu",
        "name": "智谱AI",
        "description": "智谱 GLM 系列大模型",
        "defaultApiBase": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4", "glm-4-flash"],
        "requiresApiBase": False,
    },
    "custom": {
        "id": "custom",
        "name": "自定义",
        "description": "自定义 OpenAI 兼容接口",
        "defaultApiBase": "",
        "models": [],
        "requiresApiBase": True,
    },
}

# ============ 数据存储 ============

DATA_FILE = os.path.join(os.path.dirname(__file__), "../data/llm_configs.json")

def load_configs() -> Dict[str, Any]:
    """加载配置"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"configs": [], "default_config_id": None}

def save_configs(data: Dict[str, Any]):
    """保存配置"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def mask_api_key(key: str) -> str:
    """隐藏 API Key"""
    if not key:
        return "***"
    if len(key) > 12:
        return key[:8] + "****" + key[-4:]
    return key[:4] + "****"

def convert_to_frontend_format(cfg: Dict[str, Any], mask_key: bool = True) -> Dict[str, Any]:
    """转换为前端格式（camelCase）"""
    result = {
        "id": cfg.get("id"),
        "credentialName": cfg.get("credential_name", ""),
        "displayName": cfg.get("display_name", ""),
        "provider": cfg.get("provider", ""),
        "apiKey": mask_api_key(cfg.get("api_key", "")) if mask_key else cfg.get("api_key", ""),
        "apiBase": cfg.get("api_base", ""),
        "model": cfg.get("model", ""),
        "completionMode": cfg.get("completion_mode", "chat"),
        "contextLength": cfg.get("context_length", 64000),
        "maxTokens": cfg.get("max_tokens", 64000),
        "temperature": cfg.get("temperature", 0.7),
        "isDefault": cfg.get("is_default", False),
        "isEnabled": cfg.get("is_enabled", True),
        "createdAt": cfg.get("created_at", ""),
        "updatedAt": cfg.get("updated_at", ""),
    }
    return result

# ============ API 接口 ============

@router.get("/providers")
async def get_providers():
    """获取支持的 LLM 提供商列表"""
    return list(PROVIDERS.values())

@router.get("/configs")
async def get_configs():
    """获取所有 LLM 配置"""
    data = load_configs()
    configs = [convert_to_frontend_format(cfg) for cfg in data["configs"]]
    return {"configs": configs, "default_config_id": data.get("default_config_id")}

@router.get("/configs/{config_id}")
async def get_config(config_id: str):
    """获取单个配置详情"""
    data = load_configs()
    for cfg in data["configs"]:
        if cfg["id"] == config_id:
            return convert_to_frontend_format(cfg)
    raise HTTPException(status_code=404, detail="Config not found")

@router.post("/configs")
async def create_config(config: LLMConfigCreate):
    """创建新的 LLM 配置"""
    data = load_configs()
    
    new_config = {
        "id": str(uuid.uuid4()),
        "credential_name": config.credential_name,
        "display_name": config.display_name,
        "provider": config.provider,
        "api_key": config.api_key,
        "api_base": config.api_base,
        "model": config.model,
        "completion_mode": config.completion_mode,
        "context_length": config.context_length,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "is_default": config.is_default,
        "is_enabled": config.is_enabled,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    
    # 如果设为默认，取消其他默认
    if config.is_default:
        for cfg in data["configs"]:
            cfg["is_default"] = False
        data["default_config_id"] = new_config["id"]
    
    data["configs"].append(new_config)
    save_configs(data)
    
    return convert_to_frontend_format(new_config)

@router.put("/configs/{config_id}")
async def update_config(config_id: str, config: LLMConfigUpdate):
    """更新 LLM 配置"""
    data = load_configs()
    
    for i, cfg in enumerate(data["configs"]):
        if cfg["id"] == config_id:
            update_data = config.dict(exclude_none=True)
            
            # 如果设为默认，取消其他默认
            if update_data.get("is_default"):
                for c in data["configs"]:
                    c["is_default"] = False
                data["default_config_id"] = config_id
            
            cfg.update(update_data)
            cfg["updated_at"] = datetime.now().isoformat()
            data["configs"][i] = cfg
            save_configs(data)
            
            return convert_to_frontend_format(cfg)
    
    raise HTTPException(status_code=404, detail="Config not found")

@router.delete("/configs/{config_id}")
async def delete_config(config_id: str):
    """删除 LLM 配置"""
    data = load_configs()
    
    for i, cfg in enumerate(data["configs"]):
        if cfg["id"] == config_id:
            data["configs"].pop(i)
            if data.get("default_config_id") == config_id:
                data["default_config_id"] = None
            save_configs(data)
            return {"status": "ok"}
    
    raise HTTPException(status_code=404, detail="Config not found")

@router.post("/test")
async def test_config(request: LLMTestRequest):
    """测试 LLM 配置连接"""
    import traceback
    
    data = load_configs()
    config = None
    for cfg in data["configs"]:
        if cfg["id"] == request.config_id:
            config = cfg
            break
    
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    
    try:
        # 动态导入避免启动时的导入错误
        from services.llm_service import LLMService
        
        print(f"[LLM Test] 开始测试配置: {config.get('credential_name')}")
        print(f"[LLM Test] API Base: {config.get('api_base')}")
        print(f"[LLM Test] Model: {config.get('model')}")
        
        llm_service = LLMService(config)
        result = await llm_service.test_connection(request.prompt)
        
        print(f"[LLM Test] 测试结果: {result}")
        return result
    except Exception as e:
        error_detail = traceback.format_exc()
        print(f"[LLM Test] ❌ 测试失败:")
        print(f"[LLM Test] 异常类型: {type(e).__name__}")
        print(f"[LLM Test] 异常信息: {str(e)}")
        print(f"[LLM Test] 详细堆栈:\n{error_detail}")
        
        return {
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}",
            "latencyMs": 0,
            "model": config.get("model", ""),
        }

@router.get("/default")
async def get_default_config():
    """获取默认配置"""
    data = load_configs()
    default_id = data.get("default_config_id")
    
    if not default_id:
        # 返回第一个启用的配置
        for cfg in data["configs"]:
            if cfg.get("is_enabled"):
                return convert_to_frontend_format(cfg, mask_key=False)
        return None
    
    for cfg in data["configs"]:
        if cfg["id"] == default_id:
            return convert_to_frontend_format(cfg, mask_key=False)
    
    return None
# @AI_GENERATED: end
