"""Label proposal store — non-curated workflow output (G11)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from services.slot_datasets.canvas_datasets import register_trainable_dataset
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.labeled_versions import publish_labeled_version

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_datasets"
# @AI_GENERATED: pv_tsc device-day proposals share the unified review store.
_ALLOWED_SLOTS = frozenset({"pv_day", "pv_point", "pv_tsc"})
# @AI_GENERATED: end


def _assert_slot(slot: str) -> str:
    key = str(slot or "").strip()
    if key not in _ALLOWED_SLOTS:
        raise SlotDatasetError("invalid_slot", f"slot must be one of {sorted(_ALLOWED_SLOTS)!r}")
    return key


def _proposals_path(slot: str) -> Path:
    return _DATA_DIR / slot.replace("/", "_") / "label_proposals.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_proposals(slot: str) -> list[dict[str, Any]]:
    path = _proposals_path(slot)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("proposals")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_proposals(slot: str, items: list[dict[str, Any]]) -> None:
    path = _proposals_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"slot": slot, "proposals": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def allocate_proposal_id(slot: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"lprop-{slot}-{stamp}-{uuid.uuid4().hex[:6]}"


def save_label_proposal(
    *,
    slot: str,
    clusters: dict[str, Any],
    source_file_path: str | None = None,
    source_workflow_id: str | None = None,
    source_execution_id: str | None = None,
    member_rows_path: str | None = None,
    cluster_profile: dict[str, Any] | None = None,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    """Persist a non-curated label proposal artifact."""
    key = _assert_slot(slot)
    pid = str(proposal_id or allocate_proposal_id(key)).strip()
    record: dict[str, Any] = {
        "proposal_id": pid,
        "slot": key,
        "status": "proposal",
        "clusters": clusters,
        "source_file_path": source_file_path,
        "source_workflow_id": source_workflow_id,
        "source_execution_id": source_execution_id,
        "member_rows_path": member_rows_path,
        "cluster_profile": cluster_profile or {},
        "created_at": _now_iso(),
    }
    items = _load_proposals(key)
    if any(item.get("proposal_id") == pid for item in items):
        raise SlotDatasetError("proposal_id_conflict", f"proposal already exists: {pid!r}")
    items.append(record)
    _save_proposals(key, items)
    return dict(record)


def confirm_label_proposal(
    *,
    slot: str,
    proposal_id: str,
    label_id_map: dict[str, int],
) -> dict[str, Any]:
    """Promote proposal → curated labeled version + trainable registry row."""
    key = _assert_slot(slot)
    proposal = get_label_proposal(key, proposal_id)
    if str(proposal.get("slot") or key) != key:
        raise SlotDatasetError("slot_mismatch", "proposal does not belong to this slot")
    if proposal.get("status") == "confirmed":
        raise SlotDatasetError("proposal_already_confirmed", f"proposal {proposal_id!r} already confirmed")
    if proposal.get("status") == "rejected":
        raise SlotDatasetError("proposal_rejected", f"proposal {proposal_id!r} was rejected")

    member_path = str(proposal.get("member_rows_path") or "").strip()
    if not member_path:
        raise SlotDatasetError("missing_member_rows", "proposal has no member_rows_path")
    abs_member = _BACKEND_DIR / member_path.replace("\\", "/")
    if not abs_member.is_file():
        raise SlotDatasetError("file_not_found", f"member rows file not found: {member_path}")

    frame = pd.read_csv(abs_member, encoding="utf-8")
    if "cluster_id" not in frame.columns:
        raise SlotDatasetError("missing_cluster_id", "member rows missing cluster_id column")

    clusters = proposal.get("clusters") or {}
    key_to_label: dict[str, int] = {}
    for cid, cluster in clusters.items():
        name = cluster.get("proposed_label_name") or f"cluster_{cid}"
        if name not in label_id_map:
            raise SlotDatasetError("missing_label_mapping", f"label_id_map missing entry for {name!r}")
        label_id = int(label_id_map[name])
        for mk in cluster.get("selected_member_keys") or []:
            key_to_label[str(mk)] = label_id

    if "member_key" not in frame.columns:
        entity_cols = [c for c in ("site_id", "device_id", "branch_id", "date") if c in frame.columns]
        if not entity_cols and "time" in frame.columns:
            frame["date"] = pd.to_datetime(frame["time"], errors="coerce").dt.date.astype(str)
            entity_cols = [c for c in ("site_id", "device_id", "branch_id", "date") if c in frame.columns]
        frame["member_key"] = frame.apply(
            lambda row: "|".join(str(row.get(c, "")) for c in entity_cols),
            axis=1,
        )

    labeled = frame[frame["member_key"].isin(key_to_label)].copy()
    if labeled.empty:
        raise SlotDatasetError("empty_labeled_selection", "no member rows matched selected clusters")
    labeled["label"] = labeled["member_key"].map(key_to_label)
    drop_cols = [c for c in ("member_key", "cluster_id", "date") if c in labeled.columns]
    labeled = labeled.drop(columns=drop_cols, errors="ignore")

    confirmed_dir = _DATA_DIR / key / "confirmed" / proposal_id
    confirmed_dir.mkdir(parents=True, exist_ok=True)
    csv_name = f"labeled-{proposal_id}.csv"
    csv_abs = confirmed_dir / csv_name
    labeled.to_csv(str(csv_abs), index=False, encoding="utf-8")
    rel_backend = csv_abs.relative_to(_BACKEND_DIR).as_posix()

    version = publish_labeled_version(slot=key, file_path=rel_backend, status="curated")
    canvas_row = register_trainable_dataset(
        dataset_id=version["dataset_version_id"],
        kind="labeled_version",
        slot=key,
        ref_id=version["dataset_version_id"],
        file_path=rel_backend,
        name=f"确认箱 · {proposal_id}",
    )
    from services.slot_datasets.review_admission import include_path_a_labeled_version

    confirmed_at = _now_iso()
    cumulative = include_path_a_labeled_version(
        slot=key,
        dataset_version_id=version["dataset_version_id"],
        reviewed_at=confirmed_at,
    )

    items = _load_proposals(key)
    for item in items:
        if item.get("proposal_id") == proposal_id:
            item["status"] = "confirmed"
            item["confirmed_at"] = confirmed_at
            item["dataset_version_id"] = version["dataset_version_id"]
            item["confirmed_file_path"] = rel_backend
            break
    _save_proposals(key, items)

    return {
        "proposal_id": proposal_id,
        "dataset_version_id": version["dataset_version_id"],
        "dataset_id": canvas_row["dataset_id"],
        "file_path": rel_backend,
        "sample_count": int(len(labeled)),
        "cumulative_include": {
            "source": cumulative.get("source"),
            "reviewed_at": cumulative.get("reviewed_at"),
            "freeze_dataset_id": ((cumulative.get("freeze") or {}).get("canvas_row") or {}).get("dataset_id"),
        },
    }


_MAX_MEMBER_SAMPLE = 80
_MAX_WAVEFORM_POINTS = 240
_GOLD_REL = {
    "pv_day": "data/slot_datasets/pv_day/gold/all_labeled_combined.parquet",
    "pv_point": "data/slot_datasets/pv_point/gold/point-poc-k4-labeled.parquet",
}
# 场景注册表还没写入业务名时，下拉和「可能：」备注用这套目录，避免空表。
_FALLBACK_CATALOG: dict[str, tuple[tuple[int, str], ...]] = {
    "pv_point": ((0, "正常"), (1, "组串失配"), (2, "组串遮挡"), (3, "其他故障")),
    "pv_day": ((0, "正常"), (1, "组串失配"), (2, "组串遮挡"), (3, "其他故障")),
    # @AI_GENERATED: TSC diagnoses the same PV fault label space at device-day granularity.
    "pv_tsc": ((0, "正常"), (1, "组串失配"), (2, "组串遮挡"), (3, "其他故障")),
    # @AI_GENERATED: end
}


def _cluster_mean_vector(stats: dict[str, Any]) -> dict[str, float]:
    vector: dict[str, float] = {}
    if not isinstance(stats, dict):
        return vector
    for key, value in stats.items():
        if isinstance(value, dict) and value.get("mean") is not None:
            try:
                vector[str(key)] = float(value["mean"])
            except (TypeError, ValueError):
                continue
        elif isinstance(value, (int, float)):
            vector[str(key)] = float(value)
    return vector


def _read_reference_labeled_frame(slot: str) -> pd.DataFrame | None:
    from services.slot_datasets.snapshots import get_cumulative_ledger

    candidates: list[Path] = []
    gold = _BACKEND_DIR / _GOLD_REL.get(slot, "")
    if gold.is_file():
        candidates.append(gold)
    # @AI_GENERATED
    # pv_tsc 的 gold 是内容寻址命名（all_labeled_combined-<hex>.parquet），
    # 无法写进 _GOLD_REL 静态映射；这里按目录兜底，重新 freeze 后仍能命中。
    gold_dir = _BACKEND_DIR / "data" / "slot_datasets" / slot / "gold"
    if gold_dir.is_dir():
        for pattern in ("*.parquet", "*.csv"):
            for path in sorted(gold_dir.glob(pattern)):
                if path.is_file() and path not in candidates:
                    candidates.append(path)
    # @AI_GENERATED: end
    demo_gold = _BACKEND_DIR / "data" / "slot_datasets" / slot / "loop_demo" / "gold.parquet"
    if demo_gold.is_file():
        candidates.append(demo_gold)
    try:
        latest = (get_cumulative_ledger(slot).get("latest_freeze") or {}).get("artifact_ref")
        if latest:
            freeze_path = _BACKEND_DIR / str(latest).replace("\\", "/")
            if freeze_path.is_file():
                candidates.append(freeze_path)
    except Exception:
        pass
    for path in candidates:
        try:
            if path.suffix.lower() == ".parquet":
                frame = pd.read_parquet(path)
            else:
                frame = pd.read_csv(path, encoding="utf-8")
        except Exception:
            continue
        if frame is None or frame.empty or "label" not in frame.columns:
            continue
        return frame
    return None


def _file_registry_names(slot: str) -> dict[int, str]:
    try:
        from services.iterative_labeling.label_registry import LabelRegistryService
        from services.iterative_labeling.storage.file_backend import FileLabelRegistryRepository

        registry = LabelRegistryService(slot=slot, registry_repo=FileLabelRegistryRepository())
        current = registry.get_current() or {}
        names: dict[int, str] = {}
        for item in current.get("labels") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("label_name") or "").strip()
            if not name or name.startswith("cluster_"):
                continue
            try:
                names[int(item.get("label_id"))] = name
            except (TypeError, ValueError):
                continue
        if names:
            return names
        for name, lid in (current.get("label_map") or {}).items():
            text = str(name).strip()
            if text and not text.startswith("cluster_"):
                names[int(lid)] = text
        return names
    except Exception:
        return {}


def _catalog_names_for_slot(slot: str) -> dict[int, str]:
    """Business names for dropdown + hints. File registry first, then demo/catalog fallback."""
    key = _assert_slot(slot)
    names = dict(_file_registry_names(key))
    try:
        from services.slot_datasets.loop_demo import LABELS

        for lid, name in LABELS:
            names.setdefault(int(lid), str(name))
    except Exception:
        pass
    for lid, name in _FALLBACK_CATALOG.get(key, _FALLBACK_CATALOG["pv_point"]):
        names.setdefault(int(lid), name)
    return names


def _registry_names_for_slot(slot: str) -> dict[int, str]:
    return _catalog_names_for_slot(slot)


def _hint_from_i_cal(vector: dict[str, float], id_to_name: dict[int, str], limit: int) -> list[str]:
    amp = None
    for key in ("i_cal", "value", "mean_i", "current", "power"):
        if key in vector:
            amp = vector[key]
            break
    if amp is None:
        return []
    try:
        from services.slot_datasets.loop_demo import _predict_i_cal

        pred = int(_predict_i_cal(float(amp)))
    except Exception:
        pred = 0 if float(amp) > 7.8 else (1 if float(amp) > 3.6 else 3)
    ordered: list[str] = []
    primary = id_to_name.get(pred)
    if primary:
        ordered.append(primary)
    for name in id_to_name.values():
        if name not in ordered:
            ordered.append(name)
        if len(ordered) >= limit:
            break
    return ordered[:limit]


def suggest_label_names_for_cluster(slot: str, representative_stats: dict[str, Any], limit: int = 3) -> list[str]:
    """Nearest registered labels for the current slot (hint, never auto-fill)."""
    key = _assert_slot(slot)
    cap = max(1, min(int(limit), 3))
    id_to_name = _catalog_names_for_slot(key)
    catalog = list(dict.fromkeys(id_to_name.values()))
    vector = _cluster_mean_vector(representative_stats)
    frame = _read_reference_labeled_frame(key)
    if vector and frame is not None and not frame.empty and "label" in frame.columns:
        feature_cols = [col for col in vector if col in frame.columns]
        if feature_cols:
            labeled = frame.copy()
            labeled["label"] = pd.to_numeric(labeled["label"], errors="coerce")
            labeled = labeled.dropna(subset=["label"])
            if not labeled.empty:
                class_means = labeled.groupby(labeled["label"].astype(int))[feature_cols].mean()
                scored: list[tuple[float, str]] = []
                for label_id, row in class_means.iterrows():
                    name = id_to_name.get(int(label_id))
                    if not name:
                        continue
                    dist = 0.0
                    used = 0
                    for col in feature_cols:
                        try:
                            dist += (float(vector[col]) - float(row[col])) ** 2
                            used += 1
                        except (TypeError, ValueError):
                            continue
                    if used:
                        scored.append((dist, name))
                scored.sort(key=lambda item: (item[0], item[1]))
                seen: set[str] = set()
                names: list[str] = []
                for _, name in scored:
                    if name in seen:
                        continue
                    seen.add(name)
                    names.append(name)
                    if len(names) >= cap:
                        break
                if names:
                    return names
    hinted = _hint_from_i_cal(vector, id_to_name, cap)
    if hinted:
        return hinted
    return catalog[:cap]


def _attach_suggestions(slot: str, proposal: dict[str, Any]) -> dict[str, Any]:
    payload = dict(proposal)
    clusters = dict(payload.get("clusters") or {})
    for cid, cluster in clusters.items():
        if not isinstance(cluster, dict):
            continue
        cluster = dict(cluster)
        existing = cluster.get("suggested_label_names")
        if not isinstance(existing, list) or not existing:
            cluster["suggested_label_names"] = suggest_label_names_for_cluster(
                slot, cluster.get("representative_stats") or {}
            )
        clusters[cid] = cluster
    payload["clusters"] = clusters
    return payload


def list_label_proposals(slot: str) -> list[dict[str, Any]]:
    key = _assert_slot(slot)
    items = [_attach_suggestions(key, item) for item in _load_proposals(key)]
    items.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return items


def get_label_proposal(slot: str, proposal_id: str) -> dict[str, Any]:
    key = _assert_slot(slot)
    for item in _load_proposals(key):
        if item.get("proposal_id") == proposal_id:
            return _attach_suggestions(key, item)
    raise SlotDatasetError("proposal_not_found", f"proposal {proposal_id!r} not found")


def _load_member_frame(proposal: dict[str, Any]) -> pd.DataFrame:
    member_path = str(proposal.get("member_rows_path") or "").strip()
    if not member_path:
        raise SlotDatasetError("missing_member_rows", "proposal has no member_rows_path")
    abs_member = _BACKEND_DIR / member_path.replace("\\", "/")
    if not abs_member.is_file():
        raise SlotDatasetError("file_not_found", f"member rows file not found: {member_path}")
    return pd.read_csv(abs_member, encoding="utf-8")


def _feature_bars_from_stats(stats: Any) -> list[dict[str, Any]]:
    if not isinstance(stats, dict):
        return []
    bars: list[dict[str, Any]] = []
    for name, value in stats.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        bars.append({"time": str(name), "value": float(value)})
    return bars[:24]


def _points_from_frame(subset: pd.DataFrame) -> list[dict[str, Any]]:
    if subset is None or subset.empty:
        return []
    work = subset.copy()
    time_col = "time" if "time" in work.columns else ("event_time" if "event_time" in work.columns else None)
    if time_col:
        work = work.sort_values(time_col)
    work = work.head(_MAX_WAVEFORM_POINTS)
    points: list[dict[str, Any]] = []
    for index, row in work.iterrows():
        item: dict[str, Any] = {
            "time": str(row[time_col]) if time_col else str(index),
        }
        if "value" in work.columns:
            item["value"] = None if pd.isna(row.get("value")) else float(row.get("value"))
        if "i_cal" in work.columns:
            item["i_cal"] = None if pd.isna(row.get("i_cal")) else float(row.get("i_cal"))
        if "value" not in item and "i_cal" not in item:
            value_col = next((c for c in ("current", "power") if c in work.columns), None)
            if value_col is None:
                continue
            item["value"] = None if pd.isna(row.get(value_col)) else float(row.get(value_col))
        points.append(item)
    return points


def _waveform_for_member(frame: pd.DataFrame, member_key: str) -> list[dict[str, Any]]:
    if "member_key" not in frame.columns:
        return []
    subset = frame[frame["member_key"].astype(str) == str(member_key)]
    return _points_from_frame(subset)


def _cluster_waveform(frame: pd.DataFrame, cluster: dict[str, Any]) -> list[dict[str, Any]]:
    """All selected members of a cluster, time-ordered — not just the representative's 1–2 rows."""
    keys = [str(key) for key in (cluster.get("selected_member_keys") or cluster.get("member_keys") or [])]
    if "member_key" not in frame.columns:
        return _points_from_frame(frame)
    if keys:
        subset = frame[frame["member_key"].astype(str).isin(set(keys))]
    else:
        subset = frame
    return _points_from_frame(subset)


def _cluster_member_rows(frame: pd.DataFrame, cluster: dict[str, Any], limit: int = 80) -> list[dict[str, Any]]:
    keys = [str(key) for key in (cluster.get("selected_member_keys") or cluster.get("member_keys") or [])]
    if "member_key" not in frame.columns:
        sample = frame.head(limit)
    elif keys:
        sample = frame[frame["member_key"].astype(str).isin(set(keys))].head(limit)
    else:
        sample = frame.head(limit)
    return sample.where(pd.notnull(sample), None).to_dict(orient="records")


def get_label_proposal_detail(slot: str, proposal_id: str) -> dict[str, Any]:
    key = _assert_slot(slot)
    proposal = get_label_proposal(key, proposal_id)
    if str(proposal.get("slot") or key) != key:
        raise SlotDatasetError("slot_mismatch", "proposal does not belong to this slot")
    frame = _load_member_frame(proposal)
    sample = frame.head(_MAX_MEMBER_SAMPLE)
    members = sample.where(pd.notnull(sample), None).to_dict(orient="records")
    waveforms: dict[str, list[dict[str, Any]]] = {}
    members_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for cid, cluster in (proposal.get("clusters") or {}).items():
        if not isinstance(cluster, dict):
            continue
        members_by_cluster[str(cid)] = _cluster_member_rows(frame, cluster)
        if key == "pv_day":
            bars = _feature_bars_from_stats(cluster.get("representative_stats"))
            curve = bars or _cluster_waveform(frame, cluster)
        else:
            curve = _cluster_waveform(frame, cluster)
        waveforms[str(cid)] = curve
        rep = str(cluster.get("representative_member_key") or "")
        if rep:
            waveforms[rep] = curve
    registry_names = list(_registry_names_for_slot(key).values())
    return {
        **proposal,
        "members_sample": members,
        "members_by_cluster": members_by_cluster,
        "members_total": int(len(frame)),
        "waveforms": waveforms,
        "registry_label_names": registry_names,
        "columns": [str(c) for c in frame.columns],
    }


def patch_label_proposal(
    slot: str,
    proposal_id: str,
    *,
    clusters_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = _assert_slot(slot)
    items = _load_proposals(key)
    found = None
    for item in items:
        if item.get("proposal_id") == proposal_id:
            found = item
            break
    if found is None:
        raise SlotDatasetError("proposal_not_found", f"proposal {proposal_id!r} not found")
    if str(found.get("slot") or key) != key:
        raise SlotDatasetError("slot_mismatch", "proposal does not belong to this slot")
    status = str(found.get("status") or "proposal")
    if status in {"confirmed", "rejected"}:
        raise SlotDatasetError("proposal_not_editable", f"proposal is {status}")
    clusters = dict(found.get("clusters") or {})
    for cid, patch in (clusters_patch or {}).items():
        if cid not in clusters or not isinstance(patch, dict):
            continue
        cluster = dict(clusters[cid])
        if "proposed_label_name" in patch:
            name = str(patch.get("proposed_label_name") or "").strip()
            if name:
                cluster["proposed_label_name"] = name
        if "selected_member_keys" in patch and isinstance(patch.get("selected_member_keys"), list):
            allowed = {str(k) for k in (cluster.get("member_keys") or [])}
            selected = [str(k) for k in patch["selected_member_keys"] if str(k) in allowed]
            cluster["selected_member_keys"] = selected
        clusters[cid] = cluster
    found["clusters"] = clusters
    found["updated_at"] = _now_iso()
    _save_proposals(key, items)
    return get_label_proposal_detail(key, proposal_id)


def reject_label_proposal(slot: str, proposal_id: str, *, reason: str | None = None) -> dict[str, Any]:
    key = _assert_slot(slot)
    items = _load_proposals(key)
    found = None
    for item in items:
        if item.get("proposal_id") == proposal_id:
            found = item
            break
    if found is None:
        raise SlotDatasetError("proposal_not_found", f"proposal {proposal_id!r} not found")
    if str(found.get("slot") or key) != key:
        raise SlotDatasetError("slot_mismatch", "proposal does not belong to this slot")
    if str(found.get("status") or "") == "confirmed":
        raise SlotDatasetError("proposal_already_confirmed", f"proposal {proposal_id!r} already confirmed")
    found["status"] = "rejected"
    found["rejected_at"] = _now_iso()
    if reason:
        found["reject_reason"] = str(reason)
    _save_proposals(key, items)
    return dict(found)
