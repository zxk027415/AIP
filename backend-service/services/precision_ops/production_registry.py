"""
precision_ops/production_registry.py — 生产登记文件维护

职责：
  - 维护当前认定的生产基线（workflow_id + version_tag）
  - 作为下游预测服务查询"当前应使用哪个工作流"的唯一真源
  - 原子写入，确保并发读取不会观察到中间状态
  - 按 slot（槽位）分区，支持多环境/多产品线独立管理

存储路径：{BASE_DATA_DIR}/{slot}/production_registry.json

JSON 结构：
{
  "workflow_id": "workflow-load-forecast-prediction-v3",
  "version_tag": "v2026-06-08-ares-def456",
  "updated_at": "2026-06-08T10:35:00+00:00",
  "source_event_id": "sw-evt-20260608-abc123"
}
"""
from __future__ import annotations

import logging
from typing import Optional

from services.precision_ops.utils import (
    BASE_DATA_DIR,
    _atomic_write_json,
    ensure_data_dir,
    load_json_safe,
    now_iso,
)

logger = logging.getLogger(__name__)

# 生产登记必填字段
_REQUIRED_FIELDS = {"workflow_id", "version_tag", "updated_at", "source_event_id"}


class ProductionRegistry:
    """
    生产登记文件维护类。

    存储：{BASE_DATA_DIR}/{slot}/production_registry.json
    每个槽位（slot）独立一个 JSON 文件。

    **存什么**：当前认定的生产基线对应哪一个工作流模板 ID + 版本标签。
    **为什么单独存**：作为下游预测服务查询"当前应使用哪个工作流"的唯一真源，
                     与版本注册表解耦，确保并发读取不会观察到中间状态。
    **按什么维度分区**：按 slot（槽位），支持多场景/多区域独立管理。
    """

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def get(self, slot: str) -> Optional[dict]:
        """
        读取当前生产登记条目。

        校验必填字段（workflow_id, version_tag, updated_at, source_event_id），
        缺少任一字段视为"损坏"，返回 None 并记录 registry_recovery warning。

        :param slot: 槽位名称（分区键），如 "default"
        :return: 生产登记条目字典，损坏或不存在时返回 None
        """
        path = BASE_DATA_DIR / slot / "production_registry.json"
        data = load_json_safe(path, default=None)

        if data is None:
            # 文件不存在，属于正常初始状态，不记录 warning
            return None

        missing = _REQUIRED_FIELDS - set(data.keys())
        if missing:
            logger.warning(
                "registry_recovery: slot=%s production_registry 损坏，缺少必填字段 %s，返回 None",
                slot,
                sorted(missing),
            )
            return None

        return data

    def update(
        self,
        slot: str,
        workflow_id: str,
        version_tag: str,
        event_id: str,
    ) -> dict:
        """
        原子更新生产登记条目。

        通过 _atomic_write_json（先写临时文件后 os.replace）保证原子性，
        确保并发读取方不会观察到中间状态。

        :param slot: 槽位名称（分区键）
        :param workflow_id: 当前生产工作流 ID — 下游服务据此解析模板
        :param version_tag: 版本标签 — 人类可读版本标识
        :param event_id: 来源切换事件 ID — 导致本次登记更新的切换事件，便于审计
        :return: 更新后的生产登记条目字典
        """
        ensure_data_dir(slot)
        path = BASE_DATA_DIR / slot / "production_registry.json"

        entry = {
            "workflow_id": workflow_id,
            "version_tag": version_tag,
            "updated_at": now_iso(),
            "source_event_id": event_id,
        }

        _atomic_write_json(path, entry)

        logger.info(
            "production_registry.update: slot=%s workflow_id=%s version_tag=%s event_id=%s",
            slot,
            workflow_id,
            version_tag,
            event_id,
        )
        return entry

    def emit_change_event(
        self,
        slot: str,
        new_workflow_id: str,
        event_id: str,
    ) -> None:
        """
        发送生产登记变更事件（占位实现）。

        当前仅记录 INFO 日志；未来可扩展为真正的 HTTP 通知（超时设为 5s）。
        失败时只记录 registry_event_delivery_failed warning，
        不抛出异常，不阻塞主流程。

        :param slot: 槽位名称
        :param new_workflow_id: 新生产工作流 ID
        :param event_id: 本次变更事件 ID
        """
        try:
            # 占位实现：仅记录日志
            # 未来扩展为 HTTP 发送时，这里加 requests.post(..., timeout=5)
            logger.info(
                "emit_change_event: slot=%s new_workflow_id=%s event_id=%s [placeholder, no HTTP sent]",
                slot,
                new_workflow_id,
                event_id,
            )
        except Exception as exc:
            logger.warning(
                "registry_event_delivery_failed: slot=%s event_id=%s error=%s",
                slot,
                event_id,
                exc,
            )

    def recover_from_corruption(
        self,
        slot: str,
        version_registry,
    ) -> Optional[dict]:
        """
        从损坏状态恢复生产登记。

        从 VersionRegistry 中找到最近注册的 status=production 版本：
        - 找到 → 调用 update() 重建 production_registry，返回新条目
        - 找不到 → 记录 registry_unrecoverable error，返回 None

        :param slot: 槽位名称
        :param version_registry: VersionRegistry 实例，用于查询当前生产版本
        :return: 恢复后的生产登记条目，无法恢复时返回 None
        """
        production = version_registry.get_production(slot)
        if production is None:
            logger.error(
                "registry_unrecoverable: slot=%s VersionRegistry 中没有 status=production 版本，无法恢复",
                slot,
            )
            return None

        workflow_id: str = production["workflow_id"]
        version_tag: str = production["version_tag"]

        # 生成一个恢复事件 ID（用固定前缀标识来源）
        from services.precision_ops.utils import generate_event_id
        recovery_event_id = generate_event_id(prefix="recovery-evt")

        logger.warning(
            "registry_recovery: slot=%s 从 VersionRegistry 恢复 production_registry，"
            "workflow_id=%s version_tag=%s recovery_event_id=%s",
            slot,
            workflow_id,
            version_tag,
            recovery_event_id,
        )

        return self.update(
            slot=slot,
            workflow_id=workflow_id,
            version_tag=version_tag,
            event_id=recovery_event_id,
        )

    def get_or_recover(
        self,
        slot: str,
        version_registry,
    ) -> Optional[dict]:
        """
        先尝试 get，如果返回 None（损坏/缺失）则尝试 recover_from_corruption。

        方便外部一次性调用，无需手动判断是否需要恢复。

        :param slot: 槽位名称
        :param version_registry: VersionRegistry 实例
        :return: 生产登记条目，彻底无法恢复时返回 None
        """
        entry = self.get(slot)
        if entry is not None:
            return entry

        logger.info(
            "get_or_recover: slot=%s production_registry 不存在或损坏，尝试恢复",
            slot,
        )
        return self.recover_from_corruption(slot, version_registry)
