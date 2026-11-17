# @AI_GENERATED
"""平台级数据集目录（数据集切片第 2b 步）。

把三件事分开，避免"接了数据但不知道能不能用"：

- **检测**（`inspect_dataset`）：对真实文件跑 `compute_dataset_facts`，并判定「适用路径」；
- **发布**（`publish_dataset`）：产出**不可变**条目，同一内容幂等命中；
- **选用**（`list_catalog` / `get_catalog_entry`）：新建项目时从这里挑，再挂载到项目。

目录是**平台级**的：数据集是平台资产，多个项目共享同一份发布条目，
因此**不**按 `(project_id, slot)` 分区（这与 `pv_projects` 的项目级 store 有意不同）。

首批条目 = 三条路径各自的**累计训练数据集**
（`data/slot_datasets/<slot>/snapshots/` 下的冻结快照）——用户明确要求的起点；
后续新到的数据集再增量检测 + 发布。

「适用路径」语义：
- 普通外部数据：`applicable` = 标签粒度落在路径的 `truth_granularity` 内；
- 路径累计冻结快照：它是某条路径长期准入后形成的**路径资产**，只适用于自己的
  `origin_slot`，即使底层还保留 point 标签也不跨路径复用；
- 「够不够用」由 `coverage` 字段独立报告（`sufficient` / `gaps` / `hint`），不否决适用性。

理由：普通数据的粒度口径是**硬**约束——设备日标签喂 `pv_point` 是语义错误；
累计快照在硬口径上再叠加路径所有权；覆盖门槛则是随用途变化的**软**约束。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.pv_projects.errors import ScopeError
from services.pv_projects.facts import COVERAGE_THRESHOLDS, compute_dataset_facts
from services.pv_projects.scope import PRODUCT_SLOTS, ScopeContext
from services.pv_projects.source_resolver import (
    SUPPORTED_EXTENSIONS,
    resolve_dataset_unit,
    source_base,
)
from services.pv_projects.workflows import PATH_CONTRACT_BY_SLOT

#: 目录存储的锁键（平台级；与项目 scope 无关）。
CATALOG_LOCK_KEY = "__dataset_catalog__"

#: 目录条目的来源类型。
ORIGIN_PATH_CUMULATIVE = "path_cumulative_snapshot"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _content_digest(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def catalog_path() -> Path:
    """平台级目录文件路径（**不含** projects/<pid>/）。"""
    from services.pv_projects.repositories import storage_base

    return storage_base() / "data" / "pv_projects" / "dataset_catalog.json"


def _read_catalog() -> dict[str, Any]:
    from services.pv_projects.repositories import _read_json

    payload = _read_json(catalog_path())
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return payload
    return {"entries": [], "updated_at": None}


# ---------------------------------------------------------------------------
# 发现：三条路径的累计训练数据集
# ---------------------------------------------------------------------------

def discover_path_cumulative_datasets() -> list[dict[str, Any]]:
    """扫描 `data/slot_datasets/<slot>/snapshots/`，每条路径给出一个累计训练数据集。

    多个快照时按**文件名降序**取第一个——确定性规则，不依赖文件 mtime
    （mtime 在批量生成时会相同，导致结果不可复现）。
    """
    base = source_base()
    out: list[dict[str, Any]] = []
    for slot in PRODUCT_SLOTS:
        d = base / "data" / "slot_datasets" / slot / "snapshots"
        if not d.is_dir():
            continue
        files = sorted(
            (
                p
                for p in d.iterdir()
                if p.is_file() and not p.is_symlink() and p.suffix.lower() in SUPPORTED_EXTENSIONS
            ),
            key=lambda p: p.name,
            reverse=True,
        )
        if not files:
            continue
        latest = files[0]
        try:
            st = latest.stat()
        except OSError:
            continue
        out.append(
            {
                "dataset_ref": f"slot_datasets/{slot}/snapshots/{latest.name}",
                "origin": ORIGIN_PATH_CUMULATIVE,
                "origin_slot": slot,
                "display_name": f"{slot} 累计训练集（冻结快照）",
                "size_bytes": int(st.st_size),
                "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "candidate_count": len(files),
            }
        )
    return out


# ---------------------------------------------------------------------------
# 检测：facts + 适用路径
# ---------------------------------------------------------------------------

def evaluate_applicable_paths(facts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """判定该数据集适用于哪些路径——**只看标签粒度口径**。"""
    detected = str(facts.get("label_granularity_detected") or "unknown")
    out: dict[str, dict[str, Any]] = {}
    for slot, contract in PATH_CONTRACT_BY_SLOT.items():
        allowed = list(contract.get("truth_granularity") or ())
        if detected == "unknown":
            # 无标签列 → 粒度不可判。不因此否决（无标签数据仍可做无标签实验），但在原因里标明。
            applicable = True
            reason = "未检出标签列（粒度不可判），不因此否决；请确认是否用于监督训练"
        else:
            applicable = detected in allowed
            reason = (
                f"granularity={detected} 落在 {allowed} 内"
                if applicable
                else f"granularity={detected} 不在 {allowed} 内"
            )
        out[slot] = {
            "applicable": applicable,
            "reason": reason,
            "label_granularity_detected": detected,
            "truth_granularity": allowed,
        }
    return out


def _apply_path_cumulative_ownership(entry: dict[str, Any]) -> dict[str, Any]:
    """路径累计训练快照只归自己的 ``origin_slot``，不做跨路径复用。

    普通上传数据集的 ``applicable_paths`` — 适用路径，仍由标签粒度合同计算；但
    ``path_cumulative_snapshot`` — 路径累计冻结快照，是某条路径长期准入、冻结后的
    **路径资产**，不能因为底层还保留 point 标签，就同时展示成另外两条路径的数据集。

    返回浅拷贝，不改传入对象。保留三条路径的说明键，但只有来源路径
    ``applicable=true``；这样旧目录条目无需改盘也能立刻按新语义读取。
    """
    cumulative_slot = _path_cumulative_slot(str(entry.get("dataset_ref") or ""))
    if str(entry.get("origin") or "") != ORIGIN_PATH_CUMULATIVE and not cumulative_slot:
        return dict(entry)
    origin_slot = cumulative_slot or str(entry.get("origin_slot") or "").strip()
    if origin_slot not in PRODUCT_SLOTS:
        return dict(entry)

    raw_paths = entry.get("applicable_paths") if isinstance(entry.get("applicable_paths"), dict) else {}
    constrained: dict[str, dict[str, Any]] = {}
    for slot in PRODUCT_SLOTS:
        current = raw_paths.get(slot) if isinstance(raw_paths.get(slot), dict) else {}
        own_path = slot == origin_slot
        constrained[slot] = {
            **current,
            "applicable": own_path,
            "reason": (
                f"路径累计训练快照固定归属 {origin_slot}，只供本路径训练 / 复验"
                if own_path
                else f"路径累计训练快照归属 {origin_slot}，禁止跨路径复用到 {slot}"
            ),
        }
    return {
        **entry,
        "origin": ORIGIN_PATH_CUMULATIVE,
        "origin_slot": origin_slot,
        "applicable_paths": constrained,
    }


def _coverage_view(facts: dict[str, Any]) -> dict[str, Any]:
    gaps = list(facts.get("coverage_gaps") or [])
    sufficient = bool(facts.get("sufficient_coverage"))
    return {
        "sufficient": sufficient,
        "gaps": gaps,
        "hint": "usable" if sufficient else "experiment_only",
        "thresholds": dict(COVERAGE_THRESHOLDS),
    }


def infer_origin_slot(dataset_ref: str) -> Optional[str]:
    """从引用本身推断它属于哪条路径。

    `slot_datasets/<slot>/...` 与任意含 `<slot>` 路径段的引用都能推出来；
    推不出返回 None（不猜）。
    """
    parts = str(dataset_ref or "").replace("\\", "/").split("/")
    if len(parts) >= 2 and parts[0] == "slot_datasets" and parts[1] in PRODUCT_SLOTS:
        return parts[1]
    for slot in PRODUCT_SLOTS:
        if slot in parts:
            return slot
    return None


def _path_cumulative_slot(dataset_ref: str) -> Optional[str]:
    """受信任地从冻结快照引用识别路径累计来源；其它形态返回 None。

    客户端传的 ``origin`` 只是元数据提示，不能决定服务端所有权。只有严格匹配
    ``slot_datasets/<slot>/snapshots/<file>`` 才认作路径累计快照。
    """
    parts = str(dataset_ref or "").replace("\\", "/").strip("/").split("/")
    if (
        len(parts) >= 4
        and parts[0] == "slot_datasets"
        and parts[1] in PRODUCT_SLOTS
        and parts[2] == "snapshots"
        and parts[-1]
    ):
        return parts[1]
    return None


def inspect_dataset(
    dataset_ref: str,
    *,
    mapping: dict[str, Any],
    label_policy: Optional[dict[str, Any]] = None,
    origin_slot: Optional[str] = None,
    origin: str = "manual",
    display_name: Optional[str] = None,
) -> dict[str, Any]:
    """跑质量检测并产出目录条目草稿（**不落盘**）。"""
    facts = compute_dataset_facts(dataset_ref, mapping=mapping, label_policy=label_policy)
    cumulative_slot = _path_cumulative_slot(dataset_ref)
    requested_origin_slot = str(origin_slot or "").strip() or None
    if cumulative_slot and requested_origin_slot and requested_origin_slot != cumulative_slot:
        raise ScopeError(
            "cumulative_origin_slot_mismatch",
            f"累计快照引用归属 {cumulative_slot}，不能声明为 {requested_origin_slot}。",
            next_action=f"使用 origin_slot={cumulative_slot}",
        )
    resolved_origin_slot = cumulative_slot or requested_origin_slot or infer_origin_slot(dataset_ref)
    resolved_origin = ORIGIN_PATH_CUMULATIVE if cumulative_slot else origin
    draft = {
        "dataset_ref": dataset_ref,
        "display_name": display_name or dataset_ref,
        "origin": resolved_origin,
        "origin_slot": resolved_origin_slot,
        "mapping": dict(mapping),
        "label_policy": dict(label_policy or {}),
        "facts": facts,
        "applicable_paths": evaluate_applicable_paths(facts),
        "coverage": _coverage_view(facts),
        "shard_count": int(facts.get("shard_count") or 1),
    }
    return _apply_path_cumulative_ownership(draft)


# ---------------------------------------------------------------------------
# 发布：不可变 + 幂等
# ---------------------------------------------------------------------------

def publish_dataset(draft: dict[str, Any]) -> dict[str, Any]:
    """把检测草稿发布成**不可变**目录条目；同内容摘要幂等命中。"""
    from services.pv_projects.repositories import _atomic_write_json, _scope_lock

    dataset_ref = str(draft.get("dataset_ref") or "").strip()
    if not dataset_ref:
        from services.pv_projects.errors import ScopeError

        raise ScopeError("missing_dataset_ref", "发布数据集需要 dataset_ref。")

    digest = _content_digest(
        {
            "dataset_ref": dataset_ref,
            "mapping": draft.get("mapping") or {},
            "label_policy": draft.get("label_policy") or {},
            "facts": draft.get("facts") or {},
        }
    )

    with _scope_lock(CATALOG_LOCK_KEY):
        payload = _read_catalog()
        for entry in payload["entries"]:
            if str(entry.get("content_digest")) == digest:
                return {
                    **_apply_path_cumulative_ownership(entry),
                    "idempotent_hit": True,
                }

        entry = _apply_path_cumulative_ownership({
            "entry_id": f"dsc-{uuid.uuid4().hex[:12]}",
            "dataset_ref": dataset_ref,
            "display_name": draft.get("display_name") or dataset_ref,
            "origin": draft.get("origin") or "manual",
            "origin_slot": draft.get("origin_slot"),
            "mapping": draft.get("mapping") or {},
            "label_policy": draft.get("label_policy") or {},
            "facts": draft.get("facts") or {},
            "applicable_paths": draft.get("applicable_paths") or {},
            "coverage": draft.get("coverage") or {},
            "shard_count": int(draft.get("shard_count") or 1),
            "content_digest": digest,
            "immutable": True,
            "published_at": _now_iso(),
        })
        payload["entries"].append(entry)
        payload["updated_at"] = _now_iso()
        _atomic_write_json(catalog_path(), payload)

    return {**entry, "idempotent_hit": False}


def list_catalog() -> list[dict[str, Any]]:
    """列出已发布条目（平台级；不按项目过滤）。"""
    entries = _read_catalog()["entries"]
    return sorted(
        (
            _apply_path_cumulative_ownership(e)
            for e in entries
            if isinstance(e, dict)
        ),
        key=lambda e: (str(e.get("origin_slot") or ""), str(e.get("dataset_ref") or "")),
    )


def get_catalog_entry(entry_id: str) -> Optional[dict[str, Any]]:
    target = str(entry_id or "").strip()
    for entry in _read_catalog()["entries"]:
        if isinstance(entry, dict) and str(entry.get("entry_id")) == target:
            return _apply_path_cumulative_ownership(entry)
    return None


def assert_entry_mountable(entry: dict[str, Any], target_slot: str) -> str:
    """校验目录条目能否挂到目标路径；服务端 fail-closed，不能只靠 UI 隐藏选项。

    - 路径累计快照只能挂回自己的 ``origin_slot``；
    - 普通数据必须满足该路径 ``applicable_paths[slot].applicable=true``。
    """
    slot = str(target_slot or "").strip()
    if slot not in PRODUCT_SLOTS:
        raise ScopeError(
            "invalid_mount_slot",
            f"挂载路径必须是 {list(PRODUCT_SLOTS)} 之一，收到 {slot!r}。",
        )

    normalized = _apply_path_cumulative_ownership(entry)
    origin_slot = str(normalized.get("origin_slot") or "").strip()
    if (
        str(normalized.get("origin") or "") == ORIGIN_PATH_CUMULATIVE
        and origin_slot in PRODUCT_SLOTS
        and slot != origin_slot
    ):
        raise ScopeError(
            "cumulative_cross_path_forbidden",
            f"{origin_slot} 的累计训练快照不能挂到 {slot}。",
            next_action=f"挂载到 {origin_slot}",
        )

    applicability = (normalized.get("applicable_paths") or {}).get(slot)
    if not isinstance(applicability, dict) or applicability.get("applicable") is not True:
        reason = applicability.get("reason") if isinstance(applicability, dict) else "缺少适用性结论"
        raise ScopeError(
            "dataset_not_applicable_to_slot",
            f"数据集不适用于 {slot}：{reason}",
            next_action="选择标记为适用的诊断路径",
        )
    return slot


def resolve_entry_shards(entry: dict[str, Any]) -> list[Path]:
    """把条目解析回真实分片路径（挂载/复检时用）。"""
    return list(resolve_dataset_unit(str(entry.get("dataset_ref") or ""))["shard_paths"])


# ---------------------------------------------------------------------------
# 挂载：把目录条目装进某个项目（数据集切片第 2c 步）
# ---------------------------------------------------------------------------

def mount_into_project(scope: ScopeContext, entry_id: str) -> dict[str, Any]:
    """把一个已发布目录条目挂载进项目：数据资产 + 画像 + 不可变数据版本。

    幂等键 = 条目的 `content_digest`：同一内容重复挂载返回既有三件套，不重复建资产 / 版本。

    「真实数据引用」落在 `asset.dataset_ref` 与 `profile.facts.source_ref`；
    **不**改 `dataset_version.artifact_ref` —— 那是项目内 scoped 版本元数据引用，
    property test P-LINEAGE-01 要求它以 `data/slot_datasets/projects/<pid>/` 开头。
    """
    from services.pv_projects import datasets as dataset_service
    from services.pv_projects.stores import dataset_assets

    scope.assert_writable()

    entry = get_catalog_entry(entry_id)
    if entry is None:
        raise ScopeError(
            "catalog_entry_not_found",
            f"目录里没有条目 {entry_id!r}。",
            next_action="先 GET /api/pv-projects/catalog 列出可用条目",
        )

    digest = str(entry.get("content_digest") or "")
    dataset_ref = str(entry.get("dataset_ref") or "")
    assert_entry_mountable(entry, scope.require_slot())

    # fail-closed：条目引用的分片必须**仍可解析到真实文件**（平台目录可能被移动 / 删除）。
    resolve_entry_shards(entry)

    if digest:
        for asset in dataset_service.list_dataset_assets(scope):
            if (
                str(asset.get("source_kind") or "") == "catalog"
                and str(asset.get("content_digest") or "") == digest
            ):
                return _mount_result(scope, entry, asset, idempotent_hit=True)

    asset = dataset_service.register_dataset_asset(
        scope,
        source_kind="catalog",
        file_name=Path(dataset_ref).name,
        dataset_ref=dataset_ref,
        catalog_entry_id=str(entry.get("entry_id") or entry_id),
        content_digest=digest or None,
    )
    profile = dataset_service.save_dataset_profile(
        scope,
        dataset_id=asset["dataset_id"],
        mapping=dict(entry.get("mapping") or {}),
        facts=dict(entry.get("facts") or {}),
        label_policy=dict(entry.get("label_policy") or {}),
    )
    version = dataset_service.publish_dataset_version(
        scope,
        dataset_id=asset["dataset_id"],
        dataset_profile_id=profile["dataset_profile_id"],
    )
    # 回填挂载结果：幂等命中时可直接从 asset 读出三件套 id，无需再遍历 profile / version。
    stamped = dataset_assets.replace(
        scope,
        asset["dataset_id"],
        {
            **asset,
            "dataset_profile_id": profile["dataset_profile_id"],
            "dataset_version_id": version["dataset_version_id"],
        },
    )
    return _mount_result(scope, entry, stamped, idempotent_hit=False)


def _mount_result(
    scope: ScopeContext, entry: dict[str, Any], asset: dict[str, Any], *, idempotent_hit: bool
) -> dict[str, Any]:
    # 两个入口（创建项目挂载 / 后续手工挂载）都汇聚在这里；包括 digest 幂等早返回分支。
    # 模型继承失败不回滚已经成功的数据挂载，结果通过独立字段如实回显。
    try:
        from services.pv_projects import governance as governance_service

        model_inheritance = governance_service.ensure_inherited_baseline(
            scope,
            entry=entry,
            asset=asset,
            link_basis="mount_time",
        )
    except Exception as exc:  # noqa: BLE001 — 数据资产三件套是主链，模型关联是附加链
        model_inheritance = {
            "status": "error",
            "idempotent_hit": False,
            "inherited_baseline": None,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {
        **scope.echo(),
        "mounted": True,
        "idempotent_hit": bool(idempotent_hit),
        "entry_id": entry.get("entry_id"),
        "dataset_asset": asset,
        "dataset_profile_id": asset.get("dataset_profile_id"),
        "dataset_version_id": asset.get("dataset_version_id"),
        "dataset_ref": asset.get("dataset_ref"),
        "model_inheritance": model_inheritance,
    }


# @AI_GENERATED: end
