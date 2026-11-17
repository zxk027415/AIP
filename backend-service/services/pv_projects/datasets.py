# @AI_GENERATED
"""数据接入服务：上传 / 平台资产 / 授权连接器（项目级数据资产）。

设计依据：design.md §13（数据接入向导第 1–3 步）、§26.2/§26.6；
requirements.md R13.5、R13.7、R13.25、NFR1.1–NFR1.5、NFR4.1–NFR4.3。

红线：
- 浏览器请求不接收服务器文件系统路径；只接收上传（相对 upload_ref）、平台 `asset_id` 或 `connector_id`。
- 持久化只保存 `asset_id` / `connector_id` + 逻辑对象描述，绝不保存凭据 / token / 连接串 / 机器挂载路径。
- 长连接器物化任务持久化 task_id + 状态，刷新后可按 task_id 恢复。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import hashlib
import json

from services.pv_projects.errors import ScopeError
from services.pv_projects.facts import compute_dataset_facts
from services.pv_projects.paths import assert_relative_ref, is_machine_absolute, scoped_relative_path
from services.pv_projects.scope import ScopeContext
from services.pv_projects.source_resolver import (
    SUPPORTED_EXTENSIONS,
    resolve_dataset_unit,
    to_source_alias_ref,
)
from services.pv_projects.stores import (
    dataset_assets,
    dataset_profiles,
    dataset_versions,
    materialization_tasks,
)

_DATASETS_ROOT = "data/slot_datasets"

#: 允许的数据来源类型。
#: `catalog` = 平台数据集目录条目（已发布、带质量检测结论），与浏览器上传（`upload`）语义不同：
#: 它的数据引用是**来源根内的相对引用**（如 `slot_datasets/pv_day/snapshots/x.parquet`）。
SOURCE_KINDS = ("upload", "platform_asset", "connector", "catalog")

#: 物化任务状态。
MATERIALIZATION_STATUSES = ("pending", "running", "completed", "failed", "cancelled", "timeout")

#: 禁止出现在逻辑描述中的凭据类关键字（防止误把连接串 / 口令写进逻辑描述）。
_CREDENTIAL_HINTS = ("password", "passwd", "secret", "token", "access_key", "secret_key", "://")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _assert_no_credentials(text: Optional[str], *, field: str) -> None:
    if not text:
        return
    lowered = str(text).lower()
    for hint in _CREDENTIAL_HINTS:
        if hint in lowered:
            raise ScopeError(
                "credential_like_value_forbidden",
                f"{field} 疑似包含凭据 / 连接串（命中 {hint!r}）；只允许逻辑对象描述，不保存凭据。",
                next_action="移除凭据 / 连接串，只填写逻辑对象名称与说明",
            )


def register_dataset_asset(
    scope: ScopeContext,
    *,
    source_kind: str,
    file_name: Optional[str] = None,
    upload_ref: Optional[str] = None,
    asset_id: Optional[str] = None,
    connector_id: Optional[str] = None,
    logical_object: Optional[str] = None,
    logical_description: Optional[str] = None,
    catalog_entry_id: Optional[str] = None,
    dataset_ref: Optional[str] = None,
    content_digest: Optional[str] = None,
) -> dict[str, Any]:
    """登记一个项目级数据资产；返回 dataset_id。

    `catalog` 来源额外接收 `catalog_entry_id`（目录条目 ID）、`dataset_ref`（真实数据相对引用）
    与 `content_digest`（目录条目内容摘要，供挂载幂等判定）。
    """
    scope.assert_writable()
    kind = str(source_kind or "").strip()
    if kind not in SOURCE_KINDS:
        raise ScopeError(
            "invalid_source_kind",
            f"source_kind 必须是 {SOURCE_KINDS!r} 之一，收到 {kind!r}。",
            next_action="选择上传 / 平台资产 / 连接器之一",
        )

    _assert_no_credentials(logical_object, field="logical_object")
    _assert_no_credentials(logical_description, field="logical_description")

    record: dict[str, Any] = {
        "dataset_id": f"ds-{uuid.uuid4().hex[:12]}",
        "source_kind": kind,
        "logical_object": (logical_object or "").strip() or None,
        "logical_description": (logical_description or "").strip() or None,
        "registered_at": _now_iso(),
    }

    if kind == "upload":
        # 浏览器上传：只接收相对 upload_ref（相对存储根），拒绝机器绝对路径。
        ref = (upload_ref or "").strip()
        if not ref:
            raise ScopeError("missing_upload_ref", "上传来源缺少 upload_ref。", next_action="重新上传文件")
        if is_machine_absolute(ref):
            raise ScopeError(
                "absolute_path_forbidden",
                f"upload_ref 不能是机器绝对路径：{ref!r}。",
                next_action="使用平台返回的相对上传引用",
            )
        record["upload_ref"] = assert_relative_ref(ref, field="upload_ref")
        record["file_name"] = (file_name or "").strip() or None
        record["status"] = "registered"
    elif kind == "platform_asset":
        aid = (asset_id or "").strip()
        if not aid:
            raise ScopeError("missing_asset_id", "平台资产来源缺少 asset_id。", next_action="选择一个平台数据资产")
        if is_machine_absolute(aid):
            raise ScopeError("invalid_asset_id", "asset_id 不能是机器绝对路径。")
        record["asset_id"] = aid
        record["status"] = "registered"
    elif kind == "catalog":
        # 平台数据集目录条目：数据引用是来源根内的相对引用（**不是**机器路径、也不是上传引用）。
        # 与平台资产 / 连接器不同，它指向一个已通过质量检测、可解析到真实分片的条目。
        ref = (dataset_ref or "").strip()
        if not ref:
            raise ScopeError(
                "missing_dataset_ref",
                "目录来源缺少 dataset_ref。",
                next_action="从平台数据集目录选择一个已发布条目",
            )
        record["dataset_ref"] = assert_relative_ref(ref, field="dataset_ref")
        record["catalog_entry_id"] = (catalog_entry_id or "").strip() or None
        record["content_digest"] = (content_digest or "").strip() or None
        record["file_name"] = (file_name or "").strip() or None
        record["status"] = "registered"
    else:  # connector
        cid = (connector_id or "").strip()
        if not cid:
            raise ScopeError("missing_connector_id", "连接器来源缺少 connector_id。", next_action="选择一个已授权连接器")
        record["connector_id"] = cid
        # 连接器数据需异步物化后才可用。
        record["status"] = "pending_materialization"

    return dataset_assets.append(scope, record)


def list_dataset_assets(scope: ScopeContext) -> list[dict[str, Any]]:
    return dataset_assets.list(scope)


def get_dataset_asset(scope: ScopeContext, dataset_id: str) -> Optional[dict[str, Any]]:
    return dataset_assets.find(scope, dataset_id)


def _read_head(path, *, ext: str, row_limit: int):
    """有界读文件头部若干行（不整读大文件）。"""
    import pandas as pd

    if ext == ".parquet":
        return pd.read_parquet(path).head(row_limit)
    sep = "\t" if ext == ".tsv" else ","
    return pd.read_csv(path, sep=sep, nrows=row_limit)


def _preview_rows(df, row_limit: int) -> list[dict[str, Any]]:
    """转成可直接 JSON 序列化的行：交给 pandas 的 to_json 处理 numpy / 时间类型。"""
    import json

    return json.loads(df.head(row_limit).to_json(orient="records", date_format="iso"))


def get_preview(scope: ScopeContext, dataset_id: str, *, row_limit: int = 100) -> dict[str, Any]:
    """有界预览：对**真实落盘的数据文件**读前 N 行 + 列类型。

    连接器数据尚未物化、来源不是本地文件、或文件解析失败时，如实返回 `preview_available=false`
    ——不返回空表假装成功（空表会被前端误读为"数据是空的"）。
    """
    asset = get_dataset_asset(scope, dataset_id)
    if asset is None:
        raise ScopeError(
            "dataset_not_found",
            f"当前项目下找不到数据资产 {dataset_id!r}。",
            next_action="确认 dataset_id 或重新接入数据",
            scope=scope.echo(),
        )
    limit = max(1, min(int(row_limit), 1000))
    base: dict[str, Any] = {
        **scope.echo(),
        "dataset_id": dataset_id,
        "source_kind": asset.get("source_kind"),
        "row_limit": limit,
    }
    unavailable = {**base, "columns": [], "preview_rows": [], "preview_available": False}

    alias_ref = to_source_alias_ref(_asset_source_ref(asset) or "")
    if not alias_ref:
        return {
            **unavailable,
            "note": "该来源没有可直读的本地数据文件（连接器数据需异步物化后才生成预览）；浏览器不接收服务器文件路径。",
        }

    try:
        unit = resolve_dataset_unit(alias_ref)
    except ScopeError as exc:
        return {**unavailable, "note": f"来源当前不可读（{exc.code}）；确认文件仍在来源根内。"}

    shard = unit["shard_paths"][0]
    ext = shard.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {**unavailable, "note": f"不支持预览的文件类型：{ext or '（无扩展名）'}。"}
    try:
        df = _read_head(shard, ext=ext, row_limit=limit)
    except Exception as exc:  # noqa: BLE001 — 解析失败要如实报告，不让端点 500
        return {**unavailable, "note": f"文件解析失败：{type(exc).__name__}。"}

    return {
        **base,
        "columns": [{"name": str(c), "dtype": str(df[c].dtype)} for c in df.columns],
        "preview_rows": _preview_rows(df, limit),
        "preview_available": True,
        "shard_count": int(unit.get("shard_count") or 1),
        "previewed_from": shard.name,
        "note": "预览按行数上限有界返回（取自分片组首片）；浏览器不接收服务器文件路径。",
    }


# ---------------------------------------------------------------------------
# 物化任务（长连接器作业，可恢复）
# ---------------------------------------------------------------------------

def create_materialization_task(
    scope: ScopeContext,
    *,
    dataset_id: str,
    time_range: Optional[str] = None,
    row_limit: Optional[int] = None,
) -> dict[str, Any]:
    """为连接器数据资产创建可恢复的物化任务。"""
    scope.assert_writable()
    asset = get_dataset_asset(scope, dataset_id)
    if asset is None:
        raise ScopeError("dataset_not_found", f"找不到数据资产 {dataset_id!r}。", scope=scope.echo())
    task = {
        "task_id": f"mtz-{uuid.uuid4().hex[:12]}",
        "dataset_id": dataset_id,
        "status": "pending",
        "progress": 0,
        "time_range": (time_range or "").strip() or None,
        "row_limit": int(row_limit) if row_limit else None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    return materialization_tasks.append(scope, task)


def get_materialization_task(scope: ScopeContext, task_id: str) -> Optional[dict[str, Any]]:
    return materialization_tasks.find(scope, task_id)


def update_materialization_task(
    scope: ScopeContext,
    task_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    failure_reason: Optional[str] = None,
) -> dict[str, Any]:
    """更新物化任务状态 / 进度（供 worker 或测试推进；不写凭据）。"""
    scope.assert_writable()
    task = get_materialization_task(scope, task_id)
    if task is None:
        raise ScopeError("materialization_task_not_found", f"找不到物化任务 {task_id!r}。", scope=scope.echo())
    updated = dict(task)
    if status is not None:
        if status not in MATERIALIZATION_STATUSES:
            raise ScopeError("invalid_status", f"status 必须是 {MATERIALIZATION_STATUSES!r} 之一。")
        updated["status"] = status
    if progress is not None:
        updated["progress"] = max(0, min(100, int(progress)))
    if failure_reason is not None:
        updated["failure_reason"] = str(failure_reason)
    updated["updated_at"] = _now_iso()
    return materialization_tasks.replace(scope, task_id, updated)


def cancel_materialization_task(scope: ScopeContext, task_id: str) -> dict[str, Any]:
    """取消物化任务（保留已产生的部分状态，不算失败）。"""
    return update_materialization_task(scope, task_id, status="cancelled")


# ---------------------------------------------------------------------------
# 字段映射 / 画像 与 不可变数据版本发布（design §13 第 4–7 步）
# ---------------------------------------------------------------------------

def _content_digest(payload: Any) -> str:
    """对规范化 JSON 求 SHA256，作为不可变内容摘要（稳定、可复现）。"""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _asset_source_ref(asset: dict[str, Any]) -> Optional[str]:
    # `catalog` 资产的真实数据引用落在 `dataset_ref`（`upload_ref` 只表示浏览器上传）。
    return (
        asset.get("upload_ref")
        or asset.get("dataset_ref")
        or asset.get("asset_id")
        or asset.get("connector_id")
    )


def _facts_for_asset(
    asset: dict[str, Any], *, mapping: dict[str, Any], label_policy: Optional[dict[str, Any]]
) -> tuple[dict[str, Any], Optional[str]]:
    """画像未显式传 facts 时，服务端从**真实文件**算，返回 `(facts, unavailable_reason)`。

    算不出**不抛错**：连接器数据与平台资产都没有本地文件，「没有覆盖事实」是正常结果
    （readiness 据此诚实降级为 experiment_only），而不是调用错误。降级原因如实落进
    `facts_unavailable_reason`，不静默吞掉——否则又回到「facts 恒为空且无人知道为什么」。
    """
    alias_ref = to_source_alias_ref(_asset_source_ref(asset) or "")
    if not alias_ref:
        return {}, "source_not_a_local_dataset"
    try:
        return compute_dataset_facts(alias_ref, mapping=mapping, label_policy=label_policy), None
    except ScopeError as exc:
        return {}, exc.code
    except Exception as exc:  # noqa: BLE001 — 解析异常同样降级，不阻断画像保存
        return {}, f"facts_computation_failed:{type(exc).__name__}"


def save_dataset_profile(
    scope: ScopeContext,
    *,
    dataset_id: str,
    mapping: dict[str, Any],
    facts: Optional[dict[str, Any]] = None,
    label_policy: Optional[dict[str, Any]] = None,
    ical_contract: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """保存一个字段映射 / 画像版本（不可变；每次保存生成新 dataset_profile_id）。

    `facts` 缺省（None）时**服务端从真实文件计算**——这正是「readiness 恒为 experiment_only」
    的修复点：此前 facts 完全由客户端传入、后端从不计算，而生产路径没有任何代码会写
    `sufficient_coverage`，于是质量检测在服务端实际不存在。显式传入仍作为覆盖（向后兼容）。
    """
    scope.assert_writable()
    asset = get_dataset_asset(scope, dataset_id)
    if asset is None:
        raise ScopeError("dataset_not_found", f"找不到数据资产 {dataset_id!r}。", scope=scope.echo())
    if not isinstance(mapping, dict) or not mapping:
        raise ScopeError("missing_mapping", "缺少字段映射 mapping。", next_action="确认时间 / 实体 / 测量 / 标签映射后重试")

    if facts is None:
        resolved_facts, facts_unavailable_reason = _facts_for_asset(
            asset, mapping=mapping, label_policy=label_policy
        )
        facts_origin = str(resolved_facts.get("facts_source") or "unavailable")
    else:
        resolved_facts = dict(facts)
        facts_origin = "client_provided"
        facts_unavailable_reason = None

    record: dict[str, Any] = {
        "dataset_profile_id": f"dsp-{uuid.uuid4().hex[:12]}",
        "dataset_id": dataset_id,
        "mapping": dict(mapping),
        "facts": resolved_facts,
        "facts_origin": facts_origin,
        "facts_unavailable_reason": facts_unavailable_reason,
        "label_policy": dict(label_policy or {}),
        # i_cal 是期望电流参照，不是 ground truth；rated_power_kw 只作辅助元数据。
        "i_cal_contract": dict(ical_contract) if ical_contract else None,
        "i_cal_semantics": "expected_current_reference_not_ground_truth",
        "rated_power_kw_role": "auxiliary_metadata",
        "mapping_digest": _content_digest(mapping),
        "created_at": _now_iso(),
    }
    return dataset_profiles.append(scope, record)


def get_dataset_profile(scope: ScopeContext, profile_id: str) -> Optional[dict[str, Any]]:
    return dataset_profiles.find(scope, profile_id)


def publish_dataset_version(
    scope: ScopeContext,
    *,
    dataset_id: str,
    dataset_profile_id: str,
) -> dict[str, Any]:
    """发布不可变数据版本：相对 artifact_ref + 稳定内容摘要；同一内容幂等命中，映射变化生成新版本。"""
    scope.assert_writable()
    asset = get_dataset_asset(scope, dataset_id)
    if asset is None:
        raise ScopeError("dataset_not_found", f"找不到数据资产 {dataset_id!r}。", scope=scope.echo())
    profile = get_dataset_profile(scope, dataset_profile_id)
    if profile is None:
        raise ScopeError("profile_not_found", f"找不到画像 {dataset_profile_id!r}。", scope=scope.echo())
    if str(profile.get("dataset_id")) != str(dataset_id):
        raise ScopeError(
            "profile_dataset_mismatch",
            "画像与数据资产不一致（profile.dataset_id != dataset_id）。",
            scope=scope.echo(),
        )

    digest_inputs = {
        "project_id": scope.project_id,
        "dataset_id": dataset_id,
        "source_kind": asset.get("source_kind"),
        "source_ref": _asset_source_ref(asset),
        "mapping": profile.get("mapping"),
        "facts": profile.get("facts"),
        "label_policy": profile.get("label_policy"),
    }
    content_digest = _content_digest(digest_inputs)

    # 不可变 + 幂等：相同内容摘要已存在则返回原版本，不物化重复版本。
    for existing in dataset_versions.list(scope):
        if str(existing.get("content_digest")) == content_digest and str(existing.get("dataset_id")) == str(dataset_id):
            return {**existing, "idempotent_hit": True}

    version_id = f"dsv-{uuid.uuid4().hex[:12]}"
    artifact_ref = scoped_relative_path(
        scope, f"{version_id}.json", root=_DATASETS_ROOT, include_slot=False
    )
    record = {
        "dataset_version_id": version_id,
        "dataset_id": dataset_id,
        "dataset_profile_id": dataset_profile_id,
        "artifact_ref": artifact_ref,  # 相对引用，绝不持久化机器绝对路径
        "content_digest": content_digest,
        "source_kind": asset.get("source_kind"),
        "immutable": True,
        "published_at": _now_iso(),
    }
    return {**dataset_versions.append(scope, record), "idempotent_hit": False}


def list_dataset_versions(scope: ScopeContext) -> list[dict[str, Any]]:
    return dataset_versions.list(scope)


def get_dataset_version(scope: ScopeContext, version_id: str) -> Optional[dict[str, Any]]:
    return dataset_versions.find(scope, version_id)


# @AI_GENERATED: end
