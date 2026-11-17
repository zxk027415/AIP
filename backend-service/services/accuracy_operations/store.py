# @AI_GENERATED
"""
accuracy_operations/store.py — 精度运营持久化 Store

负责 alerts / rca / recovery 三类实体的 JSON 读写（无 training_tasks）。

目录结构（均为相对 backend-service/ 的相对路径）：
  data/precision_ops/{slot}/accuracy_ops/alerts/{alert_id}.json
  data/precision_ops/{slot}/accuracy_ops/rca/{rca_report_id}.json
  data/precision_ops/{slot}/accuracy_ops/recovery/{decision_id}.json

约束：
  - 所有路径通过 os.path.relpath(path, start=backend_service_dir) 转换为相对路径
  - 禁止 os.path.abspath()
  - 写入前校验 not os.path.isabs(path)，违反则抛 ValueError
  - slot 名称仅允许小写字母、数字、下划线和连字符

References: Requirements 8.1, 8.2, 8.3, 8.4
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional

from services.accuracy_operations.models import (
    AccuracyAlert,
    DecisionStatus,
    RCAReport,
    RecoveryChannel,
    RecoveryDecision,
)
from services.precision_ops.utils import (
    BASE_DATA_DIR,
    _atomic_write_json,
    load_json_safe,
    now_iso,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 告警状态迁移常量
# ---------------------------------------------------------------------------

# 合法状态迁移集合
_ALERT_ALLOWED_TRANSITIONS: set = {
    ("open", "rca_running"),
    ("rca_running", "recovering"),
    ("rca_running", "observing"),
    ("recovering", "closed"),
    ("observing", "closed"),
    # 失败回退路径（允许从任何状态回退到 open）
    ("rca_running", "open"),
    ("recovering", "open"),
    ("observing", "open"),
}

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# BASE_DATA_DIR = backend-service/data/precision_ops/
# BASE_DATA_DIR.parent = backend-service/data/
# BASE_DATA_DIR.parent.parent = backend-service/
_BACKEND_SERVICE_DIR: Path = BASE_DATA_DIR.parent.parent

# slot 名称正则：仅允许小写字母、数字、下划线和连字符
_SLOT_RE = re.compile(r"^[a-z0-9_-]+$")

# list 操作最大返回条数
_LIST_MAX = 200


# ---------------------------------------------------------------------------
# 路径工具
# ---------------------------------------------------------------------------


def _validate_slot(slot: str) -> None:
    """校验 slot 名称格式，不合法则抛 ValueError。"""
    if not _SLOT_RE.match(slot):
        raise ValueError(
            f"非法 slot 名称 '{slot}'：仅允许小写字母、数字、下划线和连字符"
        )


def _to_relpath(abs_path: Path) -> str:
    """
    将绝对路径转换为相对于 backend_service_dir 的相对路径字符串。

    写入前校验 not os.path.isabs()，违反则抛 ValueError。

    :param abs_path: 绝对路径（Path 对象）
    :return: 相对路径字符串，如 data/precision_ops/default/accuracy_ops/alerts/alert-xx.json
    :raises ValueError: 转换后仍为绝对路径
    """
    rel = os.path.relpath(str(abs_path), start=str(_BACKEND_SERVICE_DIR))
    if os.path.isabs(rel):
        raise ValueError(
            f"路径转换后仍为绝对路径，违反持久化相对路径规范: {rel}"
        )
    return rel


def _accuracy_ops_dir(slot: str) -> Path:
    """返回 data/precision_ops/{slot}/accuracy_ops/ 的绝对路径（用于实际 I/O）。"""
    return BASE_DATA_DIR / slot / "accuracy_ops"


def _alert_path(slot: str, alert_id: str) -> Path:
    """返回单条告警 JSON 文件的绝对路径。"""
    return _accuracy_ops_dir(slot) / "alerts" / f"{alert_id}.json"


def _rca_path(slot: str, rca_report_id: str) -> Path:
    """返回单条 RCA 报告 JSON 文件的绝对路径。"""
    return _accuracy_ops_dir(slot) / "rca" / f"{rca_report_id}.json"


def _recovery_path(slot: str, decision_id: str) -> Path:
    """返回单条恢复决策 JSON 文件的绝对路径。"""
    return _accuracy_ops_dir(slot) / "recovery" / f"{decision_id}.json"


# ---------------------------------------------------------------------------
# AccuracyOperationsStore
# ---------------------------------------------------------------------------


class AccuracyOperationsStore:
    """
    精度运营持久化 Store。

    负责 alerts / rca / recovery 三类实体的 JSON 读写（无 training_tasks）。
    所有写入路径均为相对于 backend-service/ 的相对路径，
    禁止使用 os.path.abspath()。

    References: Requirements 8.1, 8.2, 8.3, 8.4
    """

    # ------------------------------------------------------------------ alerts

    def save_alert(self, slot: str, alert: AccuracyAlert) -> None:
        """
        持久化一条精度告警（新建或覆盖 upsert）。

        :param slot: 槽位名称 — 小写字母/数字/下划线/连字符
        :param alert: AccuracyAlert 实体
        :raises ValueError: slot 名称不合法或路径为绝对路径
        """
        _validate_slot(slot)
        abs_path = _alert_path(slot, alert.alert_id)
        rel = _to_relpath(abs_path)
        _atomic_write_json(abs_path, alert.dict())
        logger.debug("save_alert: 已写入 %s", rel)

    def get_alert(self, slot: str, alert_id: str) -> Optional[AccuracyAlert]:
        """
        读取单条告警，不存在或解析失败返回 None。

        :param slot: 槽位名称
        :param alert_id: 告警 ID — 格式 alert-{8hex}
        :return: AccuracyAlert 或 None
        """
        _validate_slot(slot)
        data = load_json_safe(_alert_path(slot, alert_id))
        if data is None:
            return None
        try:
            return AccuracyAlert.parse_obj(data)
        except Exception as exc:
            logger.warning(
                "get_alert: 解析失败 slot=%s alert_id=%s: %s", slot, alert_id, exc
            )
            return None

    def list_alerts(
        self,
        slot: str,
        status: Optional[str] = None,
        limit: int = 200,
    ) -> List[AccuracyAlert]:
        """
        列出 slot 下所有告警，可按 status 过滤，最多返回 limit 条（上限 200）。

        :param slot: 槽位名称
        :param status: 可选，AlertStatus 枚举值字符串
                       （open/rca_running/recovering/observing/closed）
        :param limit: 最大返回条数，上限 200
        :return: AccuracyAlert 列表，按文件名（即 alert_id）升序
        """
        _validate_slot(slot)
        effective_limit = min(limit, _LIST_MAX)
        alerts_dir = _accuracy_ops_dir(slot) / "alerts"
        if not alerts_dir.exists():
            return []

        results: List[AccuracyAlert] = []
        for json_file in sorted(alerts_dir.glob("*.json")):
            if len(results) >= effective_limit:
                break
            data = load_json_safe(json_file)
            if data is None:
                continue
            try:
                alert = AccuracyAlert.parse_obj(data)
            except Exception as exc:
                logger.warning(
                    "list_alerts: 解析失败 slot=%s file=%s: %s", slot, json_file.name, exc
                )
                continue
            if status is not None and alert.status != status:
                continue
            results.append(alert)

        return results

    def has_open_alert(
        self,
        slot: str,
        model_form: str,
        workflow_id: str,
        version_tag: Optional[str] = None,
    ) -> bool:
        """
        检查 slot 下是否已存在 status=open 且匹配 model_form + workflow_id 的告警。

        用于告警去重：同 slot + model_form + workflow_id 已有 open alert 则不重复生成。

        :param slot: 槽位名称
        :param model_form: 模型形态 — 如 "production" / "shadow"
        :param workflow_id: 退化版本的 workflow_id
        :return: True 表示已存在 open 告警
        """
        _validate_slot(slot)
        alerts_dir = _accuracy_ops_dir(slot) / "alerts"
        if not alerts_dir.exists():
            return False

        for json_file in alerts_dir.glob("*.json"):
            data = load_json_safe(json_file)
            if data is None:
                continue
            try:
                alert = AccuracyAlert.parse_obj(data)
            except Exception:
                continue
            if (
                alert.status == "open"
                and alert.model_form == model_form
                and alert.workflow_id == workflow_id
                and (version_tag is None or alert.version_tag == version_tag)
            ):
                return True
        return False

    def update_alert(self, slot: str, alert: AccuracyAlert) -> None:
        """
        更新（upsert）一条精度告警，语义与 save_alert 相同。

        这是一个原始 upsert，不做状态迁移校验，供编排器内部使用。
        API 层和 UI 触发的状态迁移请使用 transition_alert_status。

        :param slot: 槽位名称
        :param alert: AccuracyAlert 实体（已修改字段）
        :raises ValueError: slot 名称不合法或路径为绝对路径
        """
        self.save_alert(slot, alert)

    # @AI_GENERATED: 实验 restore 专用——绕过状态机直接关闭，不走 transition
    def force_close_alert(
        self,
        slot: str,
        alert_id: str,
        recovery_evidence: Optional[dict] = None,
    ) -> Optional["AccuracyAlert"]:
        """直接将告警状态改为 closed，不校验状态机迁移路径。
        仅供劣化实验 restore 使用。正常运营流程必须走 transition_alert_status。
        """
        from services.precision_ops.utils import now_iso
        alert = self.get_alert(slot, alert_id)
        if alert is None:
            return None
        alert.status = "closed"  # type: ignore[assignment]
        alert.updated_at = now_iso()
        if recovery_evidence:
            alert.recovery_evidence = recovery_evidence
        self.save_alert(slot, alert)
        return alert
    # @AI_GENERATED: end

    def transition_alert_status(
        slot: str,
        alert_id: str,
        new_status: str,
        recovery_evidence: Optional[dict] = None,
    ) -> AccuracyAlert:
        """
        校验并执行 AccuracyAlert 的状态迁移。

        规则：
        - (current_status, new_status) 必须在 _ALERT_ALLOWED_TRANSITIONS 中
        - 若 new_status == "closed"，recovery_evidence 必须非空且
          recovery_evidence.get("type") ∈ {"passed", "manual_close"}
        - 非法迁移或缺少证据时抛 ValueError
        - 更新 alert.status、alert.updated_at，关闭时同步写入 alert.recovery_evidence
        - 持久化并返回更新后的告警

        :param slot: 槽位名称 — 小写字母/数字/下划线/连字符
        :param alert_id: 告警 ID — 格式 alert-{8hex}
        :param new_status: 目标状态字符串（AlertStatus 枚举值）
        :param recovery_evidence: 恢复证据 dict，关闭时必须提供且 type ∈ {"passed", "manual_close"}
        :return: 更新后的 AccuracyAlert 实体
        :raises ValueError: 告警不存在、状态迁移非法、关闭缺少有效证据
        """
        alert = self.get_alert(slot, alert_id)
        if alert is None:
            raise ValueError(
                f"告警不存在: slot={slot}, alert_id={alert_id}"
            )

        current_status = str(alert.status)
        transition = (current_status, new_status)

        if transition not in _ALERT_ALLOWED_TRANSITIONS:
            raise ValueError(
                f"非法状态迁移: {current_status!r} → {new_status!r}，"
                f"合法迁移路径为 {_ALERT_ALLOWED_TRANSITIONS}"
            )

        if new_status == "closed":
            if recovery_evidence is None:
                raise ValueError(
                    "关闭告警时必须提供 recovery_evidence"
                )
            evidence_type = recovery_evidence.get("type")
            if evidence_type not in {"passed", "manual_close"}:
                raise ValueError(
                    f"recovery_evidence.type 必须为 'passed' 或 'manual_close'，"
                    f"实际收到: {evidence_type!r}"
                )
            alert.recovery_evidence = recovery_evidence

        alert.status = new_status  # type: ignore[assignment]
        alert.updated_at = now_iso()
        self.save_alert(slot, alert)
        return alert

    # ------------------------------------------------------------------ rca

    def save_rca(self, slot: str, rca: RCAReport) -> None:
        """
        持久化 RCA 报告（新建或覆盖 upsert）。

        :param slot: 槽位名称
        :param rca: RCAReport 实体
        :raises ValueError: slot 名称不合法或路径为绝对路径
        """
        _validate_slot(slot)
        abs_path = _rca_path(slot, rca.rca_report_id)
        rel = _to_relpath(abs_path)
        _atomic_write_json(abs_path, rca.dict())
        logger.debug("save_rca: 已写入 %s", rel)

    def get_rca(self, slot: str, rca_report_id: str) -> Optional[RCAReport]:
        """
        读取 RCA 报告，不存在或解析失败返回 None。

        :param slot: 槽位名称
        :param rca_report_id: 报告 ID — 格式 rca-{8hex}
        :return: RCAReport 或 None
        """
        _validate_slot(slot)
        data = load_json_safe(_rca_path(slot, rca_report_id))
        if data is None:
            return None
        try:
            return RCAReport.parse_obj(data)
        except Exception as exc:
            logger.warning(
                "get_rca: 解析失败 slot=%s rca_report_id=%s: %s",
                slot,
                rca_report_id,
                exc,
            )
            return None

    def get_rca_for_alert(
        self, slot: str, alert_id: str
    ) -> Optional[RCAReport]:
        """
        获取与指定 alert_id 关联的最新 RCA 报告（按 created_at 最大值）。

        :param slot: 槽位名称
        :param alert_id: 告警 ID — 格式 alert-{8hex}
        :return: 最新的 RCAReport，或 None（不存在时）
        """
        _validate_slot(slot)
        rca_dir = _accuracy_ops_dir(slot) / "rca"
        if not rca_dir.exists():
            return None

        candidates: List[RCAReport] = []
        for json_file in rca_dir.glob("*.json"):
            data = load_json_safe(json_file)
            if data is None:
                continue
            try:
                rca = RCAReport.parse_obj(data)
            except Exception:
                continue
            if rca.alert_id == alert_id:
                candidates.append(rca)

        if not candidates:
            return None
        # 按 created_at 降序，取最新一条
        return max(candidates, key=lambda r: r.created_at)

    # ------------------------------------------------------------------ recovery

    def save_decision(self, slot: str, decision: RecoveryDecision) -> None:
        """
        持久化恢复决策（新建或覆盖 upsert）。

        :param slot: 槽位名称
        :param decision: RecoveryDecision 实体
        :raises ValueError: slot 名称不合法或路径为绝对路径
        """
        _validate_slot(slot)
        abs_path = _recovery_path(slot, decision.decision_id)
        rel = _to_relpath(abs_path)
        _atomic_write_json(abs_path, decision.dict())
        logger.debug("save_decision: 已写入 %s", rel)

    def get_decision(
        self, slot: str, decision_id: str
    ) -> Optional[RecoveryDecision]:
        """
        读取单条恢复决策，不存在或解析失败返回 None。

        :param slot: 槽位名称
        :param decision_id: 决策 ID — 格式 rec-{8hex}
        :return: RecoveryDecision 或 None
        """
        _validate_slot(slot)
        data = load_json_safe(_recovery_path(slot, decision_id))
        if data is None:
            return None
        try:
            return RecoveryDecision.parse_obj(data)
        except Exception as exc:
            logger.warning(
                "get_decision: 解析失败 slot=%s decision_id=%s: %s",
                slot,
                decision_id,
                exc,
            )
            return None

    def get_decision_for_alert(
        self, slot: str, alert_id: str
    ) -> Optional[RecoveryDecision]:
        """
        获取与指定 alert_id 关联的最新恢复决策（按 created_at 最大值）。

        :param slot: 槽位名称
        :param alert_id: 告警 ID — 格式 alert-{8hex}
        :return: 最新的 RecoveryDecision，或 None（不存在时）
        """
        _validate_slot(slot)
        recovery_dir = _accuracy_ops_dir(slot) / "recovery"
        if not recovery_dir.exists():
            return None

        candidates: List[RecoveryDecision] = []
        for json_file in recovery_dir.glob("*.json"):
            data = load_json_safe(json_file)
            if data is None:
                continue
            try:
                decision = RecoveryDecision.parse_obj(data)
            except Exception:
                continue
            if decision.alert_id == alert_id:
                candidates.append(decision)

        if not candidates:
            return None
        # 按 created_at 降序，取最新一条
        return max(candidates, key=lambda d: d.created_at)

    def has_active_switch(self, slot: str) -> bool:
        """
        检查 slot 下是否存在 channel=shadow_switch 且
        status ∈ {pending, executing} 的 RecoveryDecision。

        用于仲裁器判断：同 slot 已有执行中的影子切换时不重复触发。

        :param slot: 槽位名称
        :return: True 表示存在活跃的影子切换决策
        """
        _validate_slot(slot)
        recovery_dir = _accuracy_ops_dir(slot) / "recovery"
        if not recovery_dir.exists():
            return False

        active_statuses = {DecisionStatus.pending.value, DecisionStatus.executing.value}

        for json_file in recovery_dir.glob("*.json"):
            data = load_json_safe(json_file)
            if data is None:
                continue
            try:
                decision = RecoveryDecision.parse_obj(data)
            except Exception:
                continue
            if (
                decision.channel == RecoveryChannel.shadow_switch.value
                and decision.status in active_statuses
            ):
                return True
        return False
# @AI_GENERATED: end
