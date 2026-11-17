# @AI_GENERATED: Kiro v1.0
"""验证 Agent 间事件总线"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.workflow_agent.event_bus import EventBus, EventType, AgentEvent


async def main():
    print("=" * 50)
    print("验证事件总线")
    print("=" * 50)

    bus = EventBus()
    received = []

    # 1. 订阅
    def on_regenerate(event: AgentEvent):
        received.append(("regenerate", event))

    async def on_validate(event: AgentEvent):
        received.append(("validate", event))

    bus.subscribe(EventType.WORKFLOW_REGENERATE, on_regenerate)
    bus.subscribe(EventType.WORKFLOW_VALIDATE, on_validate)
    subs = bus.list_subscriptions()
    print(f"\n1. 订阅: {subs}")
    assert len(subs) == 2, f"[FAIL] 期望2个订阅，实际{len(subs)}"
    print("   [OK]")

    # 2. 发布同步事件
    count = await bus.publish(AgentEvent(
        event_type=EventType.WORKFLOW_REGENERATE,
        source_agent="algorithm-agent",
        payload={"workflow_id": "wf-001"},
    ))
    print(f"\n2. 发布 regenerate: {count} 个处理器")
    assert count == 1 and len(received) == 1, "[FAIL]"
    print("   [OK]")

    # 3. 发布异步事件
    count = await bus.publish(AgentEvent(
        event_type=EventType.WORKFLOW_VALIDATE,
        source_agent="ops-agent",
        payload={"workflow_id": "wf-002"},
    ))
    print(f"\n3. 发布 validate (async): {count} 个处理器")
    assert count == 1 and len(received) == 2, "[FAIL]"
    print("   [OK]")

    # 4. 无订阅者事件
    count = await bus.publish(AgentEvent(
        event_type=EventType.ALGORITHM_UPDATED,
        source_agent="test",
    ))
    print(f"\n4. 无订阅者事件: {count} 个处理器")
    assert count == 0, "[FAIL]"
    print("   [OK]")

    # 5. 事件历史
    history = bus.get_history()
    print(f"\n5. 事件历史: {len(history)} 条")
    assert len(history) == 3, f"[FAIL] 期望3条，实际{len(history)}"
    print("   [OK]")

    # 6. 按类型过滤历史
    regen_history = bus.get_history(EventType.WORKFLOW_REGENERATE)
    print(f"\n6. regenerate 历史: {len(regen_history)} 条")
    assert len(regen_history) == 1, "[FAIL]"
    print("   [OK]")

    # 7. 取消订阅
    bus.unsubscribe(EventType.WORKFLOW_REGENERATE, on_regenerate)
    count = await bus.publish(AgentEvent(
        event_type=EventType.WORKFLOW_REGENERATE,
        source_agent="test",
    ))
    print(f"\n7. 取消订阅后发布: {count} 个处理器")
    assert count == 0, "[FAIL]"
    print("   [OK]")

    print("\n" + "=" * 50)
    print("全部通过")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
# @AI_GENERATED: end
