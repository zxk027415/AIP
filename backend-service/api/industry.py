# @AI_GENERATED: Kiro v1.0
"""
行业场景 API 路由 — 场景列表、模板查询、统计
"""
import json
import os
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional

router = APIRouter(prefix="/api/industry", tags=["industry"])

_scenarios_cache: List[Dict[str, Any]] = []
_templates_cache: List[Dict[str, Any]] = []


def _load_scenarios() -> List[Dict[str, Any]]:
    global _scenarios_cache
    if _scenarios_cache:
        return _scenarios_cache
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'industry_scenarios.json')
    with open(data_path, 'r', encoding='utf-8') as f:
        _scenarios_cache = json.load(f)
    return _scenarios_cache


def _load_templates() -> List[Dict[str, Any]]:
    global _templates_cache
    # @AI_GENERATED: 每次都重新加载，不使用缓存（开发阶段方便调试）
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'industry_templates.json')
    if not os.path.exists(data_path):
        return []
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    _templates_cache = data.get("templates", [])
    return _templates_cache
    # @AI_GENERATED: end


@router.get("/scenarios", summary="获取行业场景列表")
async def get_scenarios() -> List[Dict[str, Any]]:
    """返回14个行业场景元数据"""
    return _load_scenarios()


@router.get("/scenarios/{scenario_id}", summary="获取场景详情")
async def get_scenario(scenario_id: str) -> Dict[str, Any]:
    """返回单个场景详情"""
    scenarios = _load_scenarios()
    for s in scenarios:
        if s["id"] == scenario_id:
            return s
    raise HTTPException(status_code=404, detail=f"场景不存在: {scenario_id}")


@router.get("/templates", summary="获取场景算法方案列表")
async def get_templates(
    scenario_id: Optional[str] = Query(None, description="按场景ID过滤"),
    category: Optional[str] = Query(None, description="按展示分类过滤"),
) -> List[Dict[str, Any]]:
    """返回场景算法方案（L2），可按场景或分类过滤"""
    templates = _load_templates()
    if scenario_id:
        templates = [t for t in templates if t.get("scenario_id") == scenario_id]
    if category:
        templates = [t for t in templates if t.get("display_category") == category]
    return templates


@router.get("/templates/{template_id}", summary="获取模板详情（含竞争算法模板）")
async def get_template(template_id: str) -> Dict[str, Any]:
    """返回单个模板详情，包含其下所有竞争算法模板（L3）"""
    templates = _load_templates()
    for t in templates:
        if t["id"] == template_id:
            return t
    raise HTTPException(status_code=404, detail=f"模板不存在: {template_id}")


@router.get("/stats", summary="获取行业场景统计")
async def get_industry_stats() -> Dict[str, Any]:
    """返回行业场景统计摘要"""
    scenarios = _load_scenarios()
    templates = _load_templates()
    industries = set()
    total_scenario_functions = 0
    for s in scenarios:
        for tag in s.get("industry_tags", []):
            industries.add(tag)
        total_scenario_functions += s.get("function_count", 0)
    
    # 动态加载基础模块统计
    functions_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'functions.json')
    categories_count = 19
    functions_count = 780
    if os.path.exists(functions_path):
        with open(functions_path, 'r', encoding='utf-8') as f:
            func_data = json.load(f)
            categories_count = len(func_data.get('categories', []))
            functions_count = len(func_data.get('functions', []))
    
    # 统计算法模板数（工作流模板6个 + Skills数量）
    skills_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'skills', 'packaged_skills.json')
    skills_count = 0
    if os.path.exists(skills_path):
        with open(skills_path, 'r', encoding='utf-8') as f:
            skills_data = json.load(f)
            skills_count = len(skills_data)
    workflow_templates_count = 6  # OfficialTemplateLibraryPage中的MOCK_TEMPLATES
    algorithm_templates = workflow_templates_count + skills_count
    
    return {
        "total_scenarios": len(scenarios),
        "total_industries": len(industries),
        "total_industry_templates": len(templates),
        "total_functions": total_scenario_functions,
        "basic_modules": functions_count,
        "industry_templates": len(templates),
        "algorithm_templates": algorithm_templates,
        "categories": categories_count,
        "layers": 7,
    }
# @AI_GENERATED: end
