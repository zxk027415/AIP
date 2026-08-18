# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/scheduler/pv_dual_path/shadow_compare.py — 跨路径双 Champion Shadow 对比

对应设计：.kiro/specs/pv-fault-dual-path-serving/design.md §9；任务 9.1–9.6。

只加载两条路径当前 Champion，对同一批完整历史设备日做只读推理，产出三层证据报告。
报告是切换准入证据，不改游标、记录、批次、Ledger、Registry、Epoch 或任何治理事件。
"""

from __future__ import annotations

import copy
import json
import logging
import os
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from services.scheduler.pv_dual_path.persistence_utils import atomic_write_json, to_relative_path

logger = logging.getLogger(__name__)

_DEFAULT_SLOT = "pv_fault"
_BACKEND_SERVICE_DIR = Path(__file__).resolve().parents[3]
_ENV_SHADOW_DIR = "PV_SHADOW_COMPARE_DIR"
_DEFAULT_SHADOW_DIR = _BACKEND_SERVICE_DIR / "data" / "pv_dual_path" / "shadow_compare"

SEQ_PROJECTION_RULE_ID = "seq_point_majority_vote_to_day_label"
SEQ_PROJECTION_RULE_DEFINITION = (
    "将 seq_annotation 的逐点标签按时钟槽做多数票：出现次数最多的标签作为天级标签；"
    "平票时取编号较小的标签。该投影只用于共同天级证据层，不改变 Seq 原生逐点结果。"
)
_NO_LEGACY_COUNTERPART = "无 Legacy 对应值"
_NIGHT_SLOTS = frozenset(list(range(0, 72)) + list(range(264, 288)))
_BLOCKING_REASON_TOKENS = (
    "artifact",
    "unloadable",
    "inference",
    "exception",
    "load_failed",
    "predict_failed",
    "model_load",
)
_DEFERRED_REASON_TOKENS = (
    "completeness",
    "waiting_data",
    "deferred",
    "gate",
    "incomplete",
    "no_result",
)


def _resolve_shadow_dir() -> Path:
    """解析 Shadow 报告落盘目录：环境变量覆盖 > 默认相对路径。"""
    override = os.environ.get(_ENV_SHADOW_DIR)
    if override:
        override_path = Path(override)
        if override_path.is_absolute():
            return override_path
        return _BACKEND_SERVICE_DIR / override_path
    return _DEFAULT_SHADOW_DIR


def _default_load_champion_artifact(model_ref: str) -> Dict[str, Any]:
    """默认只验证 Champion 工件可解析为相对路径且文件或目录存在。"""
    relative = to_relative_path(model_ref, base_dir=_BACKEND_SERVICE_DIR)
    candidate = _BACKEND_SERVICE_DIR / relative
    if not candidate.exists():
        raise ValueError(f"champion_artifact_unloadable:{relative}")
    return {"model_ref": relative, "loaded": True}


def _majority_label(labels: Sequence[int]) -> int:
    counts: Counter[int] = Counter(int(label) for label in labels)
    return min(counts, key=lambda label: (-counts[label], label))


def _project_seq_points_to_day_label(point_predictions: Sequence[Any]) -> int:
    """按 ``seq_point_majority_vote_to_day_label`` 把逐点结果投影为天级标签。"""
    labels: List[int] = []
    for item in point_predictions:
        if isinstance(item, dict):
            labels.append(int(item.get("label", item.get("predicted_label", 0))))
        else:
            labels.append(int(item))
    if not labels:
        raise ValueError("seq_point_predictions_empty")
    return _majority_label(labels)


def _macro_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    labels = sorted(set(y_true.tolist()) | set(y_pred.tolist()))
    scores: List[float] = []
    for label in labels:
        true_mask = y_true == label
        pred_mask = y_pred == label
        tp = float(np.sum(true_mask & pred_mask))
        fp = float(np.sum(~true_mask & pred_mask))
        fn = float(np.sum(true_mask & ~pred_mask))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        if precision + recall == 0:
            scores.append(0.0)
        else:
            scores.append(2.0 * precision * recall / (precision + recall))
    return float(np.mean(scores)) if scores else 0.0


def _fault_segments(labels: Sequence[int]) -> List[Tuple[int, int]]:
    segments: List[Tuple[int, int]] = []
    start: Optional[int] = None
    for index, label in enumerate(labels):
        if int(label) != 0 and start is None:
            start = index
        elif int(label) == 0 and start is not None:
            segments.append((start, index))
            start = None
    if start is not None:
        segments.append((start, len(labels)))
    return segments


def _segment_iou(y_true: Sequence[int], y_pred: Sequence[int]) -> float:
    true_fault = np.array([int(value) != 0 for value in y_true], dtype=bool)
    pred_fault = np.array([int(value) != 0 for value in y_pred], dtype=bool)
    intersection = float(np.sum(true_fault & pred_fault))
    union = float(np.sum(true_fault | pred_fault))
    return intersection / union if union else 0.0


def _boundary_deviation(y_true: Sequence[int], y_pred: Sequence[int]) -> Optional[float]:
    true_segments = _fault_segments(y_true)
    pred_segments = _fault_segments(y_pred)
    if not true_segments or not pred_segments:
        return None
    paired = min(len(true_segments), len(pred_segments))
    deltas: List[float] = []
    for index in range(paired):
        true_start, true_end = true_segments[index]
        pred_start, pred_end = pred_segments[index]
        deltas.append(abs(true_start - pred_start))
        deltas.append(abs(true_end - pred_end))
    return round(float(np.mean(deltas)), 6) if deltas else None


def _extract_point_labels(values: Sequence[Any]) -> List[int]:
    labels: List[int] = []
    for item in values:
        if isinstance(item, dict):
            labels.append(int(item.get("label", item.get("predicted_label", 0))))
        else:
            labels.append(int(item))
    return labels


def _classify_severity(*, error: Optional[str], reason: str) -> str:
    text = f"{error or ''} {reason or ''}".lower()
    if error or any(token in text for token in _BLOCKING_REASON_TOKENS):
        if any(token in text for token in _DEFERRED_REASON_TOKENS) and not error:
            return "deferred"
        return "blocking"
    return "deferred"


@dataclass(frozen=True)
class CrossPathShadowReport:
    """跨路径双 Champion Shadow 对比报告（不可变、只产证据）。

    字段（英文名 — 中文含义）：
      - comparison_id      — 比对任务 ID。
      - legacy_model_ref    — legacy_day 当前 Champion 引用。
      - seq_model_ref       — seq_annotation 当前 Champion 引用。
      - device_day_total    — 候选设备日总数。
      - comparable_total    — 两路均成功的可比设备日数。
      - agreement_rate      — 天级标签一致率。
      - diff_items          — 天级标签不同的设备日及双方标签。
      - uncomparable_items  — 不可比项，含 blocking/deferred。
      - coverage_rate       — 已产出可比结果数 / 应产出设备日数。
      - deferred_rate       — 门禁顺延数 / 候选总数。
      - projection_rule     — Seq 逐点投影为天级的规则标识。
      - common_metrics      — 共同天级证据。
      - seq_native_metrics  — Seq 原生证据。
      - runtime_metrics     — 生产运行证据。
      - generated_at        — 报告生成 UTC 时刻。
    """

    comparison_id: str
    legacy_model_ref: str
    seq_model_ref: str
    device_day_total: int
    comparable_total: int
    agreement_rate: float
    diff_items: List[Dict[str, Any]] = field(default_factory=list)
    uncomparable_items: List[Dict[str, Any]] = field(default_factory=list)
    coverage_rate: float = 0.0
    deferred_rate: float = 0.0
    projection_rule: Optional[str] = None
    common_metrics: Dict[str, Any] = field(default_factory=dict)
    seq_native_metrics: Dict[str, Any] = field(default_factory=dict)
    runtime_metrics: Dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "legacy_model_ref": self.legacy_model_ref,
            "seq_model_ref": self.seq_model_ref,
            "device_day_total": self.device_day_total,
            "comparable_total": self.comparable_total,
            "agreement_rate": self.agreement_rate,
            "diff_items": self.diff_items,
            "uncomparable_items": self.uncomparable_items,
            "coverage_rate": self.coverage_rate,
            "deferred_rate": self.deferred_rate,
            "projection_rule": self.projection_rule,
            "common_metrics": self.common_metrics,
            "seq_native_metrics": self.seq_native_metrics,
            "runtime_metrics": self.runtime_metrics,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CrossPathShadowReport":
        return cls(
            comparison_id=payload["comparison_id"],
            legacy_model_ref=payload["legacy_model_ref"],
            seq_model_ref=payload["seq_model_ref"],
            device_day_total=payload.get("device_day_total", 0),
            comparable_total=payload.get("comparable_total", 0),
            agreement_rate=payload.get("agreement_rate", 0.0),
            diff_items=list(payload.get("diff_items") or []),
            uncomparable_items=list(payload.get("uncomparable_items") or []),
            coverage_rate=payload.get("coverage_rate", 0.0),
            deferred_rate=payload.get("deferred_rate", 0.0),
            projection_rule=payload.get("projection_rule"),
            common_metrics=dict(payload.get("common_metrics") or {}),
            seq_native_metrics=dict(payload.get("seq_native_metrics") or {}),
            runtime_metrics=dict(payload.get("runtime_metrics") or {}),
            generated_at=payload.get("generated_at", ""),
        )


class ShadowReportNotFoundError(LookupError):
    """按 `comparison_id` 查询报告未命中时抛出。"""

    def __init__(self, comparison_id: str) -> None:
        self.comparison_id = comparison_id
        super().__init__(f"未找到 Shadow 报告：comparison_id={comparison_id!r}")


class ShadowReportStore:
    """CrossPathShadowReport 的相对路径 JSON 存取。"""

    def __init__(self, base_dir: Optional[Path] = None, slot: str = _DEFAULT_SLOT) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else _resolve_shadow_dir()
        self._slot = slot

    def _slot_dir(self) -> Path:
        return self._base_dir / self._slot

    def _report_path(self, comparison_id: str) -> Path:
        return self._slot_dir() / f"{comparison_id}.json"

    def save(self, report: CrossPathShadowReport) -> Path:
        """原子落盘保存报告，返回相对路径。"""
        slot_dir = self._slot_dir()
        slot_dir.mkdir(parents=True, exist_ok=True)
        report_path = self._report_path(report.comparison_id)
        atomic_write_json(report_path, report.to_dict(), base_dir=self._base_dir)
        try:
            return report_path.relative_to(_BACKEND_SERVICE_DIR)
        except ValueError:
            try:
                return report_path.relative_to(self._base_dir)
            except ValueError:
                return Path(report_path.name)

    def load(self, comparison_id: str) -> Optional[CrossPathShadowReport]:
        report_path = self._report_path(comparison_id)
        if not report_path.exists():
            return None
        with open(report_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Shadow 报告必须是 JSON object")
        return CrossPathShadowReport.from_dict(payload)

    def load_or_raise(self, comparison_id: str) -> CrossPathShadowReport:
        report = self.load(comparison_id)
        if report is None:
            raise ShadowReportNotFoundError(comparison_id)
        return report


class ShadowCompareRunner:
    """双 Champion Shadow 对比执行器：只读加载双路径 Champion 并生成三层证据。"""

    def __init__(
        self,
        model_registry: Any = None,
        legacy_champion_reader: Optional[Callable[..., Any]] = None,
        seq_champion_reader: Optional[Callable[..., Any]] = None,
        report_store: Optional[ShadowReportStore] = None,
        *,
        slot: str = _DEFAULT_SLOT,
        artifact_loader: Optional[Callable[[str], Any]] = None,
        production_snapshot_fn: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._model_registry = model_registry
        self._legacy_champion_reader = legacy_champion_reader
        self._seq_champion_reader = seq_champion_reader
        self._report_store = report_store or ShadowReportStore()
        self._slot = slot
        self._artifact_loader = artifact_loader or _default_load_champion_artifact
        self._production_snapshot_fn = production_snapshot_fn

    def _resolve_and_load_champions(self) -> Tuple[str, str]:
        """只解析并加载两条路径当前 Champion；缺件或不可加载即拒绝。"""
        if self._model_registry is None:
            raise RuntimeError("ShadowCompareRunner 未注入 PVModelRegistry")
        state = self._model_registry.get_slot(self._slot)
        legacy_lifecycle = state.path_models.get("legacy_day")
        seq_lifecycle = state.path_models.get("seq_annotation")
        legacy_champion = legacy_lifecycle.champion if legacy_lifecycle else None
        seq_champion = seq_lifecycle.champion if seq_lifecycle else None
        if legacy_champion is None:
            raise ValueError("legacy_day 路径无合格 Champion，拒绝执行 Shadow 对比")
        if seq_champion is None:
            raise ValueError("seq_annotation 路径无合格 Champion，拒绝执行 Shadow 对比")
        legacy_ref = str(legacy_champion.model_ref)
        seq_ref = str(seq_champion.model_ref)
        for path, model_ref, lifecycle in (
            ("legacy_day", legacy_ref, legacy_lifecycle),
            ("seq_annotation", seq_ref, seq_lifecycle),
        ):
            challenger_refs = {
                str(item.model_ref) for item in (lifecycle.challengers if lifecycle else [])
            }
            retired_refs = {
                str(item.model_ref) for item in (lifecycle.retired if lifecycle else [])
            }
            if model_ref != str(lifecycle.champion.model_ref):
                raise ValueError(f"{path} Shadow 只能使用当前 Champion")
            if model_ref in challenger_refs and model_ref not in {str(lifecycle.champion.model_ref)}:
                raise ValueError(f"{path} 拒绝使用 Challenger 替代 Champion")
            if model_ref in retired_refs and model_ref != str(lifecycle.champion.model_ref):
                raise ValueError(f"{path} 拒绝使用 retired 替代 Champion")
            try:
                self._artifact_loader(model_ref)
            except Exception as exc:
                raise ValueError(
                    f"{path} Champion 工件不可加载：model_ref={model_ref!r}"
                ) from exc
        return legacy_ref, seq_ref

    def _capture_production_snapshot(self) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {}
        if self._model_registry is not None:
            state = self._model_registry.get_slot(self._slot)
            payload = state.to_dict()
            payload.pop("updated_at", None)
            snapshot["registry"] = payload
            try:
                snapshot["promotion_event_ids"] = [
                    event.promotion_event_id
                    for event in self._model_registry._promotion_store(self._slot).list_recent(limit=10000)
                ]
                snapshot["path_switch_event_ids"] = [
                    event.path_switch_event_id
                    for event in self._model_registry._path_switch_store(self._slot).list_recent(limit=10000)
                ]
            except Exception:
                snapshot["promotion_event_ids"] = []
                snapshot["path_switch_event_ids"] = []
        if self._production_snapshot_fn is not None:
            snapshot["external"] = copy.deepcopy(self._production_snapshot_fn())
        return snapshot

    def run_compare(
        self,
        start_date: date,
        end_date: date,
        device_scope: Optional[List[Dict[str, Any]]] = None,
    ) -> CrossPathShadowReport:
        if end_date < start_date:
            raise ValueError("end_date 不能早于 start_date")

        before = self._capture_production_snapshot()
        legacy_ref, seq_ref = self._resolve_and_load_champions()

        legacy_results: List[Dict[str, Any]] = []
        seq_results: List[Dict[str, Any]] = []
        if self._legacy_champion_reader is not None:
            legacy_results = list(
                self._legacy_champion_reader(
                    model_ref=legacy_ref,
                    start_date=start_date,
                    end_date=end_date,
                    device_scope=device_scope,
                )
                or []
            )
        if self._seq_champion_reader is not None:
            seq_results = list(
                self._seq_champion_reader(
                    model_ref=seq_ref,
                    start_date=start_date,
                    end_date=end_date,
                    device_scope=device_scope,
                )
                or []
            )

        legacy_index = self._index_results(legacy_results)
        seq_index = self._index_results(seq_results)
        all_keys = sorted(set(legacy_index) | set(seq_index))
        device_day_total = len(all_keys)

        comparable_total = 0
        agreement_count = 0
        diff_items: List[Dict[str, Any]] = []
        uncomparable_items: List[Dict[str, Any]] = []
        common_day_labels_legacy: List[int] = []
        common_day_labels_seq: List[int] = []
        ground_truth_day: List[int] = []
        seq_point_predictions: List[Dict[str, Any]] = []

        for key in all_keys:
            legacy_item = legacy_index.get(key)
            seq_item = seq_index.get(key)
            site_id, device_id, branch_id, biz_date = key
            if legacy_item is None or seq_item is None:
                failed_path = "legacy_day" if legacy_item is None else "seq_annotation"
                uncomparable_items.append(
                    {
                        "site_id": site_id,
                        "device_id": device_id,
                        "branch_id": branch_id,
                        "business_date": biz_date.isoformat(),
                        "failed_path": failed_path,
                        "reason": "no_result",
                        "severity": "deferred",
                    }
                )
                continue

            legacy_error = legacy_item.get("error")
            seq_error = seq_item.get("error")
            if legacy_error or seq_error:
                failed_path = "legacy_day" if legacy_error else "seq_annotation"
                reason = str(legacy_error or seq_error)
                uncomparable_items.append(
                    {
                        "site_id": site_id,
                        "device_id": device_id,
                        "branch_id": branch_id,
                        "business_date": biz_date.isoformat(),
                        "failed_path": failed_path,
                        "reason": reason,
                        "severity": _classify_severity(error=reason, reason=reason),
                    }
                )
                continue

            comparable_total += 1
            seq_points = seq_item.get("point_predictions")
            if seq_points:
                seq_label = _project_seq_points_to_day_label(seq_points)
                seq_item = dict(seq_item)
                seq_item["predicted_label"] = seq_label
                seq_point_predictions.append(seq_item)
            else:
                seq_label = int(seq_item.get("predicted_label", -1))
            legacy_label = int(legacy_item.get("predicted_label", -1))
            common_day_labels_legacy.append(legacy_label)
            common_day_labels_seq.append(seq_label)
            if legacy_item.get("ground_truth_label") is not None:
                ground_truth_day.append(int(legacy_item["ground_truth_label"]))
            elif seq_item.get("ground_truth_label") is not None:
                ground_truth_day.append(int(seq_item["ground_truth_label"]))

            if legacy_label == seq_label:
                agreement_count += 1
            else:
                diff_items.append(
                    {
                        "site_id": site_id,
                        "device_id": device_id,
                        "branch_id": branch_id,
                        "business_date": biz_date.isoformat(),
                        "legacy_label": legacy_label,
                        "seq_label": seq_label,
                    }
                )

        agreement_rate = agreement_count / comparable_total if comparable_total else 0.0
        coverage_rate = comparable_total / device_day_total if device_day_total else 0.0
        deferred_count = sum(1 for item in uncomparable_items if item.get("severity") == "deferred")
        deferred_rate = deferred_count / device_day_total if device_day_total else 0.0

        common_metrics = self._compute_common_metrics(
            common_day_labels_legacy,
            common_day_labels_seq,
            coverage_rate=coverage_rate,
            ground_truth_labels=ground_truth_day if len(ground_truth_day) == comparable_total else None,
        )
        seq_native_metrics = self._compute_seq_native_metrics(seq_point_predictions)
        runtime_metrics = self._compute_runtime_metrics(
            legacy_results, seq_results, uncomparable_items, start_date, end_date
        )

        report = CrossPathShadowReport(
            comparison_id=f"shadow-{uuid.uuid4().hex[:12]}",
            legacy_model_ref=legacy_ref,
            seq_model_ref=seq_ref,
            device_day_total=device_day_total,
            comparable_total=comparable_total,
            agreement_rate=round(agreement_rate, 6),
            diff_items=diff_items,
            uncomparable_items=uncomparable_items,
            coverage_rate=round(coverage_rate, 6),
            deferred_rate=round(deferred_rate, 6),
            projection_rule=SEQ_PROJECTION_RULE_ID,
            common_metrics=common_metrics,
            seq_native_metrics=seq_native_metrics,
            runtime_metrics=runtime_metrics,
            generated_at=datetime.utcnow().isoformat(),
        )
        self._report_store.save(report)

        after = self._capture_production_snapshot()
        if before != after:
            raise RuntimeError("Shadow 对比改变了生产或治理事实，已拒绝该副作用")
        return report

    @staticmethod
    def _index_results(results: Sequence[Dict[str, Any]]) -> Dict[tuple, Dict[str, Any]]:
        """按设备日建索引；同一设备日出现两条结果视为违反每路恰好一结果。"""
        index: Dict[tuple, Dict[str, Any]] = {}
        for item in results:
            raw_date = item.get("business_date")
            if isinstance(raw_date, date) and not isinstance(raw_date, datetime):
                biz_date = raw_date
            elif isinstance(raw_date, datetime):
                biz_date = raw_date.date()
            else:
                biz_date = date.fromisoformat(str(raw_date)[:10])
            key = (
                str(item.get("site_id") or ""),
                str(item.get("device_id") or ""),
                str(item.get("branch_id") or "1"),
                biz_date,
            )
            if key in index:
                raise ValueError(
                    "每个设备日每路只能有一个 Shadow 结果: "
                    f"{key[0]}/{key[1]}/{key[2]}/{key[3].isoformat()}"
                )
            index[key] = item
        return index

    @staticmethod
    def _compute_common_metrics(
        legacy_labels: List[int],
        seq_labels: List[int],
        *,
        coverage_rate: float,
        ground_truth_labels: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """共同天级证据：准确率、故障召回率、误报率、一致率、覆盖率与混淆计数。"""
        payload: Dict[str, Any] = {
            "projection_rule_id": SEQ_PROJECTION_RULE_ID,
            "projection_rule_definition": SEQ_PROJECTION_RULE_DEFINITION,
            "coverage_rate": round(coverage_rate, 6),
        }
        if not legacy_labels or not seq_labels:
            payload["note"] = "no_comparable_device_days"
            return payload
        n = len(legacy_labels)
        legacy_arr = np.array(legacy_labels, dtype=np.int64)
        seq_arr = np.array(seq_labels, dtype=np.int64)
        agreement = int(np.sum(legacy_arr == seq_arr))
        confusion: Dict[str, int] = {}
        for legacy_label, seq_label in zip(legacy_labels, seq_labels):
            key = f"{legacy_label}->{seq_label}"
            confusion[key] = confusion.get(key, 0) + 1
        if ground_truth_labels:
            truth = np.array(ground_truth_labels, dtype=np.int64)
            reference = "ground_truth_label"
            day_accuracy = float(np.mean(seq_arr == truth))
            truth_fault = truth != 0
            seq_fault = seq_arr != 0
            fault_recall = float(np.sum(truth_fault & seq_fault) / max(1, np.sum(truth_fault)))
            false_positive = float(np.sum(seq_fault & ~truth_fault) / max(1, np.sum(~truth_fault)))
        else:
            reference = "pairwise_legacy_as_reference"
            day_accuracy = agreement / n
            legacy_fault = legacy_arr != 0
            seq_fault = seq_arr != 0
            fault_recall = float(np.sum(legacy_fault & seq_fault) / max(1, np.sum(legacy_fault)))
            false_positive = float(np.sum(seq_fault & ~legacy_fault) / max(1, np.sum(~legacy_fault)))
        payload.update(
            {
                "device_day_count": n,
                "reference": reference,
                "day_accuracy": round(day_accuracy, 6),
                "agreement_rate": round(agreement / n, 6),
                "fault_recall": round(fault_recall, 6),
                "false_positive_rate": round(false_positive, 6),
                "legacy_fault_count": int(np.sum(legacy_arr != 0)),
                "seq_fault_count": int(np.sum(seq_arr != 0)),
                "confusion_counts": confusion,
            }
        )
        return payload

    @staticmethod
    def _compute_seq_native_metrics(seq_predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Seq 原生证据；Legacy 无对应值时显式标注，不输出伪横向结论。"""
        native: Dict[str, Any] = {
            "legacy_counterpart": _NO_LEGACY_COUNTERPART,
            "cross_path_conclusion": None,
        }
        if not seq_predictions:
            native["note"] = "no_seq_point_predictions_available"
            return native

        contract_ok = all(len(item.get("point_predictions") or []) == 288 for item in seq_predictions)
        total_points = 0
        total_fault_points = 0
        f1_scores: List[float] = []
        ious: List[float] = []
        boundary_devs: List[float] = []
        night_false_positives = 0
        night_available = False
        for item in seq_predictions:
            pred_labels = _extract_point_labels(item.get("point_predictions") or [])
            total_points += len(pred_labels)
            total_fault_points += sum(1 for label in pred_labels if label != 0)
            true_labels = item.get("point_labels")
            if true_labels is not None:
                truth = _extract_point_labels(true_labels)
                if len(truth) == len(pred_labels) and truth:
                    pred = np.array(pred_labels, dtype=np.int64)
                    true_arr = np.array(truth, dtype=np.int64)
                    f1_scores.append(_macro_f1(true_arr, pred))
                    ious.append(_segment_iou(truth, pred_labels))
                    deviation = _boundary_deviation(truth, pred_labels)
                    if deviation is not None:
                        boundary_devs.append(deviation)
                    night_available = True
                    for slot, (true_label, pred_label) in enumerate(zip(truth, pred_labels)):
                        if slot in _NIGHT_SLOTS and int(true_label) == 0 and int(pred_label) != 0:
                            night_false_positives += 1
            elif item.get("night_false_positives") is not None:
                night_available = True
                night_false_positives += int(item["night_false_positives"])

        native.update(
            {
                "total_sequences": len(seq_predictions),
                "total_points": total_points,
                "total_fault_points": total_fault_points,
                "point_level_288_contract": contract_ok,
                "point_macro_f1": round(float(np.mean(f1_scores)), 6) if f1_scores else None,
                "fault_segment_iou": round(float(np.mean(ious)), 6) if ious else None,
                "boundary_deviation": round(float(np.mean(boundary_devs)), 6) if boundary_devs else None,
                "night_false_positives": night_false_positives if night_available else None,
            }
        )
        if not f1_scores:
            native["point_macro_f1_unavailable_reason"] = "no_point_ground_truth"
            native["fault_segment_iou_unavailable_reason"] = "no_point_ground_truth"
            native["boundary_deviation_unavailable_reason"] = "no_point_ground_truth"
        return native

    @staticmethod
    def _compute_runtime_metrics(
        legacy_results: List[Dict[str, Any]],
        seq_results: List[Dict[str, Any]],
        uncomparable_items: List[Dict[str, Any]],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """运行证据：延迟、顺延率、失败率、日容量、工件加载成功率。"""

        day_span = max(1, (end_date - start_date).days + 1)

        def _path_runtime(results: List[Dict[str, Any]], path: str) -> Dict[str, Any]:
            n = len(results)
            if n == 0:
                return {
                    "total": 0,
                    "failed": 0,
                    "failure_rate": 0.0,
                    "deferred_rate": 0.0,
                    "artifact_load_success_rate": 0.0,
                    "mean_latency_ms": None,
                    "daily_capacity": 0.0,
                }
            errors = [item for item in results if item.get("error")]
            deferred = [
                item
                for item in uncomparable_items
                if item.get("failed_path") == path and item.get("severity") == "deferred"
            ]
            latencies = [
                float(item["latency_ms"])
                for item in results
                if item.get("latency_ms") is not None
            ]
            succeeded = n - len(errors)
            return {
                "total": n,
                "failed": len(errors),
                "failure_rate": round(len(errors) / n, 6),
                "deferred_rate": round(len(deferred) / n, 6),
                "artifact_load_success_rate": round(succeeded / n, 6),
                "mean_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
                "daily_capacity": round(succeeded / day_span, 6),
            }

        blocking_count = sum(1 for item in uncomparable_items if item.get("severity") == "blocking")
        deferred_count = sum(1 for item in uncomparable_items if item.get("severity") == "deferred")
        return {
            "legacy_day": _path_runtime(legacy_results, "legacy_day"),
            "seq_annotation": _path_runtime(seq_results, "seq_annotation"),
            "blocking_count": blocking_count,
            "deferred_count": deferred_count,
        }
# @AI_GENERATED: end
