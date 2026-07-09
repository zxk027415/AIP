"""
precision_ops/prelaunch_manager.py — 预上线管理器

职责：
  - 管理从复验池通过 → 正式上线之间的"预上线"观察阶段
  - 预上线项以 shadow 身份注册到 VersionRegistry，跟随真实预测运行
  - 观察期满后根据 rolling_mape 对比结果决定毕业（Promote）或失败
  - 最大并发预上线数为 2

存储路径：{BASE_DATA_DIR}/{slot}/prelaunch_queue.json

生命周期：
  verification_passed → 入预上线 (status=observing, 注册为 shadow)
    → 观察期满 + MAPE 不比生产差(容差内) → graduated → 自动 Promote
    → 观察期满 + MAPE 明显差于生产 → failed
    → 用户手动毕业 → graduated
    → 用户手动取消 → cancelled
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled, _parse_iso
from services.precision_ops.utils import (
    BASE_DATA_DIR,
    _atomic_write_json,
    ensure_data_dir,
    generate_event_id,
    load_json_safe,
    now_iso,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------
_DEFAULT_OBSERVATION_DAYS = 7
_DEFAULT_GRADUATE_TOLERANCE_PCT = 5  # 预上线 MAPE 比生产高不超过此相对百分比仍可毕业
_MAX_CONCURRENT_PRELAUNCH = 2

# 合法状态
_VALID_STATUSES = {"observing", "graduated", "failed", "cancelled"}


# ---------------------------------------------------------------------------
# PrelaunchManager
# ---------------------------------------------------------------------------

class PrelaunchManager:
    """
    预上线管理器。

    存储：{BASE_DATA_DIR}/{slot}/prelaunch_queue.json
    每个槽位独立一个 JSON 文件。

    **存什么**：所有预上线项（含进行中和历史）。
    **为什么单独存**：与候选池、复验池解耦，预上线是精度运营侧的概念。
    **按什么维度分区**：按 slot（槽位），和 precision_ops 其他模块一致。
    """

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get_queue(self, slot: str) -> List[Dict[str, Any]]:
        """
        获取指定槽位的全部预上线项。

        :param slot: 槽位名称
        :return: 预上线项列表
        """
        return self._load(slot)

    def get_observing(self, slot: str) -> List[Dict[str, Any]]:
        """
        获取当前正在观察中的预上线项。

        :param slot: 槽位名称
        :return: status=observing 的预上线项列表
        """
        return [item for item in self._load(slot) if item.get("status") == "observing"]

    def get_item(self, slot: str, prelaunch_id: str) -> Optional[Dict[str, Any]]:
        """
        按 ID 获取单条预上线项。

        :param slot: 槽位名称
        :param prelaunch_id: 预上线项 ID
        :return: 预上线项字典，不存在时返回 None
        """
        for item in self._load(slot):
            if item.get("id") == prelaunch_id:
                return item
        return None

    # ------------------------------------------------------------------
    # 入队
    # ------------------------------------------------------------------

    def enqueue(
        self,
        slot: str,
        candidate_id: str,
        workflow_id: str,
        version_tag: str,
        *,
        source_run_id: Optional[str] = None,
        observation_days: int = _DEFAULT_OBSERVATION_DAYS,
        graduate_tolerance_pct: float = _DEFAULT_GRADUATE_TOLERANCE_PCT,
        baseline_mape_at_entry: Optional[float] = None,
        note: str = "",
    ) -> Dict[str, Any]:
        """
        将一个复验通过的候选加入预上线队列。

        前置检查：
        1. 当前 observing 数量 < _MAX_CONCURRENT_PRELAUNCH
        2. 同一 candidate_id 不重复入队（状态为 observing 时）

        入队后调用方应将该候选注册到 VersionRegistry(status=shadow)。

        :param slot: 槽位名称
        :param candidate_id: 来源候选 ID
        :param workflow_id: 工作流模板 ID
        :param version_tag: 版本标签
        :param source_run_id: 来源 AutoResearch run ID（可选）
        :param observation_days: 观察天数，默认 7
        :param graduate_tolerance_pct: 毕业容差百分比，默认 5
        :param baseline_mape_at_entry: 入队时的生产 baseline MAPE（可选）
        :param note: 备注
        :return: 新创建的预上线项
        :raises ValueError: 并发上限或重复入队
        """
        queue = self._load(slot)
        observing = [item for item in queue if item.get("status") == "observing"]

        # 检查并发上限
        if len(observing) >= _MAX_CONCURRENT_PRELAUNCH:
            raise ValueError(
                f"预上线并发上限为 {_MAX_CONCURRENT_PRELAUNCH}，"
                f"当前已有 {len(observing)} 个正在观察"
            )

        # 检查重复
        for item in observing:
            if item.get("candidate_id") == candidate_id:
                raise ValueError(
                    f"候选 {candidate_id} 已在预上线观察中，不可重复入队"
                )

        prelaunch_id = generate_event_id(prefix="prelaunch")
        entry: Dict[str, Any] = {
            "id": prelaunch_id,
            "candidate_id": candidate_id,
            "workflow_id": workflow_id,
            "version_tag": version_tag,
            "slot": slot,
            "status": "observing",
            "started_at": now_iso(),
            "observation_days": observation_days,
            "graduate_tolerance_pct": graduate_tolerance_pct,
            "source_run_id": source_run_id,
            "baseline_mape_at_entry": baseline_mape_at_entry,
            "current_rolling_mape": None,
            "production_rolling_mape": None,
            "evaluated_cycles": 0,
            "graduated_at": None,
            "failed_at": None,
            "cancelled_at": None,
            "note": note,
        }

        queue.append(entry)
        self._save(slot, queue)

        # DB dual-write（异步，best-effort）
        if _is_db_enabled():
            _entry = dict(entry)

            def _db_write():
                repo = _get_lf_repo()
                if repo is None:
                    return
                try:
                    repo.save_prelaunch({
                        "id": _entry.get("id"),
                        "slot": _entry.get("slot"),
                        "candidate_id": _entry.get("candidate_id"),
                        "workflow_id": _entry.get("workflow_id"),
                        "version_tag": _entry.get("version_tag"),
                        "status": _entry.get("status"),
                        "observation_days": _entry.get("observation_days"),
                        "graduate_tolerance_pct": _entry.get("graduate_tolerance_pct"),
                        "current_rolling_mape": _entry.get("current_rolling_mape"),
                        "production_rolling_mape": _entry.get("production_rolling_mape"),
                        "evaluated_cycles": _entry.get("evaluated_cycles"),
                        "started_at": _parse_iso(_entry.get("started_at")),
                    })
                except Exception as _exc:
                    logger.warning("DB 写入 prelaunch_queue 失败（忽略）: %s", _exc)

            threading.Thread(target=_db_write, daemon=True).start()

        logger.info(
            "prelaunch_manager.enqueue: slot=%s id=%s candidate=%s workflow=%s obs_days=%d",
            slot, prelaunch_id, candidate_id, workflow_id, observation_days,
        )
        return entry

    # ------------------------------------------------------------------
    # 毕业（手动 / 自动）
    # ------------------------------------------------------------------

    def graduate(
        self,
        slot: str,
        prelaunch_id: str,
        *,
        reason: str = "manual",
    ) -> Dict[str, Any]:
        """
        标记预上线项为毕业。

        毕业后调用方应执行 Promote（切换为 production）。

        :param slot: 槽位名称
        :param prelaunch_id: 预上线项 ID
        :param reason: 毕业原因，如 "manual" 或 "auto_observation_passed"
        :return: 更新后的预上线项
        :raises ValueError: ID 不存在或状态不是 observing
        """
        queue = self._load(slot)
        item = self._find(queue, prelaunch_id)
        if item is None:
            raise ValueError(f"预上线项不存在: {prelaunch_id}")
        if item.get("status") != "observing":
            raise ValueError(
                f"预上线项 {prelaunch_id} 当前状态为 {item.get('status')}，只有 observing 可毕业"
            )

        item["status"] = "graduated"
        item["graduated_at"] = now_iso()
        item["graduate_reason"] = reason
        self._save(slot, queue)

        # DB sync（异步，best-effort）
        if _is_db_enabled():
            _item = dict(item)
            def _sync():
                repo = _get_lf_repo()
                if repo is None:
                    return
                try:
                    from sqlalchemy import update as sa_update
                    from services.db.models.load_forecast import PrelaunchQueue as PQModel
                    with repo._adapter.get_sync_session() as session:
                        session.execute(
                            sa_update(PQModel)
                            .where(PQModel.id == _item["id"])
                            .values(
                                status=_item["status"],
                                graduated_at=_parse_iso(_item.get("graduated_at")),
                            )
                        )
                except Exception as exc:
                    logger.warning("prelaunch graduate DB sync failed: %s", exc)
            threading.Thread(target=_sync, daemon=True).start()

        logger.info(
            "prelaunch_manager.graduate: slot=%s id=%s reason=%s",
            slot, prelaunch_id, reason,
        )
        return item

    # ------------------------------------------------------------------
    # 取消
    # ------------------------------------------------------------------

    def cancel(
        self,
        slot: str,
        prelaunch_id: str,
        *,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        取消预上线观察。

        取消后该候选仍保留在 VersionRegistry 中作为 shadow，
        但不再参与自动毕业评估。

        :param slot: 槽位名称
        :param prelaunch_id: 预上线项 ID
        :param reason: 取消原因
        :return: 更新后的预上线项
        :raises ValueError: ID 不存在或状态不是 observing
        """
        queue = self._load(slot)
        item = self._find(queue, prelaunch_id)
        if item is None:
            raise ValueError(f"预上线项不存在: {prelaunch_id}")
        if item.get("status") != "observing":
            raise ValueError(
                f"预上线项 {prelaunch_id} 当前状态为 {item.get('status')}，只有 observing 可取消"
            )

        item["status"] = "cancelled"
        item["cancelled_at"] = now_iso()
        item["cancel_reason"] = reason
        self._save(slot, queue)

        # DB sync（异步，best-effort；PrelaunchQueue 无 cancelled_at 列，仅同步 status）
        if _is_db_enabled():
            _item = dict(item)
            def _sync():
                repo = _get_lf_repo()
                if repo is None:
                    return
                try:
                    from sqlalchemy import update as sa_update
                    from services.db.models.load_forecast import PrelaunchQueue as PQModel
                    with repo._adapter.get_sync_session() as session:
                        session.execute(
                            sa_update(PQModel)
                            .where(PQModel.id == _item["id"])
                            .values(status=_item["status"])
                        )
                except Exception as exc:
                    logger.warning("prelaunch cancel DB sync failed: %s", exc)
            threading.Thread(target=_sync, daemon=True).start()

        logger.info(
            "prelaunch_manager.cancel: slot=%s id=%s reason=%s",
            slot, prelaunch_id, reason,
        )
        return item

    # ------------------------------------------------------------------
    # 标记失败
    # ------------------------------------------------------------------

    def mark_failed(
        self,
        slot: str,
        prelaunch_id: str,
        *,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        标记预上线项为观察失败（MAPE 不达标）。

        :param slot: 槽位名称
        :param prelaunch_id: 预上线项 ID
        :param reason: 失败原因
        :return: 更新后的预上线项
        :raises ValueError: ID 不存在或状态不是 observing
        """
        queue = self._load(slot)
        item = self._find(queue, prelaunch_id)
        if item is None:
            raise ValueError(f"预上线项不存在: {prelaunch_id}")
        if item.get("status") != "observing":
            raise ValueError(
                f"预上线项 {prelaunch_id} 当前状态为 {item.get('status')}，只有 observing 可标记失败"
            )

        item["status"] = "failed"
        item["failed_at"] = now_iso()
        item["fail_reason"] = reason
        self._save(slot, queue)

        # DB sync（异步，best-effort）
        if _is_db_enabled():
            _item = dict(item)
            def _sync():
                repo = _get_lf_repo()
                if repo is None:
                    return
                try:
                    from sqlalchemy import update as sa_update
                    from services.db.models.load_forecast import PrelaunchQueue as PQModel
                    with repo._adapter.get_sync_session() as session:
                        session.execute(
                            sa_update(PQModel)
                            .where(PQModel.id == _item["id"])
                            .values(
                                status=_item["status"],
                                failed_at=_parse_iso(_item.get("failed_at")),
                            )
                        )
                except Exception as exc:
                    logger.warning("prelaunch mark_failed DB sync failed: %s", exc)
            threading.Thread(target=_sync, daemon=True).start()

        logger.info(
            "prelaunch_manager.mark_failed: slot=%s id=%s reason=%s",
            slot, prelaunch_id, reason,
        )
        return item

    # ------------------------------------------------------------------
    # 自动评估（供定时任务调用）
    # ------------------------------------------------------------------

    def evaluate_observing(
        self,
        slot: str,
        accuracy_tracker=None,
        version_registry=None,
    ) -> List[Dict[str, Any]]:
        """
        评估所有观察中的预上线项，判断是否达到毕业/失败条件。

        毕业条件：
          1. 观察天数已满（started_at + observation_days <= now）
          2. prelaunch rolling_mape <= production rolling_mape * (1 + tolerance/100)

        失败条件：
          1. 观察天数已满
          2. prelaunch rolling_mape > production rolling_mape * (1 + tolerance/100)

        未满观察期的项只更新 current_rolling_mape 和 production_rolling_mape 字段。

        :param slot: 槽位名称
        :param accuracy_tracker: AccuracyTracker 实例（可选，用于获取 rolling_mape）
        :param version_registry: VersionRegistry 实例（可选，用于获取生产版本）
        :return: 状态发生变化的项列表
        """
        queue = self._load(slot)
        observing = [item for item in queue if item.get("status") == "observing"]
        if not observing:
            return []

        changed: List[Dict[str, Any]] = []
        now_dt = datetime.now(tz=timezone.utc)

        for item in observing:
            # 计算是否观察期已满
            started_str = item.get("started_at", "")
            try:
                started_dt = datetime.fromisoformat(started_str)
                if started_dt.tzinfo is None:
                    started_dt = started_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            obs_days = item.get("observation_days", _DEFAULT_OBSERVATION_DAYS)
            deadline = started_dt + timedelta(days=obs_days)
            observation_complete = now_dt >= deadline

            # 获取精度指标（如果 tracker 可用）
            if accuracy_tracker is not None:
                prelaunch_metrics = accuracy_tracker.get_rolling_metrics(
                    slot, item.get("workflow_id", "")
                )
                if prelaunch_metrics and prelaunch_metrics.get("status") != "insufficient_data":
                    item["current_rolling_mape"] = prelaunch_metrics.get("rolling_mape")
                    item["evaluated_cycles"] = prelaunch_metrics.get("valid_cycle_count", 0)

            if accuracy_tracker is not None and version_registry is not None:
                prod = version_registry.get_production(slot)
                if prod:
                    prod_metrics = accuracy_tracker.get_rolling_metrics(
                        slot, prod.get("workflow_id", "")
                    )
                    if prod_metrics and prod_metrics.get("status") != "insufficient_data":
                        item["production_rolling_mape"] = prod_metrics.get("rolling_mape")

            # 如果观察期已满，判断毕业/失败
            if observation_complete:
                prelaunch_mape = item.get("current_rolling_mape")
                prod_mape = item.get("production_rolling_mape")
                tolerance = item.get("graduate_tolerance_pct", _DEFAULT_GRADUATE_TOLERANCE_PCT)

                if prelaunch_mape is None or prod_mape is None:
                    # 数据不足，暂不做判断，继续观察
                    continue

                threshold = prod_mape * (1 + tolerance / 100.0)

                if prelaunch_mape <= threshold:
                    item["status"] = "graduated"
                    item["graduated_at"] = now_iso()
                    item["graduate_reason"] = (
                        f"auto: observation {obs_days}d complete, "
                        f"prelaunch_mape={prelaunch_mape:.4f} <= "
                        f"threshold={threshold:.4f} "
                        f"(prod={prod_mape:.4f} * {1 + tolerance/100:.2f})"
                    )
                    changed.append(item)
                    logger.info(
                        "prelaunch auto-graduated: slot=%s id=%s mape=%.4f prod=%.4f",
                        slot, item["id"], prelaunch_mape, prod_mape,
                    )
                else:
                    item["status"] = "failed"
                    item["failed_at"] = now_iso()
                    item["fail_reason"] = (
                        f"auto: observation {obs_days}d complete, "
                        f"prelaunch_mape={prelaunch_mape:.4f} > "
                        f"threshold={threshold:.4f} "
                        f"(prod={prod_mape:.4f} * {1 + tolerance/100:.2f})"
                    )
                    changed.append(item)
                    logger.info(
                        "prelaunch auto-failed: slot=%s id=%s mape=%.4f prod=%.4f",
                        slot, item["id"], prelaunch_mape, prod_mape,
                    )

        self._save(slot, queue)

        # DB sync for all items whose status changed（异步，best-effort）
        if _is_db_enabled() and changed:
            _changed_items = [dict(c) for c in changed]
            def _sync_all():
                repo = _get_lf_repo()
                if repo is None:
                    return
                try:
                    from sqlalchemy import update as sa_update
                    from services.db.models.load_forecast import PrelaunchQueue as PQModel
                    with repo._adapter.get_sync_session() as session:
                        for _item in _changed_items:
                            session.execute(
                                sa_update(PQModel)
                                .where(PQModel.id == _item["id"])
                                .values(
                                    status=_item["status"],
                                    graduated_at=_parse_iso(_item.get("graduated_at")),
                                    failed_at=_parse_iso(_item.get("failed_at")),
                                )
                            )
                except Exception as exc:
                    logger.warning("prelaunch evaluate_observing DB sync failed: %s", exc)
            threading.Thread(target=_sync_all, daemon=True).start()

        return changed

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _load(self, slot: str) -> List[Dict[str, Any]]:
        path = BASE_DATA_DIR / slot / "prelaunch_queue.json"
        data = load_json_safe(path, default=[])
        if not isinstance(data, list):
            logger.warning("prelaunch_queue.json 格式异常，重置为空列表: slot=%s", slot)
            return []
        return data

    def _save(self, slot: str, queue: List[Dict[str, Any]]) -> None:
        ensure_data_dir(slot)
        path = BASE_DATA_DIR / slot / "prelaunch_queue.json"
        _atomic_write_json(path, queue)

    @staticmethod
    def _find(queue: List[Dict[str, Any]], prelaunch_id: str) -> Optional[Dict[str, Any]]:
        for item in queue:
            if item.get("id") == prelaunch_id:
                return item
        return None
