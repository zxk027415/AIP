"""Slot dataset snapshot chain (G5 skeleton)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from services.slot_governance.provenance import assert_product_slot
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.reviewed_annotations import list_reviewed_annotations

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_datasets"

_PV_SLOTS = frozenset({"pv_day", "pv_point"})
SOURCE_PATH_A = "path_a"
SOURCE_DAILY_REVIEW = "daily_review"
ALLOWED_CUMULATIVE_SOURCES = frozenset({SOURCE_PATH_A, SOURCE_DAILY_REVIEW})
_DEDUP_KEYS = ["site_id", "device_id", "branch_id", "time"]
_PARQUET_FREEZE_MIN_ROWS = 5000


def _assert_pv_slot(slot: str) -> str:
    key = str(slot or "").strip()
    if not key:
        raise SlotDatasetError("missing_slot", "slot is required")
    if key not in _PV_SLOTS:
        raise SlotDatasetError(
            "invalid_slot",
            f"slot must be one of {sorted(_PV_SLOTS)!r}, got {key!r}",
        )
    return key


def _cumulative_manifest_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "cumulative_labeled_manifest.json"


def _load_cumulative_manifest(slot: str) -> dict[str, Any]:
    path = _cumulative_manifest_path(slot)
    if not path.is_file():
        return {"slot": slot, "included_labeled_version_ids": [], "inclusion_events": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"slot": slot, "included_labeled_version_ids": [], "inclusion_events": []}
    payload.setdefault("included_labeled_version_ids", [])
    payload.setdefault("inclusion_events", [])
    return payload


def _save_cumulative_manifest(slot: str, manifest: dict[str, Any]) -> dict[str, Any]:
    path = _cumulative_manifest_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = dict(manifest)
    manifest["slot"] = slot
    manifest["updated_at"] = _now_iso()
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _find_labeled_version(slot: str, dataset_version_id: str) -> dict[str, Any]:
    from services.slot_datasets.labeled_versions import list_labeled_versions

    normalized_id = str(dataset_version_id or "").strip()
    if not normalized_id:
        raise SlotDatasetError("missing_dataset_version_id", "dataset_version_id is required")
    for row in list_labeled_versions(slot):
        if row.get("dataset_version_id") == normalized_id:
            return dict(row)
    raise SlotDatasetError(
        "labeled_version_not_found",
        f"dataset_version_id={normalized_id!r} not found for slot={slot!r}",
    )


def _normalize_cumulative_source(source: str | None) -> str:
    key = str(source or SOURCE_PATH_A).strip()
    if key not in ALLOWED_CUMULATIVE_SOURCES:
        raise SlotDatasetError(
            "invalid_cumulative_source",
            f"source must be one of {sorted(ALLOWED_CUMULATIVE_SOURCES)!r}, got {key!r}",
        )
    return key


def _event_reviewed_at(event: dict[str, Any]) -> str:
    return str(event.get("reviewed_at") or event.get("included_at") or "")


def _events_upto(events: list[dict[str, Any]], reviewed_at_cutoff: str | None) -> list[dict[str, Any]]:
    if not reviewed_at_cutoff:
        return list(events)
    cutoff = str(reviewed_at_cutoff).strip()
    return [item for item in events if _event_reviewed_at(item) <= cutoff]


def include_labeled_version_in_cumulative(
    *,
    slot: str,
    dataset_version_id: str,
    source: str = SOURCE_PATH_A,
    reviewed_at: str | None = None,
    reviewer: str | None = None,
    freeze: bool = False,
) -> dict[str, Any]:
    """Record a curated labeled version in the slot cumulative manifest without mutating the version file."""
    key = _assert_pv_slot(slot)
    source_key = _normalize_cumulative_source(source)
    labeled = _find_labeled_version(key, dataset_version_id)
    manifest = _load_cumulative_manifest(key)
    included: list[str] = list(manifest.get("included_labeled_version_ids") or [])
    already_included = dataset_version_id in included
    included_at = _now_iso()
    event_reviewed_at = str(reviewed_at or included_at).strip() or included_at
    event: dict[str, Any] | None = None
    if not already_included:
        included.append(dataset_version_id)
        manifest["included_labeled_version_ids"] = included
        event = {
            "event_id": f"inc-{uuid.uuid4().hex[:12]}",
            "dataset_version_id": dataset_version_id,
            "file_path": labeled.get("file_path"),
            "source": source_key,
            "reviewed_at": event_reviewed_at,
            "reviewer": reviewer,
            "included_at": included_at,
            "sequence": len(included),
        }
        manifest.setdefault("inclusion_events", []).append(event)
        manifest = _save_cumulative_manifest(key, manifest)
    else:
        for item in manifest.get("inclusion_events") or []:
            if isinstance(item, dict) and item.get("dataset_version_id") == dataset_version_id:
                event = dict(item)
                break
    freeze_result = None
    if freeze:
        cutoff = str((event or {}).get("reviewed_at") or event_reviewed_at)
        freeze_result = freeze_cumulative_at(
            slot=key,
            reviewed_at_cutoff=cutoff,
            reason=f"auto freeze after include source={source_key}",
        )
    return {
        "slot": key,
        "dataset_version_id": dataset_version_id,
        "source": source_key,
        "reviewed_at": (event or {}).get("reviewed_at") or event_reviewed_at,
        "inclusion_event": event,
        "included_labeled_version_ids": list(manifest.get("included_labeled_version_ids") or []),
        "idempotent_replay": already_included,
        "freeze": freeze_result,
    }


def freeze_cumulative_at(
    *,
    slot: str,
    reviewed_at_cutoff: str,
    idempotency_key: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Freeze a trainable cumulative snapshot using all ledger events up to reviewed_at_cutoff."""
    key = _assert_pv_slot(slot)
    cutoff = str(reviewed_at_cutoff or "").strip()
    if not cutoff:
        raise SlotDatasetError("missing_reviewed_at_cutoff", "reviewed_at_cutoff is required")
    return build_labeled_versions_snapshot(
        slot=key,
        idempotency_key=str(idempotency_key or f"freeze-{key}-upto-{cutoff}"),
        reason=str(reason or f"freeze cumulative up to reviewed_at={cutoff}"),
        reviewed_at_cutoff=cutoff,
    )


def freeze_dataset_id_of(slot: str, record: dict[str, Any] | None) -> str:
    """Product-facing freeze id: time stamp first, legacy snap-{slot}-vN still accepted."""
    key = str(slot or "").strip()
    item = record or {}
    existing = str(item.get("freeze_id") or "").strip()
    if existing:
        return existing
    version = item.get("snapshot_version")
    if version not in (None, ""):
        return f"snap-{key}-v{int(version)}"
    return ""


def _stamp_from_iso(iso: str) -> str:
    raw = str(iso or "").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _make_freeze_id(slot: str, created_at: str) -> str:
    return f"snap-{slot}-{_stamp_from_iso(created_at)}-{uuid.uuid4().hex[:4]}"


def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "dataset_version_id": event.get("dataset_version_id"),
        "source": event.get("source") or SOURCE_PATH_A,
        "reviewed_at": event.get("reviewed_at") or event.get("included_at"),
        "file_path": event.get("file_path"),
        "reviewer": event.get("reviewer"),
    }


def get_cumulative_ledger(slot: str) -> dict[str, Any]:
    """Return inclusion ledger + freeze versions for the cumulative training dashboard."""
    key = _assert_pv_slot(slot)
    manifest = _load_cumulative_manifest(key)
    events = [
        dict(item)
        for item in (manifest.get("inclusion_events") or [])
        if isinstance(item, dict)
    ]
    for item in events:
        if not str(item.get("source") or "").strip():
            item["source"] = SOURCE_PATH_A
        item.setdefault("reviewed_at", item.get("included_at"))
    events.sort(key=lambda item: (_event_reviewed_at(item), str(item.get("included_at") or "")))
    events_by_version = {
        str(item.get("dataset_version_id") or ""): item
        for item in events
        if item.get("dataset_version_id")
    }
    chain = _load_chain(key) or {}
    freeze_versions = [
        dict(item)
        for item in (chain.get("versions") or [])
        if isinstance(item, dict)
    ]
    for item in freeze_versions:
        item["freeze_id"] = freeze_dataset_id_of(key, item)
        included = item.get("included_events")
        if not isinstance(included, list) or not included:
            ids = [str(vid) for vid in (item.get("included_labeled_version_ids") or []) if str(vid).strip()]
            item["included_events"] = [
                _event_summary(events_by_version.get(vid, {"dataset_version_id": vid}))
                for vid in ids
            ]
    freeze_versions.sort(
        key=lambda item: (
            str(item.get("created_at") or item.get("reviewed_at_cutoff") or ""),
            int(item.get("snapshot_version") or 0),
        ),
        reverse=True,
    )
    latest = freeze_versions[0] if freeze_versions else None
    return {
        "slot": key,
        "events": events,
        "event_count": len(events),
        "included_count": len(manifest.get("included_labeled_version_ids") or []),
        "freeze_versions": freeze_versions,
        "latest_freeze": latest,
        "updated_at": manifest.get("updated_at"),
        "priority": "cumulative_training",
    }


def preview_snapshot(slot: str, freeze_id: str, *, sample_rows: int = 50) -> dict[str, Any]:
    """Read a freeze artifact (csv or parquet) for the cumulative training drawer."""
    key = _assert_pv_slot(slot)
    wanted = str(freeze_id or "").strip()
    if not wanted:
        raise SlotDatasetError("snapshot_not_found", "freeze_id is required")
    ledger = get_cumulative_ledger(key)
    record = None
    for item in ledger.get("freeze_versions") or []:
        if str(item.get("freeze_id") or "") == wanted:
            record = item
            break
    if record is None:
        raise SlotDatasetError("snapshot_not_found", f"freeze {wanted!r} not found for slot {key}")
    artifact_ref = str(record.get("artifact_ref") or "").replace("\\", "/").strip()
    if not artifact_ref:
        raise SlotDatasetError("snapshot_not_found", f"freeze {wanted!r} has no artifact_ref")
    abs_path = _BACKEND_DIR / artifact_ref
    if not abs_path.is_file():
        raise SlotDatasetError("file_not_found", f"snapshot file not found: {artifact_ref}")
    frame = _read_labeled_file(abs_path)
    time_start = time_end = None
    if "time" in frame.columns:
        ts = pd.to_datetime(frame["time"], errors="coerce", utc=True)
        if ts.notna().any():
            time_start = ts.min().isoformat()
            time_end = ts.max().isoformat()
    device_keys = None
    entity_cols = [c for c in ("site_id", "device_id", "branch_id") if c in frame.columns]
    if entity_cols:
        device_keys = int(frame[entity_cols].astype(str).drop_duplicates().shape[0])
    label_distribution: dict[str, int] = {}
    if "label" in frame.columns:
        counts = frame["label"].value_counts(dropna=False)
        label_distribution = {str(idx): int(val) for idx, val in counts.items()}
    sample = frame.head(max(1, min(int(sample_rows), 50)))
    sample = sample.where(pd.notnull(sample), None)
    return {
        "slot": key,
        "freeze_id": wanted,
        "artifact_ref": artifact_ref,
        "row_count": int(len(frame)),
        "column_names": [str(c) for c in frame.columns],
        "time_start": time_start,
        "time_end": time_end,
        "device_count": device_keys,
        "label_distribution": label_distribution,
        "sample_rows": sample.to_dict(orient="records"),
        "included_event_count": record.get("included_event_count") or len(record.get("included_events") or []),
    }


def _snapshot_artifact_rel_path(slot: str, freeze_id: str, suffix: str = "csv") -> str:
    ext = str(suffix or "csv").lstrip(".").lower() or "csv"
    safe = str(freeze_id or "").strip() or f"snap-{slot}-unknown"
    return f"data/slot_datasets/{slot}/snapshots/{safe}.{ext}"


def _read_labeled_file(abs_path: Path) -> pd.DataFrame:
    suffix = abs_path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(abs_path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(abs_path, encoding="utf-8")
    raise SlotDatasetError("unsupported_labeled_file", f"unsupported labeled file type: {suffix}")


def _normalize_freeze_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "time" in out.columns:
        try:
            out["time"] = pd.to_datetime(out["time"], errors="coerce", utc=True, format="mixed")
        except (TypeError, ValueError):
            out["time"] = pd.to_datetime(out["time"], errors="coerce", utc=True)
    for col in ("site_id", "device_id", "branch_id"):
        if col in out.columns:
            out[col] = out[col].astype("string")
    for col in ("value", "i_cal", "label"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _dedupe_entity_time(frame: pd.DataFrame) -> pd.DataFrame:
    keys = [col for col in _DEDUP_KEYS if col in frame.columns]
    if len(keys) < 2:
        return frame
    return frame.drop_duplicates(subset=keys, keep="last").copy()


def _register_cumulative_canvas_row(
    slot: str,
    freeze_id: str,
    artifact_ref: str,
    *,
    reviewed_at_cutoff: str | None = None,
) -> dict[str, Any]:
    from services.slot_datasets.canvas_datasets import register_trainable_dataset

    dataset_id = str(freeze_id or "").strip()
    cutoff = str(reviewed_at_cutoff or "").strip()
    name = f"累计 · {dataset_id}" if not cutoff else f"累计 · {dataset_id} · 截止 {cutoff}"
    return register_trainable_dataset(
        dataset_id=dataset_id,
        kind="cumulative_snapshot",
        slot=slot,
        ref_id=dataset_id,
        file_path=artifact_ref,
        name=name,
        extra={"reviewed_at_cutoff": cutoff or None, "priority": "cumulative_training"},
    )


def _is_pv_point_cluster_day_box(file_path: str) -> bool:
    """Whole-day clustering confirm boxes must not enter a pv_point trainable freeze."""
    path = str(file_path or "").replace("\\", "/").lower()
    if not path:
        return False
    if "/gold/" in path:
        return False
    if "/confirmed_reviews/" in path or "/review_slices/" in path:
        return False
    needles = ("training_workspace", "/clust-", "confirmed/lprop-")
    return any(needle in path for needle in needles)


def _filter_pv_point_freeze_rows(
    labeled_rows: list[dict[str, Any]],
    included_ids: list[str],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    kept_rows: list[dict[str, Any]] = []
    kept_ids: list[str] = []
    skipped_ids: list[str] = []
    for row, version_id in zip(labeled_rows, included_ids):
        if _is_pv_point_cluster_day_box(str((row or {}).get("file_path") or "")):
            skipped_ids.append(version_id)
            continue
        kept_rows.append(row)
        kept_ids.append(version_id)
    return kept_rows, kept_ids, skipped_ids


def _materialize_labeled_snapshot_artifact(
    slot: str,
    freeze_id: str,
    labeled_versions: list[dict[str, Any]],
) -> str:
    frames: list[pd.DataFrame] = []
    saw_parquet = False
    for row in labeled_versions:
        rel_path = str(row.get("file_path") or "").strip()
        if not rel_path:
            raise SlotDatasetError("missing_file_path", f"labeled version {row.get('dataset_version_id')!r} has no file_path")
        abs_path = _BACKEND_DIR / rel_path
        if not abs_path.is_file():
            raise SlotDatasetError("file_not_found", f"labeled version file not found: {rel_path}")
        if abs_path.suffix.lower() == ".parquet":
            saw_parquet = True
        frame = _normalize_freeze_frame(_read_labeled_file(abs_path))
        frame["_dataset_version_id"] = row.get("dataset_version_id")
        frames.append(frame)
    if not frames:
        raise SlotDatasetError("empty_cumulative_manifest", "no labeled versions to build snapshot from")

    combined = _dedupe_entity_time(
        _normalize_freeze_frame(pd.concat(frames, ignore_index=True))
    )
    use_parquet = saw_parquet or len(combined) >= _PARQUET_FREEZE_MIN_ROWS
    suffix = "parquet" if use_parquet else "csv"
    artifact_rel = _snapshot_artifact_rel_path(slot, freeze_id, suffix)
    artifact_abs = _BACKEND_DIR / artifact_rel
    artifact_abs.parent.mkdir(parents=True, exist_ok=True)
    if use_parquet:
        combined.to_parquet(artifact_abs, index=False)
    else:
        combined.to_csv(artifact_abs, index=False, encoding="utf-8")
    return artifact_rel.replace("\\", "/")


def build_labeled_versions_snapshot(
    *,
    slot: str,
    idempotency_key: str,
    reason: str,
    reviewed_at_cutoff: str | None = None,
) -> dict[str, Any]:
    """Build cumulative snapshot artifact from manifest included labeled versions and register canvas row."""
    key = _assert_pv_slot(slot)
    if not str(idempotency_key or "").strip():
        raise SlotDatasetError("missing_idempotency_key", "idempotency_key is required")

    existing = find_build_by_idempotency(key, idempotency_key)
    if existing is not None:
        chain = get_snapshot_chain(key)
        version = int(existing.get("snapshot_version") or 0)
        version_record = next(
            (item for item in chain.get("versions") or [] if int(item.get("snapshot_version") or 0) == version),
            None,
        )
        artifact_ref = (version_record or {}).get("artifact_ref")
        canvas_row = None
        freeze_id = freeze_dataset_id_of(key, version_record)
        if artifact_ref and freeze_id:
            canvas_row = _register_cumulative_canvas_row(
                key,
                freeze_id,
                artifact_ref,
                reviewed_at_cutoff=(version_record or {}).get("reviewed_at_cutoff"),
            )
        return {
            "chain": chain,
            "build": existing,
            "canvas_row": canvas_row,
            "freeze_id": freeze_id,
            "artifact_ref": artifact_ref,
            "reviewed_at_cutoff": (version_record or {}).get("reviewed_at_cutoff"),
            "idempotent_replay": True,
        }

    manifest = _load_cumulative_manifest(key)
    cutoff = str(reviewed_at_cutoff or "").strip() or None
    selected_events = _events_upto(
        [item for item in (manifest.get("inclusion_events") or []) if isinstance(item, dict)],
        cutoff,
    )
    included_ids: list[str] = []
    for event in selected_events:
        version_id = str(event.get("dataset_version_id") or "").strip()
        if version_id and version_id not in included_ids:
            included_ids.append(version_id)
    if not included_ids:
        included_ids = list(manifest.get("included_labeled_version_ids") or []) if not cutoff else []
    if not included_ids:
        raise SlotDatasetError("empty_cumulative_manifest", "no labeled versions included for cumulative build")

    labeled_rows = [_find_labeled_version(key, version_id) for version_id in included_ids]
    skipped_cluster_ids: list[str] = []
    if key == "pv_point":
        labeled_rows, included_ids, skipped_cluster_ids = _filter_pv_point_freeze_rows(
            labeled_rows,
            included_ids,
        )
        if not labeled_rows:
            raise SlotDatasetError(
                "empty_point_freeze_after_filter",
                "pv_point freeze has no remaining labeled versions after excluding clustering whole-day boxes",
            )

    chain = _load_chain(key)
    if chain is None:
        snapshot_id = _stable_snapshot_id(key)
        next_version = 1
        chain = {
            "snapshot_id": snapshot_id,
            "latest_version": 0,
            "versions": [],
            "bootstrap_events": [],
            "build_events": [],
        }
    else:
        snapshot_id = str(chain.get("snapshot_id") or _stable_snapshot_id(key))
        next_version = int(chain.get("latest_version") or 0) + 1

    created_at = _now_iso()
    freeze_id = _make_freeze_id(key, created_at)
    artifact_ref = _materialize_labeled_snapshot_artifact(key, freeze_id, labeled_rows)
    kept_id_set = set(included_ids)
    included_events = [
        _event_summary(item)
        for item in selected_events
        if str(item.get("dataset_version_id") or "") in kept_id_set
    ]
    version_record = {
        "snapshot_version": next_version,
        "freeze_id": freeze_id,
        "base_snapshot_version": int(chain.get("latest_version") or 0) or None,
        "included_labeled_version_ids": included_ids,
        "included_events": included_events,
        "artifact_ref": artifact_ref,
        "source_digest": _digest({"included": included_ids, "artifact_ref": artifact_ref}),
        "created_at": created_at,
        "reason": reason,
        "build_kind": "labeled_versions",
        "manifest_digest": _digest(included_ids),
        "reviewed_at_cutoff": cutoff,
        "included_event_count": len(included_events) if included_events else len(included_ids),
        "excluded_cluster_day_version_ids": skipped_cluster_ids,
    }
    build_event = {
        "build_id": f"sb-{uuid.uuid4().hex[:12]}",
        "idempotency_key": idempotency_key,
        "snapshot_id": snapshot_id,
        "snapshot_version": next_version,
        "freeze_id": freeze_id,
        "build_kind": "labeled_versions",
        "created_at": created_at,
    }

    chain.setdefault("versions", []).append(version_record)
    chain["latest_version"] = next_version
    chain["snapshot_id"] = snapshot_id
    chain.setdefault("build_events", []).append(build_event)
    saved = _save_chain(key, chain)
    canvas_row = _register_cumulative_canvas_row(
        key,
        freeze_id,
        artifact_ref,
        reviewed_at_cutoff=cutoff,
    )
    return {
        "chain": saved,
        "build": build_event,
        "canvas_row": canvas_row,
        "artifact_ref": artifact_ref,
        "freeze_id": freeze_id,
        "reviewed_at_cutoff": cutoff,
        "idempotent_replay": False,
    }


def _chain_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "snapshot_chain.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_snapshot_id(slot: str) -> str:
    return f"snap-{str(slot).strip().replace('_', '-')}"


def _digest(obj: Any) -> str:
    encoded = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load_chain(slot: str) -> Optional[dict[str, Any]]:
    path = _chain_path(slot)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _save_chain(slot: str, chain: dict[str, Any]) -> dict[str, Any]:
    path = _chain_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    chain = dict(chain)
    chain["slot"] = slot
    chain["updated_at"] = _now_iso()
    path.write_text(json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8")
    return chain


def get_snapshot_chain(slot: str) -> dict[str, Any]:
    assert_product_slot(slot)
    chain = _load_chain(slot)
    if chain is None:
        return {
            "slot": slot,
            "snapshot_id": None,
            "latest_version": 0,
            "versions": [],
            "empty": True,
        }
    chain.setdefault("empty", False)
    return chain


def find_bootstrap_by_idempotency(slot: str, idempotency_key: str) -> Optional[dict[str, Any]]:
    chain = _load_chain(slot)
    if not chain:
        return None
    for event in chain.get("bootstrap_events") or []:
        if event.get("idempotency_key") == idempotency_key:
            return event
    return None


def find_build_by_idempotency(slot: str, idempotency_key: str) -> Optional[dict[str, Any]]:
    chain = _load_chain(slot)
    if not chain:
        return None
    for event in chain.get("build_events") or []:
        if event.get("idempotency_key") == idempotency_key:
            return event
    return None


def bootstrap_snapshot(
    *,
    slot: str,
    idempotency_key: str,
    source_digest: str,
    base_artifact_ref: str,
    dataset_profile_ref: str,
    reason: str,
    source_workflow_id: Optional[str] = None,
    source_execution_id: Optional[str] = None,
    role_partition: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    assert_product_slot(slot)
    if not idempotency_key.strip():
        raise SlotDatasetError("missing_idempotency_key", "idempotency_key is required")

    existing = find_bootstrap_by_idempotency(slot, idempotency_key)
    if existing is not None:
        chain = get_snapshot_chain(slot)
        return {"chain": chain, "bootstrap": existing, "idempotent_replay": True}

    chain = _load_chain(slot)
    if chain is not None and chain.get("snapshot_id"):
        raise SlotDatasetError(
            "snapshot_chain_exists",
            f"slot={slot!r} already has snapshot_id={chain.get('snapshot_id')!r}",
        )

    snapshot_id = _stable_snapshot_id(slot)
    version_record = {
        "snapshot_version": 1,
        "base_snapshot_version": None,
        "added_annotation_refs": [],
        "added_source_candidate_refs": [],
        "source_digest": source_digest,
        "base_artifact_ref": base_artifact_ref,
        "dataset_profile_ref": dataset_profile_ref,
        "role_partition": role_partition or {"learning": 1.0},
        "label_space_version": "v1",
        "created_at": _now_iso(),
        "reason": reason,
        "source_workflow_id": source_workflow_id,
        "source_execution_id": source_execution_id,
        "manifest_digest": _digest(
            {
                "snapshot_id": snapshot_id,
                "snapshot_version": 1,
                "source_digest": source_digest,
                "base_artifact_ref": base_artifact_ref,
            }
        ),
    }

    bootstrap_event = {
        "bootstrap_id": f"bs-{uuid.uuid4().hex[:12]}",
        "idempotency_key": idempotency_key,
        "snapshot_id": snapshot_id,
        "snapshot_version": 1,
        "created_at": _now_iso(),
    }

    new_chain = {
        "snapshot_id": snapshot_id,
        "latest_version": 1,
        "versions": [version_record],
        "bootstrap_events": [bootstrap_event],
        "build_events": [],
    }
    saved = _save_chain(slot, new_chain)
    return {"chain": saved, "bootstrap": bootstrap_event, "idempotent_replay": False}


def build_snapshot_increment(
    *,
    slot: str,
    snapshot_id: str,
    base_snapshot_version: int,
    reviewed_annotation_ids: list[str],
    idempotency_key: str,
    reason: str,
) -> dict[str, Any]:
    assert_product_slot(slot)
    if not idempotency_key.strip():
        raise SlotDatasetError("missing_idempotency_key", "idempotency_key is required")

    existing = find_build_by_idempotency(slot, idempotency_key)
    if existing is not None:
        return {"chain": get_snapshot_chain(slot), "build": existing, "idempotent_replay": True}

    chain = _load_chain(slot)
    if chain is None or chain.get("snapshot_id") != snapshot_id:
        raise SlotDatasetError("snapshot_not_found", f"snapshot_id={snapshot_id!r} not found for slot={slot!r}")

    latest = int(chain.get("latest_version") or 0)
    if latest != int(base_snapshot_version):
        raise SlotDatasetError(
            "base_version_conflict",
            f"expected base_snapshot_version={base_snapshot_version}, current latest={latest}",
        )

    reviewed = list_reviewed_annotations(slot)
    reviewed_by_id = {item["reviewed_annotation_id"]: item for item in reviewed}
    refs: list[dict[str, Any]] = []
    for ann_id in reviewed_annotation_ids:
        ann = reviewed_by_id.get(ann_id)
        if ann is None:
            raise SlotDatasetError("reviewed_annotation_not_found", f"reviewed_annotation_id={ann_id!r} missing")
        if ann.get("slot") != slot:
            raise SlotDatasetError("slot_mismatch", f"reviewed annotation slot mismatch for {ann_id!r}")
        if ann.get("annotation_role") == "locked_holdout":
            raise SlotDatasetError("locked_holdout_forbidden", f"{ann_id!r} is locked_holdout")
        refs.append(
            {
                "reviewed_annotation_id": ann_id,
                "entity_key": ann.get("entity_key"),
                "final_label": ann.get("final_label"),
            }
        )

    next_version = latest + 1
    prev = chain["versions"][-1]
    version_record = {
        "snapshot_version": next_version,
        "base_snapshot_version": latest,
        "added_annotation_refs": refs,
        "added_source_candidate_refs": [
            reviewed_by_id[ann_id].get("source_annotation_candidate_id")
            for ann_id in reviewed_annotation_ids
        ],
        "source_digest": _digest({"base": prev.get("source_digest"), "added": refs}),
        "dataset_profile_ref": prev.get("dataset_profile_ref"),
        "role_partition": prev.get("role_partition"),
        "label_space_version": prev.get("label_space_version"),
        "created_at": _now_iso(),
        "reason": reason,
        "manifest_digest": _digest({"snapshot_id": snapshot_id, "snapshot_version": next_version, "added": refs}),
    }

    build_event = {
        "build_id": f"sb-{uuid.uuid4().hex[:12]}",
        "idempotency_key": idempotency_key,
        "snapshot_id": snapshot_id,
        "snapshot_version": next_version,
        "base_snapshot_version": latest,
        "created_at": _now_iso(),
    }

    chain["versions"].append(version_record)
    chain["latest_version"] = next_version
    chain.setdefault("build_events", []).append(build_event)
    saved = _save_chain(slot, chain)
    artifact_ref = version_record.get("artifact_ref")
    canvas_row = None
    if artifact_ref:
        freeze_id = _make_freeze_id(slot, str(version_record.get("created_at") or _now_iso()))
        version_record["freeze_id"] = freeze_id
        canvas_row = _register_cumulative_canvas_row(slot, freeze_id, artifact_ref)
    return {"chain": saved, "build": build_event, "canvas_row": canvas_row, "idempotent_replay": False}


def resolve_snapshot_ref(slot: str, snapshot_id: str, snapshot_version: int) -> dict[str, Any]:
    """Validate snapshot_id@version for retrain workflow path params."""
    chain = _load_chain(slot)
    if chain is None or chain.get("snapshot_id") != snapshot_id:
        raise SlotDatasetError("snapshot_not_found", f"snapshot_id={snapshot_id!r} not found")
    for version in chain.get("versions") or []:
        if int(version.get("snapshot_version") or 0) == int(snapshot_version):
            return {
                "slot": slot,
                "snapshot_id": snapshot_id,
                "snapshot_version": snapshot_version,
                "dataset_snapshot_ref": f"{snapshot_id}@{snapshot_version}",
                "version_record": version,
            }
    raise SlotDatasetError(
        "snapshot_version_not_found",
        f"snapshot_version={snapshot_version} not found for {snapshot_id!r}",
    )


def _bootstrap_jobs_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "bootstrap_jobs.json"


def _load_bootstrap_jobs(slot: str) -> list[dict[str, Any]]:
    path = _bootstrap_jobs_path(slot)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("jobs")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_bootstrap_jobs(slot: str, items: list[dict[str, Any]]) -> None:
    path = _bootstrap_jobs_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"slot": slot, "jobs": items}, ensure_ascii=False, indent=2), encoding="utf-8")


def find_bootstrap_job(slot: str, bootstrap_job_id: str) -> Optional[dict[str, Any]]:
    for job in _load_bootstrap_jobs(slot):
        if job.get("bootstrap_job_id") == bootstrap_job_id:
            return job
    return None


def start_bootstrap_async(
    *,
    slot: str,
    idempotency_key: str,
    dataset_profile_ref: str,
    reason: str,
    bootstrap_workflow_ref: Optional[str] = None,
) -> dict[str, Any]:
    """Create bootstrap job; caller must run workflow then complete with execution id."""
    assert_product_slot(slot)
    for job in _load_bootstrap_jobs(slot):
        if job.get("idempotency_key") == idempotency_key:
            return job

    chain = _load_chain(slot)
    if chain is not None and chain.get("snapshot_id"):
        raise SlotDatasetError(
            "snapshot_chain_exists",
            f"slot={slot!r} already bootstrapped as {chain.get('snapshot_id')!r}",
        )

    from services.operator_execution.slot_workflows import resolve_train_workflow_id

    job = {
        "bootstrap_job_id": f"bsjob-{uuid.uuid4().hex[:12]}",
        "slot": slot,
        "idempotency_key": idempotency_key,
        "dataset_profile_ref": dataset_profile_ref,
        "bootstrap_workflow_ref": bootstrap_workflow_ref or resolve_train_workflow_id(slot),
        "reason": reason,
        "status": "pending",
        "created_at": _now_iso(),
    }
    items = _load_bootstrap_jobs(slot)
    items.append(job)
    _save_bootstrap_jobs(slot, items)
    return job


def complete_bootstrap_async(
    bootstrap_job_id: str,
    *,
    bootstrap_execution_id: str,
    source_digest: str,
    base_artifact_ref: str,
) -> dict[str, Any]:
    from services.slot_governance.provenance import validate_execution_source

    slot = None
    job = None
    for slot_dir in (_DATA_DIR.iterdir() if _DATA_DIR.is_dir() else []):
        if not slot_dir.is_dir():
            continue
        found = find_bootstrap_job(slot_dir.name, bootstrap_job_id)
        if found is not None:
            slot = slot_dir.name
            job = found
            break
    if job is None or slot is None:
        raise SlotDatasetError("bootstrap_job_not_found", f"bootstrap_job_id={bootstrap_job_id!r} not found")
    if job.get("status") == "completed":
        return {"job": job, "chain": get_snapshot_chain(slot), "idempotent_replay": True}

    wf_id = str(job.get("bootstrap_workflow_ref"))
    validate_execution_source(
        slot=slot,
        source_workflow_id=wf_id,
        source_execution_id=bootstrap_execution_id,
    )

    result = bootstrap_snapshot(
        slot=slot,
        idempotency_key=job["idempotency_key"],
        source_digest=source_digest,
        base_artifact_ref=base_artifact_ref,
        dataset_profile_ref=job["dataset_profile_ref"],
        reason=job.get("reason") or "bootstrap-async",
        source_workflow_id=wf_id,
        source_execution_id=bootstrap_execution_id,
    )

    job["status"] = "completed"
    job["bootstrap_execution_id"] = bootstrap_execution_id
    job["completed_at"] = _now_iso()
    items = _load_bootstrap_jobs(slot)
    for idx, item in enumerate(items):
        if item.get("bootstrap_job_id") == bootstrap_job_id:
            items[idx] = job
            break
    _save_bootstrap_jobs(slot, items)
    return {"job": job, "chain": result["chain"], "idempotent_replay": False}
