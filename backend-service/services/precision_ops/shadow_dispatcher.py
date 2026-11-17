"""
precision_ops/shadow_dispatcher.py — 影子分发器

职责：
  - 在每个预测周期内，让生产版本和所有活跃影子版本并行执行预测
  - 生产工作流最高优先级，不得被影子任务延迟
  - 影子任务失败/超时 → 记录 warning 日志，不中断整体流程
  - 生产任务失败/超时 → 发出告警事件，标记 production_failed=True
  - 使用 asyncio.Semaphore(5) 限制并发影子版本数

设计约定：
  - 不直接调用工作流执行引擎，通过可注入的 execute_fn 解耦
  - execute_fn 签名：async (workflow_id: str, input_data: dict) -> dict
  - 返回 dict 中约定 key ``predicted_value`` 为预测值；缺失时记录 warning 并跳过存储
  - forecast_timestamp 优先从 input_data 中取，其次从 result 中取，兜底 now_iso()
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

from services.precision_ops.utils import now_iso

logger = logging.getLogger(__name__)

# 最大并发影子任务数（与设计文档 asyncio.Semaphore(5) 一致）
_SHADOW_SEMAPHORE_LIMIT = 5


class ShadowDispatcher:
    """
    影子分发器：在每个预测周期内并行调度生产版本与影子版本预测。

    使用方式（生产）::

        dispatcher = ShadowDispatcher(
            version_registry=registry,
            prediction_store=store,
            execute_fn=real_execute_fn,
            config_manager=config_mgr,
        )
        result = await dispatcher.dispatch_prediction_cycle(
            slot="default",
            cycle_id="cycle-20260608-001",
            input_data={"forecast_timestamp": "2026-06-08T10:00:00+08:00", ...},
        )

    测试时注入 mock execute_fn 即可，无需启动真实执行引擎。
    """

    def __init__(
        self,
        version_registry,       # VersionRegistry 实例 — 版本注册表，提供 get_production/list_shadows
        prediction_store,       # PredictionStore 实例 — 预测结果存储，提供 record_prediction
        execute_fn: Callable[..., Coroutine[Any, Any, Dict]],
        # 异步可调用，签名 async (workflow_id: str, input_data: dict) -> dict
        config_manager,         # ConfigManager 实例 — 提供 load_config(slot) -> SlotConfig
    ) -> None:
        """
        初始化影子分发器。

        :param version_registry: VersionRegistry — 版本注册表
        :param prediction_store: PredictionStore — 预测结果存储（SQLite）
        :param execute_fn:       async callable，签名 (workflow_id, input_data) -> dict，
                                 生产时注入真实执行器，测试时注入 mock
        :param config_manager:   ConfigManager — 槽位配置管理器
        """
        self._registry = version_registry
        self._store = prediction_store
        self._execute_fn = execute_fn
        self._config_manager = config_manager

    # ------------------------------------------------------------------
    # 公开主入口
    # ------------------------------------------------------------------

    async def dispatch_prediction_cycle(
        self,
        slot: str,
        cycle_id: str,
        input_data: dict,
    ) -> dict:
        """
        执行一个完整的预测周期分发流程。

        执行顺序：
        1. 加载槽位配置（config_manager.load_config）
        2. 获取生产版本（version_registry.get_production）；无生产版本时记录 error 并提前返回
        3. 生产版本最高优先级执行（production_timeout_seconds）
           - 成功 → 提取 predicted_value，写入 prediction_store
           - 失败/超时 → 记录告警，标记 production_failed=True
        4. 所有影子版本并发执行（Semaphore(5) 限制，shadow_timeout_seconds）
           - 每个影子任务独立捕获异常，失败不中断其他任务
        5. 返回周期汇总结果

        :param slot:       槽位名称（分区键），如 "default"
        :param cycle_id:   预测周期 ID，用于存储和关联精度评估
        :param input_data: 传入执行器的输入数据字典（含 forecast_timestamp 等字段）
        :return: {
                   "cycle_id": str,           — 预测周期 ID
                   "production_failed": bool, — 生产版本是否失败/超时
                   "shadow_results": list,    — 各影子任务结果列表
                   "slot": str,               — 槽位名称
                 }
        """
        production_failed = False
        shadow_results: List[dict] = []

        # 1. 加载槽位配置
        config = self._config_manager.load_config(slot)

        # 2. 获取生产版本
        production = self._registry.get_production(slot)
        if production is None:
            logger.error(
                "dispatch_prediction_cycle: slot=%s cycle_id=%s 无生产版本，跳过本周期",
                slot,
                cycle_id,
            )
            return {
                "cycle_id": cycle_id,
                "production_failed": True,
                "shadow_results": [],
                "slot": slot,
            }

        prod_workflow_id: str = production["workflow_id"]
        prod_version_tag: str = production.get("version_tag", "")

        # 3. 生产版本执行（最高优先级，先于影子任务）
        try:
            prod_result = await self._execute_with_timeout(
                prod_workflow_id,
                input_data,
                float(config.production_timeout_seconds),
            )
            self._store_prediction(
                slot=slot,
                workflow_id=prod_workflow_id,
                version_tag=prod_version_tag,
                cycle_id=cycle_id,
                result=prod_result,
                input_data=input_data,
                label="production",
            )
            logger.info(
                "dispatch_prediction_cycle: 生产版本成功 slot=%s cycle_id=%s workflow_id=%s",
                slot, cycle_id, prod_workflow_id,
            )
        except asyncio.TimeoutError:
            production_failed = True
            logger.error(
                "dispatch_prediction_cycle: 生产版本超时 slot=%s cycle_id=%s "
                "workflow_id=%s timeout=%ss",
                slot, cycle_id, prod_workflow_id, config.production_timeout_seconds,
            )
            self._emit_production_alert(
                slot, cycle_id, prod_workflow_id,
                f"timeout(>{config.production_timeout_seconds}s)",
            )
        except Exception as exc:  # noqa: BLE001
            production_failed = True
            logger.error(
                "dispatch_prediction_cycle: 生产版本异常 slot=%s cycle_id=%s "
                "workflow_id=%s error=%s",
                slot, cycle_id, prod_workflow_id, exc,
            )
            self._emit_production_alert(slot, cycle_id, prod_workflow_id, str(exc))

        # 4. 影子版本并发执行（Semaphore 限制最大并发数）
        shadows = self._registry.list_shadows(slot)
        if shadows:
            semaphore = asyncio.Semaphore(_SHADOW_SEMAPHORE_LIMIT)
            shadow_tasks = [
                self._execute_shadow_task(
                    semaphore=semaphore,
                    shadow=shadow,
                    input_data=input_data,
                    timeout=float(config.shadow_timeout_seconds),
                    slot=slot,
                    cycle_id=cycle_id,
                )
                for shadow in shadows
            ]
            shadow_results = list(
                await asyncio.gather(*shadow_tasks, return_exceptions=False)
            )

        return {
            "cycle_id": cycle_id,
            "production_failed": production_failed,
            "shadow_results": shadow_results,
            "slot": slot,
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _execute_with_timeout(
        self,
        workflow_id: str,
        input_data: dict,
        timeout: float,
    ) -> dict:
        """
        带超时地调用 execute_fn。

        :param workflow_id: 工作流模板 ID
        :param input_data:  输入数据字典
        :param timeout:     超时秒数（浮点）
        :return: execute_fn 的返回值字典
        :raises asyncio.TimeoutError: 超过 timeout 时由 wait_for 抛出
        :raises Exception: execute_fn 内部异常透出
        """
        return await asyncio.wait_for(
            self._execute_fn(workflow_id, input_data),
            timeout=timeout,
        )

    async def _execute_shadow_task(
        self,
        semaphore: asyncio.Semaphore,
        shadow: dict,
        input_data: dict,
        timeout: float,
        slot: str,
        cycle_id: str,
    ) -> dict:
        """
        在 Semaphore 控制下执行单个影子版本预测。

        失败/超时时记录 warning 并返回 {"success": False, "error": ...}，
        不向调用方抛出异常，保证 asyncio.gather 不因单个影子任务失败而中断整体流程。

        :param semaphore:   asyncio.Semaphore — 限制全局最大并发影子任务数
        :param shadow:      影子版本条目字典（含 workflow_id、version_tag）
        :param input_data:  输入数据字典
        :param timeout:     超时秒数
        :param slot:        槽位名称（用于存储和日志）
        :param cycle_id:    预测周期 ID
        :return: {"success": bool, "workflow_id": str, "version_tag": str, ...}
        """
        shadow_workflow_id: str = shadow["workflow_id"]
        shadow_version_tag: str = shadow.get("version_tag", "")

        async with semaphore:
            try:
                result = await self._execute_with_timeout(
                    shadow_workflow_id,
                    input_data,
                    timeout,
                )
                self._store_prediction(
                    slot=slot,
                    workflow_id=shadow_workflow_id,
                    version_tag=shadow_version_tag,
                    cycle_id=cycle_id,
                    result=result,
                    input_data=input_data,
                    label="shadow",
                )
                logger.info(
                    "_execute_shadow_task: 影子版本成功 slot=%s cycle_id=%s workflow_id=%s",
                    slot, cycle_id, shadow_workflow_id,
                )
                return {
                    "success": True,
                    "workflow_id": shadow_workflow_id,
                    "version_tag": shadow_version_tag,
                }
            except asyncio.TimeoutError:
                err_msg = f"timeout(>{timeout}s)"
                logger.warning(
                    "_execute_shadow_task: 影子版本超时 slot=%s cycle_id=%s "
                    "workflow_id=%s timeout=%ss，已跳过",
                    slot, cycle_id, shadow_workflow_id, timeout,
                )
                return {
                    "success": False,
                    "workflow_id": shadow_workflow_id,
                    "version_tag": shadow_version_tag,
                    "error": err_msg,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "_execute_shadow_task: 影子版本异常 slot=%s cycle_id=%s "
                    "workflow_id=%s error=%s，已跳过",
                    slot, cycle_id, shadow_workflow_id, exc,
                )
                return {
                    "success": False,
                    "workflow_id": shadow_workflow_id,
                    "version_tag": shadow_version_tag,
                    "error": str(exc),
                }

    # ------------------------------------------------------------------
    # 私有辅助
    # ------------------------------------------------------------------

    def _store_prediction(
        self,
        slot: str,
        workflow_id: str,
        version_tag: str,
        cycle_id: str,
        result: dict,
        input_data: dict,
        label: str,
    ) -> None:
        """
        从 execute_fn 返回值中提取 predicted_value，并写入 PredictionStore。

        提取约定：
        - ``predicted_value``（预测值）— 必须在 result dict 中，key 为 "predicted_value"，
          值为数值类型；缺失或类型异常时记录 warning 并跳过存储。
        - ``forecast_timestamp``（预测目标时间戳）— 优先从 input_data 取，
          其次从 result 取，均不存在时兜底使用 now_iso() 并记录 warning。

        :param slot:        槽位名称（分区键）
        :param workflow_id: 工作流模板 ID
        :param version_tag: 版本标签
        :param cycle_id:    预测周期 ID
        :param result:      execute_fn 的返回值字典
        :param input_data:  原始输入数据字典
        :param label:       日志标签，"production" 或 "shadow"
        """
        if "predicted_value" not in result:
            logger.warning(
                "_store_prediction: %s workflow_id=%s 返回值缺少 predicted_value 字段，跳过存储",
                label, workflow_id,
            )
            return

        predicted_value = result["predicted_value"]
        if not isinstance(predicted_value, (int, float)):
            logger.warning(
                "_store_prediction: %s workflow_id=%s predicted_value 类型异常 %r，跳过存储",
                label, workflow_id, predicted_value,
            )
            return

        # forecast_timestamp — 预测目标时间戳：优先 input_data，其次 result，兜底 now_iso
        forecast_timestamp: Optional[str] = (
            input_data.get("forecast_timestamp")
            or result.get("forecast_timestamp")
        )
        if forecast_timestamp is None:
            forecast_timestamp = now_iso()
            logger.warning(
                "_store_prediction: %s workflow_id=%s input_data/result 均无 forecast_timestamp，"
                "使用当前时间 %s",
                label, workflow_id, forecast_timestamp,
            )

        try:
            self._store.record_prediction(
                slot=slot,
                workflow_id=workflow_id,
                version_tag=version_tag,
                cycle_id=cycle_id,
                forecast_timestamp=forecast_timestamp,
                predicted_value=float(predicted_value),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "_store_prediction: %s workflow_id=%s 写入 PredictionStore 失败 error=%s",
                label, workflow_id, exc,
            )

    def _emit_production_alert(
        self,
        slot: str,
        cycle_id: str,
        workflow_id: str,
        reason: str,
    ) -> None:
        """
        发出生产版本失败告警事件（production_failed）。

        当前实现通过 logger.error 记录结构化告警日志，便于外部日志聚合平台采集。
        后续可替换为发送到消息队列、告警平台或 webhook，调用方签名不变。

        :param slot:        槽位名称
        :param cycle_id:    预测周期 ID
        :param workflow_id: 工作流模板 ID（失败的生产版本）
        :param reason:      失败原因描述（"timeout" / 异常字符串）
        """
        logger.error(
            "ALERT production_failed: slot=%s cycle_id=%s workflow_id=%s reason=%s",
            slot, cycle_id, workflow_id, reason,
        )
