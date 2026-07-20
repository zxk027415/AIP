"""
槽位化 structure_profile：从 workflow_slot_profiles.json 加载，
并把 candidate_rule 解析为运行时可用的 effective_candidates。
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, List, Optional

from . import autoresearch_paths as arp

_JSON_PATH = arp.workflow_slot_profiles_path()
_LEGACY_JSON_PATH = arp.legacy_workflow_slot_profiles_path()

_EMBEDDED_FALLBACK: Dict[str, Any] = {
    "default_profile_id": "load_forecast_linear_pipeline_v1",
    "profiles": [
        {
            "profile_id": "load_forecast_linear_pipeline_v1",
            "title": "线性负荷预测流水线（回退）",
            "description": "未读取到 workflow_slot_profiles.json 时的最小档案；不含槽位明细。",
            "preflight_required": True,
            "notes": ["请补齐 backend-service/data/workflow_slot_profiles.json"],
            "slots": [],
        }
    ],
}


@lru_cache(maxsize=1)
def _raw_catalog() -> Dict[str, Any]:
    path = _JSON_PATH if _JSON_PATH.is_file() else _LEGACY_JSON_PATH
    if path.is_file():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(_EMBEDDED_FALLBACK)


def clear_slot_catalog_cache() -> None:
    """测试或热加载时可调用。"""
    _raw_catalog.cache_clear()


def list_profile_metas() -> List[Dict[str, Any]]:
    """返回 profiles 元数据（含静态 slots，不含 effective_candidates）。"""
    data = _raw_catalog()
    return list(data.get("profiles") or [])


def default_profile_id() -> Optional[str]:
    data = _raw_catalog()
    return data.get("default_profile_id")


def _ids_ts_forecast_registered(has_operator_fn) -> List[str]:
    from services.function_library_service import get_function_library_service

    svc = get_function_library_service()
    out: List[str] = []
    for fn in svc.get_all_functions():
        cat = str(getattr(fn, "category", "") or "")
        fid = str(getattr(fn, "id", "") or "")
        if cat != "ts_forecast":
            continue
        if not fid.endswith("_forecast"):
            continue
        if has_operator_fn(fid):
            out.append(fid)
    return sorted(out)


def _function_display_name(function_id: str) -> str:
    from services.function_library_service import get_function_library_service

    fn = get_function_library_service().get_function(function_id)
    if fn is None:
        return function_id
    return str(getattr(fn, "name", "") or function_id)


def resolve_structure_profile_detail(profile_id: str, has_operator_fn) -> Optional[Dict[str, Any]]:
    """
    解析单个 profile：为每个 slot 填充 effective_candidates
    （function_id, name, registered）。
    """
    pid = str(profile_id or "").strip()
    if not pid:
        return None

    profiles = list_profile_metas()
    profile = next((p for p in profiles if str(p.get("profile_id")) == pid), None)
    if profile is None:
        return None

    resolved_slots: List[Dict[str, Any]] = []
    rule_cache: Dict[str, List[str]] = {}

    for slot in profile.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        sid = str(slot.get("slot_id") or "")
        rule = str(slot.get("candidate_rule") or "").strip()
        explicit = slot.get("candidate_ids")
        if not isinstance(explicit, list):
            explicit = []

        candidate_ids: List[str] = []
        if rule == "ts_forecast_registered":
            if rule not in rule_cache:
                rule_cache[rule] = _ids_ts_forecast_registered(has_operator_fn)
            candidate_ids = list(rule_cache[rule])
            # explicit 可作为额外约束（交集）；空列表表示全量 rule 结果
            if explicit:
                allow = {str(x).strip() for x in explicit if str(x).strip()}
                candidate_ids = [x for x in candidate_ids if x in allow]
        else:
            candidate_ids = [str(x).strip() for x in explicit if str(x).strip()]

        effective: List[Dict[str, Any]] = []
        for fid in candidate_ids:
            registered = bool(has_operator_fn(fid))
            effective.append({
                "function_id": fid,
                "name": _function_display_name(fid),
                "registered": registered,
            })

        slot_out = dict(slot)
        slot_out["effective_candidates"] = [e for e in effective if e["registered"]]
        slot_out["catalog_candidates"] = effective
        resolved_slots.append(slot_out)

    out = dict(profile)
    out["slots"] = resolved_slots
    return out


def known_profile_ids() -> List[str]:
    return [str(p.get("profile_id")) for p in list_profile_metas() if p.get("profile_id")]
