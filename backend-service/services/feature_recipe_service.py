"""
Feature recipes（Phase B）：按 functionId 批量生成 structure_patch.node_switches，
不写死 node_id，适配不同模板副本。
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Callable, Dict, List

from . import autoresearch_paths as arp

_JSON_PATH = arp.feature_recipes_path()
_LEGACY_JSON_PATH = arp.legacy_feature_recipes_path()


@lru_cache(maxsize=1)
def _raw_catalog() -> Dict[str, Any]:
    path = _JSON_PATH if _JSON_PATH.is_file() else _LEGACY_JSON_PATH
    if path.is_file():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"recipes": []}


def clear_feature_recipe_cache() -> None:
    _raw_catalog.cache_clear()


def list_feature_recipe_metas() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in (_raw_catalog().get("recipes") or []):
        if not isinstance(r, dict):
            continue
        rid = str(r.get("recipe_id") or "").strip()
        if not rid:
            continue
        out.append({
            "recipe_id": rid,
            "title": str(r.get("title") or rid),
            "description": str(r.get("description") or ""),
        })
    return out


def known_recipe_ids() -> set:
    return {
        str(r.get("recipe_id") or "").strip()
        for r in (_raw_catalog().get("recipes") or [])
        if isinstance(r, dict) and str(r.get("recipe_id") or "").strip()
    }


def resolve_recipe_structure_patch(
    workflow_id: str,
    recipe_id: str,
    load_workflow_fn: Callable[[str], Any],
) -> Dict[str, Any]:
    rid = str(recipe_id or "").strip()
    if not rid:
        return {}
    recipe = next(
        (
            x for x in (_raw_catalog().get("recipes") or [])
            if isinstance(x, dict) and str(x.get("recipe_id") or "").strip() == rid
        ),
        None,
    )
    if recipe is None:
        return {}
    wf = load_workflow_fn(workflow_id)
    if wf is None:
        return {}
    rows = recipe.get("node_switches_by_function") or []
    if not isinstance(rows, list) or len(rows) == 0:
        return {}

    by_fid: Dict[str, List[str]] = {}
    for n in (wf.dict().get("nodes") or []):
        cfg = ((n.get("data") or {}).get("config") or {})
        fid = str(cfg.get("functionId") or "").strip()
        nid = str(n.get("id") or "").strip()
        if fid and nid:
            by_fid.setdefault(fid, []).append(nid)

    switches: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("functionId") or "").strip()
        en = item.get("enabled")
        if not fid or not isinstance(en, bool):
            continue
        for nid in by_fid.get(fid, []):
            switches.append({"node_id": nid, "enabled": en, "functionId": fid})
    return {"node_switches": switches}
