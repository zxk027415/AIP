# @AI_GENERATED
"""AutoResearch experiment_patch：从候选归一化，并应用到工作流 JSON（日滚预测前）。

与 api.workflows_enhanced 中 AR 比对链路对齐：
  structure → global_config / node_param_patches
避免日滚只靠 version_tag、丢掉 AR 实验配置。
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def normalize_experiment_patch(source: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """从候选池或复验项字段归一化为 ModelVersion.experiment_patch。"""
    if not isinstance(source, dict):
        return {}
    # 候选池命名 / 复验队列命名 / 旧名
    override = (
        source.get("challenger_override")
        or source.get("challenger_config_override")
        or source.get("override")
        or {}
    )
    parameter = (
        source.get("effective_parameter_patch")
        or source.get("challenger_global_config_patch")
        or source.get("global_config_patch")
        or {}
    )
    structure = (
        source.get("effective_structure_patch")
        or source.get("challenger_structure_override")
        or source.get("structure_patch")
        or {}
    )
    node_patches = (
        source.get("node_param_patches")
        or source.get("challenger_node_param_patches")
        or []
    )
    if not isinstance(override, dict):
        override = {}
    if not isinstance(parameter, dict):
        parameter = {}
    if not isinstance(structure, dict):
        structure = {}
    if not isinstance(node_patches, list):
        node_patches = []
    patch = {
        "challenger_override": dict(override),
        "effective_parameter_patch": dict(parameter),
        "effective_structure_patch": dict(structure),
        "node_param_patches": list(node_patches),
    }
    # 去掉全空
    if not any(
        [
            patch["challenger_override"],
            patch["effective_parameter_patch"],
            patch["effective_structure_patch"],
            patch["node_param_patches"],
        ]
    ):
        return {}
    return patch


def experiment_patch_fingerprint(patch: Optional[Dict[str, Any]]) -> str:
    """短指纹，便于日志与 cycle 审计。"""
    import hashlib
    import json

    if not patch:
        return "nopatch"
    raw = json.dumps(patch, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def apply_experiment_patch_to_workflow_dict(
    wf_data: Dict[str, Any],
    experiment_patch: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """把 AR patch 打进工作流 dict（深拷贝后返回）。

    优先复用 workflows_enhanced 的白名单 apply；失败则做保守 dict 级合并。
    """
    if not experiment_patch:
        return wf_data
    patch = normalize_experiment_patch(experiment_patch)
    if not patch:
        return wf_data

    # 1) 优先走 AR 同源 apply（保真）
    try:
        from api.workflows_enhanced import (
            EnhancedWorkflow,
            _apply_runtime_parameter_layers_to_workflow,
            _apply_structure_patch_to_workflow,
        )

        wf_obj = EnhancedWorkflow(**copy.deepcopy(wf_data))
        structure = patch.get("effective_structure_patch") or {}
        if structure:
            wf_obj = _apply_structure_patch_to_workflow(wf_obj, structure)
        gcp = dict(patch.get("effective_parameter_patch") or {})
        # challenger_override 里常见 train_days / ensemble_mode 并入 global_config
        override = patch.get("challenger_override") or {}
        if isinstance(override, dict):
            if "train_days" in override and "backtest_train_days" not in gcp:
                try:
                    gcp["backtest_train_days"] = int(override["train_days"])
                except (TypeError, ValueError):
                    pass
            for key in ("ensemble_mode", "backtest_use_bayesian_tuning", "backtest_bo_n_iter"):
                if key in override and key not in gcp:
                    gcp[key] = override[key]
        npp = patch.get("node_param_patches") or []
        if gcp or npp:
            wf_obj = _apply_runtime_parameter_layers_to_workflow(wf_obj, gcp, npp)
        out = wf_obj.dict() if hasattr(wf_obj, "dict") else wf_obj.model_dump()
        logger.info(
            "apply_experiment_patch: AR-apply ok fingerprint=%s",
            experiment_patch_fingerprint(patch),
        )
        return out
    except Exception as exc:
        logger.warning(
            "apply_experiment_patch: AR-apply 失败，回退 dict 合并: %s", exc
        )

    # 2) 保守回退：直接改 dict
    out = copy.deepcopy(wf_data)
    meta = dict(out.get("metadata") or {})
    gc = dict(meta.get("global_config") or {})
    gcp = dict(patch.get("effective_parameter_patch") or {})
    override = patch.get("challenger_override") or {}
    if isinstance(override, dict) and "train_days" in override:
        try:
            gcp.setdefault("backtest_train_days", int(override["train_days"]))
        except (TypeError, ValueError):
            pass
    gc.update({k: v for k, v in gcp.items() if k})
    meta["global_config"] = gc
    out["metadata"] = meta

    nodes = list(out.get("nodes") or [])
    node_map = {str(n.get("id")): n for n in nodes if isinstance(n, dict)}
    structure = patch.get("effective_structure_patch") or {}
    for item in structure.get("node_switches") or []:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("node_id") or "")
        enabled = item.get("enabled")
        node = node_map.get(nid)
        if node is None or not isinstance(enabled, bool):
            continue
        data = dict(node.get("data") or {})
        cfg = dict(data.get("config") or {})
        cfg["enabled"] = enabled
        data["config"] = cfg
        node["data"] = data
    for item in patch.get("node_param_patches") or []:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("node_id") or "")
        pp = item.get("param_patch") if isinstance(item.get("param_patch"), dict) else {}
        node = node_map.get(nid)
        if node is None or not pp:
            continue
        data = dict(node.get("data") or {})
        cfg = dict(data.get("config") or {})
        cfg.update(pp)
        data["config"] = cfg
        node["data"] = data
    out["nodes"] = list(node_map.values()) or nodes
    return out


def _iter_candidate_pool_rows_for_patch() -> List[Dict[str, Any]]:
    """读取带完整 AR patch 字段的候选行。

    注意：`_load_candidate_pool_list()` 在 DB 优先读开启时会丢掉
    challenger_override / parameter / structure / node_param_patches。
    部署回填必须优先读 JSON 候选池文件，必要时再从 DB evidence 里解包。
    """
    rows: List[Dict[str, Any]] = []
    # 1) JSON 全量（保真）
    try:
        import json
        from pathlib import Path

        import services.autoresearch_paths as arp

        paths = [
            Path(arp.as_str(arp.candidate_pool_path())),
            Path(arp.as_str(arp.legacy_candidate_pool_path())),
        ]
        for p in paths:
            if not p.is_file():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            cand = data.get("candidates") if isinstance(data, dict) else None
            if isinstance(cand, list):
                rows.extend([c for c in cand if isinstance(c, dict)])
                break
    except Exception as exc:
        logger.warning("读取 JSON 候选池失败: %s", exc)

    # 2) 若 JSON 空，再尝试 list API，并展开 evidence 内嵌 patch
    if not rows:
        try:
            from api.workflows_enhanced import _load_candidate_pool_list

            for row in _load_candidate_pool_list() or []:
                if not isinstance(row, dict):
                    continue
                merged = dict(row)
                evidence = merged.get("evidence") if isinstance(merged.get("evidence"), dict) else {}
                payload = evidence.get("_ar_experiment_fields") if isinstance(evidence, dict) else None
                if isinstance(payload, dict):
                    for key in (
                        "challenger_override",
                        "effective_parameter_patch",
                        "effective_structure_patch",
                        "node_param_patches",
                    ):
                        if key in payload and key not in merged:
                            merged[key] = payload[key]
                rows.append(merged)
        except Exception as exc:
            logger.warning("从 list API 回填候选失败: %s", exc)
    return rows


def load_experiment_patch_from_candidate_id(candidate_id: Optional[str]) -> Dict[str, Any]:
    """按 candidate_id 从候选池回填 patch（入池时未带 body 时的兜底）。"""
    if not candidate_id:
        return {}
    try:
        target = str(candidate_id).strip()
        for row in _iter_candidate_pool_rows_for_patch():
            rid = str(row.get("id") or row.get("candidate_id") or "").strip()
            if rid == target:
                return normalize_experiment_patch(row)
    except Exception as exc:
        logger.warning("load_experiment_patch_from_candidate_id 失败: %s", exc)
    return {}
# @AI_GENERATED: end
