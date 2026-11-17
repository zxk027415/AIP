# @AI_GENERATED
"""三条诊断路径的平台级并列总览。

用户拍板：精度运营 / 模型部署未选路径时，默认三条路径各一行
（路径名 + 当前模型/champion + 最近精度 + 数据集），再点进去下钻。
本模块只组装已有事实来源，不另立阈值或精度口径。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.slot_datasets.feed_semantics import SUPPORTED_SLOTS, describe_slot

SLOT_LABELS: Dict[str, str] = {
    "pv_day": "天路径",
    "pv_point": "点路径",
    "pv_tsc": "TSC 路径",
}


def _rel_ref(value: Any) -> Optional[str]:
    text = str(value or "").replace("\\", "/").strip()
    return text or None


def _model_summary(slot: str) -> Dict[str, Any]:
    from services.slot_governance.registry import get_registry_store

    registry = get_registry_store().get(slot)
    champion = registry.get("champion") if isinstance(registry.get("champion"), dict) else None
    challenger = registry.get("challenger") if isinstance(registry.get("challenger"), dict) else None
    rolling = (
        registry.get("rolling_detect_model")
        if isinstance(registry.get("rolling_detect_model"), dict)
        else None
    )

    champion_ref = None
    if champion:
        champion_ref = _rel_ref(
            champion.get("champion_model_ref") or champion.get("champion_model_artifact_ref")
        )
    challenger_ref = None
    if challenger:
        challenger_ref = _rel_ref(
            challenger.get("challenger_model_ref")
            or challenger.get("challenger_model_candidate_id")
            or challenger.get("challenger_model_artifact_ref")
        )
    current = champion_ref
    if not current and rolling:
        current = _rel_ref(rolling.get("model_candidate_id") or rolling.get("model_artifact_ref"))
    if not current:
        current = challenger_ref
    return {
        "champion": champion_ref,
        "challenger": challenger_ref,
        "current_model": current,
    }


def _accuracy_summary(slot: str) -> Dict[str, Any]:
    """最近精度：有计入样本才给数字；缺真值返回 null，不把「没评」写成 0.0。

    同时回出**产出这份精度的模型**：`model_id`（最近一天用的模型）与 `model_ids`
    （累计区间内出现过的全部模型，去重保序）。累计精度是按样本加权跨天汇总的，
    若区间里换过模型就**不能**把这个数字归给单一模型 —— 用 `multi_model` 如实标出，
    由前端决定是否显示归属，而不是在这里悄悄取一个。
    """
    from services.slot_datasets.loop_demo import load_daily_accuracy
    from services.slot_datasets.mock_gold_review import load_mock_accuracy

    daily = load_daily_accuracy(slot)
    cumulative = daily.get("cumulative") if isinstance(daily.get("cumulative"), dict) else {}
    counted = cumulative.get("counted_units")
    acc = cumulative.get("classifier_accuracy")
    source = "loop_demo/daily_accuracy.json"

    by_day = [row for row in (daily.get("by_day") or []) if isinstance(row, dict)]
    model_ids: List[str] = []
    for row in by_day:
        mid = str(row.get("model_id") or "").strip()
        if mid and mid not in model_ids:
            model_ids.append(mid)
    # “最近业务日精度”取最近一个**真正计入真值评估**的日，而不是最近喂入日。
    # 历史数据里存在最新日 counted_units=0、classifier_accuracy=0.0 的假零；应跳过它，
    # 回看上一条可评日。若都不可评则诚实置空。
    latest = next(
        (
            row
            for row in reversed(by_day)
            if int(row.get("counted_units") or 0) > 0
            and row.get("classifier_accuracy") is not None
        ),
        {},
    )
    model_id = str(latest.get("model_id") or "").strip() or None
    latest_day = str(latest.get("day") or "").strip() or None
    latest_counted_units = int(latest.get("counted_units") or 0)
    latest_accuracy = latest.get("classifier_accuracy") if latest else None

    if acc is None or int(counted or 0) <= 0:
        acc = None
        counted = int(counted or 0)
        mock = load_mock_accuracy(slot)
        by_model = mock.get("by_model") if isinstance(mock.get("by_model"), dict) else {}
        for model_key, row in by_model.items():
            if not isinstance(row, dict):
                continue
            row_counted = int(row.get("counted_units") or 0)
            row_acc = row.get("classifier_accuracy")
            if row_acc is None or row_counted <= 0:
                continue
            acc = row_acc
            counted = row_counted
            source = "mock_accuracy.json"
            # 兜底源是按模型分组的，模型归属就取这一行自己的候选 ID。
            fallback_mid = str(row.get("model_candidate_id") or model_key or "").strip()
            if fallback_mid:
                model_id = fallback_mid
                model_ids = [fallback_mid]
            latest_day = None
            latest_accuracy = None
            latest_counted_units = None
            break
        else:
            source = None
            counted = counted if counted else None
    return {
        "classifier_accuracy": acc,
        "counted_units": counted,
        "source": source,
        "model_id": model_id,
        "model_ids": model_ids,
        "multi_model": len(model_ids) > 1,
        "latest_day": latest_day,
        "latest_accuracy": latest_accuracy,
        "latest_counted_units": latest_counted_units,
    }


def _dataset_current(slot: str) -> Dict[str, Any]:
    from services.slot_datasets import feed_sources as feed_sources_service

    current = feed_sources_service.describe_current(slot, with_facts=True)
    source = current.get("source") if isinstance(current.get("source"), dict) else None
    return {
        "selected": bool(current.get("selected")),
        "dataset_ref": (source or {}).get("dataset_ref"),
        "row_count": (source or {}).get("row_count"),
        "has_gold": (source or {}).get("has_gold"),
        "fingerprint": (source or {}).get("fingerprint"),
        "note": current.get("note"),
    }


def _available_datasets(slot: str) -> List[Dict[str, Any]]:
    """该路径下可挂载 / 可适用的数据集（目录已发布优先，累计快照作未发布候选）。"""
    from services.pv_projects import catalog as catalog_service

    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for entry in catalog_service.list_catalog():
        if not isinstance(entry, dict):
            continue
        origin = str(entry.get("origin_slot") or "")
        applicable = (entry.get("applicable_paths") or {}).get(slot) or {}
        is_applicable = bool(isinstance(applicable, dict) and applicable.get("applicable"))
        # 已发布条目只服从 applicable_paths；origin_slot 说明“从哪来”，不等于“能去哪”。
        if not is_applicable:
            continue
        ref = str(entry.get("dataset_ref") or "")
        if not ref or ref in seen:
            continue
        seen.add(ref)
        items.append(
            {
                "entry_id": entry.get("entry_id"),
                "dataset_ref": ref,
                "display_name": entry.get("display_name") or ref,
                "origin_slot": origin or None,
                "applicable": True,
                "mountable": True,
            }
        )
    for src in catalog_service.discover_path_cumulative_datasets():
        if str(src.get("origin_slot") or "") != slot:
            continue
        ref = str(src.get("dataset_ref") or "")
        if not ref or ref in seen:
            continue
        seen.add(ref)
        items.append(
            {
                "entry_id": None,
                "dataset_ref": ref,
                "display_name": src.get("display_name") or ref,
                "origin_slot": slot,
                "applicable": True,
                "mountable": False,
            }
        )
    return items


def _accuracy_attribution(slot: str, accuracy: Dict[str, Any]) -> Dict[str, Any]:
    """这份按日精度是哪个模型、哪个项目产出的。

    `model_id` 为 `loop_demo_rule` 时是内置规则回放，**没有模型**，归属为 None
    —— 这是正常状态，不是解析失败。
    """
    from services.slot_governance.project_attribution import resolve_model_project

    model_id = accuracy.get("model_id")
    return {
        "model_id": model_id,
        "model_count": len(accuracy.get("model_ids") or []),
        # 累计区间混了多个模型时，累计数字不可归给单一项目，前端据此收起归属展示。
        "multi_model": bool(accuracy.get("multi_model")),
        "latest_day": accuracy.get("latest_day"),
        "latest_accuracy": accuracy.get("latest_accuracy"),
        "latest_counted_units": accuracy.get("latest_counted_units"),
        "project": resolve_model_project(slot, model_id),
    }


def build_slot_row(slot: str) -> Dict[str, Any]:
    key = str(slot)
    semantics = describe_slot(key)
    models = _model_summary(key)
    accuracy = _accuracy_summary(key)
    dataset = _dataset_current(key)
    available = _available_datasets(key)
    return {
        "slot": key,
        "label": SLOT_LABELS.get(key, key),
        "granularity": semantics.get("granularity"),
        "semantics": semantics,
        "champion": models["champion"],
        "challenger": models["challenger"],
        "current_model": models["current_model"],
        "classifier_accuracy": accuracy["classifier_accuracy"],
        "counted_units": accuracy["counted_units"],
        "accuracy_source": accuracy["source"],
        # 按日精度的产出模型与项目归属（供「精度运营」显示这条精度来自哪个项目）。
        "accuracy_attribution": _accuracy_attribution(key, accuracy),
        "dataset": dataset,
        "available_datasets": available,
        "available_dataset_count": len(available),
    }


def build_overview() -> Dict[str, Any]:
    rows = [build_slot_row(slot) for slot in SUPPORTED_SLOTS]
    return {"paths": rows, "total": len(rows)}
# @AI_GENERATED: end
