# @AI_GENERATED
# -*- coding: utf-8 -*-
"""Seq 不可变设备日批次与 Ledger 的崩溃恢复协调器。

该模块把推理前幂等判定与“先落不可变批次、后提交 Ledger”的恢复窗口收敛为单一流程：

1. 每轮或启动时扫描当前 ``slot`` — 槽位与 ``modeling_path`` — 建模路径分区的批次；
2. 对同一设备日按 ``supersedes_batch_id`` — 被替代批次 ID 连续补齐 Ledger；
3. 推理前计算 ``input_fingerprint`` — 输入指纹，相同成功指纹直接跳过；
4. 输入变化进入 revision_pending/running，成功写新批次，失败保留旧 succeeded 事实。

不可变批次是恢复证据，不替代 SeqDeviceDayLedger 的生产处理权威；批次目录由部署配置决定，
持久化引用仍只使用相对路径。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, Optional

from services.scheduler.pv_dual_path.path_isolation import PathIsolationRegistry
from services.scheduler.pv_dual_path.seq_device_day_ledger import (
    DeviceDayKey,
    LedgerOperationError,
    LedgerRecord,
    SeqDeviceDayLedgerRepository,
    stable_input_fingerprint,
)


class ImmutableBatchRecoveryError(RuntimeError):
    """批次链冲突、字段缺失或恢复写入失败的可诊断异常。"""


@dataclass(frozen=True)
class InferenceDecision:
    """设备日推理前判定。

    ``action`` — 动作，取 ``skip`` 或 ``run``；``fingerprint`` — 当前输入指纹；
    ``supersedes_batch_id`` — 本轮成功批次应替代的旧批次；``recovered_batch_id`` — 本轮
    预检期间从孤儿批次恢复出的批次 ID。
    """

    key: DeviceDayKey
    activation_epoch_id: str
    action: str
    fingerprint: str
    supersedes_batch_id: Optional[str]
    recovered_batch_id: Optional[str] = None


@dataclass(frozen=True)
class ReconciliationSummary:
    """一次设备日批次对账摘要。"""

    scanned: int
    reconciled_batch_ids: List[str]
    already_consistent_batch_ids: List[str]
    ignored_batch_ids: List[str]


class ImmutableBatchRecovery:
    """协调不可变批次枚举、Ledger 对账和 predictor 前幂等领取。"""

    def __init__(
        self,
        ledger: SeqDeviceDayLedgerRepository,
        batches: PathIsolationRegistry,
        *,
        slot: str = "pv_fault",
        modeling_path: str = "seq_annotation",
    ) -> None:
        self._ledger = ledger
        self._batches = batches
        self._slot = str(slot or "").strip()
        self._modeling_path = str(modeling_path or "").strip()
        if not self._slot:
            raise ValueError("slot — 槽位不可为空")
        if self._modeling_path != "seq_annotation":
            raise ValueError("不可变设备日恢复仅允许 modeling_path='seq_annotation'")

    @staticmethod
    def fingerprint_points(points: Iterable[Any]) -> str:
        """兼容 ``time``/``event_time`` 字段，计算稳定设备日输入指纹。"""

        normalized: List[Dict[str, Any]] = []
        for point in points:
            if isinstance(point, Mapping):
                event_time = point.get("event_time", point.get("time"))
                if "value" in point:
                    value = point["value"]
                elif "measurement_value" in point:
                    value = point["measurement_value"]
                else:
                    raise ValueError("设备日输入点缺少 value — 测量值")
                if event_time is None:
                    raise ValueError("设备日输入点缺少 event_time/time — 事件时间")
                normalized.append({"event_time": event_time, "value": value})
            else:
                normalized.append(point)
        return stable_input_fingerprint(normalized)

    @staticmethod
    def _payload_matches_key(payload: Mapping[str, Any], key: DeviceDayKey) -> bool:
        """判断新合同批次是否属于目标设备日；旧批次缺字段时返回 False。"""

        try:
            payload_date = date.fromisoformat(str(payload.get("business_date"))[:10])
        except (TypeError, ValueError):
            return False
        return (
            str(payload.get("slot") or "") == key.slot
            and str(payload.get("modeling_path") or "") == key.modeling_path
            and str(payload.get("site_id") or "") == key.site_id
            and str(payload.get("device_id") or "") == key.device_id
            and str(payload.get("branch_id") or "") == key.branch_id
            and payload_date == key.business_date
        )

    @staticmethod
    def _required_batch_fields(payload: Mapping[str, Any], batch_id: str) -> Dict[str, Any]:
        fingerprint = str(payload.get("input_fingerprint") or "").strip()
        epoch_id = str(payload.get("activation_epoch_id") or "").strip()
        if not fingerprint or not epoch_id or "supersedes_batch_id" not in payload:
            raise ImmutableBatchRecoveryError(
                f"批次 {batch_id!r} 缺少 input_fingerprint、activation_epoch_id "
                "或 supersedes_batch_id 新合同字段"
            )
        supersedes = str(payload.get("supersedes_batch_id") or "").strip() or None
        return {
            "fingerprint": fingerprint,
            "activation_epoch_id": epoch_id,
            "supersedes_batch_id": supersedes,
        }

    def reconcile_device_day(self, key: DeviceDayKey) -> ReconciliationSummary:
        """按 supersedes 链恢复目标设备日所有可连续确认的孤儿批次。

        若同一旧批次分叉出多个修订批次，恢复器拒绝猜测；旧合同批次因缺设备日/epoch 字段
        无法安全确认时只归入 ignored，不伪造 succeeded。
        """

        if key.slot != self._slot or key.modeling_path != self._modeling_path:
            raise ImmutableBatchRecoveryError(
                f"恢复分区不匹配：key={key.describe()}, "
                f"coordinator=({self._slot!r}, {self._modeling_path!r})"
            )

        scanned_ids = self._batches.list_batch_ids(self._slot, self._modeling_path)
        pending: Dict[str, Dict[str, Any]] = {}
        ignored: List[str] = []
        for batch_id in scanned_ids:
            payload = self._batches.read_batch(self._slot, self._modeling_path, batch_id)
            if not isinstance(payload, Mapping) or not self._payload_matches_key(payload, key):
                ignored.append(batch_id)
                continue
            try:
                fields = self._required_batch_fields(payload, batch_id)
            except ImmutableBatchRecoveryError:
                ignored.append(batch_id)
                continue
            pending[batch_id] = {**dict(payload), **fields}

        reconciled: List[str] = []
        consistent: List[str] = []
        while pending:
            current = self._ledger.query(key)
            current_batch_id = current.batch_id if current is not None else None

            for batch_id in list(pending):
                item = pending[batch_id]
                if (
                    current is not None
                    and current.status == "succeeded"
                    and current.batch_id == batch_id
                    and current.input_fingerprint == item["fingerprint"]
                ):
                    consistent.append(batch_id)
                    pending.pop(batch_id)

            eligible = [
                (batch_id, item)
                for batch_id, item in pending.items()
                if item["supersedes_batch_id"] == current_batch_id
            ]
            if not eligible:
                break
            if len(eligible) > 1:
                raise ImmutableBatchRecoveryError(
                    "不可变批次修订链发生分叉："
                    f"key={key.describe()}, predecessor={current_batch_id!r}, "
                    f"children={sorted(batch_id for batch_id, _ in eligible)!r}"
                )
            batch_id, item = eligible[0]
            self._ledger.reconcile_succeeded_from_batch(
                key,
                batch_id=batch_id,
                fingerprint=item["fingerprint"],
                activation_epoch_id=item["activation_epoch_id"],
                supersedes_batch_id=item["supersedes_batch_id"],
            )
            reconciled.append(batch_id)
            pending.pop(batch_id)

        ignored.extend(sorted(pending))
        return ReconciliationSummary(
            scanned=len(scanned_ids),
            reconciled_batch_ids=reconciled,
            already_consistent_batch_ids=consistent,
            ignored_batch_ids=sorted(set(ignored)),
        )

    def prepare_for_inference(
        self,
        key: DeviceDayKey,
        points: Iterable[Any],
        *,
        activation_epoch_id: str,
    ) -> InferenceDecision:
        """在 predictor 前完成恢复、指纹幂等判定并原子领取 Ledger。

        相同成功指纹返回 ``action='skip'``，调用方不得执行 predictor；新增或变化输入返回
        ``action='run'`` 且记录已进入 running。修订记录保留旧 batch_id 作为 supersedes 来源。
        """

        epoch_id = str(activation_epoch_id or "").strip()
        if not epoch_id:
            raise ImmutableBatchRecoveryError("activation_epoch_id — 启用周期标识不可为空")
        summary = self.reconcile_device_day(key)
        fingerprint = self.fingerprint_points(points)
        current = self._ledger.query(key)
        recovered_batch_id = (
            summary.reconciled_batch_ids[-1] if summary.reconciled_batch_ids else None
        )
        if (
            current is not None
            and current.status == "succeeded"
            and current.input_fingerprint == fingerprint
        ):
            return InferenceDecision(
                key=key,
                activation_epoch_id=epoch_id,
                action="skip",
                fingerprint=fingerprint,
                supersedes_batch_id=current.batch_id,
                recovered_batch_id=recovered_batch_id,
            )

        candidate = self._ledger.upsert_candidate(
            key,
            fingerprint,
            is_ready=True,
            activation_epoch_id=epoch_id,
        )
        if candidate.status == "succeeded" and candidate.input_fingerprint == fingerprint:
            return InferenceDecision(
                key=key,
                activation_epoch_id=epoch_id,
                action="skip",
                fingerprint=fingerprint,
                supersedes_batch_id=candidate.batch_id,
                recovered_batch_id=recovered_batch_id,
            )
        running = self._ledger.mark_running(key)
        return InferenceDecision(
            key=key,
            activation_epoch_id=epoch_id,
            action="run",
            fingerprint=fingerprint,
            supersedes_batch_id=running.batch_id,
            recovered_batch_id=recovered_batch_id,
        )

    def persist_success(
        self,
        decision: InferenceDecision,
        *,
        batch_id: str,
        payload: Mapping[str, Any],
    ) -> LedgerRecord:
        """先原子写不可变批次，再提交 Ledger；Ledger 失败由下轮扫描恢复。"""

        if decision.action != "run":
            raise ImmutableBatchRecoveryError("只有 action='run' 的判定可以提交成功批次")
        normalized_batch_id = str(batch_id or "").strip()
        if not normalized_batch_id:
            raise ImmutableBatchRecoveryError("batch_id — 不可变批次标识不可为空")
        out = {
            **dict(payload),
            **decision.key.as_primary_key(),
            "business_date": decision.key.business_date.isoformat(),
            "activation_epoch_id": decision.activation_epoch_id,
            "input_fingerprint": decision.fingerprint,
            "supersedes_batch_id": decision.supersedes_batch_id,
        }
        existing = self._batches.read_batch(self._slot, self._modeling_path, normalized_batch_id)
        if existing is None:
            self._batches.write_batch(
                self._slot,
                self._modeling_path,
                normalized_batch_id,
                out,
            )
        elif any(
            existing.get(field) != out.get(field)
            for field in (
                "site_id",
                "device_id",
                "branch_id",
                "business_date",
                "activation_epoch_id",
                "input_fingerprint",
                "supersedes_batch_id",
            )
        ):
            raise ImmutableBatchRecoveryError(
                f"batch_id={normalized_batch_id!r} 已存在但合同字段不一致，拒绝覆盖"
            )
        return self._ledger.reconcile_succeeded_from_batch(
            decision.key,
            batch_id=normalized_batch_id,
            fingerprint=decision.fingerprint,
            activation_epoch_id=decision.activation_epoch_id,
            supersedes_batch_id=decision.supersedes_batch_id,
        )

    def record_failure(self, decision: InferenceDecision, error: str) -> LedgerRecord:
        """记录 predictor/持久化失败；修订失败由 Ledger 恢复旧 succeeded 事实。"""

        if decision.action != "run":
            raise ImmutableBatchRecoveryError("skip 判定不能记录推理失败")
        try:
            return self._ledger.mark_failed(decision.key, str(error))
        except LedgerOperationError as exc:
            raise ImmutableBatchRecoveryError(str(exc)) from exc
# @AI_GENERATED: end
