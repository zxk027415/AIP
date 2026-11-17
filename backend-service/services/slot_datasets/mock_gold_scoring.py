"""Score gold units with real detection predictions or production/candidate models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from services.iterative_labeling.accuracy_evaluator import AccuracyEvaluator
from services.slot_datasets.errors import SlotDatasetError

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENTITY_COLS = ("site_id", "device_id", "branch_id")
_ID_WINDOW = ["site_id", "device_id", "branch_id", "time_window"]


def _as_int_label(value: Any) -> Optional[int]:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return int(parsed)


def _calendar_day(value: Any) -> str:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d")
    raw = str(value or "").strip()
    return raw[:10] if raw else ""


def _entity_key(row: pd.Series | dict[str, Any]) -> str:
    return "|".join(str(row.get(col, "") or "") for col in _ENTITY_COLS)


def _point_time_token(value: Any) -> str:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return str(value or "").strip()


def unit_key_for(slot: str, row: pd.Series | dict[str, Any], *, time_value: Any = None) -> str:
    entity = _entity_key(row)
    stamp = time_value if time_value is not None else row.get("time") or row.get("time_window") or row.get("date")
    if slot == "pv_day":
        return f"{entity}|{_calendar_day(stamp)}"
    return f"{entity}|{_point_time_token(stamp)}"


def accuracy_from_pairs(pairs: list[tuple[int, int]]) -> dict[str, Any]:
    evaluator = AccuracyEvaluator()
    for predicted, truth in pairs:
        pred_i = int(predicted)
        truth_i = int(truth)
        evaluator.update(
            {"verdict_label": truth_i, "action_type": "confirm" if pred_i == truth_i else "correct"},
            {"predicted_label": pred_i},
            label_source="mock_gold",
        )
    return evaluator.get_current_accuracy()


def _assign_unit_key(frame: pd.DataFrame, slot: str) -> pd.Series:
    entity = (
        frame.get("site_id", "").astype(str)
        + "|"
        + frame.get("device_id", "").astype(str)
        + "|"
        + frame.get("branch_id", "").astype(str)
    )
    stamp = frame["time"] if "time" in frame.columns else frame.get("time_window", frame.get("date"))
    if slot == "pv_day":
        day = pd.to_datetime(stamp, utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
        return entity + "|" + day.fillna("")
    ts = pd.to_datetime(stamp, utc=True, errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return entity + "|" + ts.fillna("")


def gold_truth_by_unit(slot: str, gold: pd.DataFrame) -> dict[str, int]:
    if "label" not in gold.columns or gold.empty:
        return {}
    work = gold.dropna(subset=["label"]).copy()
    work["label"] = pd.to_numeric(work["label"], errors="coerce")
    work = work.dropna(subset=["label"])
    if work.empty:
        return {}
    work["_unit_key"] = _assign_unit_key(work, slot)
    grouped = work.groupby("_unit_key", sort=False)["label"].agg(lambda series: int(series.mode().iloc[0]))
    return {str(key): int(value) for key, value in grouped.items()}


def stratified_sample(frame: pd.DataFrame, n: int, *, random_state: int = 42) -> pd.DataFrame:
    labeled = frame.dropna(subset=["label"]).copy()
    if labeled.empty or n <= 0:
        return labeled.iloc[0:0].copy()
    labeled["_label_i"] = pd.to_numeric(labeled["label"], errors="coerce")
    labeled = labeled.dropna(subset=["_label_i"])
    if labeled.empty:
        return labeled
    groups = [grp for _, grp in labeled.groupby("_label_i", sort=False)]
    per = max(1, int(n) // max(len(groups), 1))
    chunks: list[pd.DataFrame] = []
    leftover_idx: list[Any] = []
    for grp in groups:
        take = min(len(grp), per)
        chunks.append(grp.sample(n=take, random_state=random_state) if take < len(grp) else grp)
        if take < len(grp):
            leftover_idx.extend(list(grp.index.difference(chunks[-1].index)))
    out = pd.concat(chunks, ignore_index=False)
    if len(out) < n and leftover_idx:
        extra = labeled.loc[leftover_idx]
        need = min(len(extra), n - len(out))
        if need:
            out = pd.concat([out, extra.sample(n=need, random_state=random_state)])
    return out.head(n).drop(columns=["_label_i"], errors="ignore")


def load_recent_prediction_units(slot: str, *, max_files: int = 8) -> list[dict[str, Any]]:
    batch_dir = _BACKEND_DIR / "data" / "iterative_labeling" / "prediction_batches" / slot
    if not batch_dir.is_dir():
        return []
    units: list[dict[str, Any]] = []
    paths = sorted(batch_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths[: max(1, max_files)]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in payload.get("units") or []:
            if isinstance(item, dict):
                row = dict(item)
                row["_prediction_batch_id"] = payload.get("prediction_batch_id") or path.stem
                units.append(row)
    return units


def join_predictions_with_gold(
    slot: str,
    gold: pd.DataFrame,
    *,
    max_units: int,
) -> list[dict[str, Any]]:
    truth = gold_truth_by_unit(slot, gold)
    if not truth:
        return []
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for unit in load_recent_prediction_units(slot):
        pred = _as_int_label(unit.get("predicted_label") if unit.get("predicted_label") is not None else unit.get("suggested_label"))
        if pred is None:
            continue
        key = unit_key_for(slot, unit, time_value=unit.get("time_window") or unit.get("date") or unit.get("time"))
        if key in seen or key not in truth:
            continue
        seen.add(key)
        hits.append(
            {
                "unit_key": key,
                "predicted_label": pred,
                "gold_label": truth[key],
                "confidence": float(unit.get("confidence") or 0.0),
                "origin": "detection_join",
                "site_id": unit.get("site_id"),
                "device_id": unit.get("device_id"),
                "branch_id": unit.get("branch_id"),
                "time": unit.get("time_window") or unit.get("time") or unit.get("date"),
            }
        )
        if len(hits) >= max_units:
            break
    return hits


def resolve_role_models(slot: str) -> list[dict[str, Any]]:
    from services.scheduler.slot_workflow_runner import resolve_slot_scheduler_model
    from services.slot_governance.registry import get_registry_store

    production = resolve_slot_scheduler_model(slot)
    prod_id = str(production.get("model_id") or production.get("model_candidate_id") or "").strip()
    prod_art = str(production.get("model_artifact_ref") or "").replace("\\", "/").strip()
    roles = []
    if prod_id or prod_art:
        roles.append(
            {
                "role": "production",
                "model_candidate_id": prod_id,
                "model_artifact_ref": prod_art,
                "source": production.get("source"),
            }
        )
    registry = get_registry_store().get(slot) or {}
    challenger = registry.get("challenger") if isinstance(registry.get("challenger"), dict) else {}
    cand_id = str(
        challenger.get("challenger_model_candidate_id") or challenger.get("challenger_model_ref") or ""
    ).strip()
    cand_art = str(challenger.get("challenger_model_artifact_ref") or "").replace("\\", "/").strip()
    if (cand_id or cand_art) and cand_id != prod_id:
        roles.append(
            {
                "role": "candidate",
                "model_candidate_id": cand_id,
                "model_artifact_ref": cand_art,
                "source": "challenger",
            }
        )
    return roles


def _pkl_path(artifact_ref: str) -> Path:
    raw = str(artifact_ref or "").replace("\\", "/").strip()
    if raw.startswith("backend-service/"):
        raw = raw[len("backend-service/") :]
    return _BACKEND_DIR / raw


def _tcn_artifact_rel(artifact_ref: str) -> str:
    raw = str(artifact_ref or "").replace("\\", "/").strip()
    if raw.startswith("backend-service/"):
        return raw
    return f"backend-service/{raw}"


def score_point_artifact(gold: pd.DataFrame, artifact_ref: str, sample: pd.DataFrame) -> list[dict[str, Any]]:
    from services.timeseries_point.causal_window import build_causal_window_for_pending_point
    from services.timeseries_point.predict import predict_point_outcome

    work = gold.copy()
    work["time"] = pd.to_datetime(work["time"], utc=True, errors="coerce")
    work = work.dropna(subset=["time"]).sort_values(["site_id", "device_id", "branch_id", "time"]).reset_index(drop=True)
    if "i_cal" not in work.columns and "value" in work.columns:
        work["i_cal"] = work["value"]
    work["_unit_key"] = _assign_unit_key(work, "pv_point")
    work["_rank"] = work.groupby(list(_ENTITY_COLS), dropna=False).cumcount()
    eligible_keys = set(_assign_unit_key(sample.copy(), "pv_point")) if not sample.empty else set()
    artifact = _tcn_artifact_rel(artifact_ref)
    hits: list[dict[str, Any]] = []
    mask = work["_rank"] >= 7
    if eligible_keys:
        mask &= work["_unit_key"].isin(eligible_keys)
    for pos in work.index[mask]:
        row = work.loc[pos]
        truth = _as_int_label(row.get("label"))
        if truth is None:
            continue
        window = build_causal_window_for_pending_point(
            work,
            entity_keys=list(_ENTITY_COLS),
            time_column="time",
            feature_columns=[col for col in ("value", "i_cal") if col in work.columns],
            pending_row_index=int(work.index.get_loc(pos)),
            context_length=8,
        )
        outcome = predict_point_outcome(window, artifact_dir=artifact)
        if outcome.kind != "prediction" or outcome.label is None:
            continue
        hits.append(
            {
                "unit_key": str(row["_unit_key"]),
                "predicted_label": int(outcome.label),
                "gold_label": truth,
                "confidence": float(outcome.confidence or 0.0),
                "origin": "gold_replay_predict",
                "site_id": row.get("site_id"),
                "device_id": row.get("device_id"),
                "branch_id": row.get("branch_id"),
                "time": row.get("time"),
            }
        )
        if eligible_keys and len(hits) >= len(eligible_keys):
            break
        if not eligible_keys and len(hits) >= 30:
            break
    return hits


def score_day_artifact(gold: pd.DataFrame, artifact_ref: str, sample: pd.DataFrame) -> list[dict[str, Any]]:
    from services.operator_backends.extract_statistical_features import execute as extract_stats
    from services.operator_backends.handle_missing import execute as handle_missing
    from services.operator_backends.random_forest_classifier import _load_model
    from services.operator_backends.time_window_split import execute as split_windows

    wanted = {unit_key_for("pv_day", row) for _, row in sample.iterrows()}
    work = gold.copy()
    work["time"] = pd.to_datetime(work["time"], utc=True, errors="coerce")
    work = work.dropna(subset=["time"])
    if "i_cal" not in work.columns and "value" in work.columns:
        work["i_cal"] = work["value"]
    work["_day"] = work["time"].dt.strftime("%Y-%m-%d")
    work["_unit_key"] = (
        work["site_id"].astype(str)
        + "|"
        + work["device_id"].astype(str)
        + "|"
        + work["branch_id"].astype(str)
        + "|"
        + work["_day"]
    )
    subset = work[work["_unit_key"].isin(wanted)].copy() if wanted else work
    if subset.empty:
        return []
    split = split_windows.execute(
        {
            "window": "1d",
            "id_fields": list(_ENTITY_COLS),
            "time_field": "time",
            "solar_mode": "day_and_night",
            "power_col": "value",
            "irr_threshold": 0.05,
            "attach_night_features": True,
        },
        {"data": subset.drop(columns=["_unit_key", "_day"], errors="ignore")},
    )["data"]
    cleaned = handle_missing.execute(
        {
            "method": "drop_insufficient",
            "keep_threshold": 0.75,
            "id_fields": list(_ID_WINDOW),
            "value_fields": [col for col in ("value", "i_cal") if col in split.columns],
        },
        {"data": split},
    )["data"]
    stats = extract_stats.execute(
        {
            "mode": "groupby_aggregate",
            "id_fields": list(_ID_WINDOW),
            "value_fields": [col for col in ("value", "i_cal") if col in cleaned.columns],
            "compute_diff": True,
            "quantiles": [0.25, 0.75],
        },
        {"data": cleaned},
    )["data"]
    extra_frames: list[pd.DataFrame] = []
    try:
        from services.operator_backends.tsfresh_extract import execute as tsfresh_extract

        extra_frames.append(
            tsfresh_extract.execute(
                {
                    "id_fields": list(_ID_WINDOW),
                    "value_fields": [col for col in ("value", "i_cal") if col in cleaned.columns],
                },
                {"data": cleaned},
            )["data"]
        )
    except Exception:
        extra_frames = extra_frames
    try:
        from services.operator_backends.ts_comparison_features import execute as compare_features

        extra_frames.append(
            compare_features.execute(
                {
                    "id_fields": list(_ID_WINDOW),
                    "value_fields": [col for col in ("value", "i_cal") if col in cleaned.columns],
                    "options": {"compute_correlation": True, "compute_distance": True, "compute_regression": True},
                },
                {"data": cleaned},
            )["data"]
        )
    except Exception:
        extra_frames = extra_frames

    merged = stats.reset_index() if isinstance(stats.index, pd.MultiIndex) else stats.copy()
    for extra in extra_frames:
        if extra is None or extra.empty:
            continue
        frame = extra.reset_index() if isinstance(extra.index, pd.MultiIndex) else extra.copy()
        common = [col for col in _ID_WINDOW if col in merged.columns and col in frame.columns]
        new_cols = [col for col in frame.columns if col not in merged.columns]
        if common and new_cols:
            merged = merged.merge(frame[common + new_cols], on=common, how="left")

    pkl = _pkl_path(artifact_ref)
    model, feature_list = _load_model("explicit", str(pkl))
    present = [col for col in (feature_list or []) if col in merged.columns]
    if not present:
        raise SlotDatasetError("day_features_mismatch", "RFC feature_list 与 gold 窗口特征对不上")
    preds = model.predict(merged[present]).astype(int)
    truth_map = gold_truth_by_unit("pv_day", subset)
    hits: list[dict[str, Any]] = []
    for index, pred in enumerate(preds):
        row = merged.iloc[index]
        key = unit_key_for("pv_day", row, time_value=row.get("time_window"))
        truth = truth_map.get(key)
        if truth is None:
            continue
        hits.append(
            {
                "unit_key": key,
                "predicted_label": int(pred),
                "gold_label": int(truth),
                "confidence": 0.0,
                "origin": "gold_replay_predict",
                "site_id": row.get("site_id"),
                "device_id": row.get("device_id"),
                "branch_id": row.get("branch_id"),
                "time": row.get("time_window"),
            }
        )
    return hits


def score_artifact(slot: str, gold: pd.DataFrame, artifact_ref: str, sample: pd.DataFrame) -> list[dict[str, Any]]:
    if not str(artifact_ref or "").strip():
        return []
    if slot == "pv_point":
        return score_point_artifact(gold, artifact_ref, sample)
    return score_day_artifact(gold, artifact_ref, sample)
