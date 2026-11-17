# @AI_GENERATED: Kiro v1.0
"""
Curator Master Agent - 算法策划主控 Agent
负责理解用户意图，路由到合适的子 Agent
"""
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class CuratorMasterAgent:
    """
    算法策划 Master Agent
    
    职责：
    1. 理解用户意图
    2. 路由到合适的子 Agent
    3. 整合子 Agent 的结果
    4. 生成最终响应
    """
    
    def __init__(self):
        self.sub_agents = {}
        self._init_sub_agents()
    
    def _init_sub_agents(self):
        """初始化子 Agents"""
        from .sub_agents import (
            SolutionSearchAgent,
            TemplateRecommendAgent,
            ScenarioAnalyzeAgent,
        )
        
        self.sub_agents = {
            "solution_search": SolutionSearchAgent(),
            "template_recommend": TemplateRecommendAgent(),
            "scenario_analyze": ScenarioAnalyzeAgent(),
        }
    
    def classify_intent(self, message: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        分类用户意图
        
        返回:
        {
            "primary_intent": "solution_search" | "template_recommend" | "scenario_analyze" | "general",
            "secondary_intents": [...],
            "keywords": [...],
            "confidence": 0.0-1.0,
            "context_keywords": [...],  # 从对话历史中提取的关键词
        }
        """
        context = context or {}
        msg_lower = message.lower()
        
        # 从对话历史中提取上下文关键词
        context_keywords = self._extract_context_keywords(context)
        
        # 意图关键词映射
        intent_keywords = {
            "solution_search": [
                "解决方案", "方案", "怎么做", "如何实现", "业务场景",
                "光伏预测", "负荷预测", "故障诊断", "功率预测",
                "新能源", "储能", "电网", "设备维护",
            ],
            "template_recommend": [
                "模板", "算法模板", "工作流", "skill", "私有模板",
                "我的模板", "有哪些模板", "模板列表", "推荐模板",
                "工作流模板", "skills",
            ],
            "scenario_analyze": [
                "分析", "需求", "场景分析", "细化", "具体需求",
                "数据特征", "业务目标", "精度要求",
            ],
            # @AI_GENERATED
            "load_forecast_action": [
                "触发", "训练负荷", "负荷预测训练", "跑一下负荷", "执行负荷",
                "负荷回测", "backtest", "预测场景",
                "trigger", "train", "predict",
            ],
            # @AI_GENERATED: end
        }
        
        # 计算各意图的匹配分数
        scores = {}
        matched_keywords = {}
        
        for intent, keywords in intent_keywords.items():
            score = 0
            matches = []
            for kw in keywords:
                if kw in msg_lower:
                    score += 1
                    matches.append(kw)
            scores[intent] = score
            matched_keywords[intent] = matches
        
        # 确定主要意图
        max_score = max(scores.values()) if scores else 0
        
        if max_score == 0:
            # 当前消息没有明确意图，检查是否是上下文相关的查询
            # 例如 "根据我的业务场景推荐" 需要结合上下文理解
            if self._is_context_dependent_query(message, context_keywords):
                # 根据上下文关键词确定意图
                primary_intent = self._infer_intent_from_context(message, context_keywords)
                confidence = 0.7
            else:
                primary_intent = "general"
                confidence = 0.3
        else:
            primary_intent = max(scores, key=scores.get)
            confidence = min(max_score / 3, 1.0)  # 3个关键词以上为满分
        
        # 确定次要意图
        secondary_intents = [
            intent for intent, score in scores.items()
            if score > 0 and intent != primary_intent
        ]
        
        # 特殊规则：如果同时提到解决方案和模板，优先推荐模板
        if scores.get("solution_search", 0) > 0 and scores.get("template_recommend", 0) > 0:
            # 用户可能想要两者，但先推荐模板
            if "模板" in msg_lower or "skill" in msg_lower:
                primary_intent = "template_recommend"
                secondary_intents = ["solution_search"] + [i for i in secondary_intents if i != "solution_search"]
        
        return {
            "primary_intent": primary_intent,
            "secondary_intents": secondary_intents,
            "keywords": matched_keywords.get(primary_intent, []),
            "confidence": confidence,
            "all_scores": scores,
            "context_keywords": context_keywords,
        }
    
    def _extract_context_keywords(self, context: Dict[str, Any]) -> List[str]:
        """
        从对话历史中提取关键词
        
        重要：只从用户消息中提取，不从助手响应中提取
        这样可以聚焦于用户的核心意图，而不是被助手响应中的各种关键词干扰
        """
        keywords = []
        history = context.get("conversation_history", [])
        
        # 重要关键词列表 - 用于识别用户意图的核心关键词
        important_keywords = [
            "光伏", "风电", "新能源", "发电", "功率", "预测",
            "负荷", "电网", "储能", "电池", "soc",
            "故障", "诊断", "维护", "设备", "振动",
            "质量", "缺陷", "检测", "视觉",
            "碳", "排放", "碳足迹",
        ]
        
        # 只从用户消息中提取关键词
        for msg in history:
            if msg.get("role") != "user":
                continue  # 跳过助手消息
            
            content = (msg.get("content") or "").lower()
            for kw in important_keywords:
                if kw in content and kw not in keywords:
                    keywords.append(kw)
        
        return keywords
    
    def _is_context_dependent_query(self, message: str, context_keywords: List[str]) -> bool:
        """检查是否是依赖上下文的查询"""
        msg_lower = message.lower()
        
        # 指示词：表明用户在引用之前的对话
        context_indicators = [
            "我的", "这个", "那个", "上面", "刚才", "之前",
            "根据", "基于", "按照", "针对",
            "业务场景", "需求", "场景",
        ]
        
        # 如果消息中有指示词，且对话历史中有关键词，则是上下文相关查询
        has_indicator = any(ind in msg_lower for ind in context_indicators)
        has_context = len(context_keywords) > 0
        
        return has_indicator and has_context
    
    def _infer_intent_from_context(self, message: str, context_keywords: List[str]) -> str:
        """根据上下文推断意图"""
        msg_lower = message.lower()
        
        # 如果消息提到模板/推荐，且上下文有业务关键词
        if any(kw in msg_lower for kw in ["模板", "推荐", "算法"]):
            return "template_recommend"
        
        # 如果消息提到分析/需求
        if any(kw in msg_lower for kw in ["分析", "需求", "细化"]):
            return "scenario_analyze"
        
        # 默认搜索解决方案
        return "solution_search"
    
    async def process(self, message: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        处理用户消息
        
        返回:
        {
            "response": str,  # 最终响应文本
            "intent": {...},  # 意图分类结果
            "sub_agent_results": {...},  # 子 Agent 结果
            "suggested_actions": [...],  # 建议操作
        }
        """
        context = context or {}
        
        # 1. 分类意图
        intent = self.classify_intent(message, context)
        logger.info(f"[CuratorMaster] 意图分类: {intent['primary_intent']} (confidence: {intent['confidence']})")
        
        # 获取上下文关键词
        context_keywords = intent.get("context_keywords", [])
        if context_keywords:
            logger.info(f"[CuratorMaster] 上下文关键词: {context_keywords}")
        
        # 2. 路由到子 Agent
        sub_agent_results = {}
        primary_intent = intent["primary_intent"]
        
        # 构建增强的上下文，包含对话历史中的关键词
        enhanced_context = context.copy()
        enhanced_context["context_keywords"] = context_keywords
        
        if primary_intent == "solution_search":
            # 搜索解决方案
            result = await self.sub_agents["solution_search"].search(message, enhanced_context)
            sub_agent_results["solution_search"] = result
            
            # 同时推荐算法模板
            template_result = await self.sub_agents["template_recommend"].recommend(message, enhanced_context)
            sub_agent_results["template_recommend"] = template_result
            
        elif primary_intent == "template_recommend":
            # 推荐算法模板 - 传递增强的上下文
            result = await self.sub_agents["template_recommend"].recommend(message, enhanced_context)
            sub_agent_results["template_recommend"] = result
            
        elif primary_intent == "scenario_analyze":
            # 分析场景
            result = await self.sub_agents["scenario_analyze"].analyze(message, enhanced_context)
            sub_agent_results["scenario_analyze"] = result
            
        # @AI_GENERATED
        elif primary_intent == "load_forecast_action":
            # 负荷预测操作 — 调用 Agent Tool
            from services.agent_tools import get_tool_executor
            executor = get_tool_executor()
            msg_lower = message.lower()

            if any(kw in msg_lower for kw in ["回测", "backtest"]):
                tool_result = await executor.execute("trigger_load_forecast_backtest", {
                    "task_type": self._extract_task_type(message),
                    "start_date": "2025-01-01",
                    "end_date": "2025-01-07",
                })
            elif any(kw in msg_lower for kw in ["训练", "train", "建模"]):
                # 训练优先于预测（因为"负荷预测训练"同时包含"预测"和"训练"）
                tool_result = await executor.execute("trigger_load_forecast_train", {
                    "task_type": self._extract_task_type(message),
                })
            elif any(kw in msg_lower for kw in ["预测", "predict", "forecast", "推理"]):
                tool_result = await executor.execute("trigger_load_forecast_predict", {
                    "task_type": self._extract_task_type(message),
                    "model_id": "",
                })
            elif any(kw in msg_lower for kw in ["场景", "scenario"]):
                tool_result = await executor.execute("get_forecast_scenarios", {})
            else:
                # 默认触发训练
                tool_result = await executor.execute("trigger_load_forecast_train", {
                    "task_type": self._extract_task_type(message),
                })

            sub_agent_results["load_forecast_action"] = tool_result
        # @AI_GENERATED: end
        
        else:
            # 通用处理：同时调用解决方案搜索和模板推荐
            solution_result = await self.sub_agents["solution_search"].search(message, enhanced_context)
            template_result = await self.sub_agents["template_recommend"].recommend(message, enhanced_context)
            sub_agent_results["solution_search"] = solution_result
            sub_agent_results["template_recommend"] = template_result
        
        # 3. 整合结果生成响应
        response = self._generate_response(message, intent, sub_agent_results)
        
        # 4. 生成建议操作
        sub_agent_results["_original_message"] = message
        suggested_actions = self._generate_suggested_actions(intent, sub_agent_results)
        
        return {
            "response": response,
            "intent": intent,
            "sub_agent_results": sub_agent_results,
            "suggested_actions": suggested_actions,
        }
    
    # @AI_GENERATED
    @staticmethod
    def _extract_task_type(message: str) -> str:
        """从消息中提取预测场景类型"""
        msg = message.upper()
        for tt in ["DI", "WI", "MI", "D", "W", "M"]:
            if tt in msg:
                return tt
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in ["日内", "超短期"]):
            return "DI"
        if any(kw in msg_lower for kw in ["日前", "短期"]):
            return "D"
        if "周内" in msg_lower:
            return "WI"
        if "周前" in msg_lower:
            return "W"
        if "月内" in msg_lower:
            return "MI"
        if "月前" in msg_lower:
            return "M"
        return "D"  # 默认日前
    # @AI_GENERATED: end

    def _generate_response(
        self, 
        message: str, 
        intent: Dict[str, Any], 
        sub_agent_results: Dict[str, Any]
    ) -> str:
        """整合子 Agent 结果生成最终响应"""
        
        parts = []
        primary_intent = intent["primary_intent"]
        
        # 解决方案搜索结果
        if "solution_search" in sub_agent_results:
            solution_result = sub_agent_results["solution_search"]
            if solution_result.get("solutions"):
                parts.append(self._format_solutions(solution_result))
        
        # 算法模板推荐结果
        if "template_recommend" in sub_agent_results:
            template_result = sub_agent_results["template_recommend"]
            if template_result.get("has_templates"):
                parts.append(self._format_templates(template_result))
            elif primary_intent == "template_recommend":
                parts.append(self._format_no_templates(template_result))
        
        # 场景分析结果
        if "scenario_analyze" in sub_agent_results:
            analyze_result = sub_agent_results["scenario_analyze"]
            parts.append(self._format_analysis(analyze_result))
        
        # @AI_GENERATED
        # 负荷预测操作结果
        if "load_forecast_action" in sub_agent_results:
            lf_result = sub_agent_results["load_forecast_action"]
            parts.append(self._format_load_forecast_result(lf_result))
        # @AI_GENERATED: end
        
        # 如果没有任何结果
        if not parts:
            parts.append(self._format_general_response(message))
        
        return "\n\n---\n\n".join(parts)
    
    def _format_solutions(self, result: Dict[str, Any]) -> str:
        """格式化解决方案搜索结果"""
        solutions = result.get("solutions", [])
        if not solutions:
            return ""
        
        lines = ["## 🎯 解决方案推荐\n"]
        lines.append("| 方案名称 | 场景 | 匹配度 |")
        lines.append("|---------|------|--------|")
        
        for sol in solutions[:5]:
            name = sol.get("name", "")
            scenario = sol.get("scenario_id", "")
            score = sol.get("score", 0)
            score_bar = "⭐" * min(int(score / 20), 5)
            lines.append(f"| {name} | {scenario} | {score_bar} |")
        
        if result.get("total_searched", 0) > 0:
            lines.append(f"\n*共搜索 {result['total_searched']} 个解决方案*")
        
        return "\n".join(lines)
    
    # @AI_GENERATED: Kiro v1.0
    def _format_templates(self, result: Dict[str, Any]) -> str:
        """格式化算法模板推荐结果，包含可点击的回测链接"""
        lines = ["## 🔧 算法模板推荐\n"]
        
        # 检查是否是通用查询
        is_general = result.get("is_general_query", False)
        if is_general:
            lines[0] = "## 🔧 算法模板库\n"
        
        # 工作流模板
        workflows = result.get("workflow_templates", [])
        if workflows:
            lines.append("### 工作流模板\n")
            lines.append("| 模板名称 | 状态 | 场景 | 匹配度 | 操作 |")
            lines.append("|---------|------|------|--------|------|")
            for w in workflows[:5]:
                name = w.get("name", "")
                template_id = w.get("id", "")
                status = w.get("status", "")
                scenario = w.get("scenario_name", "")
                score = w.get("score", 0)
                status_emoji = {"published": "✅", "testing": "🧪", "draft": "📝"}.get(status, "")
                score_bar = "⭐" * min(int(score / 20), 5) if not is_general else "-"
                # 生成回测链接 - 指向算法 Agent 的 Sandbox Agent
                backtest_link = f"[🧪 回测](/algorithm-agent?agent=sandbox&templateId={template_id}&templateType=workflow&templateName={name})"
                lines.append(f"| {name} | {status_emoji} {status} | {scenario} | {score_bar} | {backtest_link} |")
        
        # Skills
        skills = result.get("skills", [])
        if skills:
            lines.append("\n### Skills\n")
            lines.append("| Skill 名称 | 版本 | 状态 | 匹配度 | 操作 |")
            lines.append("|-----------|------|------|--------|------|")
            for s in skills[:5]:
                name = s.get("name", "")
                skill_id = s.get("id", "")
                version = s.get("version", "")
                status = s.get("status", "")
                score = s.get("score", 0)
                status_emoji = {"deployed": "🚀", "ready": "✅", "training": "⏳", "packaged": "📦"}.get(status, "")
                score_bar = "⭐" * min(int(score / 20), 5) if not is_general else "-"
                # 生成回测链接 - 指向算法 Agent 的 Sandbox Agent
                backtest_link = f"[🧪 测试](/algorithm-agent?agent=sandbox&templateId={skill_id}&templateType=skill&templateName={name})"
                lines.append(f"| {name} | v{version} | {status_emoji} {status} | {score_bar} | {backtest_link} |")
        
        # 统计信息
        total_workflows = result.get("total_workflows", 0)
        total_skills = result.get("total_skills", 0)
        lines.append(f"\n*系统共有 {total_workflows} 个工作流模板，{total_skills} 个 Skills*")
        
        # 如果是通用查询，添加提示
        if is_general:
            lines.append("\n💡 **提示**：描述您的具体业务场景，我可以推荐更匹配的模板。")
        
        # 添加操作提示
        lines.append("\n📌 点击「回测」或「测试」链接可进入回测助手，通过对话配置数据集、预测时长和算法参数。")
        
        return "\n".join(lines)
    # @AI_GENERATED: end
    
    def _format_no_templates(self, result: Dict[str, Any]) -> str:
        """格式化无模板匹配的响应"""
        lines = ["## 🔧 算法模板\n"]
        lines.append("⚠️ 未找到与您需求匹配的算法模板。\n")
        lines.append("**建议**：")
        lines.append("1. 前往「算法模板库」查看所有可用模板")
        lines.append("2. 基于工作流编辑器创建新模板")
        lines.append("3. 描述更具体的业务场景，我可以帮您分析需求")
        
        return "\n".join(lines)
    
    def _format_analysis(self, result: Dict[str, Any]) -> str:
        """格式化场景分析结果"""
        lines = ["## 📋 场景分析\n"]
        
        if result.get("scenario_type"):
            lines.append(f"**场景类型**：{result['scenario_type']}")
        
        if result.get("data_requirements"):
            lines.append("\n**数据要求**：")
            for req in result["data_requirements"]:
                lines.append(f"- {req}")
        
        if result.get("recommended_approach"):
            lines.append(f"\n**推荐方案**：{result['recommended_approach']}")
        
        if result.get("clarification_questions"):
            lines.append("\n**需要进一步了解**：")
            for q in result["clarification_questions"]:
                lines.append(f"- {q}")
        
        return "\n".join(lines)
    
    # @AI_GENERATED
    @staticmethod
    def _format_load_forecast_result(result: Dict[str, Any]) -> str:
        """格式化负荷预测操作结果"""
        if "error" in result:
            return f"❌ **负荷预测操作失败**\n\n{result['error']}"

        lines = []
        summary = result.get("summary", "")
        if summary:
            lines.append(f"### ⚡ {summary}")
            lines.append("")

        # 场景列表
        if "scenarios" in result:
            lines.append("| 场景 | 代码 | 说明 |")
            lines.append("|------|------|------|")
            for s in result["scenarios"]:
                lines.append(f"| {s.get('name', '')} | {s.get('task_type', '')} | {s.get('rounding_unit', '')} |")
            return "\n".join(lines)

        # 训练/预测/回测结果
        for key in ["task_id", "model_id", "duration", "point_count",
                     "time_range", "total_days", "success_days",
                     "status", "current_step", "completed_steps",
                     "error_message", "failed_step"]:
            val = result.get(key)
            if val is not None:
                lines.append(f"- **{key}**: {val}")

        # 预测预览
        preview = result.get("forecast_preview")
        if preview:
            lines.append("")
            lines.append("| 时间 | 预测值 |")
            lines.append("|------|--------|")
            for p in preview:
                lines.append(f"| {p['time']} | {p['value']} |")

        # 添加跳转提示
        lines.append("")
        lines.append("📊 **正在跳转到训练可视化界面...**")

        return "\n".join(lines) if lines else str(result)
    # @AI_GENERATED: end

    def _format_general_response(self, message: str) -> str:
        """格式化通用响应"""
        return """我是算法策划助手，可以帮您：

1. **搜索解决方案**：描述您的业务场景，我会推荐匹配的AI解决方案
2. **推荐算法模板**：查看系统中的工作流模板和Skills
3. **分析需求**：帮您细化业务需求，确定技术方案

请告诉我您的具体需求，或者选择下方的快捷操作。"""
    
    def _generate_suggested_actions(
        self, 
        intent: Dict[str, Any], 
        sub_agent_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """生成建议操作"""
        actions = []
        primary_intent = intent["primary_intent"]
        
        if primary_intent == "solution_search":
            actions = [
                {"label": "查看解决方案详情", "action": "view-solution-detail"},
                {"label": "推荐算法模板", "action": "recommend-templates"},
                {"label": "分析数据需求", "action": "analyze-data"},
            ]
        elif primary_intent == "template_recommend":
            actions = [
                {"label": "查看模板详情", "action": "view-template-detail"},
                {"label": "创建新模板", "action": "create-template"},
                {"label": "搜索解决方案", "action": "search-solutions"},
            ]
        elif primary_intent == "scenario_analyze":
            actions = [
                {"label": "推荐解决方案", "action": "recommend-solutions"},
                {"label": "推荐算法模板", "action": "recommend-templates"},
                {"label": "配置数据集", "action": "config-dataset"},
            ]
        # @AI_GENERATED
        elif primary_intent == "load_forecast_action":
            # 返回跳转到训练页面的 action，前端检测到后自动导航
            lf_result = sub_agent_results.get("load_forecast_action", {})
            task_type = lf_result.get("task_type") or intent.get("keywords", ["D"])[0] if intent.get("keywords") else "D"
            # 从意图中提取参数
            actions = [
                {
                    "label": "打开训练可视化界面",
                    "action": "navigate-load-forecast-training",
                    "params": {
                        "task_type": self._extract_task_type(
                            sub_agent_results.get("_original_message", "")),
                    },
                },
                {"label": "查看预测场景", "action": "view-forecast-scenarios"},
            ]
        # @AI_GENERATED: end
        else:
            actions = [
                {"label": "搜索解决方案", "action": "search-solutions"},
                {"label": "查看算法模板", "action": "view-templates"},
                {"label": "分析业务场景", "action": "analyze-scenario"},
            ]
        
        return actions


# 单例
_master_agent = None

def get_curator_master_agent() -> CuratorMasterAgent:
    """获取 Curator Master Agent 单例"""
    global _master_agent
    if _master_agent is None:
        _master_agent = CuratorMasterAgent()
    return _master_agent
# @AI_GENERATED: end
