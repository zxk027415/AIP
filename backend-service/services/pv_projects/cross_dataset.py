# @AI_GENERATED
"""跨数据集验证批次与证据聚合（design D-GOV-01；任务 8.1–8.3）。

红线（不得改写）：
- 跨数据集验证只证明**迁移 / 交互 / 隔离**，`governance_effect="none"`：其证据 ID 用 `xdpv-` 前缀，
  绝不能当作模型正式复验 `verification_id`（governance 已在 `_assert_not_product_validation_id` 拒绝）。
- **零污染（SHA256）**：验证只读输入源，记录每个源的内容哈希；重算必须一致，
  验证过程不写回、不修改任何生产源或其他项目 / 数据集（A/B scope 隔离）。
- 离线基准证据（offline_benchmark_evidence）只读登记 + 解释；`governance_effect="none"`。
  已知存在 leaky_device_ical 与 calibration CSV，但**没有** calibration_audit_id 注册表，如实标注。

本模块只写 scoped 项目证据（validation_batches / benchmark_evidence），不触碰生产 registry / 指针。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services.pv_projects.governance import GovernanceGateError
from services.pv_projects.scope import ScopeContext
from services.pv_projects.stores import benchmark_evidence as _benchmark_evidence, validation_batches as _validation_batches

#: 跨数据集产品复验 ID 前缀（与 governance.PRODUCT_VALIDATION_ID_PREFIXES 对齐）。
VALIDATION_ID_PREFIX = "xdpv-"

#: 跨数据集验证维度（只证明这三件事，不证明模型精度 / 治理）。
VALIDATION_DIMENSIONS: tuple[str, ...] = ("migration", "interaction", "isolation")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(payload: Any) -> str:
    """对任意可序列化对象做稳定 SHA256（sort_keys，UTF-8）。"""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _dataset_source_hash(dataset: dict[str, Any]) -> str:
    """对单个数据集**输入源描述**做内容哈希（只读快照，用于零污染前后比对）。"""
    return _sha256(
        {
            "dataset_key": dataset.get("dataset_key"),
            "source_ref": dataset.get("source_ref"),        # 相对引用，不含绝对路径
            "dataset_version_id": dataset.get("dataset_version_id"),
            "content_digest": dataset.get("content_digest"),
        }
    )


class CrossDatasetValidationService:
    """跨数据集验证：创建批次、登记逐数据集结果、聚合证据、校验零污染。"""

    # -- 创建批次 ----------------------------------------------------------

    @staticmethod
    def create_batch(
        scope: ScopeContext,
        *,
        datasets: list[dict[str, Any]],
        evaluation_contract: Optional[dict[str, Any]] = None,
        note: Optional[str] = None,
    ) -> dict[str, Any]:
        """创建一个跨数据集验证批次（scoped）。记录每个源的输入哈希（零污染基线）。"""
        scope.assert_writable()
        if not datasets:
            raise GovernanceGateError(
                "no_datasets",
                "跨数据集验证至少需要一个数据集。",
                category="business_gate_blocked",
            )
        entries: list[dict[str, Any]] = []
        for ds in datasets:
            entries.append(
                {
                    "dataset_key": ds.get("dataset_key"),
                    "source_ref": ds.get("source_ref"),
                    "dataset_version_id": ds.get("dataset_version_id"),
                    "content_digest": ds.get("content_digest"),
                    "input_source_hash": _dataset_source_hash(ds),  # 零污染基线
                    "result": None,  # 未跑
                }
            )
        batch = {
            "validation_id": f"{VALIDATION_ID_PREFIX}{uuid.uuid4().hex[:12]}",
            "governance_effect": "none",  # 红线：无治理效力
            "evaluation_contract": evaluation_contract or {},
            "datasets": entries,
            "dimensions": list(VALIDATION_DIMENSIONS),
            "status": "created",
            "note": note,
            "governance_note": "跨数据集验证只证明迁移 / 交互 / 隔离，不具模型治理效力；validation_id 不能作为正式复验证据。",
            "created_at": _now_iso(),
        }
        return _validation_batches.append(scope, batch)

    # -- 登记逐数据集结果 --------------------------------------------------

    @staticmethod
    def record_result(
        scope: ScopeContext,
        validation_id: str,
        *,
        dataset_key: str,
        metrics: dict[str, Any],
        dimension_findings: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """登记某数据集在批次中的结果（只读评测产物；不回写源，不改治理）。"""
        scope.assert_writable()
        batch = _validation_batches.find(scope, validation_id)
        if batch is None:
            raise GovernanceGateError(
                "validation_batch_not_found",
                f"当前项目下找不到验证批次 {validation_id!r}。",
                category="business_gate_blocked",
            )
        found = False
        for entry in batch.get("datasets", []):
            if str(entry.get("dataset_key")) == str(dataset_key):
                entry["result"] = {
                    "metrics": metrics or {},
                    "dimension_findings": dimension_findings or {},
                    # 结果哈希与输入哈希分离；输入哈希应保持不变（零污染）。
                    "post_run_input_source_hash": _dataset_source_hash(entry),
                    "recorded_at": _now_iso(),
                }
                found = True
                break
        if not found:
            raise GovernanceGateError(
                "dataset_not_in_batch",
                f"数据集 {dataset_key!r} 不在批次 {validation_id!r} 中。",
                category="business_gate_blocked",
            )
        batch["status"] = "running"
        batch["updated_at"] = _now_iso()
        return _validation_batches.replace(scope, validation_id, batch)

    # -- 聚合证据（ValidationEvidenceBundle） ------------------------------

    @staticmethod
    def aggregate_evidence(scope: ScopeContext, validation_id: str) -> dict[str, Any]:
        """聚合跨数据集证据束：逐数据集结果 + 迁移 / 交互 / 隔离维度汇总；governance_effect=none。"""
        batch = _validation_batches.find(scope, validation_id)
        if batch is None:
            raise GovernanceGateError(
                "validation_batch_not_found",
                f"当前项目下找不到验证批次 {validation_id!r}。",
                category="business_gate_blocked",
            )
        datasets = batch.get("datasets", [])
        completed = [d for d in datasets if d.get("result")]
        per_dataset = [
            {
                "dataset_key": d.get("dataset_key"),
                "dataset_version_id": d.get("dataset_version_id"),
                "metrics": (d.get("result") or {}).get("metrics", {}),
                "dimension_findings": (d.get("result") or {}).get("dimension_findings", {}),
            }
            for d in completed
        ]
        bundle = {
            **scope.echo(),
            "validation_id": validation_id,
            "governance_effect": "none",
            "dataset_count": len(datasets),
            "completed_count": len(completed),
            "per_dataset": per_dataset,
            "dimension_summary": {
                dim: [pd["dataset_key"] for pd in per_dataset if (pd["dimension_findings"] or {}).get(dim)]
                for dim in VALIDATION_DIMENSIONS
            },
            "can_be_verification_evidence": False,  # 红线：不能当正式复验
            "note": "证据束仅证明迁移 / 交互 / 隔离；不能晋升为模型治理证据，不能设指针 / Promote。",
        }
        return bundle

    # -- 零污染校验（SHA256 前后一致 + A/B 隔离） --------------------------

    @staticmethod
    def verify_zero_pollution(scope: ScopeContext, validation_id: str) -> dict[str, Any]:
        """校验零污染：每个数据集的输入源哈希在跑前 / 跑后一致（验证只读，不写回源）。"""
        batch = _validation_batches.find(scope, validation_id)
        if batch is None:
            raise GovernanceGateError(
                "validation_batch_not_found",
                f"当前项目下找不到验证批次 {validation_id!r}。",
                category="business_gate_blocked",
            )
        checks: list[dict[str, Any]] = []
        polluted = False
        for entry in batch.get("datasets", []):
            baseline = entry.get("input_source_hash")
            recompute = _dataset_source_hash(entry)
            post = (entry.get("result") or {}).get("post_run_input_source_hash")
            ok = baseline == recompute and (post is None or post == baseline)
            if not ok:
                polluted = True
            checks.append(
                {
                    "dataset_key": entry.get("dataset_key"),
                    "baseline_hash": baseline,
                    "recomputed_hash": recompute,
                    "post_run_hash": post,
                    "unchanged": ok,
                }
            )
        return {
            **scope.echo(),
            "validation_id": validation_id,
            "zero_pollution": not polluted,
            "checks": checks,
        }

    @staticmethod
    def list_batches(scope: ScopeContext) -> list[dict[str, Any]]:
        return _validation_batches.list(scope)


# ---------------------------------------------------------------------------
# 8.3 只读离线基准证据
# ---------------------------------------------------------------------------

def register_offline_benchmark_evidence(
    scope: ScopeContext,
    *,
    benchmark_source: str,
    manifest_ref: Optional[str] = None,
    metrics: Optional[dict[str, Any]] = None,
    calibration_note: Optional[str] = None,
) -> dict[str, Any]:
    """只读登记离线基准证据版本（governance_effect=none）。

    如实标注：存在 leaky_device_ical 与 calibration CSV，但没有 calibration_audit_id 注册表，
    因此 i_cal 校准只能作为只读诚实标注，不构成新建评测能力。
    """
    scope.assert_writable()
    record = {
        "benchmark_evidence_version": f"obe-{uuid.uuid4().hex[:12]}",
        "governance_effect": "none",
        "read_only": True,
        "benchmark_source": benchmark_source,
        "manifest_ref": manifest_ref,  # 相对引用（如 PVDAQ run_manifest.json）
        "metrics": metrics or {},
        "calibration_audit_id": None,  # 尚无注册表，如实置空
        "calibration_note": calibration_note
        or "存在 leaky_device_ical 与 calibration CSV，但无 calibration_audit_id 注册表；i_cal 仅只读标注，不构成评测能力。",
        "content_hash": _sha256({"benchmark_source": benchmark_source, "manifest_ref": manifest_ref, "metrics": metrics or {}}),
        "registered_at": _now_iso(),
    }
    return _benchmark_evidence.append(scope, record)


def list_offline_benchmark_evidence(scope: ScopeContext) -> list[dict[str, Any]]:
    return _benchmark_evidence.list(scope)


# @AI_GENERATED: end
