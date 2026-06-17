# @AI_GENERATED: Kiro v1.0
"""
Algorithm Recommend Service - 完整实现
集成 Workflow Agent 场景匹配 + 算法库查询 (1054 个算法)
"""
import os
import json
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# 使用相对导入
from .workflow_agent.skills.scenario_match import (
    ScenarioMatchSkill,
    ScenarioMatchRequest,
    RuleBasedScenarioMatcher,
)
from .workflow_agent.knowledge.algorithm_library import (
    get_algorithm_library,
    get_template_library,
    AlgorithmLibrary,
    IndustryTemplateLibrary,
)

logger = logging.getLogger(__name__)

# 数据文件路径
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCENARIO_MAPPINGS_PATH = os.path.join(DATA_DIR, "scenario_algorithm_mappings.json")


@dataclass
class AlgorithmRecommendation:
    """算法推荐结果"""
    algorithm_id: str
    algorithm_name: str
    category: str
    score: int
    rationale: str
    source: str  # 'basic_module' | 'industry_template' | 'scenario_mapping'
    scenario_id: Optional[str] = None
    scenario_name: Optional[str] = None
    profile: Optional[str] = None  # 'high-accuracy' | 'balanced' | 'low-latency'
    data_requirements: Optional[Dict[str, Any]] = None
    expected_metrics: Optional[Dict[str, Any]] = None


class AlgorithmRecommendService:
    """算法推荐服务 - 完整实现"""

    def __init__(self):
        self._scenario_skill = ScenarioMatchSkill(matcher=RuleBasedScenarioMatcher())
        self._algorithm_library: Optional[AlgorithmLibrary] = None
        self._template_library: Optional[IndustryTemplateLibrary] = None
        self._scenario_mappings: Optional[Dict] = None

    def _get_algorithm_library(self) -> AlgorithmLibrary:
        if self._algorithm_library is None:
            self._algorithm_library = get_algorithm_library()
        return self._algorithm_library

    def _get_template_library(self) -> IndustryTemplateLibrary:
        if self._template_library is None:
            self._template_library = get_template_library()
        return self._template_library

    def _load_scenario_mappings(self) -> Dict:
        if self._scenario_mappings is None:
            path = os.path.normpath(SCENARIO_MAPPINGS_PATH)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._scenario_mappings = json.load(f)
            else:
                self._scenario_mappings = {}
        return self._scenario_mappings

    async def recommend(
        self,
        description: str,
        data_characteristics: Optional[Dict[str, Any]] = None,
        business_objective: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        完整算法推荐流程:
        1. 使用 ScenarioMatchSkill 匹配行业场景
        2. 根据匹配场景获取行业模板推荐
        3. 根据数据特征和业务目标筛选基础模块
        4. 综合评分排序返回推荐结果
        """
        start_time = time.time()
        recommendations: List[AlgorithmRecommendation] = []

        # Step 1: 场景匹配
        scenario_matches = await self._match_scenarios(description)
        matched_scenario_ids = [m["scenario_id"] for m in scenario_matches]

        # Step 2: 获取行业模板推荐
        template_recs = self._get_template_recommendations(
            matched_scenario_ids, scenario_matches, description
        )
        recommendations.extend(template_recs)

        # Step 3: 获取场景-算法映射推荐
        mapping_recs = self._get_scenario_mapping_recommendations(
            matched_scenario_ids, scenario_matches
        )
        recommendations.extend(mapping_recs)

        # Step 4: 获取基础模块推荐
        basic_recs = self._get_basic_module_recommendations(
            description, data_characteristics, business_objective
        )
        recommendations.extend(basic_recs)

        # Step 5: 去重和综合评分
        final_recs = self._deduplicate_and_rank(recommendations, max_results)

        # 构建返回结果
        processing_time = int((time.time() - start_time) * 1000)
        
        return {
            "recommendations": [self._rec_to_dict(r) for r in final_recs],
            "matched_scenarios": scenario_matches,
            "total_algorithms_searched": self._get_total_algorithm_count(),
            "processing_time_ms": processing_time,
        }

    async def _match_scenarios(self, description: str) -> List[Dict]:
        """使用 ScenarioMatchSkill 匹配场景（简化版，避免模型导入冲突）"""
        try:
            # 直接使用 RuleBasedScenarioMatcher 进行匹配，避免 SkillContext 依赖
            scenarios = self._scenario_skill._load_scenarios()
            from .workflow_agent.skills.scenario_match import _extract_entities
            
            extracted = _extract_entities(description)
            raw_matches = self._scenario_skill._matcher.match(description, scenarios)
            
            # 过滤 confidence < 30 的结果
            return [
                {
                    "scenario_id": sid,
                    "scenario_name": name,
                    "confidence_score": conf,
                    "rationale": rationale,
                }
                for sid, name, conf, rationale in raw_matches
                if conf >= 30
            ]
        except Exception as e:
            logger.warning(f"场景匹配失败: {e}")
            return []

    def _get_template_recommendations(
        self,
        scenario_ids: List[str],
        scenario_matches: List[Dict],
        description: str,
    ) -> List[AlgorithmRecommendation]:
        """从行业模板库获取推荐"""
        recommendations = []
        template_lib = self._get_template_library()
        
        # 构建场景ID到匹配信息的映射
        scenario_info = {m["scenario_id"]: m for m in scenario_matches}

        for scenario_id in scenario_ids:
            templates = template_lib.get_by_scenario(scenario_id)
            match_info = scenario_info.get(scenario_id, {})
            base_score = match_info.get("confidence_score", 50)

            for template in templates:
                # 计算模板与描述的相关性
                relevance_boost = self._calculate_text_relevance(
                    description,
                    template.get("name", "") + " " + template.get("description", "")
                )
                
                score = min(100, base_score + relevance_boost)
                
                # 获取默认工作流信息
                workflows = template.get("default_workflows", [])
                high_accuracy_wf = next(
                    (w for w in workflows if w.get("profile") == "high-accuracy"),
                    workflows[0] if workflows else None
                )
                
                rec = AlgorithmRecommendation(
                    algorithm_id=template.get("id"),
                    algorithm_name=template.get("name"),
                    category=template.get("display_category", "行业模板"),
                    score=score,
                    rationale=f"基于场景匹配「{match_info.get('scenario_name', scenario_id)}」推荐，{template.get('description', '')}",
                    source="industry_template",
                    scenario_id=scenario_id,
                    scenario_name=match_info.get("scenario_name"),
                    profile="high-accuracy" if high_accuracy_wf else None,
                    data_requirements=self._extract_data_requirements(high_accuracy_wf),
                    expected_metrics=self._extract_expected_metrics(template),
                )
                recommendations.append(rec)

        return recommendations

    def _get_scenario_mapping_recommendations(
        self,
        scenario_ids: List[str],
        scenario_matches: List[Dict],
    ) -> List[AlgorithmRecommendation]:
        """从场景-算法映射获取推荐"""
        recommendations = []
        mappings = self._load_scenario_mappings()
        algo_lib = self._get_algorithm_library()
        
        scenario_info = {m["scenario_id"]: m for m in scenario_matches}

        for scenario_id in scenario_ids:
            if scenario_id not in mappings:
                continue
                
            match_info = scenario_info.get(scenario_id, {})
            base_score = match_info.get("confidence_score", 50)

            for profile, layers in mappings[scenario_id].items():
                if profile.startswith("_"):
                    continue
                    
                # 提取算法模型层的算法
                model_algos = layers.get("算法模型层", [])
                
                for algo_id in model_algos:
                    algo = algo_lib.get_by_id(algo_id)
                    if not algo:
                        continue
                    
                    # 根据 profile 调整分数
                    profile_boost = {"high-accuracy": 15, "balanced": 10, "low-latency": 5}.get(profile, 0)
                    score = min(100, base_score + profile_boost)
                    
                    rec = AlgorithmRecommendation(
                        algorithm_id=algo_id,
                        algorithm_name=algo.get("name", algo_id),
                        category=algo.get("category", "算法模型"),
                        score=score,
                        rationale=f"场景「{match_info.get('scenario_name', scenario_id)}」的{profile}方案推荐算法",
                        source="scenario_mapping",
                        scenario_id=scenario_id,
                        scenario_name=match_info.get("scenario_name"),
                        profile=profile,
                    )
                    recommendations.append(rec)

        return recommendations

    def _get_basic_module_recommendations(
        self,
        description: str,
        data_characteristics: Optional[Dict[str, Any]],
        business_objective: Optional[str],
    ) -> List[AlgorithmRecommendation]:
        """从基础模块库获取推荐"""
        recommendations = []
        algo_lib = self._get_algorithm_library()
        all_algos = algo_lib.get_all()

        # 关键词映射到算法类别
        objective_category_map = {
            "预测": ["ts_forecast", "regression", "deep_learning"],
            "分类": ["classification", "deep_learning"],
            "异常检测": ["anomaly_detection"],
            "聚类": ["clustering"],
            "回归": ["regression"],
            "优化": ["optimization"],
            "图像": ["industrial_vision", "deep_learning"],
            "信号": ["signal_processing"],
        }

        # 确定目标类别
        target_categories = set()
        search_text = description + " " + (business_objective or "")
        
        for keyword, categories in objective_category_map.items():
            if keyword in search_text:
                target_categories.update(categories)

        # 如果没有匹配到特定类别，使用通用推荐
        if not target_categories:
            target_categories = {"ts_forecast", "regression", "classification"}

        for algo in all_algos:
            algo_category = algo.get("category", "")
            
            # 类别匹配
            if algo_category not in target_categories:
                continue
            
            # 计算文本相关性
            relevance = self._calculate_text_relevance(
                search_text,
                algo.get("name", "") + " " + algo.get("description", "")
            )
            
            if relevance < 10:
                continue
            
            # 数据特征匹配加分
            data_boost = 0
            if data_characteristics:
                data_boost = self._calculate_data_match_score(algo, data_characteristics)
            
            score = min(100, 40 + relevance + data_boost)
            
            rec = AlgorithmRecommendation(
                algorithm_id=algo.get("id"),
                algorithm_name=algo.get("name"),
                category=algo_category,
                score=score,
                rationale=f"基于业务目标和数据特征推荐的基础算法模块",
                source="basic_module",
                data_requirements=self._get_algo_data_requirements(algo),
            )
            recommendations.append(rec)

        return recommendations

    def _calculate_text_relevance(self, query: str, target: str) -> int:
        """计算文本相关性分数 (0-30)"""
        if not query or not target:
            return 0
        
        query_lower = query.lower()
        target_lower = target.lower()
        
        # 关键词列表
        keywords = [
            "光伏", "pv", "solar", "风电", "wind", "功率", "power",
            "预测", "forecast", "负荷", "load", "储能", "storage",
            "电池", "battery", "质量", "quality", "缺陷", "defect",
            "异常", "anomaly", "分类", "classification", "回归", "regression",
            "lstm", "xgboost", "arima", "transformer", "cnn", "rnn",
            "时序", "timeseries", "深度学习", "deep learning",
        ]
        
        score = 0
        for kw in keywords:
            if kw in query_lower and kw in target_lower:
                score += 5
        
        return min(30, score)

    def _calculate_data_match_score(
        self, algo: Dict, data_characteristics: Dict[str, Any]
    ) -> int:
        """计算算法与数据特征的匹配分数 (0-20)"""
        score = 0
        
        data_type = data_characteristics.get("data_type", "")
        algo_category = algo.get("category", "")
        
        # 时序数据匹配时序算法
        if data_type in ["时序", "timeseries"] and algo_category == "ts_forecast":
            score += 10
        
        # 图像数据匹配视觉算法
        if data_type in ["图像", "image"] and algo_category == "industrial_vision":
            score += 10
        
        # 数据量匹配
        data_volume = data_characteristics.get("data_volume", 0)
        if data_volume > 100000 and "deep" in algo.get("name", "").lower():
            score += 5
        elif data_volume < 10000 and "xgboost" in algo.get("id", "").lower():
            score += 5
        
        return min(20, score)

    def _extract_data_requirements(self, workflow: Optional[Dict]) -> Optional[Dict]:
        """从工作流提取数据需求"""
        if not workflow:
            return None
        
        layers = workflow.get("layers", {})
        data_layer = layers.get("数据管理层", [])
        process_layer = layers.get("数据处理层", [])
        
        return {
            "data_sources": data_layer,
            "preprocessing": process_layer,
        }

    def _extract_expected_metrics(self, template: Dict) -> Optional[Dict]:
        """提取预期指标"""
        workflows = template.get("default_workflows", [])
        if not workflows:
            return None
        
        metrics = set()
        for wf in workflows:
            eval_layer = wf.get("layers", {}).get("评估输出层", [])
            metrics.update(eval_layer)
        
        return {"evaluation_metrics": list(metrics)} if metrics else None

    def _get_algo_data_requirements(self, algo: Dict) -> Optional[Dict]:
        """获取算法的数据需求"""
        params = algo.get("parameters", [])
        if not params:
            return None
        
        return {
            "parameters": [p.get("name") for p in params[:5]],
            "input_type": algo.get("input_type", "tabular"),
        }

    def _deduplicate_and_rank(
        self, recommendations: List[AlgorithmRecommendation], max_results: int
    ) -> List[AlgorithmRecommendation]:
        """去重并排序"""
        # 按 algorithm_id 去重，保留最高分
        seen = {}
        for rec in recommendations:
            key = rec.algorithm_id
            if key not in seen or rec.score > seen[key].score:
                seen[key] = rec
        
        # 按分数排序
        sorted_recs = sorted(seen.values(), key=lambda x: x.score, reverse=True)
        
        return sorted_recs[:max_results]

    def _rec_to_dict(self, rec: AlgorithmRecommendation) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "algorithm_id": rec.algorithm_id,
            "algorithm_name": rec.algorithm_name,
            "category": rec.category,
            "score": rec.score,
            "rationale": rec.rationale,
            "source": rec.source,
        }
        
        if rec.scenario_id:
            result["scenario_id"] = rec.scenario_id
        if rec.scenario_name:
            result["scenario_name"] = rec.scenario_name
        if rec.profile:
            result["profile"] = rec.profile
        if rec.data_requirements:
            result["data_requirements"] = rec.data_requirements
        if rec.expected_metrics:
            result["expected_metrics"] = rec.expected_metrics
        
        return result

    def _get_total_algorithm_count(self) -> int:
        """获取算法库总数"""
        algo_count = self._get_algorithm_library().total_count()
        template_count = self._get_template_library().total_count()
        return algo_count + template_count


# 模块级单例
_service_instance: Optional[AlgorithmRecommendService] = None


def get_algorithm_recommend_service() -> AlgorithmRecommendService:
    global _service_instance
    if _service_instance is None:
        _service_instance = AlgorithmRecommendService()
    return _service_instance
# @AI_GENERATED: end
