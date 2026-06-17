# @AI_GENERATED
"""
LLM 辅助打标服务
为待审核诊断单元生成建议标签与理由，受当前标签注册表约束，失败容错，绝不写真值。

映射需求 7：LLM 辅助打标
- 7.1: 为每个待审核单元生成 LLM_Suggestion（suggested_label + reason）
- 7.2: 复用 api/llm_config.py 默认配置，不新增独立密钥管理
- 7.3: 限定 suggested_label 取值来自当前 Label_Registry；越界标 out_of_registry=true
- 7.4: 禁止将 LLM_Suggestion 直接写入真值标签
- 7.5: 调用失败/超时置 available=false，不中断审核流程
- 7.6: 记录 llm_config_ref、generated_at
"""

import httpx
import json
import traceback
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from services.llm_service import LLMService


async def generate_suggestion(
    unit: Dict[str, Any],
    label_registry: Dict[str, Any],
    llm_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    为单个诊断单元生成 LLM 建议标签。
    
    Args:
        unit: 诊断单元，包含 unit_key（诊断单元标识）、时序上下文摘要等
        label_registry: 当前标签注册表，含 labels 数组（每项含 label_id、label_name）
        llm_config: 可选，LLM 配置；若为 None，自动获取默认配置
    
    Returns:
        LLM_Suggestion 字典，包含：
        - unit_key（诊断单元标识）
        - suggested_label（建议标签 label_id，越界/缺失时为 null）
        - reason（建议理由）
        - out_of_registry（是否疑似新类别，LLM 给出注册表外标签时为 true）
        - llm_config_ref（所用 LLM 配置引用）
        - generated_at（生成时间 ISO 格式）
        - available（是否可用，调用失败/超时置 false）
    
    映射需求:
    - 7.1: 生成 suggested_label + reason
    - 7.2: 复用默认配置
    - 7.3: 约束取自注册表，越界标 out_of_registry
    - 7.5: 失败容错，置 available=false
    - 7.6: 记录 llm_config_ref、generated_at
    """
    unit_key = unit.get("unit_key", "")
    generated_at = datetime.now().isoformat()
    
    # 初始化默认返回结果（失败状态）
    suggestion = {
        "unit_key": unit_key,
        "suggested_label": None,
        "reason": "",
        "out_of_registry": False,
        "llm_config_ref": None,
        "generated_at": generated_at,
        "available": False,
    }
    
    try:
        # 获取 GLM 服务配置（从环境变量，需求 7.2）
        if llm_config is None:
            glm_api_key = os.getenv("GLM_API_KEY", "")
            glm_base_url = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
            glm_model = os.getenv("GLM_MODEL", "glm-5.1")
            glm_timeout_s = float(os.getenv("GLM_TIMEOUT_S", "120"))
            glm_enable = os.getenv("GLM_ENABLE", "true").lower() == "true"
            
            if not glm_enable:
                suggestion["reason"] = "GLM 未启用"
                return suggestion
            
            if not glm_api_key:
                suggestion["reason"] = "GLM_API_KEY 环境变量未设置"
                return suggestion
            
            llm_config = {
                "provider": "zhipu",
                "api_key": glm_api_key,
                "api_base": glm_base_url,
                "model": glm_model,
                "timeout_s": glm_timeout_s,
                "temperature": 0.3,
            }
            llm_config_ref = f"glm-{glm_model}"
        else:
            llm_config_ref = llm_config.get("id", "llm-custom")
        
        # 创建 LLM 服务实例
        llm_service = LLMService(llm_config)
        suggestion["llm_config_ref"] = llm_config_ref
        
        # 提取注册表中的标签列表（需求 7.3：约束取自当前注册表）
        labels = label_registry.get("labels", [])
        if not labels:
            suggestion["reason"] = "标签注册表为空，无法生成建议"
            return suggestion
        
        # 构建标签列表描述
        label_descriptions = []
        for label in labels:
            label_id = label.get("label_id")
            label_name = label.get("label_name", "")
            label_descriptions.append(f"- {label_id}: {label_name}")
        
        labels_text = "\n".join(label_descriptions)
        
        # 提取诊断单元的时序上下文摘要（假设在 unit 中）
        # 实际使用时，这里应该包含电流/电压曲线摘要、异常特征等
        unit_summary = unit.get("summary", unit.get("context", ""))
        if not unit_summary:
            unit_summary = f"诊断单元 {unit_key}（摘要信息缺失）"
        
        # 构建 prompt（需求 7.1：生成 suggested_label + reason）
        prompt = f"""你是一个光伏故障诊断专家。请根据以下信息，为诊断单元推荐一个最合适的故障标签。

诊断单元信息：
{unit_summary}

可选标签列表（必须从中选择一个）：
{labels_text}

要求：
1. 你**必须**从上述标签列表中选择一个 label_id
2. 提供详细的理由，说明为什么选择该标签
3. 如果确实无法归类到任何已有标签，可以说明"疑似新类别"

请以 JSON 格式返回：
{{
    "suggested_label_id": <选中的 label_id 数字>,
    "reason": "<详细理由>"
}}
"""
        
        # 调用 LLM（需求 7.5：失败容错）
        messages = [{"role": "user", "content": prompt}]
        response = await llm_service.chat(messages, temperature=0.3)
        
        response_content = response.get("content", "").strip()
        
        # 解析 LLM 返回的 JSON
        parsed = _parse_llm_response(response_content)
        
        if parsed is None:
            suggestion["reason"] = f"LLM 返回格式无效: {response_content[:200]}"
            return suggestion
        
        raw_label_id = parsed.get("suggested_label_id")
        reason = parsed.get("reason", "")
        
        # 验证建议标签是否在注册表内（需求 7.3）
        valid_label_ids = [label.get("label_id") for label in labels]
        
        if raw_label_id not in valid_label_ids:
            # 越界标签，标注 out_of_registry=true（需求 7.3）
            suggestion["suggested_label"] = None
            suggestion["reason"] = reason + f" [注意：LLM 建议的标签 {raw_label_id} 不在当前注册表中，疑似新类别]"
            suggestion["out_of_registry"] = True
            suggestion["available"] = True
        else:
            # 有效标签
            suggestion["suggested_label"] = raw_label_id
            suggestion["reason"] = reason
            suggestion["out_of_registry"] = False
            suggestion["available"] = True
        
        return suggestion
    
    except httpx.TimeoutException as e:
        # 超时，置 available=false（需求 7.5）
        suggestion["reason"] = f"LLM 调用超时: {str(e)}"
        suggestion["available"] = False
        return suggestion
    
    except httpx.HTTPStatusError as e:
        # HTTP 错误，置 available=false（需求 7.5）
        error_detail = ""
        try:
            error_detail = e.response.text[:200]
        except:
            pass
        suggestion["reason"] = f"LLM 调用失败 (HTTP {e.response.status_code}): {error_detail}"
        suggestion["available"] = False
        return suggestion
    
    except Exception as e:
        # 其他异常，置 available=false（需求 7.5）
        error_trace = traceback.format_exc()
        print(f"[LLM Labeling Assistant] 生成建议时异常:")
        print(f"[LLM Labeling Assistant] 单元: {unit_key}")
        print(f"[LLM Labeling Assistant] 异常: {str(e)}")
        print(f"[LLM Labeling Assistant] 堆栈:\n{error_trace}")
        
        suggestion["reason"] = f"生成建议时异常: {type(e).__name__}: {str(e)}"
        suggestion["available"] = False
        return suggestion


def _parse_llm_response(content: str) -> Optional[Dict[str, Any]]:
    """
    解析 LLM 返回的 JSON 响应。
    
    Args:
        content: LLM 返回的文本内容
    
    Returns:
        解析后的字典，包含 suggested_label_id 和 reason；解析失败返回 None
    """
    # 尝试提取 JSON 块（处理 LLM 可能返回 markdown 格式）
    content = content.strip()
    
    # 移除可能的 markdown 代码块标记
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    
    if content.endswith("```"):
        content = content[:-3]
    
    content = content.strip()
    
    # 尝试解析 JSON
    try:
        parsed = json.loads(content)
        
        # 验证必需字段
        if "suggested_label_id" not in parsed:
            return None
        
        # 尝试转换 label_id 为整数
        try:
            parsed["suggested_label_id"] = int(parsed["suggested_label_id"])
        except (ValueError, TypeError):
            return None
        
        return parsed
    
    except json.JSONDecodeError:
        # JSON 解析失败，尝试其他格式或返回 None
        return None


async def generate_suggestions_batch(
    units: List[Dict[str, Any]],
    label_registry: Dict[str, Any],
    llm_config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    批量为多个诊断单元生成 LLM 建议标签。
    
    Args:
        units: 诊断单元列表
        label_registry: 当前标签注册表
        llm_config: 可选，LLM 配置
    
    Returns:
        LLM_Suggestion 列表，与输入 units 顺序一致
    
    说明：
    - 当前实现为串行调用，适合小批量（<100 单元）
    - 若需要大批量并发，可在外层使用 asyncio.gather 或队列
    - 每个单元失败不影响其他单元（需求 7.5）
    """
    suggestions = []
    
    for unit in units:
        suggestion = await generate_suggestion(unit, label_registry, llm_config)
        suggestions.append(suggestion)
    
    return suggestions


# 禁止将 LLM_Suggestion 直接写入真值（需求 7.4）
# 本模块只生成建议，不提供任何写入真值的接口
# 真值标签的写入由 review_session.py 的 Human_Verdict 逻辑独占
# @AI_GENERATED: end
