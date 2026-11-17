"""Model candidate registration with workflow provenance gate."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.slot_governance.provenance import ProvenanceError, assert_product_slot, validate_execution_provenance

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_governance"


def _candidates_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "model_candidates.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_candidates(slot: str) -> list[dict[str, Any]]:
    path = _candidates_path(slot)
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        items = payload.get("candidates")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_candidates(slot: str, items: list[dict[str, Any]]) -> None:
    path = _candidates_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"slot": slot, "candidates": items}, handle, ensure_ascii=False, indent=2)


def list_model_candidates(slot: str) -> list[dict[str, Any]]:
    assert_product_slot(slot)
    return _load_candidates(slot)


def find_model_candidate(model_candidate_id: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Search all slot partitions for a candidate id."""
    root = _DATA_DIR
    if not root.is_dir():
        return None, None
    target = str(model_candidate_id or "").strip()
    if not target:
        return None, None
    for slot_dir in root.iterdir():
        if not slot_dir.is_dir():
            continue
        for item in _load_candidates(slot_dir.name):
            if item.get("model_candidate_id") == target:
                return item.get("slot") or slot_dir.name, item
    return None, None


# @AI_GENERATED: workflow provenance with optional cumulative-retrain lineage

def register_model_candidate(
    *,
    slot: str,
    source_workflow_id: str,
    source_execution_id: str,
    model_artifact_ref: str,
    source_workflow_version: Optional[str] = None,
    model_ref: Optional[str] = None,
    scenario_key: Optional[str] = None,
    source_kind: Optional[str] = None,
    source_retrain_request_id: Optional[str] = None,
    source_snapshot_id: Optional[str] = None,
    evaluation_contract: Optional[dict[str, Any]] = None,
    project_id: Optional[str] = None,
    source_project_candidate_id: Optional[str] = None,
) -> dict[str, Any]:
    """Register a governed artifact after validating its persisted execution.

    Cumulative retraining callers may attach request/snapshot lineage, but those
    fields supplement rather than replace the mandatory workflow provenance.

    项目归属（`project_id` — 产出该模型的项目 ID；`source_project_candidate_id` —
    项目侧候选 ID `cand-*`）由领域桥传入，供「模型部署 / 精度运营」显示模型来自哪个项目。
    显式落字段而不是靠 `model_ref` 前缀反猜：`model_ref` 的语义是「调用方自定引用」，
    不保证一定是 `cand-*`（累计重训来源就填的是 artifact 路径）。
    """
    if scenario_key not in (None, ""):
        raise ProvenanceError(
            "scenario_key_not_allowed",
            "scenario_key is not allowed; send slot directly",
        )

    provenance = validate_execution_provenance(
        slot=slot,
        source_workflow_id=source_workflow_id,
        source_execution_id=source_execution_id,
        model_artifact_ref=model_artifact_ref,
    )

    if source_workflow_version not in (None, ""):
        provenance["source_workflow_version"] = source_workflow_version

    candidate_id = f"mc-{uuid.uuid4().hex[:12]}"
    record: dict[str, Any] = {
        "model_candidate_id": candidate_id,
        "slot": slot,
        "source_workflow_id": provenance["source_workflow_id"],
        "source_workflow_version": provenance.get("source_workflow_version"),
        "source_execution_id": provenance["source_execution_id"],
        "model_artifact_ref": provenance["model_artifact_ref"],
        "model_ref": model_ref or candidate_id,
        "registered_at": _now_iso(),
        "status": "registered",
        "execution_status": provenance.get("execution_status"),
    }
    if str(source_kind or "").strip():
        record["source_kind"] = str(source_kind).strip()
    if str(source_retrain_request_id or "").strip():
        record["source_retrain_request_id"] = str(source_retrain_request_id).strip()
    if str(source_snapshot_id or "").strip():
        record["source_snapshot_id"] = str(source_snapshot_id).strip()
    if evaluation_contract is not None:
        record["evaluation_contract"] = dict(evaluation_contract)
    # 项目归属：只在真有值时写字段，保持与历史记录（无这两个键）的形状兼容。
    if str(project_id or "").strip():
        record["project_id"] = str(project_id).strip()
    if str(source_project_candidate_id or "").strip():
        record["source_project_candidate_id"] = str(source_project_candidate_id).strip()

    items = _load_candidates(slot)
    items.append(record)
    _save_candidates(slot, items)
    return record
# @AI_GENERATED: end

# @AI_GENERATED
def register_retrain_model_candidate(
    *,
    slot: str,
    retrain_request_id: str,
    snapshot_id: str | None,
    model_artifact_ref: str,
    evaluation_contract: Optional[dict[str, Any]] = None,
    model_ref: Optional[str] = None,
) -> dict[str, Any]:
    """登记累计重训产物，不伪造工作流 execution provenance。

    ``source_kind`` 明确标记为 ``cumulative_retrain``；同一重训请求或同一工件
    重试时返回原记录，供 registry challenger 和调度器共享唯一模型真源。
    """
    assert_product_slot(slot)
    request_id = str(retrain_request_id or "").strip()
    artifact = str(model_artifact_ref or "").replace("\\", "/").strip()
    if not request_id:
        raise ProvenanceError("missing_retrain_request", "retrain_request_id is required")
    if not artifact:
        raise ProvenanceError("missing_model_artifact", "model_artifact_ref is required")

    items = _load_candidates(slot)
    for item in items:
        if (
            str(item.get("source_kind") or "") == "cumulative_retrain"
            and (
                str(item.get("source_retrain_request_id") or "") == request_id
                or str(item.get("model_artifact_ref") or "").replace("\\", "/") == artifact
            )
        ):
            return item

    candidate_id = f"mc-{uuid.uuid4().hex[:12]}"
    contract = dict(evaluation_contract or {})
    record: dict[str, Any] = {
        "model_candidate_id": candidate_id,
        "slot": slot,
        "source_kind": "cumulative_retrain",
        "source_workflow_id": None,
        "source_workflow_version": None,
        "source_execution_id": None,
        "source_retrain_request_id": request_id,
        "source_snapshot_id": str(snapshot_id or "").strip() or None,
        "model_artifact_ref": artifact,
        "model_ref": model_ref or candidate_id,
        "evaluation_contract": contract,
        "registered_at": _now_iso(),
        "status": "registered",
        "execution_status": "succeeded",
    }
    items.append(record)
    _save_candidates(slot, items)
    return record
# @AI_GENERATED: end
