"""Resolve pv_day / pv_point train_eval inputs to cumulative freeze (or explicit dataset_id)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.slot_datasets.canvas_datasets import get_trainable_dataset
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.snapshots import get_cumulative_ledger, freeze_dataset_id_of

_PV_SLOTS = frozenset({"pv_day", "pv_point"})
_TRAIN_ROLES = frozenset({"train_eval"})
_LOAD_FUNCTION_IDS = frozenset({"load_csv", "load_labeled_dataset"})
_POINT_PLACEHOLDER_MARKERS = ("test_fixtures", "labeled_points.parquet")
_MIN_DAY_FREEZE_ROWS = 80


def _config_mapping(config: Any) -> dict[str, Any]:
    if config is None:
        return {}
    if isinstance(config, dict):
        return dict(config)
    if hasattr(config, "model_dump"):
        return config.model_dump()
    if hasattr(config, "dict"):
        return config.dict()
    return {}


def _function_id(config: Any) -> str:
    mapping = _config_mapping(config)
    return str(mapping.get("functionId") or mapping.get("function_id") or "").strip()


def _file_path(config: Any) -> str:
    mapping = _config_mapping(config)
    return str(mapping.get("file_path") or "").replace("\\", "/").strip()


def _looks_like_placeholder(path: str, slot: str) -> bool:
    lowered = str(path or "").replace("\\", "/").lower()
    if slot == "pv_point":
        return any(marker in lowered for marker in _POINT_PLACEHOLDER_MARKERS)
    return "slot_datasets/" not in lowered


def _looks_like_user_chosen(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/")
    return "slot_datasets/" in normalized or "/snapshots/" in normalized


def _count_rows(file_path: str) -> int:
    raw = str(file_path or "").replace("\\", "/").strip()
    if not raw:
        return 0
    backend_dir = Path(__file__).resolve().parents[2]
    candidates = [Path(raw), backend_dir / raw, backend_dir.parent / raw]
    for path in candidates:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        try:
            if suffix == ".parquet":
                import pyarrow.parquet as pq

                return int(pq.ParquetFile(path).metadata.num_rows)
            with path.open("r", encoding="utf-8") as handle:
                return max(0, sum(1 for _ in handle) - 1)
        except OSError:
            return 0
    return 0


def resolve_train_source(
    *,
    slot: str,
    dataset_id: str | None = None,
    explicit: bool = False,
) -> dict[str, Any] | None:
    """Return {dataset_id, file_path, kind, row_count} for train_eval, or None to keep template path."""
    key = str(slot or "").strip()
    if key not in _PV_SLOTS:
        return None
    wanted = str(dataset_id or "").strip()
    if wanted:
        row = get_trainable_dataset(key, wanted)
        if row is None:
            raise SlotDatasetError("dataset_not_found", f"trainable dataset not found: {wanted}")
        file_path = str(row.get("file_path") or "").replace("\\", "/")
        return {
            "dataset_id": str(row.get("dataset_id") or wanted),
            "file_path": file_path,
            "kind": str(row.get("kind") or ""),
            "row_count": _count_rows(file_path),
            "reason": "explicit_dataset_id",
        }

    ledger = get_cumulative_ledger(key)
    latest = ledger.get("latest_freeze") or {}
    freeze_id = freeze_dataset_id_of(key, latest)
    if not freeze_id:
        return None
    row = get_trainable_dataset(key, freeze_id)
    file_path = str((row or {}).get("file_path") or latest.get("artifact_ref") or "").replace("\\", "/")
    if not file_path:
        return None
    row_count = _count_rows(file_path)
    if key == "pv_day" and not explicit and row_count < _MIN_DAY_FREEZE_ROWS:
        return None
    return {
        "dataset_id": freeze_id,
        "file_path": file_path,
        "kind": str((row or {}).get("kind") or "cumulative_snapshot"),
        "row_count": row_count,
        "reason": "latest_cumulative_freeze",
    }


def _set_node_config(node: Any, updates: dict[str, Any]) -> None:
    data = getattr(node, "data", None)
    if data is None:
        return
    config = getattr(data, "config", None)
    mapping = _config_mapping(config)
    mapping.update(updates)
    function_id = str(mapping.get("functionId") or "").strip()
    if function_id == "load_labeled_dataset":
        mapping["dataset_id"] = updates.get("dataset_id")
    if isinstance(config, dict):
        config.update(updates)
        data.config = config
        return
    if config is not None:
        for key, value in updates.items():
            try:
                setattr(config, key, value)
            except Exception:
                pass
        try:
            data.config = type(config)(**mapping)
            return
        except Exception:
            pass
    data.config = mapping


def apply_train_source_to_workflow(workflow: Any, payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Patch train_eval load nodes onto the resolved freeze / dataset_id. No-op for other templates."""
    request = payload if isinstance(payload, dict) else {}
    metadata = getattr(workflow, "metadata", None) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    template_role = str(metadata.get("template_role") or request.get("template_role") or "").strip()
    slot = str(request.get("slot") or metadata.get("slot") or "").strip()
    if slot not in _PV_SLOTS:
        return None
    if template_role and template_role not in _TRAIN_ROLES:
        return None
    if not template_role:
        workflow_id = str(getattr(workflow, "id", "") or "")
        if "train-eval" not in workflow_id and "train_eval" not in workflow_id:
            return None

    nodes = list(getattr(workflow, "nodes", None) or [])
    explicit_id = str(request.get("dataset_id") or "").strip() or None
    if not explicit_id:
        for node in nodes:
            config = getattr(getattr(node, "data", None), "config", None)
            if _function_id(config) not in _LOAD_FUNCTION_IDS:
                continue
            path = _file_path(config)
            if _looks_like_user_chosen(path):
                return {
                    "dataset_id": None,
                    "file_path": path,
                    "kind": "live_nodes",
                    "reason": "keep_live_nodes_path",
                }

    source = resolve_train_source(slot=slot, dataset_id=explicit_id, explicit=bool(explicit_id))
    if source is None:
        return None

    patched = 0
    for node in nodes:
        config = getattr(getattr(node, "data", None), "config", None)
        function_id = _function_id(config)
        if function_id not in _LOAD_FUNCTION_IDS:
            continue
        path = _file_path(config)
        if explicit_id or _looks_like_placeholder(path, slot) or not path:
            _set_node_config(
                node,
                {
                    "file_path": source["file_path"],
                    "dataset_id": source["dataset_id"],
                },
            )
            patched += 1
    if patched == 0:
        return source
    source["patched_load_nodes"] = patched
    return source
