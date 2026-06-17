# @AI_GENERATED: Kiro v1.0
"""
SolutionSearchAgent - 解决方案搜索子 Agent
专门负责从解决方案库中搜索匹配的AI解决方案
"""
import json
import os
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SolutionSearchAgent:
    """
    解决方案搜索 Agent
    
    职责：
    1. 从解决方案库（行业模板）中搜索匹配的方案
    2. 根据关键词和场景进行智能匹配
    3. 返回排序后的推荐结果
    """
    
    def __init__(self):
        self.backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self._solution_cache = None
    
    def _load_solutions(self) -> List[Dict[str, Any]]:
        """加载解决方案库（行业模板）"""
        if self._solution_cache is not None:
            return self._solution_cache
        
        import sys
        if self.backend_dir not in sys.path:
            sys.path.insert(0, self.backend_dir)
        
        try:
            from services.workflow_agent.knowledge.algorithm_library import get_template_library
            template_lib = get_template_library()
            self._solution_cache = template_lib.get_all()
            logger.info(f"[SolutionSearchAgent] 加载 {len(self._solution_cache)} 个解决方案")
        except Exception as e:
            logger.error(f"[SolutionSearchAgent] 加载解决方案库失败: {e}")
            self._solution_cache = []
        
        return self._solution_cache
    
    async def search(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        搜索解决方案
        
        参数:
            query: 用户查询
            context: 上下文信息
        
        返回:
        {
            "solutions": [...],  # 匹配的解决方案列表
            "total_searched": int,  # 搜索的总数
            "matched_scenario": {...},  # 匹配的场景
        }
        """
        context = context or {}
        solutions = self._load_solutions()
        
        # 关键词提取
        keywords = self._extract_keywords(query)
        
        # 场景匹配
        matched_scenario = self._match_scenario(query)
        
        # 计算匹配分数
        scored_solutions = []
        for sol in solutions:
            score = self._calculate_score(sol, query, keywords, matched_scenario)
            if score > 0:
                scored_solutions.append({
                    "id": sol.get("id"),
                    "name": sol.get("name"),
                    "description": (sol.get("description") or "")[:200],
                    "scenario_id": sol.get("scenario_id"),
                    "algorithms": sol.get("algorithms", [])[:5],
                    "score": score,
                    "type": "solution",
                })
        
        # 排序
        scored_solutions.sort(key=lambda x: x["score"], reverse=True)
        
        return {
            "solutions": scored_solutions[:10],
            "total_searched": len(solutions),
            "matched_scenario": matched_scenario,
            "keywords": keywords,
        }
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        # 预定义的重要关键词
        important_keywords = [
            "光伏", "风电", "新能源", "发电", "功率", "预测",
            "负荷", "电网", "储能", "电池", "soc",
            "故障", "诊断", "维护", "设备", "振动",
            "质量", "缺陷", "检测", "视觉",
            "碳", "排放", "碳足迹",
            "钢铁", "炼钢", "轧钢",
        ]
        
        query_lower = query.lower()
        found = [kw for kw in important_keywords if kw in query_lower]
        
        return found
    
    def _match_scenario(self, query: str) -> Optional[Dict[str, Any]]:
        """匹配场景"""
        scenario_keywords = {
            "renewable-energy": {
                "name": "新能源发电",
                "keywords": ["光伏", "风电", "新能源", "发电", "功率预测", "pv", "solar", "wind"],
            },
            "power-grid": {
                "name": "电网调度",
                "keywords": ["电网", "负荷", "调度", "配电", "输电", "grid", "load"],
            },
            "energy-storage": {
                "name": "储能管理",
                "keywords": ["储能", "电池", "soc", "充放电", "battery", "storage"],
            },
            "equipment-maintenance": {
                "name": "设备维护",
                "keywords": ["设备", "故障", "诊断", "维护", "振动", "equipment", "fault"],
            },
            "quality-control": {
                "name": "质量控制",
                "keywords": ["质量", "缺陷", "检测", "视觉", "quality", "defect"],
            },
            "carbon-management": {
                "name": "碳管理",
                "keywords": ["碳", "排放", "碳足迹", "carbon", "emission"],
            },
            "steel-manufacturing": {
                "name": "钢铁制造",
                "keywords": ["钢铁", "炼钢", "轧钢", "高炉", "steel"],
            },
        }
        
        query_lower = query.lower()
        best_match = None
        best_score = 0
        
        for scenario_id, info in scenario_keywords.items():
            score = sum(1 for kw in info["keywords"] if kw in query_lower)
            if score > best_score:
                best_score = score
                best_match = {
                    "id": scenario_id,
                    "name": info["name"],
                    "match_score": score,
                }
        
        return best_match
    
    def _calculate_score(
        self, 
        solution: Dict[str, Any], 
        query: str, 
        keywords: List[str],
        matched_scenario: Optional[Dict[str, Any]]
    ) -> int:
        """计算解决方案匹配分数"""
        score = 0
        
        name = (solution.get("name") or "").lower()
        description = (solution.get("description") or "").lower()
        scenario_id = solution.get("scenario_id", "")
        
        # 场景匹配加分
        if matched_scenario and scenario_id == matched_scenario.get("id"):
            score += 50
        
        # 关键词匹配
        for kw in keywords:
            if kw in name:
                score += 30
            if kw in description:
                score += 15
        
        # 特定关键词精确匹配
        query_lower = query.lower()
        if "光伏" in query_lower and "光伏" in name:
            score += 40
        if "功率预测" in query_lower and "预测" in name:
            score += 30
        if "负荷" in query_lower and "负荷" in name:
            score += 40
        if "故障" in query_lower and "故障" in name:
            score += 40
        if "储能" in query_lower and "储能" in name:
            score += 40
        
        return min(score, 100)
# @AI_GENERATED: end
