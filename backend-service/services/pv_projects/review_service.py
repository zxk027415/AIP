# @AI_GENERATED
"""项目化统一审核队列 / 审核详情 / 精度表面（design §17、§18；任务 4.2）。

设计红线：
- 队列按 `(project_id, review_slot)` 分区；不跨项目 / 不跨槽 / 不 fallback。
- **裁定（verdict）、完成审核（complete）、完成并准入（complete-and-admit）是三个独立动作**：
  - 保存裁定只改逐条 item 结论，不代表审核完成，更不代表准入。
  - 完成审核要求所有 item 均已裁定；只置 `completed`，不写累计台账。
  - 完成并准入才追加准入事件（scoped `cumulative_events`），且**幂等**。
- 并发重判冲突用乐观锁 `expected_review_version`（CAS）；版本不一致即 fail-closed，不覆盖他人裁定。
- 精度：给出统计范围 / 人工真值数 / 类别支持度 / 指标定义 / 数据与模型版本 / 不可比原因；
  无有效真值时 `value=None`（前端渲染“未产出”而非 0%）；**绝不**据低分自动触发调参 / Promote。
- 本模块只写 scoped 项目证据（reviews / cumulative_events），不触碰生产 registry / 指针。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services.pv_projects.governance import GovernanceGateError
from services.pv_projects.scope import ScopeContext
from services.pv_projects.stores import cumulative_events as _cumulative_events, reviews as _reviews

#: 审核会话状态。
REVIEW_STATUS_OPEN = "open"
REVIEW_STATUS_IN_REVIEW = "in_review"
REVIEW_STATUS_COMPLETED = "completed"
REVIEW_STATUS_ADMITTED = "admitted"

#: 单条 item 允许的裁定。
ITEM_VERDICTS: tuple[str, ...] = ("accept", "reject", "uncertain")

#: 审核来源类型（design §17）。
REVIEW_SOURCE_KINDS: tuple[str, ...] = (
    "label_proposal",       # 模型辅助打标提案
    "detection_batch",      # 检测批次
    "model_assisted_label", # 模型辅助标注
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require(scope: ScopeContext, review_id: str) -> dict[str, Any]:
    rec = _reviews.find(scope, review_id)
    if rec is None:
        raise GovernanceGateError(
            "review_not_found",
            f"当前项目 / 路径下找不到审核会话 review_id={review_id!r}。",
            category="business_gate_blocked",
            next_action="返回审核队列重新选择",
        )
    return rec


def _assert_version(review: dict[str, Any], expected_review_version: int) -> None:
    current = int(review.get("review_version") or 0)
    if current != int(expected_review_version):
        raise GovernanceGateError(
            "review_version_conflict",
            "审核版本已变化，可能有人并发重判；请刷新后基于最新版本重试。",
            category="business_gate_blocked",
            current_value=current,
            required_value=int(expected_review_version),
            next_action="刷新审核详情后基于最新 review_version 重试",
            retryable=True,
        )


# ---------------------------------------------------------------------------
# 只读
# ---------------------------------------------------------------------------

def list_reviews(scope: ScopeContext) -> list[dict[str, Any]]:
    """列出当前 (project_id, review_slot) 的审核会话（不跨 scope / 不 fallback）。"""
    return _reviews.list(scope)

def queue_view(scope: ScopeContext) -> dict[str, Any]:
    """审核队列视图：来源 / 粒度 / 数据版本 / 模型 / 执行 / 进度 / 准入就绪。"""
    rows: list[dict[str, Any]] = []
    for r in list_reviews(scope):
        items = r.get("items") or []
        judged = sum(1 for it in items if it.get("verdict"))
        total = len(items)
        rows.append(
            {
                "review_id": r.get("review_id"),
                "review_slot": r.get("slot"),
                "source_kind": r.get("source_kind"),
                "unit_granularity": r.get("unit_granularity"),
                "dataset_version_id": r.get("dataset_version_id"),
                "model_ref": r.get("model_ref"),
                "source_execution_id": r.get("source_execution_id"),
                "status": r.get("status"),
                "review_version": r.get("review_version", 0),
                "progress": {"judged": judged, "total": total},
                "admission_ready": r.get("status") == REVIEW_STATUS_COMPLETED and not r.get("admitted_event_id"),
                "admitted_event_id": r.get("admitted_event_id"),
            }
        )
    return {**scope.echo(), "reviews": rows, "total": len(rows)}


def get_review(scope: ScopeContext, review_id: str) -> dict[str, Any]:
    """审核详情（含逐条 item 与路径特定证据字段）。"""
    return _require(scope, review_id)


# ---------------------------------------------------------------------------
# 写入：登记 / 三个独立动作
# ---------------------------------------------------------------------------

def create_review(
    scope: ScopeContext,
    *,
    source_kind: str,
    unit_granularity: str,
    items: list[dict[str, Any]],
    dataset_version_id: Optional[str] = None,
    model_ref: Optional[str] = None,
    source_execution_id: Optional[str] = None,
) -> dict[str, Any]:
    """登记一个审核会话（scoped 证据写入）。"""
    scope.assert_writable()
    if source_kind not in REVIEW_SOURCE_KINDS:
        raise GovernanceGateError(
            "invalid_review_source",
            f"未知审核来源 {source_kind!r}，允许 {REVIEW_SOURCE_KINDS!r}。",
            category="business_gate_blocked",
        )
    normalized_items: list[dict[str, Any]] = []
    for idx, it in enumerate(items or []):
        normalized_items.append(
            {
                "item_id": str(it.get("item_id") or f"item-{idx}"),
                "unit_ref": it.get("unit_ref"),
                "proposed_label": it.get("proposed_label"),
                "evidence": it.get("evidence") or {},
                "verdict": None,
                "verdict_label": None,
                "verdict_at": None,
            }
        )
    record = {
        "review_id": f"rev-{uuid.uuid4().hex[:12]}",
        "slot": scope.require_slot(),
        "source_kind": source_kind,
        "unit_granularity": unit_granularity,
        "dataset_version_id": dataset_version_id,
        "model_ref": model_ref,
        "source_execution_id": source_execution_id,
        "items": normalized_items,
        "status": REVIEW_STATUS_OPEN,
        "review_version": 0,
        "admitted_event_id": None,
        "created_at": _now_iso(),
    }
    return _reviews.append(scope, record)


def save_verdict(
    scope: ScopeContext,
    review_id: str,
    *,
    expected_review_version: int,
    item_verdicts: list[dict[str, Any]],
) -> dict[str, Any]:
    """动作①：保存逐条裁定（CAS）。**只改结论，不完成、不准入。**"""
    scope.assert_writable()
    review = _require(scope, review_id)
    if review.get("status") == REVIEW_STATUS_ADMITTED:
        raise GovernanceGateError(
            "review_already_admitted",
            "该审核会话已准入，裁定被冻结，不能再修改。",
            category="business_gate_blocked",
        )
    _assert_version(review, expected_review_version)

    by_id = {str(v.get("item_id")): v for v in (item_verdicts or [])}
    updated = 0
    for it in review.get("items", []):
        patch = by_id.get(str(it.get("item_id")))
        if not patch:
            continue
        verdict = str(patch.get("verdict") or "").strip()
        if verdict and verdict not in ITEM_VERDICTS:
            raise GovernanceGateError(
                "invalid_verdict",
                f"非法裁定 {verdict!r}，允许 {ITEM_VERDICTS!r}。",
                category="business_gate_blocked",
            )
        it["verdict"] = verdict or None
        it["verdict_label"] = patch.get("verdict_label")
        it["verdict_at"] = _now_iso() if verdict else None
        updated += 1

    review["status"] = REVIEW_STATUS_IN_REVIEW
    review["review_version"] = int(review.get("review_version") or 0) + 1
    review["updated_at"] = _now_iso()
    saved = _reviews.replace(scope, review_id, review)
    return {"review": saved, "updated_items": updated}


def complete_review(
    scope: ScopeContext,
    review_id: str,
    *,
    expected_review_version: int,
) -> dict[str, Any]:
    """动作②：完成审核（CAS）。要求所有 item 已裁定；**只置 completed，不写台账**。"""
    scope.assert_writable()
    review = _require(scope, review_id)
    _assert_version(review, expected_review_version)
    items = review.get("items", [])
    unjudged = [it.get("item_id") for it in items if not it.get("verdict")]
    if unjudged:
        raise GovernanceGateError(
            "review_incomplete",
            f"仍有 {len(unjudged)} 条未裁定，不能完成审核。",
            category="business_gate_blocked",
            current_value=f"unjudged={len(unjudged)}",
            required_value="全部已裁定",
            next_action="先完成剩余条目的裁定",
        )
    review["status"] = REVIEW_STATUS_COMPLETED
    review["review_version"] = int(review.get("review_version") or 0) + 1
    review["completed_at"] = _now_iso()
    saved = _reviews.replace(scope, review_id, review)
    return {"review": saved}


def complete_and_admit(
    scope: ScopeContext,
    review_id: str,
    *,
    expected_review_version: int,
    idempotency_key: str,
    operator: str,
) -> dict[str, Any]:
    """动作③：完成并准入（CAS + 幂等）。追加 scoped 准入事件到累计台账。

    准入只接受 `verdict=accept` 的条目为真值来源；`reject/uncertain` 不进入台账。
    幂等：同 `idempotency_key` 命中已有准入事件即回放，不重复写。
    """
    scope.assert_writable()
    if not str(idempotency_key or "").strip():
        raise GovernanceGateError("missing_idempotency_key", "缺少 idempotency_key。", category="business_gate_blocked")
    if not str(operator or "").strip():
        raise GovernanceGateError("missing_operator", "缺少 operator。", category="business_gate_blocked")

    # 幂等命中。
    for ev in _cumulative_events.list(scope):
        if str(ev.get("idempotency_key") or "") == str(idempotency_key) and ev.get("kind") == "admission":
            return {"review": _require(scope, review_id), "admission": ev, "idempotent_replay": True}

    review = _require(scope, review_id)
    _assert_version(review, expected_review_version)
    if review.get("admitted_event_id"):
        existing = next(
            (e for e in _cumulative_events.list(scope) if e.get("event_id") == review["admitted_event_id"]),
            None,
        )
        return {"review": review, "admission": existing, "idempotent_replay": True}

    items = review.get("items", [])
    unjudged = [it.get("item_id") for it in items if not it.get("verdict")]
    if unjudged:
        raise GovernanceGateError(
            "review_incomplete",
            f"仍有 {len(unjudged)} 条未裁定，不能准入。",
            category="business_gate_blocked",
            next_action="先完成剩余条目的裁定",
        )

    accepted = [it for it in items if it.get("verdict") == "accept"]
    event = {
        "event_id": f"adm-{uuid.uuid4().hex[:12]}",
        "kind": "admission",
        "slot": scope.require_slot(),
        "review_id": review_id,
        "source_kind": review.get("source_kind"),
        "unit_granularity": review.get("unit_granularity"),
        "dataset_version_id": review.get("dataset_version_id"),
        "model_ref": review.get("model_ref"),
        "admitted_count": len(accepted),
        "rejected_count": sum(1 for it in items if it.get("verdict") == "reject"),
        "uncertain_count": sum(1 for it in items if it.get("verdict") == "uncertain"),
        "accepted_unit_refs": [it.get("unit_ref") for it in accepted],
        "operator": operator,
        "idempotency_key": idempotency_key,
        "admitted_at": _now_iso(),
    }
    saved_event = _cumulative_events.append(scope, event)

    review["status"] = REVIEW_STATUS_ADMITTED
    review["admitted_event_id"] = saved_event["event_id"]
    review["review_version"] = int(review.get("review_version") or 0) + 1
    review["admitted_at"] = _now_iso()
    saved_review = _reviews.replace(scope, review_id, review)
    return {"review": saved_review, "admission": saved_event, "idempotent_replay": False}


# ---------------------------------------------------------------------------
# 精度表面（诚实、可空、绝不联动调参 / Promote）
# ---------------------------------------------------------------------------

def review_accuracy(scope: ScopeContext, review_id: str) -> dict[str, Any]:
    """精度表面：统计范围 / 人工真值数 / 类别支持 / 指标定义 / 版本 / 不可比原因。

    - 无有效人工真值（`accept` 条目为 0）→ `value=None`，前端渲染“未产出”而非 0%。
    - 仅统计范围内 accept 条目；`comparable` 为 false 时给出 `non_comparability_reasons`。
    - 本函数**只读汇总**，不触发任何调参 / Promote。
    """
    review = _require(scope, review_id)
    items = review.get("items", [])
    accepted = [it for it in items if it.get("verdict") == "accept"]
    human_truth_count = len(accepted)

    class_support: dict[str, int] = {}
    for it in accepted:
        label = str(it.get("verdict_label") or it.get("proposed_label") or "unknown")
        class_support[label] = class_support.get(label, 0) + 1

    non_comparability: list[str] = []
    if human_truth_count == 0:
        non_comparability.append("no_valid_human_truth")
    if not review.get("dataset_version_id"):
        non_comparability.append("missing_dataset_version")
    if not review.get("model_ref"):
        non_comparability.append("missing_model_version")

    comparable = human_truth_count > 0 and not non_comparability
    return {
        **scope.echo(),
        "review_id": review_id,
        "statistical_scope": {
            "review_slot": review.get("slot"),
            "unit_granularity": review.get("unit_granularity"),
            "total_items": len(items),
            "accepted_items": human_truth_count,
        },
        "human_truth_count": human_truth_count,
        "class_support": class_support,
        "metric_definition": "accepted human truth 上的分类一致率（未接入真实评测引擎时仅描述统计范围）",
        "dataset_version_id": review.get("dataset_version_id"),
        "model_ref": review.get("model_ref"),
        "comparable": comparable,
        "non_comparability_reasons": non_comparability,
        # 无有效真值时诚实置空，由前端渲染“未产出”。
        "value": None,
        "value_display": "未产出" if human_truth_count == 0 else "待接入评测引擎",
        "auto_action_note": "低分不联动调参 / Promote；任何模型晋升仍需正式复验与生产授权。",
    }


# @AI_GENERATED: end
