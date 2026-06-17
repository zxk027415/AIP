# @AI_GENERATED: Kiro v1.0
"""
Curator Agent - 算法策划 Master Agent
采用 Master + Sub-Agent 架构

Master Agent: 负责理解用户意图，路由到合适的子 Agent
Sub-Agents:
  - SolutionSearchAgent: 搜索解决方案库
  - TemplateRecommendAgent: 推荐算法模板（工作流和Skills）
  - ScenarioAnalyzeAgent: 分析业务场景，细化需求

重要概念区分：
  - 解决方案库：包含行业解决方案（业务场景描述），不是模板
  - 算法模板：工作流模板和Skills，是可执行的算法实现
"""

from .master_agent import CuratorMasterAgent, get_curator_master_agent
from .sub_agents import SolutionSearchAgent, TemplateRecommendAgent, ScenarioAnalyzeAgent

__all__ = [
    "CuratorMasterAgent",
    "get_curator_master_agent",
    "SolutionSearchAgent", 
    "TemplateRecommendAgent",
    "ScenarioAnalyzeAgent",
]
# @AI_GENERATED: end
