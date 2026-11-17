# @AI_GENERATED
"""
services/deployment/store.py — 部署槽位 JSON 持久化

存储介质：
  - data/deployment/slots.json       — 部署槽位快照（可覆盖写）
  - data/deployment/switch_log.json  — 切换事件日志（append-only，永不修改已有条目）

路径解析：
  - 所有路径均相对于 backend-service/ 目录动态计算
  - 遵循项目 "全项目强制使用相对路径" 规则（见 .kiro/steering/relative-paths-only.md）
  - 参考已有实现 services/precision_ops/utils.py 的 BASE_DATA_DIR 计算方式

写入语义：
  - slots.json    — 原子写入（先写临时文件后 os.replace），并发读取不会看到中间状态
  - switch_log.json — append-only：读取现有列表 → 追加新条目 → 原子写回，
    已有条目的字段永不修改；`SwitchEventLog.append()` 是唯一写入入口
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.deployment.models import DeploymentSlot, ModelVersion, SwitchEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 路径常量 — 相对于 backend-service/ 目录
# ---------------------------------------------------------------------------
# 本文件位于 backend-service/services/deployment/store.py
# 向上两级到 backend-service/，再拼上 data/deployment/
_THIS_DIR = Path(__file__).resolve().parent          # .../services/deployment/
_BACKEND_DIR = _THIS_DIR.parent.parent               # .../backend-service/
BASE_DATA_DIR: Path = _BACKEND_DIR / "data" / "deployment"
"""部署数据根目录（backend-service/data/deployment/）— 动态计算，不硬编码绝对路径。"""

SLOTS_FILE: Path = BASE_DATA_DIR / "slots.json"
"""槽位快照文件路径。JSON 结构：{ "<slot>": DeploymentSlot, ... }（dict 按 slot 名称索引）。"""

SWITCH_LOG_FILE: Path = BASE_DATA_DIR / "switch_log.json"
"""切换事件日志文件路径。JSON 结构：[SwitchEvent, ...]（append-only 列表）。"""


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _ensure_base_dir() -> None:
    """确保 data/deployment/ 目录存在。"""
    BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write_json(path: Path, data: Any) -> None:
    """
    原子写入 JSON 文件（先写临时文件后 os.replace）。

    保证并发读取方不会观察到部分写入状态；跨平台可用（Windows / Linux / macOS）。

    :param path: 目标文件路径
    :param data: 可 JSON 序列化的 Python 对象
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    dir_str = str(path.parent)
    fd, tmp_path = tempfile.mkstemp(dir=dir_str, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_json_safe(path: Path, default: Any) -> Any:
    """
    安全读取 JSON 文件。文件不存在或解析失败时返回 default（不抛异常，只记 warning）。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("deployment.store: 读取 %s 失败: %s", path, exc)
        return default


# ---------------------------------------------------------------------------
# 影子模型排序 — 按 accuracy_score 降序（Property 3 / Requirement 3.4）
# ---------------------------------------------------------------------------

def sort_shadow_models_by_accuracy(models: List[ModelVersion]) -> List[ModelVersion]:
    """
    对影子模型列表按 `accuracy_score`（精度评分）降序排列。

    对应 Requirement 3.4 与 Property 3：
      "For any deployment slot containing multiple shadow models with distinct
       accuracy scores, the returned shadow model list SHALL be sorted in
       descending order by accuracy_score."

    处理规则：
      - accuracy_score = None 的模型统一排在末尾（视为"未评估，无法比较"）
      - accuracy_score 相同的模型保持稳定原始顺序（Python sorted 是稳定排序）

    :param models: 待排序的影子模型列表
    :return: 新的列表副本，按 accuracy_score 降序排列
    """
    return sorted(
        models,
        key=lambda m: (
            m.accuracy_score is None,           # None 排在末尾（True > False）
            -(m.accuracy_score or 0.0),         # 非 None：负号实现降序
        ),
    )


# ---------------------------------------------------------------------------
# DeploymentSlotStore — 槽位快照读写
# ---------------------------------------------------------------------------

class DeploymentSlotStore:
    """
    部署槽位持久化存储。

    存储路径：`data/deployment/slots.json`
    JSON 结构：dict，key 为 slot 名称，value 为 DeploymentSlot 序列化字典。

    示例：
        {
          "load_forecast": {
            "slot": "load_forecast",
            "production_model": {...},
            "shadow_models": [...],
            ...
          },
          "default": {...}
        }

    并发保护：进程内锁（_lock）避免同一进程的多线程写入交错。
    写入方式：原子替换（临时文件 + os.replace），并发读取安全。
    读取影子列表时自动按 accuracy_score 降序排列。
    """

    def __init__(
        self,
        slots_path: Optional[Path] = None,
        pv_adapter: Optional[Any] = None,
    ) -> None:
        """
        :param slots_path: 可选，覆盖默认的 slots.json 路径（主要用于测试）
        :param pv_adapter: 可选，注入 PVDeploymentReadAdapter（测试用临时 Registry）
        """
        self._path: Path = slots_path if slots_path is not None else SLOTS_FILE
        self._lock = threading.Lock()
        # @AI_GENERATED: pv_fault 只读适配，默认惰性构造，测试可注入
        self._pv_adapter = pv_adapter
        # @AI_GENERATED: end

    # -------- 读取 --------

    def load_all(self) -> Dict[str, DeploymentSlot]:
        """
        读取所有槽位。文件不存在时返回空 dict。

        影子模型列表在返回前会自动按 accuracy_score 降序排列。

        :return: 槽位字典，key = slot 名称，value = DeploymentSlot 对象
        """
        raw = _load_json_safe(self._path, default={})
        if not isinstance(raw, dict):
            logger.warning(
                "deployment.store: slots.json 顶层结构应为 dict，实际为 %s，忽略",
                type(raw).__name__,
            )
            return self._overlay_pv_fault({})

        result: Dict[str, DeploymentSlot] = {}
        for slot_name, slot_data in raw.items():
            if not isinstance(slot_data, dict):
                logger.warning(
                    "deployment.store: 跳过异常槽位条目 slot=%s（非 dict）", slot_name
                )
                continue
            try:
                slot_obj = DeploymentSlot(**slot_data)
            except Exception as exc:
                logger.warning(
                    "deployment.store: slot=%s 反序列化失败，跳过：%s",
                    slot_name,
                    exc,
                )
                continue
            # 保证影子模型返回时按精度评分降序
            slot_obj.shadow_models = sort_shadow_models_by_accuracy(slot_obj.shadow_models)
            result[slot_name] = slot_obj
        # @AI_GENERATED: pv_fault 展示映射 Registry，丢弃 slots.json 中的可写副本
        return self._overlay_pv_fault(result)
        # @AI_GENERATED: end

    def get(self, slot: str) -> Optional[DeploymentSlot]:
        """
        读取单个槽位。不存在时返回 None。

        :param slot: 槽位名称
        :return: DeploymentSlot 对象或 None
        """
        return self.load_all().get(slot)

    # @AI_GENERATED: pv_fault 只读 overlay / 写拒绝
    def _adapter(self):
        if self._pv_adapter is None:
            from services.deployment.pv_read_adapter import PVDeploymentReadAdapter

            self._pv_adapter = PVDeploymentReadAdapter()
        return self._pv_adapter

    def _overlay_pv_fault(self, result: Dict[str, DeploymentSlot]) -> Dict[str, DeploymentSlot]:
        """读路径丢弃 slots.json 里的 pv_fault，改映射 Registry；写失败不影响其他槽位。"""
        from services.deployment.pv_read_adapter import PV_FAULT_SLOT

        result.pop(PV_FAULT_SLOT, None)
        try:
            slot_obj = self._adapter().get_slot(PV_FAULT_SLOT)
            slot_obj.shadow_models = sort_shadow_models_by_accuracy(slot_obj.shadow_models)
            result[PV_FAULT_SLOT] = slot_obj
        except Exception as exc:
            logger.warning(
                "deployment.store: pv_fault 只读适配失败，跳过展示 overlay: %s",
                exc,
            )
        return result
    # @AI_GENERATED: end

    # -------- 写入 --------

    def save_all(self, slots: Dict[str, DeploymentSlot]) -> None:
        """
        全量覆盖写入所有槽位。

        写入前会对每个槽位的 shadow_models 按 accuracy_score 降序排序，
        确保持久化数据本身就是有序的。

        :param slots: 完整的槽位字典
        """
        # @AI_GENERATED: 拒绝把 pv_fault 写进 slots.json
        from services.deployment.pv_read_adapter import reject_pv_fault_write

        for name, slot in slots.items():
            reject_pv_fault_write(name)
            if slot is not None:
                reject_pv_fault_write(slot.slot)
        # @AI_GENERATED: end
        with self._lock:
            _ensure_base_dir()
            serialized: Dict[str, Dict[str, Any]] = {}
            for name, slot in slots.items():
                # 序列化前排序，确保落盘数据有序
                slot.shadow_models = sort_shadow_models_by_accuracy(slot.shadow_models)
                serialized[name] = slot.model_dump()
            _atomic_write_json(self._path, serialized)
        # @AI_GENERATED: Phase 1 双写 — 全量覆盖时逐个 slot 同步到 DB
        for _slot in slots.values():
            _dual_write_slot_to_db(_slot)
        # @AI_GENERATED: end

    def upsert(self, slot: DeploymentSlot) -> None:
        """
        插入或更新单个槽位。以 `slot.slot`（槽位名称）为主键。

        :param slot: 要写入的 DeploymentSlot 对象
        """
        # @AI_GENERATED: 拒绝 Arena 写 pv_fault
        from services.deployment.pv_read_adapter import reject_pv_fault_write

        reject_pv_fault_write(slot.slot)
        # @AI_GENERATED: end
        with self._lock:
            _ensure_base_dir()
            # 直接读取原始 dict，避免 load_all → save_all 造成的双重排序开销
            raw = _load_json_safe(self._path, default={})
            if not isinstance(raw, dict):
                raw = {}
            # 序列化前排序 shadow_models
            slot.shadow_models = sort_shadow_models_by_accuracy(slot.shadow_models)
            raw[slot.slot] = slot.model_dump()
            _atomic_write_json(self._path, raw)
        # @AI_GENERATED: Phase 1 双写 — 写完 slots.json 后同步 upsert deployment_slot + deployment_model_version
        _dual_write_slot_to_db(slot)
        # @AI_GENERATED: end

    # @AI_GENERATED: prelaunch 状态转换操作
    def promote_prelaunch_to_shadow(self, slot_name: str, workflow_id: str) -> bool:
        """
        将预上线模型毕业为 shadow。

        操作语义（原子）：
          1. 从 prelaunch_models 中找到对应 workflow_id 的条目
          2. 将其 status 改为 "shadow"，清空 prelaunch_meta
          3. 移入 shadow_models（保持按精度降序排列）

        Args:
            slot_name:   槽位名称
            workflow_id: 要毕业的工作流 ID

        Returns:
            True — 找到并成功转换；False — 未找到目标（静默失败，调用方判断）
        """
        # @AI_GENERATED: 拒绝 Arena 写 pv_fault
        from services.deployment.pv_read_adapter import reject_pv_fault_write

        reject_pv_fault_write(slot_name)
        # @AI_GENERATED: end
        with self._lock:
            _ensure_base_dir()
            raw = _load_json_safe(self._path, default={})
            if not isinstance(raw, dict):
                return False
            slot_data = raw.get(slot_name)
            if not isinstance(slot_data, dict):
                return False

            try:
                from services.deployment.models import DeploymentSlot
                slot_obj = DeploymentSlot(**slot_data)
            except Exception as exc:
                logger.warning(
                    "deployment.store.promote_prelaunch_to_shadow: "
                    "反序列化失败 slot=%s: %s", slot_name, exc
                )
                return False

            # 找目标 prelaunch 条目
            target = next(
                (m for m in slot_obj.prelaunch_models
                 if m.workflow_id == workflow_id and m.status == "prelaunch"),
                None,
            )
            if target is None:
                logger.warning(
                    "deployment.store.promote_prelaunch_to_shadow: "
                    "未找到 slot=%s workflow_id=%s 的 prelaunch 条目",
                    slot_name, workflow_id,
                )
                return False

            # 状态转换
            target.status = "shadow"
            target.prelaunch_meta = None  # 清空预上线元数据

            # 从 prelaunch_models 移到 shadow_models
            slot_obj.prelaunch_models = [
                m for m in slot_obj.prelaunch_models if m.workflow_id != workflow_id
            ]
            slot_obj.shadow_models.append(target)
            slot_obj.shadow_models = sort_shadow_models_by_accuracy(slot_obj.shadow_models)

            from datetime import datetime as _dt
            slot_obj.updated_at = _dt.now().isoformat()

            raw[slot_name] = slot_obj.model_dump()
            _atomic_write_json(self._path, raw)

        # JSON 写完后双写 DB（此前漏调会导致 DB 状态落后）
        try:
            _dual_write_slot_to_db(slot_obj)
        except Exception as exc:
            logger.warning(
                "deployment.store.promote_prelaunch_to_shadow dual-write failed: %s",
                exc,
            )

        logger.info(
            "deployment.store.promote_prelaunch_to_shadow: "
            "slot=%s workflow=%s 已从 prelaunch 毕业为 shadow",
            slot_name, workflow_id,
        )
        return True

    def fail_prelaunch(self, slot_name: str, workflow_id: str, reason: str = "") -> bool:
        """
        将预上线模型标记为观察失败（retired）。

        保留 prelaunch_meta 作为历史记录（里面有失败 MAPE 等审计信息）。
        将条目从 prelaunch_models 移出，追加到 shadow_models 的末尾
        （status=retired，不参与锦标赛排序，但通过 /versions 端点可查询）。

        Args:
            slot_name:   槽位名称
            workflow_id: 要标记失败的工作流 ID
            reason:      失败原因（写入 prelaunch_meta 备注字段）

        Returns:
            True — 成功；False — 未找到目标
        """
        # @AI_GENERATED: 拒绝 Arena 写 pv_fault
        from services.deployment.pv_read_adapter import reject_pv_fault_write

        reject_pv_fault_write(slot_name)
        # @AI_GENERATED: end
        with self._lock:
            _ensure_base_dir()
            raw = _load_json_safe(self._path, default={})
            if not isinstance(raw, dict):
                return False
            slot_data = raw.get(slot_name)
            if not isinstance(slot_data, dict):
                return False

            try:
                from services.deployment.models import DeploymentSlot
                slot_obj = DeploymentSlot(**slot_data)
            except Exception as exc:
                logger.warning(
                    "deployment.store.fail_prelaunch: 反序列化失败 slot=%s: %s",
                    slot_name, exc,
                )
                return False

            target = next(
                (m for m in slot_obj.prelaunch_models
                 if m.workflow_id == workflow_id and m.status == "prelaunch"),
                None,
            )
            if target is None:
                return False

            target.status = "retired"
            if target.prelaunch_meta is not None:
                target.prelaunch_meta.note = (
                    reason or f"prelaunch 观察期满未达标，自动失败"
                )

            slot_obj.prelaunch_models = [
                m for m in slot_obj.prelaunch_models if m.workflow_id != workflow_id
            ]
            # retired 放到 shadow_models 末尾（供 /versions 查询历史，不参与锦标赛）
            slot_obj.shadow_models.append(target)
            slot_obj.shadow_models = sort_shadow_models_by_accuracy(slot_obj.shadow_models)

            from datetime import datetime as _dt
            slot_obj.updated_at = _dt.now().isoformat()

            raw[slot_name] = slot_obj.model_dump()
            _atomic_write_json(self._path, raw)

        logger.info(
            "deployment.store.fail_prelaunch: slot=%s workflow=%s 预上线失败 → retired",
            slot_name, workflow_id,
        )
        return True
    # @AI_GENERATED: end


# ---------------------------------------------------------------------------
# SwitchEventLog — 切换事件 append-only 日志
# ---------------------------------------------------------------------------

class SwitchEventLog:
    """
    切换事件日志（append-only）。

    存储路径：`data/deployment/switch_log.json`
    JSON 结构：list，每个元素为 SwitchEvent 的序列化字典，按追加顺序排列。

    Append-only 约束：
      - `append()` 是唯一写入入口；不提供 update / delete 方法
      - 每次 append 读取现有列表 → 追加新条目 → 原子写回
      - 已有条目字段永不修改，保证审计可靠性

    对应 Requirement 5.3：
      "THE Algorithm_Deployment SHALL 记录每次切换事件，包括触发类型（自动/手动）、
       切换时间和切换前后的精度指标。"

    并发保护：进程内锁（_lock）串行化 append 操作。
    """

    def __init__(self, log_path: Optional[Path] = None) -> None:
        """
        :param log_path: 可选，覆盖默认的 switch_log.json 路径（主要用于测试）
        """
        self._path: Path = log_path if log_path is not None else SWITCH_LOG_FILE
        self._lock = threading.Lock()

    # -------- 读取 --------

    def load_all(self) -> List[SwitchEvent]:
        """
        读取所有切换事件（按追加顺序，最早在前）。

        :return: SwitchEvent 列表；文件不存在或损坏时返回空列表
        """
        raw = _load_json_safe(self._path, default=[])
        if not isinstance(raw, list):
            logger.warning(
                "deployment.store: switch_log.json 顶层结构应为 list，实际为 %s，忽略",
                type(raw).__name__,
            )
            return []

        events: List[SwitchEvent] = []
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                logger.warning("deployment.store: 跳过异常事件条目 index=%d", idx)
                continue
            try:
                events.append(SwitchEvent(**item))
            except Exception as exc:
                logger.warning(
                    "deployment.store: switch_log[%d] 反序列化失败，跳过：%s",
                    idx,
                    exc,
                )
                continue
        return events

    def list_by_slot(self, slot: str) -> List[SwitchEvent]:
        """
        读取某个槽位下的所有切换事件（按追加顺序）。

        :param slot: 槽位名称
        :return: 该槽位的 SwitchEvent 列表
        """
        return [e for e in self.load_all() if e.slot == slot]

    # -------- 写入（append-only）--------

    def append(self, event: SwitchEvent) -> SwitchEvent:
        """
        追加一条切换事件到日志文件。这是唯一的写入入口。

        实现细节：
          1. 获取进程内锁
          2. 读取现有列表（若文件不存在则视为空列表）
          3. 追加新事件的序列化字典
          4. 原子写回

        已有条目的字段在任何情况下都不会被修改。

        :param event: 要追加的 SwitchEvent 对象
        :return: 传入的 event（未做任何修改，便于链式调用）
        """
        # @AI_GENERATED: 拒绝为 pv_fault 追加 Arena 切换审计
        from services.deployment.pv_read_adapter import reject_pv_fault_write

        reject_pv_fault_write(event.slot)
        # @AI_GENERATED: end
        with self._lock:
            _ensure_base_dir()
            raw = _load_json_safe(self._path, default=[])
            if not isinstance(raw, list):
                logger.warning(
                    "deployment.store: switch_log.json 结构异常（非 list），重置为空列表"
                )
                raw = []
            raw.append(event.model_dump())
            _atomic_write_json(self._path, raw)
        logger.info(
            "deployment.store.SwitchEventLog: 追加切换事件 event_id=%s slot=%s "
            "trigger_type=%s from=%s to=%s",
            event.event_id,
            event.slot,
            event.trigger_type,
            event.from_workflow_id,
            event.to_workflow_id,
        )
        # @AI_GENERATED: Phase 1 双写 — 写完 switch_log.json 后同步 insert switch_event
        _dual_write_switch_event_to_db(event)
        # @AI_GENERATED: end
        return event
# @AI_GENERATED: end


# @AI_GENERATED: Phase 1 双写辅助函数 — 部署槽位 / 切换事件 → MySQL
def _dual_write_slot_to_db(slot: "DeploymentSlot") -> None:
    """把 DeploymentSlot 拆成 deployment_slot + deployment_model_version 写入 MySQL。

    - deployment_slot：一行槽位配置（生产 workflow、冷却期、上限、训练窗口等）
    - deployment_model_version：production/shadow/prelaunch 每个版本一行

    失败降级 warning，不阻塞 slots.json 写入。
    """
    try:
        from services.db.repositories import get_deployment_repo, is_dual_write_enabled
        if not is_dual_write_enabled():
            return
        repo = get_deployment_repo()
        if repo is None:
            return

        prod = slot.production_model
        repo.upsert_slot({
            "slot": slot.slot[:64],
            "production_workflow_id": (prod.workflow_id[:128] if prod else None),
            "cooldown_days": int(getattr(slot, "cooldown_days", 0) or 0) or 3,
            "max_shadow_slots": int(getattr(slot, "max_shadow_slots", 3) or 3),
            "max_prelaunch_slots": int(getattr(slot, "max_prelaunch_slots", 2) or 2),
            "training_window_days": getattr(slot, "training_window_days", None),
            "switch_observation_days": getattr(slot, "switch_observation_days", None),
        })

        # 汇总所有版本（production + shadow + prelaunch）
        versions = []
        if prod:
            versions.append((prod, "production"))
        for m in (slot.shadow_models or []):
            versions.append((m, m.status or "shadow"))
        for m in (slot.prelaunch_models or []):
            versions.append((m, m.status or "prelaunch"))

        for mv, status in versions:
            meta = None
            if mv.prelaunch_meta is not None:
                try:
                    meta = mv.prelaunch_meta.model_dump()
                except Exception:
                    meta = None
            repo.upsert_model_version({
                "slot": slot.slot[:64],
                "workflow_id": mv.workflow_id[:128],
                "version_tag": (mv.version_tag or "")[:128] or None,
                "status": str(status)[:32],
                "accuracy_score": mv.accuracy_score,
                "consecutive_better_days": int(mv.consecutive_better_days or 0),
                "source_run_id": (mv.source_run_id or None),
                "source_candidate_id": (mv.source_candidate_id or None),
                # DB 尚无独立 experiment_patch 列：嵌进 prelaunch_meta_json 保活
                "prelaunch_meta_json": {
                    **(meta or {}),
                    **(
                        {"_experiment_patch": getattr(mv, "experiment_patch", None)}
                        if getattr(mv, "experiment_patch", None)
                        else {}
                    ),
                }
                if (meta is not None or getattr(mv, "experiment_patch", None))
                else None,
            })
    except Exception as exc:
        logger.warning("deployment dual-write slot → DB failed (non-fatal): %s", exc)


def _dual_write_switch_event_to_db(event: "SwitchEvent") -> None:
    """把 SwitchEvent 同步 insert 到 MySQL switch_event 表。"""
    try:
        from services.db.repositories import get_deployment_repo, is_dual_write_enabled
        if not is_dual_write_enabled():
            return
        repo = get_deployment_repo()
        if repo is None:
            return
        d = event.model_dump()
        repo.append_switch_event({
            "event_id": str(d.get("event_id"))[:64],
            "slot": str(d.get("slot") or "default")[:64],
            "trigger_type": str(d.get("trigger_type") or "manual")[:32],
            "from_workflow_id": (str(d["from_workflow_id"])[:128] if d.get("from_workflow_id") else None),
            "to_workflow_id": str(d.get("to_workflow_id") or "")[:128],
            # SwitchEvent 用 pre_switch_mape / post_switch_mape
            "from_mape": d.get("pre_switch_mape"),
            "to_mape": d.get("post_switch_mape"),
            "actor": (str(d.get("actor"))[:64] if d.get("actor") else None),
            "reason": (str(d.get("reason"))[:2048] if d.get("reason") else None),
            "ts": _parse_switch_ts(d),
        })
    except Exception as exc:
        logger.warning("deployment dual-write switch_event → DB failed (non-fatal): %s", exc)


def _parse_switch_ts(d: dict):
    """从 SwitchEvent dump 里解析时间戳（兼容多种字段名）。"""
    from datetime import datetime as _dt
    for key in ("switch_time", "ts", "switched_at", "created_at", "timestamp"):
        val = d.get(key)
        if val:
            if isinstance(val, _dt):
                return val
            try:
                return _dt.fromisoformat(str(val).replace("Z", "+00:00"))
            except Exception:
                continue
    return _dt.utcnow()
# @AI_GENERATED: end
