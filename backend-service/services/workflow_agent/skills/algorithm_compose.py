# @AI_GENERATED: Kiro v1.0
"""
算法组合推荐 Skill — 为指定场景算法方案生成竞争算法模板
层级：用户选择 L2 模板 → Skill 返回该模板下的 N 个 L3 竞争算法模板（由 L4 基础模块搭建）
预留 LLMAlgorithmComposer 接口，当前使用 RuleBasedAlgorithmComposer
"""
import time
import uuid
import logging
from typing import Dict, List, Optional

from pydantic import BaseModel

from models.workflow_agent_models import (
    AlgorithmComposeRequest,
    AlgorithmComposeResponse,
    AlgorithmCombination,
    AlgorithmLayer,
    AlgorithmRecommendation,
    CombinationProfile,
    SkillContext,
    UserConstraints,
)
from services.workflow_agent.skills.base_skill import BaseSkill
from services.workflow_agent.knowledge.algorithm_library import (
    get_algorithm_library,
    get_template_library,
)

logger = logging.getLogger(__name__)

LAYER_ORDER = ["数据管理层", "数据处理层", "算法模型层", "评估输出层"]


class AlgorithmComposer:
    """算法组合器基类（策略模式）"""
    def compose(
        self,
        scenario_id: str,
        template_id: Optional[str],
        constraints: Optional[UserConstraints],
    ) -> List[AlgorithmCombination]:
        raise NotImplementedError


class RuleBasedAlgorithmComposer(AlgorithmComposer):
    """基于模板库的算法组合器 — 从 industry_templates.json 读取竞争算法模板"""

    def compose(
        self,
        scenario_id: str,
        template_id: Optional[str],
        constraints: Optional[UserConstraints],
    ) -> List[AlgorithmCombination]:
        tpl_lib = get_template_library()
        base_lib = get_algorithm_library()

        # 如果指定了具体模板，返回该模板的竞争算法模板
        if template_id:
            workflows = tpl_lib.get_workflows(template_id)
            tpl = tpl_lib.get_by_id(template_id)
            if not workflows:
                logger.warning(f"模板 '{template_id}' 无预置算法模板，回退到场景级推荐")
            else:
                return self._workflows_to_combinations(
                    workflows, base_lib, template_id,
                    tpl.get("name", template_id) if tpl else template_id,
                )

        # 未指定模板：返回该场景下所有模板的第一个算法模板作为概览
        templates = tpl_lib.get_by_scenario(scenario_id)
        if not templates:
            logger.warning(f"场景 '{scenario_id}' 无模板数据")
            return []

        combinations: List[AlgorithmCombination] = []
        for tpl in templates[:10]:  # 最多返回 10 个模板的推荐
            workflows = tpl.get("default_workflows", [])
            if not workflows:
                continue
            combos = self._workflows_to_combinations(
                workflows, base_lib, tpl["id"], tpl["name"],
            )
            combinations.extend(combos)
        return combinations

    def _workflows_to_combinations(
        self,
        workflows: List[Dict],
        base_lib,
        template_id: str,
        template_name: str,
    ) -> List[AlgorithmCombination]:
        """将模板的竞争算法模板转换为 AlgorithmCombination 列表"""
        combinations: List[AlgorithmCombination] = []

        for wf in workflows:
            profile_str = wf.get("profile", "balanced")
            try:
                profile = CombinationProfile(profile_str)
            except ValueError:
                profile = CombinationProfile.BALANCED

            layers_data = wf.get("layers", {})
            layers: List[AlgorithmLayer] = []
            covered_layers = 0
            lib_hit_count = 0
            algo_count = 0

            for layer_name in LAYER_ORDER:
                algo_ids = layers_data.get(layer_name, [])
                recommendations: List[AlgorithmRecommendation] = []
                for aid in algo_ids:
                    fn = base_lib.get_by_id(aid)
                    name = fn["name"] if fn else aid
                    # 单算法置信度：库中存在 90，不存在 50
                    conf = 90 if fn else 50
                    if fn:
                        lib_hit_count += 1
                    recommendations.append(AlgorithmRecommendation(
                        algorithm_id=aid,
                        algorithm_name=name,
                        confidence=conf,
                        rationale=f"模板 [{template_name}] {profile_str} 方案推荐",
                    ))
                    algo_count += 1

                if recommendations:
                    layers.append(AlgorithmLayer(
                        layer_name=layer_name,
                        algorithms=recommendations,
                    ))
                    covered_layers += 1

            # --- 多维度置信度计算 ---
            # 1) 算法库命中率 (40%权重): 所有算法都在库中 → 满分
            lib_ratio = lib_hit_count / algo_count if algo_count > 0 else 0
            score_lib = lib_ratio * 100

            # 2) 层级覆盖度 (25%权重): 4层全覆盖 → 满分
            score_coverage = (covered_layers / len(LAYER_ORDER)) * 100

            # 3) 方案 profile 基础分 (20%权重):
            #    high-accuracy 方案算法丰富度高，给更高基础分
            #    balanced 居中，low-latency 精简但高效
            profile_base = {
                CombinationProfile.HIGH_ACCURACY: 90,
                CombinationProfile.BALANCED: 80,
                CombinationProfile.LOW_LATENCY: 75,
            }
            score_profile = profile_base.get(profile, 80)

            # 4) 算法丰富度 (15%权重): 算法数量在合理范围内加分
            #    4-12个算法为最佳范围
            if 4 <= algo_count <= 12:
                score_richness = 90
            elif algo_count < 4:
                score_richness = max(40, algo_count * 20)
            else:
                score_richness = max(60, 100 - (algo_count - 12) * 5)

            overall = (
                score_lib * 0.40
                + score_coverage * 0.25
                + score_profile * 0.20
                + score_richness * 0.15
            )
            overall = min(100, max(0, overall))

            combinations.append(AlgorithmCombination(
                combination_id=f"combo-{uuid.uuid4().hex[:8]}",
                template_id=template_id,
                template_name=template_name,
                profile=profile,
                layers=layers,
                overall_confidence=round(overall, 1),
                description=f"{template_name} - {wf.get('name', profile_str)}",
            ))

        return combinations


class LLMAlgorithmComposer(AlgorithmComposer):
    """基于大模型的算法组合器（未来实现）"""
    def compose(
        self,
        scenario_id: str,
        template_id: Optional[str],
        constraints: Optional[UserConstraints],
    ) -> List[AlgorithmCombination]:
        raise NotImplementedError("LLM 组合器尚未实现")


class AlgorithmComposeSkill(BaseSkill):
    """算法组合推荐 Skill"""

    skill_name = "algorithm-compose"
    required_role = "user"

    def __init__(self, composer: Optional[AlgorithmComposer] = None):
        self._composer = composer or RuleBasedAlgorithmComposer()

    async def validate_input(self, request: BaseModel) -> None:
        if isinstance(request, AlgorithmComposeRequest):
            if not request.scenario_id.strip():
                raise ValueError("scenario_id 不能为空")

    async def execute(
        self, request: BaseModel, context: SkillContext
    ) -> AlgorithmComposeResponse:
        if not isinstance(request, AlgorithmComposeRequest):
            raise ValueError("请求类型错误，期望 AlgorithmComposeRequest")

        start = time.time()
        template_id = getattr(request, "template_id", None)
        constraints = getattr(request, "constraints", None)

        combinations = self._composer.compose(
            request.scenario_id, template_id, constraints,
        )

        return AlgorithmComposeResponse(
            scenario_id=request.scenario_id,
            template_id=template_id,
            combinations=combinations,
            total_combinations=len(combinations),
            processing_time_ms=int((time.time() - start) * 1000),
        )
# @AI_GENERATED: end