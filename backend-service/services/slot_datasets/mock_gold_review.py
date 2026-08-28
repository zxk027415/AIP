"""Admit a small gold-labeled batch through complete-and-admit, with real model-vs-gold accuracy."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.gold_bootstrap import DAY_GOLD_REL, POINT_GOLD_REL
from services.slot_datasets.mock_gold_scoring import (
    accuracy_from_pairs,
    join_predictions_with_gold,
    resolve_role_models,
    score_artifact,
    stratified_sample,
)
from services.slot_datasets.review_session_admission import complete_review_session_and_admit

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_GOLD = {"pv_day": DAY_GOLD_REL, "pv_point": POINT_GOLD_REL}
_MIN_JOIN_HITS = 4


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _accuracy_path(slot: str) -> Path:
    return _BACKEND_DIR / "data" / "slot_datasets" / slot / "mock_accuracy.json"


def load_mock_accuracy(slot: str) -> dict[str, Any]:
    path = _accuracy_path(slot)
    if not path.is_file():
        return {"slot": slot, "by_model": {}, "empty": True}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"slot": slot, "by_model": {}, "empty": True}
    if not isinstance(payload, dict):
        return {"slot": slot, "by_model": {}, "empty": True}
    payload.setdefault("slot", slot)
    payload.setdefault("by_model", {})
    payload["empty"] = not bool(payload.get("by_model"))
    return payload


def _save_mock_accuracy(payload: dict[str, Any]) -> None:
    path = _accuracy_path(str(payload.get("slot") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _rows_for_units(slot: str, gold: pd.DataFrame, units: list[dict[str, Any]]) -> pd.DataFrame:
    from services.slot_datasets.mock_gold_scoring import _assign_unit_key

    wanted = {str(item.get("unit_key") or "") for item in units}
    work = gold.copy()
    work["_unit_key"] = _assign_unit_key(work, slot)
    matched = work[work["_unit_key"].isin(wanted)].copy()
    return matched.drop(columns=["_unit_key"], errors="ignore") if not matched.empty else gold.head(0)


def _score_roles(
    slot: str,
    gold: pd.DataFrame,
    sample: pd.DataFrame,
    roles: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    scored: dict[str, list[dict[str, Any]]] = {}
    for role in roles:
        artifact = str(role.get("model_artifact_ref") or "").strip()
        cid = str(role.get("model_candidate_id") or artifact or role.get("role") or "model")
        try:
            scored[cid] = score_artifact(slot, gold, artifact, sample)
        except Exception:
            scored[cid] = []
        role["scored_units"] = len(scored[cid])
    return scored


def run_mock_gold_review(slot: str, *, max_units: int = 30, reviewer: str = "mock_gold") -> dict[str, Any]:
    key = str(slot or "").strip()
    if key not in {"pv_day", "pv_point"}:
        raise SlotDatasetError("invalid_slot", "mock gold review only supports pv_day/pv_point")
    gold_path = _BACKEND_DIR / _GOLD[key]
    if not gold_path.is_file():
        raise SlotDatasetError("gold_not_found", f"gold file missing: {_GOLD[key]}")
    frame = pd.read_parquet(gold_path) if gold_path.suffix.lower() == ".parquet" else pd.read_csv(gold_path)
    if "label" not in frame.columns:
        raise SlotDatasetError("gold_missing_label", "gold file has no label column")
    labeled = frame.dropna(subset=["label"])
    if labeled.empty:
        raise SlotDatasetError("gold_empty", "gold has no labeled rows")

    cap = max(1, min(int(max_units), 30))
    joined = join_predictions_with_gold(key, labeled, max_units=cap)
    origin = "detection_join"
    production_units = joined
    roles = resolve_role_models(key)
    by_model: dict[str, Any] = {}

    if len(joined) < min(_MIN_JOIN_HITS, cap):
        origin = "gold_replay_predict"
        sample = stratified_sample(labeled, cap)
        if sample.empty:
            raise SlotDatasetError("gold_empty", "stratified gold sample is empty")
        scored = _score_roles(key, labeled, sample, roles)
        prod = next((item for item in roles if item.get("role") == "production"), None)
        prod_cid = str((prod or {}).get("model_candidate_id") or "")
        production_units = scored.get(prod_cid) or next(iter(scored.values()), [])
        for role in roles:
            cid = str(role.get("model_candidate_id") or "")
            hits = scored.get(cid) or []
            pairs = [(int(item["predicted_label"]), int(item["gold_label"])) for item in hits]
            snap = accuracy_from_pairs(pairs)
            by_model[cid or role["role"]] = {
                "role": role.get("role"),
                "model_candidate_id": cid,
                "model_artifact_ref": role.get("model_artifact_ref"),
                "classifier_accuracy": snap.get("classifier_accuracy"),
                "macro_f1": (snap.get("macro") or {}).get("f1"),
                "counted_units": snap.get("counted_units"),
                "origin": origin,
            }
    else:
        pairs = [(int(item["predicted_label"]), int(item["gold_label"])) for item in joined]
        snap = accuracy_from_pairs(pairs)
        prod = next((item for item in roles if item.get("role") == "production"), roles[0] if roles else None)
        if prod:
            cid = str(prod.get("model_candidate_id") or "production")
            by_model[cid] = {
                "role": "production",
                "model_candidate_id": cid,
                "model_artifact_ref": prod.get("model_artifact_ref"),
                "classifier_accuracy": snap.get("classifier_accuracy"),
                "macro_f1": (snap.get("macro") or {}).get("f1"),
                "counted_units": snap.get("counted_units"),
                "origin": origin,
            }
        sample = stratified_sample(labeled, cap)
        for role in roles:
            if role.get("role") == "production":
                continue
            cid = str(role.get("model_candidate_id") or "")
            try:
                hits = score_artifact(key, labeled, str(role.get("model_artifact_ref") or ""), sample)
            except Exception:
                hits = []
            cand_pairs = [(int(item["predicted_label"]), int(item["gold_label"])) for item in hits]
            cand_snap = accuracy_from_pairs(cand_pairs)
            by_model[cid or "candidate"] = {
                "role": "candidate",
                "model_candidate_id": cid,
                "model_artifact_ref": role.get("model_artifact_ref"),
                "classifier_accuracy": cand_snap.get("classifier_accuracy"),
                "macro_f1": (cand_snap.get("macro") or {}).get("f1"),
                "counted_units": cand_snap.get("counted_units"),
                "origin": "gold_replay_predict",
            }

    if not production_units:
        raise SlotDatasetError(
            "mock_score_empty",
            "无法得到真实预测对照：没有可 join 的检测批次，且生产模型在 gold 子集上没有打出预测",
        )

    from services.iterative_labeling.storage.file_backend import FileReviewResultRepository

    repo = FileReviewResultRepository()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    review_id = f"rev-mock-gold-{key}-{stamp}"
    slice_dir = Path(repo.data_root) / "time_slices"
    slice_dir.mkdir(parents=True, exist_ok=True)
    slice_name = f"mock-gold-{key}-{stamp}.csv"
    slice_abs = slice_dir / slice_name
    slice_rows = _rows_for_units(key, labeled, production_units)
    if slice_rows.empty:
        slice_rows = labeled.head(len(production_units))
    slice_rows.to_csv(slice_abs, index=False, encoding="utf-8")
    slice_rel = f"time_slices/{slice_name}"

    units = []
    verdicts = []
    for item in production_units:
        pred = int(item["predicted_label"])
        truth = int(item["gold_label"])
        action = "confirm" if pred == truth else "correct"
        units.append(
            {
                "unit_key": item["unit_key"],
                "predicted_label": pred,
                "confidence": float(item.get("confidence") or 0.0),
                "status": "confirmed",
                "final_label": truth,
            }
        )
        verdicts.append(
            {
                "unit_key": item["unit_key"],
                "verdict_label": truth,
                "predicted_label": pred,
                "action_type": action,
                "is_ground_truth": True,
                "reviewer": reviewer,
            }
        )
    prod_pairs = [(int(item["predicted_label"]), int(item["gold_label"])) for item in production_units]
    accuracy_snapshot = accuracy_from_pairs(prod_pairs)
    try:
        from api.iterative_labeling import _accuracy_evaluators, _accuracy_key

        evaluator_key = _accuracy_key(key, review_id)
        from services.iterative_labeling.accuracy_evaluator import AccuracyEvaluator

        evaluator = AccuracyEvaluator()
        for item in production_units:
            pred = int(item["predicted_label"])
            truth = int(item["gold_label"])
            evaluator.update(
                {"verdict_label": truth, "action_type": "confirm" if pred == truth else "correct"},
                {"predicted_label": pred},
                label_source="mock_gold",
            )
        _accuracy_evaluators[evaluator_key] = evaluator
    except Exception:
        pass

    session = {
        "review_id": review_id,
        "slot": key,
        "status": "reviewing",
        "reviewer": reviewer,
        "reviewed_count": len(units),
        "total_count": len(units),
        "units": units,
        "verdicts": verdicts,
        "freeform_labels": [
            {"unit_key": unit["unit_key"], "dataset_path": slice_rel, "row_count": 1}
            for unit in units
        ],
        "prediction_context": {
            "source": "mock_gold",
            "gold_path": _GOLD[key],
            "origin": origin,
        },
        "accuracy_snapshot": accuracy_snapshot,
        "created_at": _now_iso(),
    }
    repo.save_verdict(key, review_id, session)
    admitted = complete_review_session_and_admit(
        slot=key,
        review_id=review_id,
        review_repo=repo,
        reviewer=reviewer,
    )
    better = None
    prod_row = next((row for row in by_model.values() if row.get("role") == "production"), None)
    cand_row = next((row for row in by_model.values() if row.get("role") == "candidate"), None)
    if prod_row and cand_row and int(cand_row.get("counted_units") or 0) > 0:
        cand_f1 = float(cand_row.get("macro_f1") or 0)
        prod_f1 = float(prod_row.get("macro_f1") or 0)
        cand_acc = float(cand_row.get("classifier_accuracy") or 0)
        prod_acc = float(prod_row.get("classifier_accuracy") or 0)
        if cand_f1 > prod_f1 or (cand_f1 == prod_f1 and cand_acc > prod_acc):
            better = cand_row.get("model_candidate_id")

    accuracy_payload = {
        "slot": key,
        "review_id": review_id,
        "origin": origin,
        "updated_at": _now_iso(),
        "hit_count": len(production_units),
        "note": f"{'检测 join' if origin == 'detection_join' else 'gold 回放预测'} {len(production_units)} 条",
        "by_model": by_model,
        "better_model_candidate_id": better,
        "production_accuracy": accuracy_snapshot,
    }
    _save_mock_accuracy(accuracy_payload)
    refreshed = repo.load_session(key, review_id) or session
    refreshed["accuracy_snapshot"] = accuracy_snapshot
    refreshed["mock_origin"] = origin
    repo.save_verdict(key, review_id, refreshed)

    return {
        "slot": key,
        "review_id": review_id,
        "source": "daily_review",
        "hit_count": len(production_units),
        "note": accuracy_payload["note"],
        "origin": origin,
        "accuracy": accuracy_snapshot,
        "by_model": by_model,
        "better_model_candidate_id": better,
        "admission": admitted,
    }
