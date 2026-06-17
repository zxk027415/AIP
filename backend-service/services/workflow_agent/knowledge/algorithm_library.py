# @AI_GENERATED: Kiro v1.0
"""
算法库数据加载服务
- L4 基础算法模块：从 functions.json 加载
- L2 场景算法方案：从 industry_templates.json 加载（含 L3 竞争算法模板）
"""
import json
import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
FUNCTIONS_PATH = os.path.join(DATA_DIR, "functions.json")
TEMPLATES_PATH = os.path.join(DATA_DIR, "industry_templates.json")

# L4 基础模块分类→层级映射
CATEGORY_TO_LAYER: Dict[str, str] = {
    "data_source": "数据接入层",
    "data_preprocessing": "数据处理层",
    "feature_engineering": "数据处理层",
    "algorithm_model": "算法模型层",
    "model_training": "算法模型层",
    "evaluation_metrics": "评估输出层",
    "visualization": "评估输出层",
    "statistical_analysis": "数据处理层",
    "signal_processing": "数据处理层",
    "matrix_operations": "数据处理层",
    "optimization": "算法模型层",
    "deep_learning": "算法模型层",
    "classification": "算法模型层",
    "clustering": "算法模型层",
    "regression": "算法模型层",
    "anomaly_detection": "算法模型层",
    "time_series": "算法模型层",
    "nlp": "算法模型层",
    "image_processing": "数据处理层",
    "reinforcement_learning": "算法模型层",
}


class AlgorithmLibrary:
    """算法库加载与查询服务（L4 基础模块）"""

    def __init__(self):
        self._functions: Optional[List[Dict]] = None
        self._categories: Optional[List[Dict]] = None
        self._by_id: Optional[Dict[str, Dict]] = None
        self._by_category: Optional[Dict[str, List[Dict]]] = None
        self._by_layer: Optional[Dict[str, List[Dict]]] = None

    def _load(self) -> None:
        if self._functions is not None:
            return
        path = os.path.normpath(FUNCTIONS_PATH)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._categories = data.get("categories", [])
        self._functions = data.get("functions", [])
        self._by_id = {fn["id"]: fn for fn in self._functions}
        self._by_category = {}
        self._by_layer = {}
        for fn in self._functions:
            cat = fn.get("category", "")
            self._by_category.setdefault(cat, []).append(fn)
            layer = CATEGORY_TO_LAYER.get(cat, "算法模型层")
            self._by_layer.setdefault(layer, []).append(fn)

    def get_all(self) -> List[Dict]:
        self._load()
        return self._functions or []

    def get_by_id(self, algorithm_id: str) -> Optional[Dict]:
        self._load()
        return (self._by_id or {}).get(algorithm_id)

    def get_by_category(self, category: str) -> List[Dict]:
        self._load()
        return (self._by_category or {}).get(category, [])

    def get_by_layer(self, layer_name: str) -> List[Dict]:
        self._load()
        return (self._by_layer or {}).get(layer_name, [])

    def get_categories(self) -> List[Dict]:
        self._load()
        return self._categories or []

    def get_algorithm_ids(self) -> set:
        self._load()
        return set((self._by_id or {}).keys())

    def total_count(self) -> int:
        self._load()
        return len(self._functions or [])


class IndustryTemplateLibrary:
    """场景算法方案库（L2 方案 + L3 竞争算法模板）"""

    def __init__(self):
        self._templates: Optional[List[Dict]] = None
        self._by_id: Optional[Dict[str, Dict]] = None
        self._by_scenario: Optional[Dict[str, List[Dict]]] = None
        self._by_category: Optional[Dict[str, List[Dict]]] = None

    def _load(self) -> None:
        if self._templates is not None:
            return
        path = os.path.normpath(TEMPLATES_PATH)
        if not os.path.exists(path):
            logger.warning(f"模板文件不存在: {path}")
            self._templates = []
            self._by_id = {}
            self._by_scenario = {}
            self._by_category = {}
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._templates = data.get("templates", [])
        self._by_id = {t["id"]: t for t in self._templates}
        self._by_scenario = {}
        self._by_category = {}
        for t in self._templates:
            sid = t.get("scenario_id", "")
            self._by_scenario.setdefault(sid, []).append(t)
            cat = t.get("display_category", "")
            self._by_category.setdefault(cat, []).append(t)

    def get_all(self) -> List[Dict]:
        self._load()
        return self._templates or []

    def get_by_id(self, template_id: str) -> Optional[Dict]:
        self._load()
        return (self._by_id or {}).get(template_id)

    def get_by_scenario(self, scenario_id: str) -> List[Dict]:
        """获取某个行业场景下的所有算法方案"""
        self._load()
        return (self._by_scenario or {}).get(scenario_id, [])

    def get_by_category(self, category: str) -> List[Dict]:
        """获取某个展示分类下的所有算法方案"""
        self._load()
        return (self._by_category or {}).get(category, [])

    def get_workflows(self, template_id: str) -> List[Dict]:
        """获取某个模板的所有竞争算法模板（L3）"""
        tpl = self.get_by_id(template_id)
        if not tpl:
            return []
        return tpl.get("default_workflows", [])

    def get_scenario_ids(self) -> List[str]:
        """获取所有有模板的场景ID"""
        self._load()
        return list((self._by_scenario or {}).keys())

    def get_display_categories(self) -> List[str]:
        """获取所有展示分类名称"""
        self._load()
        return list((self._by_category or {}).keys())

    def total_count(self) -> int:
        self._load()
        return len(self._templates or [])


# 模块级单例
_library_instance: Optional[AlgorithmLibrary] = None
_template_library_instance: Optional[IndustryTemplateLibrary] = None


def get_algorithm_library() -> AlgorithmLibrary:
    global _library_instance
    if _library_instance is None:
        _library_instance = AlgorithmLibrary()
    return _library_instance


def get_template_library() -> IndustryTemplateLibrary:
    global _template_library_instance
    if _template_library_instance is None:
        _template_library_instance = IndustryTemplateLibrary()
    return _template_library_instance
# @AI_GENERATED: end