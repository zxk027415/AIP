# @AI_GENERATED
"""
services/deployment/switch_decision.py — 精度维护切换决策引擎

职责（Responsibilities）：
  - `check_switch_eligibility(slot)` — 检查影子模型是否连续优于生产模型
    超过 `switch_observation_days` 天，返回切换建议
    （字段旧名 `evaluation_window_days` 已重命名，Pydantic AliasChoices 兼容读取旧数据）
  - `execute_switch(slot, target_workflow_id, trigger_type, reason, ...)`
    将目标 shadow 提升为 production，原 production 降级为 retired，
    并追加 SwitchEvent 到 append-only 日志
  - `execute_rollback(slot, reason)` — 冷却期内恢复前一 production 模型，
    当前 production 降级为 retired，追加 rollback 事件（`rollback_of` 指向
    被回滚的 event_id）

对应需求 / 设计：
  - Requirements 5.1 / 5.2 / 5.3 / 5.4 / 5.5
    （`.kiro/specs/algorithm-deployment-refactor/requirements.md`）
  - design.md 中 SwitchDecisionEngine（切换决策引擎）组件
  - Correctness Properties 4 / 5 / 6 / 7（同一 design.md）
  - "Error Handling → 模型切换错误处理" 表：切换目标不存在 / 目标非 shadow /
    冷却期内重复切换 / 无前版本回滚 —— 均以 `SwitchDecisionError.code`
    字段结构化上报，方便 FastAPI 层翻译为 HTTP 状态码

设计要点：
  - 所有状态转换均通过 `DeploymentSlotStore.upsert()` 落盘 —— 内存对象在
    落盘后作废，调用方应重新从 store 读取
  - 切换事件通过 `SwitchEventLog.append()` 追加，绝不修改已有条目
  - 冷却期检查基于同一 slot 的最后一次 SwitchEvent（含 rollback），首次切换
    不受冷却期限制；`force=True` 时人工绕过冷却期
  - Retired 模型保留在 `slot.shadow_models` 中（status='retired'），
    以便 rollback 时回溯前一 production
  - `now` 通过构造函数注入（默认 `datetime.now`），保证可测试

不做的事（Non-goals）：
  - 不主动定时轮询触发自动切换 —— 上层调度器决定何时调用
  - 不修改 shadow 模型的 `consecutive_better_days` 计数 —— 由上层精度评估
    模块维护；本引擎只读取该字段做资格判定
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from services.deployment.models import (
    DeploymentSlot,
    ModelVersion,
    SwitchEvent,
)
from services.deployment.store import (
    DeploymentSlotStore,
    SwitchEventLog,
    sort_shadow_models_by_accuracy,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 错误类型 — 供 FastAPI 层结构化翻译
# ---------------------------------------------------------------------------

class SwitchDecisionError(ValueError):
    """
    切换决策错误 —— 承载结构化 `code` 字段供上层 FastAPI 翻译。

    对应 design.md 中 "Error Handling → 模型切换错误处理" 表：

      | code                       | HTTP 状态 | 含义                            |
      | -------------------------- | --------- | ------------------------------- |
      | slot_not_found             | 404       | 槽位不存在                       |
      | target_not_found           | 404       | 目标模型 workflow_id 不在 shadow |
      | invalid_state_transition   | 400       | 目标非 shadow 状态               |
      | cooldown_active            | 409       | 冷却期内重复切换                 |
      | no_previous_version        | 400       | 回滚时无前一版本                 |
      | no_current_production      | 400       | 回滚时当前无 production          |
      | pv_fault_registry_read_only| 409       | pv_fault 只读，禁止 Arena 写入   |
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code: str = code
        self.message: str = message

    def __repr__(self) -> str:  # pragma: no cover — 调试用
        return f"SwitchDecisionError(code={self.code!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# SwitchEligibility — 切换资格检测结果
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SwitchEligibility:
    """
    切换资格检测结果。

    字段：
      - eligible                 — 是否满足切换条件（bool）
      - target_workflow_id       — 建议切换的 shadow 模型 workflow_id（可选）
      - reason                   — 人类可读诊断，取值见下方常量表
      - consecutive_better_days  — 胜出 shadow 的连续优于天数（不满足时为 0）

    reason 枚举（用作前端 UI 标签及日志检索关键字）：
      - 'eligible'              — 满足切换条件
      - 'slot_not_found'        — 槽位不存在
      - 'no_shadow'             — 当前无 shadow 模型
      - 'no_production_baseline' — 当前无 production 模型，无法比较
      - 'not_enough_days'       — 无 shadow 达到 switch_observation_days
      - 'not_better_than_prod'  — 达到天数但精度未真正优于 production
    """

    eligible: bool
    target_workflow_id: Optional[str]
    reason: str
    # @AI_GENERATED: 返回标签以便调用方按完整版本身份执行切换
    target_version_tag: Optional[str] = None
    # @AI_GENERATED: end
    consecutive_better_days: int = 0


# ---------------------------------------------------------------------------
# SwitchDecisionEngine — 切换决策引擎
# ---------------------------------------------------------------------------

class SwitchDecisionEngine:
    """
    模型切换决策引擎。

    通过依赖注入 `DeploymentSlotStore` + `SwitchEventLog` + `now` callable
    保持纯业务逻辑，无隐式全局状态。

    典型使用：

      >>> engine = SwitchDecisionEngine(
      ...     slot_store=DeploymentSlotStore(),
      ...     event_log=SwitchEventLog(),
      ... )
      >>> eligibility = engine.check_switch_eligibility("load_forecast")
      >>> if eligibility.eligible:
      ...     event = engine.execute_switch(
      ...         slot="load_forecast",
      ...         target_workflow_id=eligibility.target_workflow_id,
      ...         trigger_type="auto",
      ...         reason="连续 7 天 MAPE 优于生产",
      ...     )
    """

    def __init__(
        self,
        slot_store: DeploymentSlotStore,
        event_log: SwitchEventLog,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        """
        :param slot_store: 部署槽位持久化存储
        :param event_log:  切换事件 append-only 日志
        :param now:        当前时间函数（可注入以支持测试冻结时间）；
                           默认 `datetime.now`
        """
        self._slot_store = slot_store
        self._event_log = event_log
        self._now: Callable[[], datetime] = now if now is not None else datetime.now

    # -------------------------------------------------------------------
    # 4.1 check_switch_eligibility — 切换资格检测（Requirements 5.1, 5.4）
    # -------------------------------------------------------------------

    def check_switch_eligibility(self, slot: str) -> SwitchEligibility:
        """
        检查槽位下是否存在可切换的 shadow 模型。

        判定规则（对应 Property 4）：
          - 从 `slot.shadow_models` 中挑选 `consecutive_better_days` 最大者
            作为候选（相同天数则由 store 已按精度降序保证优先取精度更好的）
          - 候选必须同时满足：
              a) `consecutive_better_days >= switch_observation_days`
              b) `accuracy_score < production.accuracy_score`
                 （MAPE 越低越好；None 视为不满足）

        注意：
          - 无论 `auto_switch_enabled` 为 True/False 都会返回资格判定结果，
            便于 UI 展示"可切换但未启用自动"的提示（Requirement 5.1 要求
            "在界面上高亮提示可切换"，不局限于自动模式）
          - 无 production 模型时无法比较，直接返回 eligible=False，
            reason='no_production_baseline'

        :param slot: 槽位名称
        :return: SwitchEligibility 数据类
        """
        # @AI_GENERATED: pv_fault 不走 Arena 自动切换资格
        from services.deployment.pv_read_adapter import (
            PV_FAULT_READ_ONLY_CODE,
            is_pv_fault_slot,
        )

        if is_pv_fault_slot(slot):
            return SwitchEligibility(
                eligible=False,
                target_workflow_id=None,
                reason=PV_FAULT_READ_ONLY_CODE,
            )
        # @AI_GENERATED: end
        slot_obj = self._slot_store.get(slot)
        if slot_obj is None:
            return SwitchEligibility(
                eligible=False,
                target_workflow_id=None,
                reason="slot_not_found",
            )

        production = slot_obj.production_model
        if production is None:
            return SwitchEligibility(
                eligible=False,
                target_workflow_id=None,
                reason="no_production_baseline",
            )

        # 只考虑 status == 'shadow' 的候选（排除已 retired 记录）
        shadow_candidates: List[ModelVersion] = [
            m for m in slot_obj.shadow_models if m.status == "shadow"
        ]
        if not shadow_candidates:
            return SwitchEligibility(
                eligible=False,
                target_workflow_id=None,
                reason="no_shadow",
            )

        # 已按 accuracy_score 降序（升序更好 = MAPE 更低），但真正的排序键
        # 是"精度更好"。项目约定 accuracy_score 由外部维护，本模块不重新计算。
        # 挑选连续优于天数最大的候选；相同天数取 accuracy_score 更好的
        # （store 已按 accuracy_score 降序，这里再按 consecutive_better_days
        # 二次稳定排序即可）。
        ranked = sorted(
            shadow_candidates,
            key=lambda m: (
                -m.consecutive_better_days,
                # accuracy_score None 视为最差
                m.accuracy_score if m.accuracy_score is not None else float("inf"),
            ),
        )
        best = ranked[0]

        window_days = int(slot_obj.switch_observation_days or 0)
        if best.consecutive_better_days < window_days:
            return SwitchEligibility(
                eligible=False,
                target_workflow_id=best.workflow_id,
                reason="not_enough_days",
                consecutive_better_days=best.consecutive_better_days,
            )

        prod_score = production.accuracy_score
        shadow_score = best.accuracy_score
        # 若任一评分缺失，视为无法确认优势（保守拒绝）
        if prod_score is None or shadow_score is None:
            return SwitchEligibility(
                eligible=False,
                target_workflow_id=best.workflow_id,
                reason="not_better_than_prod",
                consecutive_better_days=best.consecutive_better_days,
            )
        if not (shadow_score < prod_score):
            return SwitchEligibility(
                eligible=False,
                target_workflow_id=best.workflow_id,
                reason="not_better_than_prod",
                consecutive_better_days=best.consecutive_better_days,
            )

        return SwitchEligibility(
            eligible=True,
            target_workflow_id=best.workflow_id,
            reason="eligible",
            target_version_tag=best.version_tag,
            consecutive_better_days=best.consecutive_better_days,
        )

    # -------------------------------------------------------------------
    # 4.3 execute_switch — 模型切换执行（Requirements 5.2, 5.3）
    # -------------------------------------------------------------------

    def execute_switch(
        self,
        slot: str,
        target_workflow_id: str,
        trigger_type: str,
        reason: str = "",
        pre_switch_mape: Optional[float] = None,
        force: bool = False,
        target_version_tag: Optional[str] = None,
    ) -> SwitchEvent:
        """
        将目标 shadow 模型提升为 production，原 production 降级为 retired。

        参数：
          - slot                — 槽位名称
          - target_workflow_id  — 待提升的 shadow 模型 workflow_id
          - trigger_type        — "auto" | "manual"
          - reason              — 切换原因备注（可选，人类可读）
          - pre_switch_mape     — 切换前精度覆盖值；未提供时取
                                  `production.accuracy_score`
          - force               — 手动 UI 可传 True 绕过冷却期检查

        前置校验（失败时抛 `SwitchDecisionError`，`code` 字段用于上层翻译）：
          - slot 不存在 → code='slot_not_found'
          - target_workflow_id 不在 shadow_models → code='target_not_found'
          - 目标模型 status != 'shadow' → code='invalid_state_transition'
          - 冷却期内重复切换（且 force=False）→ code='cooldown_active'

        副作用：
          1. 原 production.status 置为 'retired'，并保留在
             `slot.shadow_models` 列表末尾（供未来 rollback 查找）
          2. 目标 shadow.status 置为 'production'，`consecutive_better_days`
             清零；从 `shadow_models` 中移除，赋值给 `production_model`
          3. `slot.updated_at` 更新为 now().isoformat()
          4. 通过 `slot_store.upsert()` 持久化槽位
          5. 通过 `event_log.append()` 追加 SwitchEvent

        :return: 已持久化的 SwitchEvent
        """
        # @AI_GENERATED: pv_fault 禁止 Arena switch
        from services.deployment.pv_read_adapter import (
            PV_FAULT_READ_ONLY_CODE,
            PV_FAULT_READ_ONLY_MESSAGE,
            is_pv_fault_slot,
        )

        if is_pv_fault_slot(slot):
            raise SwitchDecisionError(
                code=PV_FAULT_READ_ONLY_CODE,
                message=PV_FAULT_READ_ONLY_MESSAGE,
            )
        # @AI_GENERATED: end
        if trigger_type not in ("auto", "manual"):
            raise SwitchDecisionError(
                code="invalid_state_transition",
                message=f"trigger_type 必须为 'auto' 或 'manual'，收到 {trigger_type!r}",
            )

        slot_obj = self._slot_store.get(slot)
        if slot_obj is None:
            raise SwitchDecisionError(
                code="slot_not_found",
                message=f"槽位不存在：slot={slot!r}",
            )

        # 定位目标 shadow；同 workflow 存在多个版本时必须显式传 version_tag。
        candidates = [
            model for model in slot_obj.shadow_models
            if model.workflow_id == target_workflow_id
            and (target_version_tag is None or model.version_tag == target_version_tag)
        ]
        if not candidates:
            raise SwitchDecisionError(
                code="target_not_found",
                message=(
                    f"目标模型不存在于 slot={slot!r} 的 shadow_models 中："
                    f"target_workflow_id={target_workflow_id!r}, "
                    f"target_version_tag={target_version_tag!r}"
                ),
            )
        if len(candidates) > 1:
            raise SwitchDecisionError(
                code="invalid_state_transition",
                message=(
                    f"workflow_id={target_workflow_id!r} 存在多个影子版本，"
                    "必须指定 target_version_tag"
                ),
            )
        target = candidates[0]
        if target.status != "shadow":
            raise SwitchDecisionError(
                code="invalid_state_transition",
                message=(
                    f"只能切换 status='shadow' 的模型，当前 status={target.status!r} "
                    f"（target_workflow_id={target_workflow_id!r}）"
                ),
            )

        # 冷却期检查（复用 SwitchEvent，无论 trigger_type 均生效；force=True 可绕过）
        if not force:
            self._enforce_cooldown(slot_obj)

        now_dt = self._now()
        now_iso = now_dt.isoformat()

        # 快照原 production 用于事件字段
        old_production = slot_obj.production_model
        from_workflow_id = old_production.workflow_id if old_production is not None else ""
        from_version_tag = old_production.version_tag if old_production is not None else ""
        resolved_pre_switch_mape: Optional[float] = pre_switch_mape
        if resolved_pre_switch_mape is None and old_production is not None:
            resolved_pre_switch_mape = old_production.accuracy_score

        # -------- 状态转换 --------
        # 1) 移除 shadow_models 中的目标条目
        new_shadow_list: List[ModelVersion] = [
            model for model in slot_obj.shadow_models if model is not target
        ]
        # 2) 原 production 降级为 retired，加入 shadow_models 末尾以便审计与回滚
        if old_production is not None:
            retired_prev = old_production.model_copy(
                update={"status": "retired"}
            )
            new_shadow_list.append(retired_prev)
        # 3) 目标提升为 production，consecutive_better_days 清零
        new_production = target.model_copy(
            update={
                "status": "production",
                "consecutive_better_days": 0,
                # deployed_at 保持不变（历史注册时间），若上层想刷新可另行更新
            }
        )
        slot_obj.production_model = new_production
        slot_obj.shadow_models = sort_shadow_models_by_accuracy(new_shadow_list)
        slot_obj.updated_at = now_iso

        # 4) 持久化槽位
        self._slot_store.upsert(slot_obj)

        # 5) 追加切换事件
        event = SwitchEvent(
            event_id=uuid.uuid4().hex,
            slot=slot,
            trigger_type=trigger_type,
            switch_time=now_iso,
            from_workflow_id=from_workflow_id,
            from_version_tag=from_version_tag,
            to_workflow_id=new_production.workflow_id,
            to_version_tag=new_production.version_tag,
            pre_switch_mape=resolved_pre_switch_mape,
            post_switch_mape=None,  # 由后置评估模块补写
            reason=reason,
            rollback_of=None,
        )
        self._event_log.append(event)
        logger.info(
            "switch_decision.execute_switch: slot=%s from=%s to=%s trigger=%s "
            "pre_switch_mape=%s force=%s",
            slot,
            from_workflow_id or "<none>",
            new_production.workflow_id,
            trigger_type,
            resolved_pre_switch_mape,
            force,
        )
        return event

    # -------------------------------------------------------------------
    # 4.6 execute_rollback — 回滚逻辑（Requirement 5.5）
    # -------------------------------------------------------------------

    def execute_rollback(
        self,
        slot: str,
        reason: str = "auto_rollback_due_to_threshold",
    ) -> SwitchEvent:
        """
        回滚到前一 production 模型。

        触发规则由上层判定（"冷却期内且精度低于阈值"），本方法只做状态还原
        与事件记录。

        前置校验：
          - slot 不存在 → code='slot_not_found'
          - 该 slot 无历史 SwitchEvent → code='no_previous_version'
          - 当前无 production 模型 → code='no_current_production'
          - 从事件日志推断的 from_workflow_id 在当前 shadow_models 中找不到
            retired 记录 → code='no_previous_version'

        副作用：
          1. 当前 production.status 置为 'retired'，保留在 shadow_models 末尾
          2. 前一 production（retired 状态）恢复为 'production'，从 shadow_models
             移除并赋值给 production_model
          3. `slot.updated_at` 更新
          4. 通过 `slot_store.upsert()` 持久化
          5. 追加 SwitchEvent，`rollback_of` 指向被回滚的最近非-rollback 事件

        :return: 回滚 SwitchEvent
        """
        # @AI_GENERATED: pv_fault 禁止 Arena rollback
        from services.deployment.pv_read_adapter import (
            PV_FAULT_READ_ONLY_CODE,
            PV_FAULT_READ_ONLY_MESSAGE,
            is_pv_fault_slot,
        )

        if is_pv_fault_slot(slot):
            raise SwitchDecisionError(
                code=PV_FAULT_READ_ONLY_CODE,
                message=PV_FAULT_READ_ONLY_MESSAGE,
            )
        # @AI_GENERATED: end
        slot_obj = self._slot_store.get(slot)
        if slot_obj is None:
            raise SwitchDecisionError(
                code="slot_not_found",
                message=f"槽位不存在：slot={slot!r}",
            )

        if slot_obj.production_model is None:
            raise SwitchDecisionError(
                code="no_current_production",
                message=f"槽位 {slot!r} 当前无 production 模型，无法回滚",
            )

        # 找到最近一次"被回滚的"事件：即最后一次非 rollback 事件
        history = self._event_log.list_by_slot(slot)
        target_event: Optional[SwitchEvent] = None
        for ev in reversed(history):
            if ev.rollback_of is None:
                target_event = ev
                break
        if target_event is None:
            raise SwitchDecisionError(
                code="no_previous_version",
                message=f"槽位 {slot!r} 无可回滚的历史切换事件",
            )

        # 从 shadow_models 中定位前一 production（应为 retired 状态）
        prev_workflow_id = target_event.from_workflow_id
        prev_version_tag = target_event.from_version_tag
        prev_model: Optional[ModelVersion] = None
        for m in slot_obj.shadow_models:
            if (
                m.workflow_id == prev_workflow_id
                and m.version_tag == prev_version_tag
                and m.status == "retired"
            ):
                prev_model = m
                break
        if prev_model is None:
            raise SwitchDecisionError(
                code="no_previous_version",
                message=(
                    f"槽位 {slot!r} 的前一 production 记录未找到："
                    f"workflow_id={prev_workflow_id!r}（可能已被清理）"
                ),
            )

        now_dt = self._now()
        now_iso = now_dt.isoformat()

        current_prod = slot_obj.production_model
        current_workflow_id = current_prod.workflow_id
        current_version_tag = current_prod.version_tag
        current_pre_mape = current_prod.accuracy_score  # 作为 rollback 事件的 pre_switch_mape

        # -------- 状态转换 --------
        # 1) 当前 production 降级为 retired，加入 shadow_models 末尾
        retired_current = current_prod.model_copy(update={"status": "retired"})
        # 2) 前一 production 恢复为 production，从 shadow_models 移除
        new_shadow_list: List[ModelVersion] = [
            m for m in slot_obj.shadow_models
            if not (m.workflow_id == prev_workflow_id and m.version_tag == prev_version_tag)
        ]
        new_shadow_list.append(retired_current)
        restored_production = prev_model.model_copy(
            update={
                "status": "production",
                "consecutive_better_days": 0,
            }
        )
        slot_obj.production_model = restored_production
        slot_obj.shadow_models = sort_shadow_models_by_accuracy(new_shadow_list)
        slot_obj.updated_at = now_iso

        self._slot_store.upsert(slot_obj)

        event = SwitchEvent(
            event_id=uuid.uuid4().hex,
            slot=slot,
            trigger_type="auto",  # 回滚默认作为自动动作，若上层为手动可再扩展参数
            switch_time=now_iso,
            from_workflow_id=current_workflow_id,
            from_version_tag=current_version_tag,
            to_workflow_id=restored_production.workflow_id,
            to_version_tag=restored_production.version_tag,
            pre_switch_mape=current_pre_mape,
            post_switch_mape=None,
            reason=reason,
            rollback_of=target_event.event_id,
        )
        self._event_log.append(event)
        logger.info(
            "switch_decision.execute_rollback: slot=%s from=%s to=%s "
            "rollback_of=%s",
            slot,
            current_workflow_id,
            restored_production.workflow_id,
            target_event.event_id,
        )
        return event

    # -------------------------------------------------------------------
    # 内部工具
    # -------------------------------------------------------------------

    def _enforce_cooldown(self, slot_obj: DeploymentSlot) -> None:
        """
        若上一次 SwitchEvent 距今在冷却期内则抛 cooldown_active。

        - 首次切换（无历史事件）不受限
        - rollback 事件同样计入冷却期起点（避免"刚回滚就切换"抖动）
        - `slot.cooldown_hours <= 0` 视为不启用冷却
        """
        cooldown_hours = int(slot_obj.cooldown_hours or 0)
        if cooldown_hours <= 0:
            return

        history = self._event_log.list_by_slot(slot_obj.slot)
        if not history:
            return
        last_event = history[-1]
        try:
            last_dt = datetime.fromisoformat(last_event.switch_time)
        except (TypeError, ValueError):
            # 事件时间字段异常，保守放行（避免因日志损坏卡死切换）
            logger.warning(
                "switch_decision._enforce_cooldown: 无法解析 switch_time=%r，"
                "放行冷却期检查 event_id=%s",
                last_event.switch_time,
                last_event.event_id,
            )
            return

        elapsed = self._now() - last_dt
        if elapsed < timedelta(hours=cooldown_hours):
            remaining = timedelta(hours=cooldown_hours) - elapsed
            # 向上取整为整数小时用于人类可读消息
            remaining_hours = int(remaining.total_seconds() // 3600) + 1
            raise SwitchDecisionError(
                code="cooldown_active",
                message=(
                    f"切换后冷却期内，请等待约 {remaining_hours} 小时"
                    f"（cooldown_hours={cooldown_hours}）"
                ),
            )
# @AI_GENERATED: end
