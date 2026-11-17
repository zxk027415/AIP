# @AI_GENERATED: Kiro v1.0
"""
业务约束知识库加载服务
从 domain_constraints.json 加载14个场景的约束定义
"""
import json
import os
import logging
from typing import Dict, List, Optional, Any
from utils.cache import constraint_cache

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
CONSTRAINTS_PATH = os.path.join(DATA_DIR, "domain_constraints.json")


class DomainConstraintsLibrary:
    """业务约束知识库"""

    def __init__(self):
        self._data: Optional[Dict[str, Any]] = None

    def _load(self) -> None:
        if self._data is not None:
            return
        path = os.path.normpath(CONSTRAINTS_PATH)
        if not os.path.exists(path):
            logger.warning(f"约束文件不存在: {path}")
            self._data = {}
            return
        with open(path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        # 移除注释字段
        self._data.pop("_comment", None)

    def get_constraints(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """获取指定场景的全部约束（Redis/内存缓存）"""
        # 尝试缓存
        cached = constraint_cache.get(scenario_id)
        if cached is not None:
            return cached
        self._load()
        result = (self._data or {}).get(scenario_id)
        if result is not None:
            constraint_cache.set(scenario_id, result)
        return result

    def get_parameter_constraints(self, scenario_id: str) -> Dict[str, Any]:
        """获取指定场景的参数约束"""
        c = self.get_constraints(scenario_id)
        return c.get("parameter_constraints", {}) if c else {}

    def get_evaluation_metrics(self, scenario_id: str) -> List[str]:
        """获取指定场景的评估指标"""
        c = self.get_constraints(scenario_id)
        return c.get("evaluation_metrics", []) if c else []

    def get_business_rules(self, scenario_id: str) -> List[Dict[str, str]]:
        """获取指定场景的业务规则"""
        c = self.get_constraints(scenario_id)
        return c.get("business_rules", []) if c else []

    def get_all_scenario_ids(self) -> List[str]:
        """获取所有有约束定义的场景ID"""
        self._load()
        return list((self._data or {}).keys())

    def has_scenario(self, scenario_id: str) -> bool:
        self._load()
        return scenario_id in (self._data or {})


_instance: Optional[DomainConstraintsLibrary] = None


def get_domain_constraints_library() -> DomainConstraintsLibrary:
    global _instance
    if _instance is None:
        _instance = DomainConstraintsLibrary()
    return _instance
# @AI_GENERATED: end
