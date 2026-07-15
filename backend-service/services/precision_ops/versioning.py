# @AI_GENERATED
"""精度运营的版本身份工具，统一 workflow_id 与 version_tag 的持久化键。"""
from __future__ import annotations

from typing import Optional, Tuple


def make_version_key(workflow_id: str, version_tag: Optional[str] = None) -> str:
    """返回兼容旧数据的版本级指标键；未提供标签时保持旧 workflow_id 键。"""
    normalized_tag = (version_tag or "").strip()
    return f"{workflow_id}@{normalized_tag}" if normalized_tag else workflow_id


def split_version_key(version_key: str) -> Tuple[str, Optional[str]]:
    """拆分版本级指标键；旧格式 workflow_id 返回空版本标签。"""
    if "@" not in version_key:
        return version_key, None
    workflow_id, version_tag = version_key.rsplit("@", 1)
    return workflow_id, version_tag or None
# @AI_GENERATED: end
