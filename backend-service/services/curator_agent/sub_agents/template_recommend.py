# @AI_GENERATED: Kiro v1.0
"""
TemplateRecommendAgent - 算法模板推荐子 Agent
专门负责推荐工作流模板和Skills
"""
import os
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class TemplateRecommendAgent:
    """
    算法模板推荐 Agent
    
    职责：
    1. 从数据库查询工作流模板和Skills
    2. 根据用户需求进行智能匹配
    3. 返回排序后的推荐结果
    
    重要：算法模板 ≠ 解决方案
    - 算法模板：工作流模板和Skills，是可执行的算法实现
    - 解决方案：行业解决方案，是业务场景的描述
    """
    
    def __init__(self):
        self.backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    def _get_db_session(self):
        """获取数据库会话"""
        import sys
        if self.backend_dir not in sys.path:
            sys.path.insert(0, self.backend_dir)
        from database import SessionLocal
        return SessionLocal()
    
    async def recommend(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        推荐算法模板
        
        参数:
            query: 用户查询
            context: 上下文信息（包含 context_keywords 从对话历史提取的关键词）
        
        返回:
        {
            "has_templates": bool,
            "workflow_templates": [...],
            "skills": [...],
            "total_workflows": int,
            "total_skills": int,
        }
        """
        context = context or {}
        
        # 从数据库加载模板
        workflows, skills = self._load_templates_from_db()
        
        # 提取关键词 - 结合当前查询和上下文关键词
        keywords = self._extract_keywords(query)
        context_keywords = context.get("context_keywords", [])
        
        # 合并关键词（上下文关键词用于理解多轮对话）
        all_keywords = list(set(keywords + context_keywords))
        
        # 识别核心场景关键词（用于严格筛选）
        core_scenario_keywords = self._identify_core_scenario(context_keywords)
        
        logger.info(f"[TemplateRecommendAgent] 查询关键词: {keywords}, 上下文关键词: {context_keywords}, 核心场景: {core_scenario_keywords}")
        
        # 检查是否是通用查询（没有具体关键词）
        query_lower = query.lower()
        is_general_query = any(kw in query_lower for kw in [
            "有哪些", "列出", "所有", "全部", "模板列表", "私有模板", "我的模板"
        ])
        
        # 检查是否是上下文相关的查询（如 "根据我的业务场景推荐"）
        is_context_query = any(kw in query_lower for kw in [
            "我的", "这个", "根据", "基于", "业务场景", "需求"
        ]) and context_keywords
        
        # 如果是通用查询且没有具体关键词，返回所有模板
        if is_general_query and not keywords and not context_keywords:
            return {
                "has_templates": len(workflows) > 0 or len(skills) > 0,
                "workflow_templates": [
                    {
                        "id": w.get("id"),
                        "name": w.get("name"),
                        "description": (w.get("description") or "")[:200],
                        "status": w.get("status"),
                        "scenario_id": w.get("scenario_id"),
                        "scenario_name": w.get("scenario_name"),
                        "category": w.get("category"),
                        "tags": w.get("tags", []),
                        "node_count": w.get("node_count", 0),
                        "score": 50,  # 默认分数
                        "type": "workflow_template",
                    }
                    for w in workflows[:5]
                ],
                "skills": [
                    {
                        "id": s.get("id"),
                        "name": s.get("skill_name"),
                        "version": s.get("skill_version"),
                        "description": (s.get("description") or "")[:200],
                        "status": s.get("status"),
                        "source_template_name": s.get("source_template_name"),
                        "training_enabled": s.get("training_enabled"),
                        "score": 50,  # 默认分数
                        "type": "skill",
                    }
                    for s in skills[:5]
                ],
                "total_workflows": len(workflows),
                "total_skills": len(skills),
                "keywords": keywords,
                "is_general_query": True,
            }
        
        # 计算匹配分数 - 工作流模板
        # 使用合并后的关键词（当前查询 + 上下文）
        scored_workflows = []
        for w in workflows:
            score = self._calculate_workflow_score(w, query, all_keywords)
            # 如果是上下文查询，检查是否匹配核心场景
            if is_context_query and core_scenario_keywords:
                if not self._matches_core_scenario(w, core_scenario_keywords):
                    continue  # 跳过不匹配核心场景的模板
            if score > 0:
                scored_workflows.append({
                    "id": w.get("id"),
                    "name": w.get("name"),
                    "description": (w.get("description") or "")[:200],
                    "status": w.get("status"),
                    "scenario_id": w.get("scenario_id"),
                    "scenario_name": w.get("scenario_name"),
                    "category": w.get("category"),
                    "tags": w.get("tags", []),
                    "node_count": w.get("node_count", 0),
                    "score": score,
                    "type": "workflow_template",
                })
        
        # 计算匹配分数 - Skills
        # 使用合并后的关键词（当前查询 + 上下文）
        scored_skills = []
        for s in skills:
            score = self._calculate_skill_score(s, query, all_keywords)
            # 如果是上下文查询，检查是否匹配核心场景
            if is_context_query and core_scenario_keywords:
                if not self._matches_core_scenario_skill(s, core_scenario_keywords):
                    continue  # 跳过不匹配核心场景的 Skill
            if score > 0:
                scored_skills.append({
                    "id": s.get("id"),
                    "name": s.get("skill_name"),
                    "version": s.get("skill_version"),
                    "description": (s.get("description") or "")[:200],
                    "status": s.get("status"),
                    "source_template_name": s.get("source_template_name"),
                    "training_enabled": s.get("training_enabled"),
                    "score": score,
                    "type": "skill",
                })
        
        # 排序
        scored_workflows.sort(key=lambda x: x["score"], reverse=True)
        scored_skills.sort(key=lambda x: x["score"], reverse=True)
        
        # 筛选高匹配度结果
        high_match_workflows = [w for w in scored_workflows if w["score"] >= 30][:5]
        high_match_skills = [s for s in scored_skills if s["score"] >= 30][:5]
        
        has_templates = len(high_match_workflows) > 0 or len(high_match_skills) > 0
        
        # 如果是上下文相关查询但没有匹配结果，降低阈值重试
        if is_context_query and not has_templates and context_keywords:
            logger.info(f"[TemplateRecommendAgent] 上下文查询无高匹配结果，降低阈值重试")
            high_match_workflows = [w for w in scored_workflows if w["score"] >= 15][:5]
            high_match_skills = [s for s in scored_skills if s["score"] >= 15][:5]
            has_templates = len(high_match_workflows) > 0 or len(high_match_skills) > 0
        
        return {
            "has_templates": has_templates,
            "workflow_templates": high_match_workflows,
            "skills": high_match_skills,
            "total_workflows": len(workflows),
            "total_skills": len(skills),
            "keywords": keywords,
            "context_keywords": context_keywords,
            "is_context_query": is_context_query,
        }
    
    async def list_all(self, status_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        列出所有算法模板
        
        参数:
            status_filter: 状态过滤
        
        返回:
        {
            "workflow_templates": [...],
            "skills": [...],
            "summary": {...},
        }
        """
        workflows, skills = self._load_templates_from_db()
        
        # 状态过滤
        if status_filter:
            workflows = [w for w in workflows if w.get("status") == status_filter]
            skills = [s for s in skills if s.get("status") == status_filter]
        
        # 统计
        workflow_status_counts = {}
        for w in workflows:
            status = w.get("status") or "unknown"
            workflow_status_counts[status] = workflow_status_counts.get(status, 0) + 1
        
        skill_status_counts = {}
        for s in skills:
            status = s.get("status") or "unknown"
            skill_status_counts[status] = skill_status_counts.get(status, 0) + 1
        
        return {
            "workflow_templates": [
                {
                    "id": w.get("id"),
                    "name": w.get("name"),
                    "description": (w.get("description") or "")[:150],
                    "status": w.get("status"),
                    "scenario_name": w.get("scenario_name"),
                    "category": w.get("category"),
                    "tags": w.get("tags", []),
                    "type": "workflow_template",
                }
                for w in workflows
            ],
            "skills": [
                {
                    "id": s.get("id"),
                    "name": s.get("skill_name"),
                    "version": s.get("skill_version"),
                    "description": (s.get("description") or "")[:150],
                    "status": s.get("status"),
                    "source_template_name": s.get("source_template_name"),
                    "type": "skill",
                }
                for s in skills
            ],
            "summary": {
                "total_workflows": len(workflows),
                "workflow_status_counts": workflow_status_counts,
                "total_skills": len(skills),
                "skill_status_counts": skill_status_counts,
            },
        }
    
    def _load_templates_from_db(self) -> tuple:
        """从数据库加载模板"""
        import sys
        if self.backend_dir not in sys.path:
            sys.path.insert(0, self.backend_dir)
        
        db = self._get_db_session()
        try:
            from models.algo_template import Skill as SkillModel, WorkflowTemplate as WorkflowTemplateModel
            
            workflows_query = db.query(WorkflowTemplateModel).all()
            workflows = [w.to_dict() for w in workflows_query]
            
            skills_query = db.query(SkillModel).all()
            skills = [s.to_dict() for s in skills_query]
            
            logger.info(f"[TemplateRecommendAgent] 加载 {len(workflows)} 个工作流模板，{len(skills)} 个 Skills")
            
            return workflows, skills
        except Exception as e:
            logger.error(f"[TemplateRecommendAgent] 加载模板失败: {e}")
            return [], []
        finally:
            db.close()
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        important_keywords = [
            "光伏", "风电", "新能源", "发电", "功率", "预测",
            "负荷", "电网", "储能", "电池", "soc",
            "故障", "诊断", "维护", "设备", "振动",
            "质量", "缺陷", "检测", "视觉",
            "lstm", "xgboost", "ridge", "机器学习", "深度学习",
        ]
        
        query_lower = query.lower()
        found = [kw for kw in important_keywords if kw in query_lower]
        
        return found
    
    def _calculate_workflow_score(
        self, 
        workflow: Dict[str, Any], 
        query: str, 
        keywords: List[str]
    ) -> int:
        """计算工作流模板匹配分数"""
        score = 0
        
        name = (workflow.get("name") or "").lower()
        description = (workflow.get("description") or "").lower()
        tags = workflow.get("tags") or []
        tags_lower = [t.lower() for t in tags]
        
        query_lower = query.lower()
        
        # 关键词匹配
        for kw in keywords:
            if kw in name:
                score += 30
            if kw in description:
                score += 15
            if any(kw in t for t in tags_lower):
                score += 20
        
        # 特定关键词精确匹配
        if "光伏" in query_lower and "光伏" in name:
            score += 40
        if "功率预测" in query_lower and "预测" in name:
            score += 30
        if "负荷" in query_lower and "负荷" in name:
            score += 40
        if "故障" in query_lower and "故障" in name:
            score += 40
        
        # 状态加分
        if workflow.get("status") == "published":
            score += 15
        
        return min(score, 100)
    
    def _calculate_skill_score(
        self, 
        skill: Dict[str, Any], 
        query: str, 
        keywords: List[str]
    ) -> int:
        """计算 Skill 匹配分数"""
        score = 0
        
        name = (skill.get("skill_name") or "").lower()
        description = (skill.get("description") or "").lower()
        
        query_lower = query.lower()
        
        # 关键词匹配
        for kw in keywords:
            if kw in name:
                score += 35
            if kw in description:
                score += 20
        
        # 特定关键词精确匹配
        if "光伏" in query_lower and "光伏" in name:
            score += 50
        if "功率预测" in query_lower and "预测" in name:
            score += 30
        if "负荷" in query_lower and "负荷" in name:
            score += 50
        if "故障" in query_lower and "故障" in name:
            score += 50
        
        # 状态加分
        if skill.get("status") == "deployed":
            score += 25
        elif skill.get("status") == "ready":
            score += 15
        
        return min(score, 100)
    
    def _identify_core_scenario(self, keywords: List[str]) -> List[str]:
        """
        从关键词中识别核心场景关键词
        
        核心场景关键词是用于严格筛选的关键词，如 "光伏"、"风电"、"负荷" 等
        而 "预测"、"发电" 等是通用关键词，不用于严格筛选
        """
        # 核心场景关键词（用于严格筛选）
        core_keywords = {
            "光伏": ["光伏", "pv", "solar"],
            "风电": ["风电", "wind"],
            "负荷": ["负荷", "load"],
            "储能": ["储能", "电池", "soc", "battery"],
            "故障": ["故障", "诊断", "fault"],
            "质量": ["质量", "缺陷", "检测"],
            "碳": ["碳", "排放", "碳足迹"],
        }
        
        found_core = []
        for kw in keywords:
            kw_lower = kw.lower()
            for core_name, core_variants in core_keywords.items():
                if kw_lower in core_variants and core_name not in found_core:
                    found_core.append(core_name)
        
        return found_core
    
    def _matches_core_scenario(self, workflow: Dict[str, Any], core_keywords: List[str]) -> bool:
        """检查工作流模板是否匹配核心场景"""
        name = (workflow.get("name") or "").lower()
        description = (workflow.get("description") or "").lower()
        
        for core in core_keywords:
            if core.lower() in name or core.lower() in description:
                return True
        
        return False
    
    def _matches_core_scenario_skill(self, skill: Dict[str, Any], core_keywords: List[str]) -> bool:
        """检查 Skill 是否匹配核心场景"""
        name = (skill.get("skill_name") or "").lower()
        description = (skill.get("description") or "").lower()
        
        for core in core_keywords:
            if core.lower() in name or core.lower() in description:
                return True
        
        return False
# @AI_GENERATED: end
