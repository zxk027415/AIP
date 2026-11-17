"""
光伏故障人机协同迭代标注闭环 - 编排与领域服务包

本包实现迭代标注闭环的核心编排逻辑：
- orchestrator: 闭环编排器，阶段状态机
- review_session: 审核会话管理
- llm_labeling_assistant: LLM 辅助打标
- accuracy_evaluator: 三方精度评估
- label_registry: 标签注册表管理
- backfill: 打标数据回流
- iteration_tracker: 迭代历史追踪
- storage: 存储抽象层（接口 + 文件实现）
"""

__version__ = "0.1.0"
