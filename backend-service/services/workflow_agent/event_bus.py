# @AI_GENERATED: Kiro v1.0
"""
Agent 间事件总线 — 本地实现，预留 Redis Pub/Sub 通道
支持 Algorithm Agent 触发算法模板重新生成、Ops Agent 触发算法模板验证
"""
import asyncio
import logging
from typing import Dict, List, Callable, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """事件类型"""
    WORKFLOW_REGENERATE = "workflow_regenerate"
    WORKFLOW_VALIDATE = "workflow_validate"
    ALGORITHM_UPDATED = "algorithm_updated"


class AgentEvent(BaseModel):
    """事件消息"""
    event_type: EventType
    source_agent: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# 事件处理器类型
EventHandler = Callable[[AgentEvent], Any]


class EventBus:
    """
    本地事件总线（单进程内）。
    预留 Redis Pub/Sub 接口，当前使用内存队列。
    """

    def __init__(self, use_redis: bool = False, redis_url: Optional[str] = None):
        self._handlers: Dict[EventType, List[EventHandler]] = {}
        self._use_redis = use_redis
        self._redis_url = redis_url
        self._history: List[AgentEvent] = []
        self._max_history = 100

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """订阅事件"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.info(f"事件订阅: {event_type.value} ← {handler.__name__}")

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """取消订阅"""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h is not handler
            ]

    async def publish(self, event: AgentEvent) -> int:
        """
        发布事件，返回成功处理的 handler 数量。
        当前为本地分发，后续可替换为 Redis PUBLISH。
        """
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            logger.debug(f"事件 {event.event_type.value} 无订阅者")
            return 0

        success_count = 0
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
                success_count += 1
            except Exception as e:
                logger.error(
                    f"事件处理器 {handler.__name__} 异常: {e}", exc_info=True
                )
        return success_count

    def get_history(self, event_type: Optional[EventType] = None,
                    limit: int = 20) -> List[AgentEvent]:
        """获取事件历史"""
        events = self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def list_subscriptions(self) -> Dict[str, int]:
        """列出所有订阅"""
        return {k.value: len(v) for k, v in self._handlers.items() if v}


# 全局单例
event_bus = EventBus()
# @AI_GENERATED: end
