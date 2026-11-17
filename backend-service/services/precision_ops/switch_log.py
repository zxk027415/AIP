"""
precision_ops/switch_log.py — 切换审计日志（仅追加）

存储格式：JSONL（JSON Lines），每行一条 JSON 事件。
存储路径：{BASE_DATA_DIR}/{slot}/switch_log.jsonl

设计文档：Property 15 — 切换日志仅追加（Append-Only Log）
  对于任意操作序列，Switch Log 的长度应单调递增，
  且已写入的记录内容不应被修改。
  Validates: Requirements 5.1
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from services.precision_ops.utils import BASE_DATA_DIR, ensure_data_dir

logger = logging.getLogger(__name__)

# 必填字段列表
_REQUIRED_FIELDS = (
    "event_id",
    "timestamp",
    "slot",
    "trigger_type",
    "source_workflow_id",
    "target_workflow_id",
    "source_rolling_mape",
    "target_rolling_mape",
    "decision_reason",
)

# decision_reason 最大字符数
_MAX_REASON_LEN = 500


class SwitchLog:
    """
    切换审计日志（仅追加）。

    以 JSONL 格式记录每次工作流切换事件，每行一条 JSON，
    文件只增不改，保证审计可靠性。

    用法示例：
        log = SwitchLog()
        log.append({
            "event_id": "sw-evt-20260608-abc123",
            "timestamp": "2026-06-08T10:35:00+00:00",
            "slot": "default",
            "trigger_type": "automatic",
            "source_workflow_id": "workflow-v2",
            "target_workflow_id": "workflow-v3",
            "source_rolling_mape": 5.82,
            "target_rolling_mape": 4.12,
            "decision_reason": "生产版本退化超阈值",
        })
    """

    # ------------------------------------------------------------------
    # 路径工具
    # ------------------------------------------------------------------

    def _get_log_path(self, slot: str) -> Path:
        """
        返回指定槽位的 .jsonl 日志文件路径。

        :param slot: 槽位名称（分区键），如 "default"
        :return: switch_log.jsonl 的 Path 对象
        """
        return BASE_DATA_DIR / slot / "switch_log.jsonl"

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def append(self, event: dict) -> None:
        """
        追加一条不可变切换事件到 .jsonl 文件。

        会校验所有必填字段是否存在；若 ``decision_reason`` 超过
        500 字符则截断并记录 warning。写完后立即 flush 确保持久化。

        注意：直接以追加模式写文件，不使用 ``_atomic_write_json``
        （那是替换语义，与仅追加语义冲突）。

        :param event: 包含所有必填字段的切换事件字典
        :raises ValueError: 缺少必填字段时抛出
        """
        # --- 必填字段校验 ---
        missing = [f for f in _REQUIRED_FIELDS if f not in event]
        if missing:
            raise ValueError(f"切换事件缺少必填字段: {missing}")

        # --- decision_reason 截断 ---
        reason = event.get("decision_reason", "")
        if isinstance(reason, str) and len(reason) > _MAX_REASON_LEN:
            logger.warning(
                "SwitchLog.append: decision_reason 超过 %d 字符，已截断（原长 %d）",
                _MAX_REASON_LEN,
                len(reason),
            )
            event = {**event, "decision_reason": reason[:_MAX_REASON_LEN]}

        slot = event.get("slot", "")
        ensure_data_dir(slot)
        log_path = self._get_log_path(slot)

        line = json.dumps(event, ensure_ascii=False)
        # 以追加模式打开，每次写完立即 flush
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get_last_event(self, slot: str) -> Optional[dict]:
        """
        返回指定槽位日志文件的最后一条事件。

        文件不存在或为空时返回 None。

        :param slot: 槽位名称
        :return: 最后一条事件字典，或 None
        """
        log_path = self._get_log_path(slot)
        if not log_path.exists():
            return None

        last_line: Optional[str] = None
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
        except OSError as exc:
            logger.warning("SwitchLog.get_last_event: 读取 %s 失败: %s", log_path, exc)
            return None

        if last_line is None:
            return None

        try:
            return json.loads(last_line)
        except json.JSONDecodeError as exc:
            logger.warning("SwitchLog.get_last_event: 最后一行 JSON 解析失败: %s", exc)
            return None

    def query(
        self,
        slot: str,
        page: int = 1,
        page_size: int = 20,
        trigger_type: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> dict:
        """
        分页查询指定槽位的切换日志（最新在前）。

        支持按 ``trigger_type``（精确匹配）和时间范围过滤。
        ``page_size`` 超过 100 时自动 clamp 到 100。

        :param slot: 槽位名称
        :param page: 页码，从 1 开始
        :param page_size: 每页条数，最大 100
        :param trigger_type: 过滤触发类型（精确匹配），如 "automatic"、"manual"、"rollback"
        :param start_time: 起始时间（ISO 8601 字符串，含）
        :param end_time: 结束时间（ISO 8601 字符串，含）
        :return: ``{"total": n, "page": p, "page_size": ps, "events": [...]}``
        """
        # page_size clamp
        page_size = min(max(1, page_size), 100)
        page = max(1, page)

        log_path = self._get_log_path(slot)
        all_events: list[dict] = []

        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            all_events.append(json.loads(stripped))
                        except json.JSONDecodeError as exc:
                            logger.warning(
                                "SwitchLog.query: 跳过无法解析的行: %s", exc
                            )
            except OSError as exc:
                logger.warning("SwitchLog.query: 读取 %s 失败: %s", log_path, exc)

        # 反向（最新在前）
        all_events.reverse()

        # --- 过滤 ---
        filtered: list[dict] = []
        for evt in all_events:
            # trigger_type 精确匹配
            if trigger_type is not None and evt.get("trigger_type") != trigger_type:
                continue
            # 时间范围（ISO 8601 字符串直接比较，利用字典序）
            ts = evt.get("timestamp", "")
            if start_time is not None and ts < start_time:
                continue
            if end_time is not None and ts > end_time:
                continue
            filtered.append(evt)

        total = len(filtered)
        offset = (page - 1) * page_size
        events_page = filtered[offset: offset + page_size]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "events": events_page,
        }
