"""
precision_ops/switch_engine.py — 切换决策引擎

职责：
  - 评估是否应执行自动切换（evaluate）
  - 执行版本切换操作（execute_switch），含 per-slot 文件锁保护和失败回滚
  - 回滚最近一次切换（rollback）
  - 切换后精度观察（evaluate_post_switch）

存储（per-slot 锁文件）：{BASE_DATA_DIR}/{slot}/switch_engine.lock

设计文档：Properties 12-14, 16-18, 20, 21
  Validates: Requirements 4.1-4.5, 5.3-5.6, 6.2, 7.1-7.2
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from typing import TypedDict
except ImportError:  # Python < 3.8
    from typing_extensions import TypedDict  # type: ignore

from services.precision_ops.utils import (
    BASE_DATA_DIR,
    _atomic_write_json,
    ensure_data_dir,
    generate_event_id,
    load_json_safe,
    now_iso,
)

logger = logging.getLogger(__name__)

# fcntl 在 Windows 上不可用，降级为无锁
try:
    import fcntl
    _FCNTL_AVAILABLE = True
except ImportError:
    _FCNTL_AVAILABLE = False
    logger.warning("fcntl 不可用，切换操作将不使用文件锁")


# ---------------------------------------------------------------------------
# TypedDict
# ---------------------------------------------------------------------------

class SwitchDecision(TypedDict):
    """
    SwitchDecision — 切换决策结果

    字段说明（英文 — 中文）：
      should_switch       — 是否应切换
      target_workflow_id  — 切换目标工作流 ID（不切换时为 None）
      reason              — 决策原因（人类可读文本）
      suppressed          — 是否被冷却期或禁用标志抑制
      source_mape         — 原生产版本当前 rolling_mape（不可用时为 None）
      target_mape         — 目标版本当前 rolling_mape（不可用时为 None）
    """

    should_switch: bool
    target_workflow_id: Optional[str]
    reason: str
    suppressed: bool
    source_mape: Optional[float]
    target_mape: Optional[float]


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _hours_since(iso_str: str) -> float:
    """
    计算从 ISO 8601 时间戳到当前时间（UTC）经过的小时数。

    时区处理：无时区信息时假定为 UTC。

    :param iso_str: ISO 8601 格式时间戳字符串
    :return: 经过的小时数（浮点数）
    :raises ValueError: iso_str 无法解析时抛出
    """
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now_dt = datetime.now(tz=timezone.utc)
    delta = now_dt - dt
    return delta.total_seconds() / 3600.0


def _lock_file(f) -> None:
    """获取文件排他锁（fcntl 可用时）"""
    if _FCNTL_AVAILABLE:
        fcntl.flock(f, fcntl.LOCK_EX)


def _unlock_file(f) -> None:
    """释放文件锁（fcntl 可用时）"""
    if _FCNTL_AVAILABLE:
        fcntl.flock(f, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# SwitchDecisionEngine
# ---------------------------------------------------------------------------

class SwitchDecisionEngine:
    """
    切换决策引擎 — 评估、执行、回滚、切换后观察

    依赖注入（测试友好，不在内部创建依赖）：
      version_registry    — VersionRegistry 实例，读取/转换版本状态
      accuracy_tracker    — AccuracyTracker 实例，读取滚动精度指标
      switch_log          — SwitchLog 实例，追加和查询切换审计日志
      production_registry — ProductionRegistry 实例，更新生产登记
      config_manager      — ConfigManager 实例，加载槽位配置

    存储（per-slot 锁文件）：{BASE_DATA_DIR}/{slot}/switch_engine.lock
    """

    def __init__(
        self,
        version_registry,
        accuracy_tracker,
        switch_log,
        production_registry,
        config_manager,
    ) -> None:
        """
        :param version_registry:    VersionRegistry 实例
        :param accuracy_tracker:    AccuracyTracker 实例
        :param switch_log:          SwitchLog 实例
        :param production_registry: ProductionRegistry 实例
        :param config_manager:      ConfigManager 实例
        """
        self._version_registry = version_registry
        self._accuracy_tracker = accuracy_tracker
        self._switch_log = switch_log
        self._production_registry = production_registry
        self._config_manager = config_manager

    # ------------------------------------------------------------------
    # 切换决策
    # ------------------------------------------------------------------

    def evaluate(self, slot: str) -> SwitchDecision:
        """
        评估是否应执行自动切换。

        决策流程（参考 design.md 切换决策算法）：
        1. 检查 auto_switch_enabled（False → 返回 suppressed=True）
        2. 检查冷却期（距上次切换 < cooldown_hours → 返回 suppressed=True）
        3. 检查生产版本退化：
           (prod_mape - baseline_mape) / baseline_mape * 100 >= degradation_threshold_pct
        4. 寻找满足分差的最优候选：
           (prod_mape - shadow_mape) / prod_mape * 100 >= switch_margin_pct
        5. 多候选时选 rolling_mape 最低；差异 < 0.0001 时选 valid_cycle_count 更大的

        :param slot: 槽位名称（分区键）
        :return: SwitchDecision TypedDict
        """
        config = self._config_manager.load_config(slot)

        # Step 1: auto_switch_enabled 检查
        if not config.auto_switch_enabled:
            return SwitchDecision(
                should_switch=False,
                target_workflow_id=None,
                reason="自动切换已禁用（auto_switch_enabled=False）",
                suppressed=True,
                source_mape=None,
                target_mape=None,
            )

        # Step 2: 冷却期检查
        last_event = self._switch_log.get_last_event(slot)
        if last_event is not None:
            ts = last_event.get("timestamp", "")
            if ts:
                try:
                    elapsed_hours = _hours_since(ts)
                    if elapsed_hours < config.cooldown_hours:
                        return SwitchDecision(
                            should_switch=False,
                            target_workflow_id=None,
                            reason=(
                                f"冷却期内（距上次切换 {elapsed_hours:.1f}h，"
                                f"冷却期 {config.cooldown_hours}h）"
                            ),
                            suppressed=True,
                            source_mape=None,
                            target_mape=None,
                        )
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "evaluate: 解析上次切换时间戳失败: %s，跳过冷却期检查", exc
                    )

        # Step 3: 生产版本退化检测
        production = self._version_registry.get_production(slot)
        if production is None:
            return SwitchDecision(
                should_switch=False,
                target_workflow_id=None,
                reason="槽位无生产版本",
                suppressed=False,
                source_mape=None,
                target_mape=None,
            )

        prod_metrics = self._accuracy_tracker.get_rolling_metrics(
            slot, production["workflow_id"]
        )
        if prod_metrics is None or prod_metrics.get("status") == "insufficient_data":
            return SwitchDecision(
                should_switch=False,
                target_workflow_id=None,
                reason="生产版本精度数据不足，无法评估退化",
                suppressed=False,
                source_mape=None,
                target_mape=None,
            )

        baseline_mape = production.get("baseline_mape")
        if baseline_mape is None or baseline_mape == 0.0:
            return SwitchDecision(
                should_switch=False,
                target_workflow_id=None,
                reason="生产版本无基线 MAPE（baseline_mape），无法评估退化",
                suppressed=False,
                source_mape=prod_metrics["rolling_mape"],
                target_mape=None,
            )

        prod_mape: float = prod_metrics["rolling_mape"]
        degradation_pct = (prod_mape - baseline_mape) / baseline_mape * 100

        if degradation_pct < config.degradation_threshold_pct:
            return SwitchDecision(
                should_switch=False,
                target_workflow_id=None,
                reason=(
                    f"生产版本未退化（退化率 {degradation_pct:.1f}% < "
                    f"阈值 {config.degradation_threshold_pct}%）"
                ),
                suppressed=False,
                source_mape=prod_mape,
                target_mape=None,
            )

        # Step 4: 寻找满足切换分差的候选
        shadows = self._version_registry.list_shadows(slot)
        candidates: List[tuple] = []

        for shadow in shadows:
            metrics = self._accuracy_tracker.get_rolling_metrics(
                slot, shadow["workflow_id"]
            )
            if metrics is None or metrics.get("status") == "insufficient_data":
                continue
            if metrics["valid_cycle_count"] < config.min_valid_cycles:
                continue
            shadow_mape: float = metrics["rolling_mape"]
            margin_pct = (prod_mape - shadow_mape) / prod_mape * 100
            if margin_pct >= config.switch_margin_pct:
                candidates.append((shadow, metrics, margin_pct))

        if not candidates:
            return SwitchDecision(
                should_switch=False,
                target_workflow_id=None,
                reason=(
                    f"生产版本退化 {degradation_pct:.1f}%（超阈值 "
                    f"{config.degradation_threshold_pct}%），"
                    f"但无影子版本满足切换分差要求（{config.switch_margin_pct}%）"
                ),
                suppressed=False,
                source_mape=prod_mape,
                target_mape=None,
            )

        # Step 5: 多候选时选最优
        # rolling_mape 最低；差异 < 0.0001 时选 valid_cycle_count 更大的
        candidates.sort(
            key=lambda x: (
                round(x[1]["rolling_mape"] / 0.0001) * 0.0001,  # 差异 < 0.0001 视为相同
                -x[1]["valid_cycle_count"],  # valid_cycle_count 降序
            )
        )
        best_shadow, best_metrics, best_margin = candidates[0]

        return SwitchDecision(
            should_switch=True,
            target_workflow_id=best_shadow["workflow_id"],
            reason=(
                f"生产版本退化 {degradation_pct:.1f}%（超阈值 "
                f"{config.degradation_threshold_pct}%），"
                f"影子版本 {best_shadow.get('version_tag', best_shadow['workflow_id'])} "
                f"MAPE({best_metrics['rolling_mape']:.4f}) 优于生产({prod_mape:.4f}) "
                f"分差 {best_margin:.1f}%"
            ),
            suppressed=False,
            source_mape=prod_mape,
            target_mape=best_metrics["rolling_mape"],
        )

    # ------------------------------------------------------------------
    # 执行切换
    # ------------------------------------------------------------------

    def execute_switch(
        self,
        slot: str,
        target_workflow_id: str,
        trigger_type: str,
        reason: str,
    ) -> dict:
        """
        执行工作流版本切换操作。

        校验 target_workflow_id 必须存在于该 slot 的版本注册表中，否则抛出 ValueError。
        使用 per-slot fcntl 文件锁（{BASE_DATA_DIR}/{slot}/switch_engine.lock）保护整个切换过程。

        原子步骤：
        1. 备份当前 version_registry 数据
        2. transition_status：target shadow → production（同时降级当前生产版本）
        3. production_registry.update(...)
        4. switch_log.append(event)
        5. production_registry.emit_change_event(...)

        如果步骤 2 或 3 失败：
        - 通过备份数据回滚 version_registry（原子写回）
        - 向 switch_log 写入 switch_failed 事件
        - 重新抛出原始异常

        :param slot:               槽位名称（分区键）
        :param target_workflow_id: 目标工作流 ID（必须已在注册表中存在）
        :param trigger_type:       触发类型（"automatic" / "manual" / "rollback"）
        :param reason:             决策原因（超 500 字符自动截断）
        :return: 切换事件 dict
        :raises ValueError: target_workflow_id 不存在于 slot 的版本注册表时抛出
        """
        # --- 校验目标版本存在于该 slot ---
        all_versions = self._version_registry.list_all(slot)
        target_entry: Optional[dict] = None
        for v in all_versions:
            if v.get("workflow_id") == target_workflow_id:
                target_entry = v
                break

        if target_entry is None:
            raise ValueError(
                f"目标工作流 {target_workflow_id!r} 不存在于 slot={slot!r} 的版本注册表中"
            )

        # --- 找到当前生产版本 ---
        current_prod = self._version_registry.get_production(slot)

        # --- 读取精度指标快照（切换事件记录用） ---
        source_mape: Optional[float] = None
        target_mape: Optional[float] = None

        if current_prod is not None:
            prod_metrics = self._accuracy_tracker.get_rolling_metrics(
                slot, current_prod["workflow_id"]
            )
            if prod_metrics is not None:
                source_mape = prod_metrics["rolling_mape"]

        target_metrics = self._accuracy_tracker.get_rolling_metrics(
            slot, target_workflow_id
        )
        if target_metrics is not None:
            target_mape = target_metrics["rolling_mape"]

        # --- 构造切换事件 ---
        event_id = generate_event_id()
        event: Dict[str, Any] = {
            "event_id": event_id,
            "timestamp": now_iso(),
            "slot": slot,
            "trigger_type": trigger_type,
            "source_workflow_id": current_prod["workflow_id"] if current_prod else "",
            "target_workflow_id": target_workflow_id,
            "source_rolling_mape": source_mape,
            "target_rolling_mape": target_mape,
            "decision_reason": reason[:500],
        }

        # --- 备份当前 version_registry 数据（用于失败回滚）---
        registry_path = BASE_DATA_DIR / slot / "version_registry.json"
        backup_data = load_json_safe(registry_path, default=None)

        # --- per-slot 文件锁 ---
        ensure_data_dir(slot)
        lock_path = BASE_DATA_DIR / slot / "switch_engine.lock"
        lock_fd = open(str(lock_path), "w")
        try:
            _lock_file(lock_fd)

            # --- 步骤 2: 版本状态转换 ---
            # target shadow → production（transition_status 会自动将现有 production 降级为 shadow）
            try:
                self._version_registry.transition_status(
                    target_workflow_id,
                    target_entry["version_tag"],
                    "production",
                )
            except Exception as exc:
                logger.error(
                    "execute_switch: 版本状态转换失败（slot=%s, target=%s）: %s",
                    slot, target_workflow_id, exc,
                )
                self._write_switch_failed_event(event, f"版本状态转换失败: {exc}")
                raise

            # --- 步骤 3: 更新 production_registry ---
            try:
                self._production_registry.update(
                    slot=slot,
                    workflow_id=target_workflow_id,
                    version_tag=target_entry["version_tag"],
                    event_id=event_id,
                )
            except Exception as exc:
                logger.error(
                    "execute_switch: 更新 production_registry 失败（slot=%s）: %s",
                    slot, exc,
                )
                # 回滚 version_registry 到备份状态
                self._rollback_registry(slot, backup_data)
                self._write_switch_failed_event(
                    event, f"更新 production_registry 失败: {exc}"
                )
                raise

            # --- 步骤 4: 追加切换日志 ---
            try:
                self._switch_log.append(event)
            except Exception as exc:
                # 日志写入失败不回滚切换本身（参考 design.md 错误处理策略）
                logger.warning(
                    "execute_switch: 追加切换日志失败（slot=%s）: %s"
                    "（切换已执行，仅日志写入失败）",
                    slot, exc,
                )

            # --- 步骤 5: 发送变更事件 ---
            self._production_registry.emit_change_event(
                slot=slot,
                new_workflow_id=target_workflow_id,
                event_id=event_id,
            )

        finally:
            _unlock_file(lock_fd)
            lock_fd.close()

        logger.info(
            "execute_switch: 成功 slot=%s %s → %s trigger_type=%s event_id=%s",
            slot,
            current_prod["workflow_id"] if current_prod else "(none)",
            target_workflow_id,
            trigger_type,
            event_id,
        )
        return event

    # ------------------------------------------------------------------
    # 回滚
    # ------------------------------------------------------------------

    def rollback(self, slot: str) -> dict:
        """
        回滚最近一次切换操作。

        从 switch_log 获取最近一条事件，检查回滚窗口，
        以 trigger_type="rollback" 反向执行 execute_switch。

        :param slot: 槽位名称（分区键）
        :return: 回滚切换事件 dict
        :raises ValueError: 无切换历史可用，或超出回滚窗口时抛出
        """
        last_event = self._switch_log.get_last_event(slot)
        if last_event is None:
            raise ValueError(f"无切换历史可用（slot={slot!r}）")

        config = self._config_manager.load_config(slot)

        # 检查回滚窗口
        ts = last_event.get("timestamp", "")
        if not ts:
            raise ValueError(
                f"最近切换事件缺少 timestamp，无法检查回滚窗口（slot={slot!r}）"
            )

        try:
            elapsed_hours = _hours_since(ts)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"无法解析切换事件 timestamp={ts!r}，无法检查回滚窗口: {exc}"
            ) from exc

        if elapsed_hours > config.rollback_window_hours:
            raise ValueError(
                f"超出回滚窗口（距上次切换 {elapsed_hours:.1f}h > "
                f"回滚窗口 {config.rollback_window_hours}h），slot={slot!r}"
            )

        source_wf = last_event.get("source_workflow_id", "")
        target_wf = last_event.get("target_workflow_id", "")

        if not source_wf:
            raise ValueError(
                f"最近切换事件缺少 source_workflow_id，无法回滚（slot={slot!r}）"
            )

        reason = (
            f"回滚切换事件 {last_event.get('event_id', '')}："
            f"{target_wf} → {source_wf}"
        )

        return self.execute_switch(
            slot=slot,
            target_workflow_id=source_wf,
            trigger_type="rollback",
            reason=reason,
        )

    # ------------------------------------------------------------------
    # 切换后观察
    # ------------------------------------------------------------------

    def evaluate_post_switch(self, slot: str) -> Optional[str]:
        """
        切换后精度观察：读取最近一次 automatic 切换事件，检查新生产版本是否出现退化。

        如果新生产版本当前 rolling_mape 超出切换时的 target_rolling_mape 的
        degradation_threshold_pct 百分比，返回告警字符串；否则返回 None。

        :param slot: 槽位名称（分区键）
        :return: 告警消息字符串，或 None（无告警）
        """
        # 获取最近一次 automatic 切换事件
        result = self._switch_log.query(
            slot, trigger_type="automatic", page_size=1
        )
        events = result.get("events", [])
        if not events:
            return None

        last_auto_event = events[0]
        target_wf = last_auto_event.get("target_workflow_id")
        event_target_mape = last_auto_event.get("target_rolling_mape")

        if target_wf is None or event_target_mape is None:
            return None

        # 读取新生产版本当前 rolling_mape
        current_metrics = self._accuracy_tracker.get_rolling_metrics(slot, target_wf)
        if current_metrics is None or current_metrics.get("status") == "insufficient_data":
            return None

        current_mape: float = current_metrics["rolling_mape"]
        config = self._config_manager.load_config(slot)

        # 退化判断：当前 MAPE 超出切换时 target_mape 的 degradation_threshold_pct 百分比
        threshold_mape = event_target_mape * (
            1 + config.degradation_threshold_pct / 100.0
        )
        if current_mape > threshold_mape:
            event_id = last_auto_event.get("event_id", "")
            return (
                f"[切换后告警] slot={slot} 新生产版本 {target_wf} "
                f"当前 MAPE({current_mape:.4f}) 超出切换时 target_mape({event_target_mape:.4f}) "
                f"的 {config.degradation_threshold_pct}% 阈值（告警线 {threshold_mape:.4f}），"
                f"来源切换事件 {event_id}，建议检查或回滚"
            )

        return None

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _rollback_registry(self, slot: str, backup_data: Optional[dict]) -> None:
        """
        将 version_registry 回滚到备份状态（原子写回）。

        :param slot:        槽位名称
        :param backup_data: 备份数据（None 时跳过回滚）
        """
        if backup_data is None:
            logger.warning(
                "_rollback_registry: slot=%s 无备份数据，跳过回滚", slot
            )
            return
        try:
            registry_path = BASE_DATA_DIR / slot / "version_registry.json"
            _atomic_write_json(registry_path, backup_data)
            logger.info(
                "_rollback_registry: slot=%s version_registry 已回滚至备份状态", slot
            )
        except Exception as exc:
            logger.error(
                "_rollback_registry: slot=%s 回滚 version_registry 失败: %s", slot, exc
            )

    def _write_switch_failed_event(self, original_event: dict, error_msg: str) -> None:
        """
        向 switch_log 追加一条 switch_failed 事件（尽力写入，失败仅记录 warning）。

        :param original_event: 原始切换事件字典（复制后修改 trigger_type）
        :param error_msg:      失败原因（最多 500 字符）
        """
        failed_event = {
            **original_event,
            "event_id": generate_event_id(prefix="sw-failed"),
            "timestamp": now_iso(),
            "trigger_type": "switch_failed",
            "decision_reason": (
                f"[切换失败] {error_msg[:450]} | 原因: {original_event.get('decision_reason', '')}"
            )[:500],
        }
        try:
            self._switch_log.append(failed_event)
        except Exception as exc:
            logger.warning(
                "_write_switch_failed_event: 写入 switch_failed 事件失败: %s", exc
            )
