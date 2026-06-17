# @AI_GENERATED: Kiro v1.0
"""
LLM 服务
支持多种大模型提供商的统一调用接口
"""
import httpx
import time
from typing import Dict, Any, List, Optional, Callable, Awaitable
import json


class LLMService:
    """LLM 统一服务类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider = config.get("provider", "openai")
        self.api_key = config.get("api_key", "")
        self.api_base = config.get("api_base", "")
        self.model = config.get("model", "")
        self.max_tokens = config.get("max_tokens", 64000)
        self.context_length = config.get("context_length", 64000)
        self.temperature = config.get("temperature", 0.7)
        self.completion_mode = config.get("completion_mode", "chat")
        self.timeout_s = float(config.get("timeout_s", 60.0))
    
    async def test_connection(self, prompt: str = "你好") -> Dict[str, Any]:
        """测试连接"""
        start_time = time.time()
        try:
            response = await self.chat([{"role": "user", "content": prompt}])
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "success": True,
                "latencyMs": latency_ms,
                "response": response.get("content", ""),
                "model": self.model,
                "tokensUsed": response.get("tokens_used", 0),
            }
        except httpx.ConnectError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "latencyMs": latency_ms,
                "error": f"连接失败: 无法连接到 {self.api_base}，请检查网络或 API 地址",
                "model": self.model,
            }
        except httpx.TimeoutException as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "latencyMs": latency_ms,
                "error": f"请求超时: 服务器响应时间过长",
                "model": self.model,
            }
        except httpx.HTTPStatusError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_detail = ""
            try:
                error_detail = e.response.text[:500]
            except:
                pass
            return {
                "success": False,
                "latencyMs": latency_ms,
                "error": f"HTTP {e.response.status_code}: {error_detail}",
                "model": self.model,
            }
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "latencyMs": latency_ms,
                "error": f"{type(e).__name__}: {str(e)}",
                "model": self.model,
            }
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """发送聊天请求"""
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens
        
        if self.provider in ["openai", "deepseek", "qwen", "zhipu", "custom"]:
            return await self._chat_openai_compatible(messages, temp, tokens, tools)
        elif self.provider == "azure":
            return await self._chat_azure(messages, temp, tokens, tools)
        elif self.provider == "anthropic":
            return await self._chat_anthropic(messages, temp, tokens)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    async def chat_stream_with_tools(
        self,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
        on_content: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        流式 chat，支持 tools；在收到每个 text delta 时回调 on_content（按到达顺序）；
        流结束后返回与非流式 chat 相同结构的 dict（含 content、tool_calls）。
        不支持的 provider 回退为普通 chat 并在有回调时整段 on_content 一次。
        """
        if self.provider in ["openai", "deepseek", "qwen", "zhipu", "custom"]:
            return await self._openai_compatible_stream_with_tools(
                messages, temperature, max_tokens, tools, on_content
            )
        result = await self.chat(messages, temperature, max_tokens, tools)
        if on_content and result.get("content"):
            await on_content(result["content"])
        return result

    async def _openai_compatible_stream_with_tools(
        self,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]],
        on_content: Optional[Callable[[str], Awaitable[None]]],
    ) -> Dict[str, Any]:
        api_base = self.api_base.rstrip("/")
        url = f"{api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if max_tokens and max_tokens < 10000:
            payload["max_tokens"] = max_tokens

        acc_content: List[str] = []
        # index -> {id, name, type, args}
        tool_acc: Dict[int, Dict[str, str]] = {}
        finish_reason = ""

        async with httpx.AsyncClient(timeout=max(5.0, float(self.timeout_s))) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        ch = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    cho = ch.get("choices", [{}])[0]
                    delta = cho.get("delta", {}) or {}
                    if cho.get("finish_reason"):
                        finish_reason = cho.get("finish_reason") or finish_reason
                    seg = delta.get("content")
                    if seg:
                        acc_content.append(seg)
                        if on_content:
                            await on_content(seg)
                    for tcd in delta.get("tool_calls") or []:
                        idx = tcd.get("index", 0)
                        if idx not in tool_acc:
                            tool_acc[idx] = {"id": "", "name": "", "type": "function", "args": ""}
                        if tcd.get("id"):
                            tool_acc[idx]["id"] = tcd["id"]
                        fn = tcd.get("function") or {}
                        if fn.get("name"):
                            tool_acc[idx]["name"] = fn["name"]
                        if fn.get("arguments"):
                            tool_acc[idx]["args"] += fn["arguments"]

        full_text = "".join(acc_content)
        if tool_acc:
            tool_calls = []
            for i in sorted(tool_acc):
                t = tool_acc[i]
                tool_calls.append(
                    {
                        "id": t["id"],
                        "type": "function",
                        "function": {
                            "name": t["name"],
                            "arguments": t["args"],
                        },
                    }
                )
            return {
                "content": full_text,
                "tool_calls": tool_calls,
                "finish_reason": finish_reason,
                "model": self.model,
            }
        return {
            "content": full_text,
            "finish_reason": finish_reason,
            "model": self.model,
        }

    # @AI_GENERATED: Kiro v1.0
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """流式聊天请求，返回异步生成器"""
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens
        
        if self.provider in ["openai", "deepseek", "qwen", "zhipu", "custom"]:
            async for chunk in self._chat_stream_openai_compatible(messages, temp, tokens):
                yield chunk
        else:
            # 不支持流式的 provider，降级为普通调用
            result = await self.chat(messages, temp, tokens)
            yield result.get("content", "")
    
    async def _chat_stream_openai_compatible(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ):
        """OpenAI 兼容接口流式调用"""
        api_base = self.api_base.rstrip("/")
        url = f"{api_base}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        
        if max_tokens and max_tokens < 10000:
            payload["max_tokens"] = max_tokens
        
        async with httpx.AsyncClient(timeout=max(5.0, float(self.timeout_s))) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
    # @AI_GENERATED: end
    
    async def _chat_openai_compatible(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """OpenAI 兼容接口调用"""
        # 确保 api_base 不以 / 结尾
        api_base = self.api_base.rstrip("/")
        url = f"{api_base}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        
        # 添加 tools 参数（Function Calling）
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        # 某些 API（如腾讯云 DeepSeek）不支持 max_tokens 参数
        # 只有在明确需要限制时才添加，且使用较小的值
        if max_tokens and max_tokens < 10000:
            payload["max_tokens"] = max_tokens
        
        async with httpx.AsyncClient(timeout=max(5.0, float(self.timeout_s))) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            choice = data.get("choices", [{}])[0]
            usage = data.get("usage", {})
            message = choice.get("message", {})
            
            result = {
                "content": message.get("content", ""),
                "model": data.get("model", self.model),
                "tokens_used": usage.get("total_tokens", 0),
                "finish_reason": choice.get("finish_reason", ""),
            }
            
            # 处理 tool_calls
            if message.get("tool_calls"):
                result["tool_calls"] = message["tool_calls"]
            
            return result
    
    async def _chat_azure(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Azure OpenAI 接口调用"""
        # Azure 使用不同的 URL 格式
        api_base = self.api_base.rstrip("/")
        url = f"{api_base}/openai/deployments/{self.model}/chat/completions?api-version=2024-02-15-preview"
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        # 添加 tools 参数
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            choice = data.get("choices", [{}])[0]
            usage = data.get("usage", {})
            message = choice.get("message", {})
            
            result = {
                "content": message.get("content", ""),
                "model": self.model,
                "tokens_used": usage.get("total_tokens", 0),
                "finish_reason": choice.get("finish_reason", ""),
            }
            
            if message.get("tool_calls"):
                result["tool_calls"] = message["tool_calls"]
            
            return result
    
    async def _chat_anthropic(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """Anthropic Claude 接口调用"""
        api_base = self.api_base.rstrip("/")
        url = f"{api_base}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        
        # 转换消息格式（Anthropic 不支持 system 在 messages 中）
        system_msg = ""
        claude_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                claude_messages.append(msg)
        
        payload = {
            "model": self.model,
            "messages": claude_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_msg:
            payload["system"] = system_msg
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            content_blocks = data.get("content", [])
            content = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    content += block.get("text", "")
            
            usage = data.get("usage", {})
            
            return {
                "content": content,
                "model": data.get("model", self.model),
                "tokens_used": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                "finish_reason": data.get("stop_reason", ""),
            }


async def get_llm_service(config_id: Optional[str] = None) -> Optional[LLMService]:
    """获取 LLM 服务实例"""
    import os
    
    config_file = os.path.join(os.path.dirname(__file__), "../data/llm_configs.json")
    if not os.path.exists(config_file):
        return None
    
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    config = None
    
    if config_id:
        for cfg in data.get("configs", []):
            if cfg["id"] == config_id and cfg.get("is_enabled"):
                config = cfg
                break
    else:
        # 使用默认配置
        default_id = data.get("default_config_id")
        if default_id:
            for cfg in data.get("configs", []):
                if cfg["id"] == default_id and cfg.get("is_enabled"):
                    config = cfg
                    break
        
        # 如果没有默认，使用第一个启用的
        if not config:
            for cfg in data.get("configs", []):
                if cfg.get("is_enabled"):
                    config = cfg
                    break
    
    if config:
        return LLMService(config)
    
    return None
# @AI_GENERATED: end
