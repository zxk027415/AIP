# @AI_GENERATED: Kiro v1.0
"""
最佳实践知识库加载服务
从 best_practices.json 加载系统预置最佳实践
"""
import json
import os
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
PRACTICES_PATH = os.path.join(DATA_DIR, "best_practices.json")


class BestPracticesLibrary:
    """最佳实践知识库"""

    def __init__(self):
        self._practices: Optional[List[Dict[str, Any]]] = None
        self._by_scenario: Optional[Dict[str, List[Dict]]] = None

    def _load(self) -> None:
        if self._practices is not None:
            return
        path = os.path.normpath(PRACTICES_PATH)
        if not os.path.exists(path):
            logger.warning(f"最佳实践文件不存在: {path}")
            self._practices = []
            self._by_scenario = {}
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._practices = data.get("practices", [])
        self._by_scenario = {}
        for p in self._practices:
            sid = p.get("scenario_id", "")
            self._by_scenario.setdefault(sid, []).append(p)

    def get_by_scenario(self, scenario_id: str) -> List[Dict[str, Any]]:
        self._load()
        return (self._by_scenario or {}).get(scenario_id, [])

    def get_all(self) -> List[Dict[str, Any]]:
        self._load()
        return self._practices or []

    def get_by_id(self, practice_id: str) -> Optional[Dict[str, Any]]:
        self._load()
        for p in (self._practices or []):
            if p.get("id") == practice_id:
                return p
        return None


_instance: Optional[BestPracticesLibrary] = None


def get_best_practices_library() -> BestPracticesLibrary:
    global _instance
    if _instance is None:
        _instance = BestPracticesLibrary()
    return _instance
# @AI_GENERATED: end
