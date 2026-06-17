"""
autoresearch_registry_service.py
搜索空间注册表加载与解析服务。

职责：
  - 从 data/autoresearch_search_registries/ 目录加载注册表 JSON
  - 解析四层结构（training/feature/model/data）
  - 根据 run_state 的饱和状态决定当前激活哪些层
  - 提供按层获取参数定义的接口

注册表 JSON 格式见：data/autoresearch_search_registries/load_forecast_v1.json
"""

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from . import autoresearch_paths as arp

# 注册表文件目录：新路径写入 data/autoresearch/registries，旧路径只读兜底。
_REGISTRY_DIR = arp.registries_dir()
_LEGACY_REGISTRY_DIR = arp.legacy_registries_dir()

# 空注册表：找不到 registry_id 时的降级返回值
_EMPTY_REGISTRY: Dict[str, Any] = {
    "registry_id": "__empty__",
    "description": "空注册表（降级）",
    "layers": {},
}


@lru_cache(maxsize=32)
def _load_registry_cached(registry_id: str) -> Dict[str, Any]:
    """
    从磁盘加载注册表 JSON，带 LRU 缓存。
    找不到文件时返回空注册表，不抛异常（保证向后兼容）。
    """
    path = _REGISTRY_DIR / f"{registry_id}.json"
    if not path.exists():
        legacy_path = _LEGACY_REGISTRY_DIR / f"{registry_id}.json"
        if legacy_path.exists():
            path = legacy_path
    if not path.exists():
        return dict(_EMPTY_REGISTRY)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(_EMPTY_REGISTRY)
        # v1/v2 用 "layers"，v3 用 "actions"，两者都合法
        if "layers" not in data and "actions" not in data:
            return dict(_EMPTY_REGISTRY)
        return data
    except Exception:
        return dict(_EMPTY_REGISTRY)


def clear_registry_cache() -> None:
    """热加载时清除缓存（测试或手动刷新时调用）。"""
    _load_registry_cached.cache_clear()


def load_registry(registry_id: str) -> Dict[str, Any]:
    """
    加载指定 registry_id 的注册表。

    Args:
        registry_id（注册表 ID）: 对应 data/autoresearch_search_registries/{registry_id}.json

    Returns:
        注册表 dict；找不到时返回空注册表（不报错）
    """
    if not registry_id or not str(registry_id).strip():
        return dict(_EMPTY_REGISTRY)
    return _load_registry_cached(str(registry_id).strip())


def list_registry_ids() -> List[str]:
    """列出所有可用的注册表 ID（文件名去掉 .json 后缀）。"""
    ids = set()
    for directory in (_REGISTRY_DIR, _LEGACY_REGISTRY_DIR):
        if not directory.exists():
            continue
        ids.update(p.stem for p in directory.glob("*.json") if p.is_file())
    return sorted(ids)


def get_layer_params(registry: Dict[str, Any], layer_name: str) -> Dict[str, Any]:
    """
    获取指定层的参数定义 dict。

    Args:
        registry（注册表对象）: load_registry() 的返回值
        layer_name（层名）: "training" / "feature" / "model" / "data"

    Returns:
        该层的 params dict；层不存在时返回空 dict
    """
    layers = registry.get("layers") or {}
    layer = layers.get(layer_name) or {}
    return dict(layer.get("params") or {})


def get_layers_sorted(registry: Dict[str, Any]) -> List[tuple]:
    """
    按 activation_order 升序返回 (layer_name, layer_spec) 列表。

    Returns:
        [(layer_name, layer_spec), ...] 按 activation_order 排序
    """
    layers = registry.get("layers") or {}
    return sorted(
        layers.items(),
        key=lambda x: int((x[1] or {}).get("activation_order") or 999),
    )


def get_active_layers(
    registry: Dict[str, Any],
    run_state: Dict[str, Any],
    k: int = 4,
    threshold: float = 0.05,
) -> List[str]:
    """
    任务 10.2：根据 run_state 的饱和状态，决定当前应激活哪些搜索层。

    规则：按 activation_order 逐层检查，当前层未饱和则停止激活后续层。
    第一层（training）始终激活。

    Args:
        registry（注册表对象）: load_registry() 的返回值
        run_state（运行状态）: _auto_research_store[run_id]
        k（饱和判定轮数）: 连续 k 轮改善 < threshold 才算饱和
        threshold（改善阈值）: mape_improvement 阈值

    Returns:
        当前应激活的层名列表，如 ["training", "feature"]
    """
    sorted_layers = get_layers_sorted(registry)
    if not sorted_layers:
        return []

    active: List[str] = []
    for layer_name, _layer_spec in sorted_layers:
        active.append(layer_name)
        if not _is_layer_saturated(run_state, layer_name, k=k, threshold=threshold):
            break  # 当前层还没饱和，不激活后续层
    return active


# C1 FIX: per-layer iteration caps to prevent training layer never saturating
# Training layer params (e.g. train_days) can always produce >5% MAPE change,
# so mape_improvement threshold alone never triggers saturation.
_LAYER_MAX_ITERATIONS = {
    "training": 12,    # force move to feature after 12 training-layer iterations
    "feature": 16,
    "model": 20,
    "data": 20,
}

def _is_layer_saturated(
    run_state: Dict[str, Any],
    layer_name: str,
    k: int = 4,
    threshold: float = 0.05,
) -> bool:
    """
    任务 10.1：判断指定层是否已饱和。

    逻辑：
    1. 从 iterations 中找出"本轮采样了该层参数"的迭代（通过 sampled_layers 字段）
    2. 取最近 k 轮，若全部 mape_improvement < threshold 则判定饱和
    3. 采样轮数 < k 时返回 False（数据不足）
    4. C1 FIX: 超过层最大迭代数时强制饱和

    Args:
        run_state（运行状态）: _auto_research_store[run_id]
        layer_name（层名）: 要检查的层
        k（饱和判定轮数）: 默认 4
        threshold（改善阈值）: 默认 0.05

    Returns:
        True 表示该层已饱和
    """
    iterations = run_state.get("iterations") or []
    # 筛选：成功 + 采样了该层
    layer_iters = [
        it for it in iterations
        if isinstance(it, dict)
        and str(it.get("status")) == "success"
        and layer_name in (it.get("sampled_layers") or [])
    ]
    # C1 FIX: force saturation after max iterations for this layer
    _max_iters = _LAYER_MAX_ITERATIONS.get(layer_name, 99)
    if len(layer_iters) >= _max_iters:
        return True

    recent = layer_iters[-k:]
    if len(recent) < k:
        return False
    for it in recent:
        ev = it.get("evaluation") or {}
        mi = ev.get("mape_improvement")
        if mi is None:
            return False
        try:
            if float(mi) >= threshold:
                return False
        except (TypeError, ValueError):
            return False
    return True


def get_param_patch_target(param_spec: Dict[str, Any]) -> str:
    """
    获取参数的 patch 目标类型。

    Returns:
        "global_config" / "node_param" / "structure_switch" / "model_focus"
    """
    return str(param_spec.get("patch_target") or "global_config")
