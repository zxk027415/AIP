"""
precision_ops/config_manager.py — 槽位配置管理器

提供：
  - SlotConfig  : 槽位配置数据类（含所有参数及默认值）
  - VALID_RANGES: 数值参数的合法范围字典（供校验使用）
  - ConfigManager: 配置加载、保存、校验、热更新
"""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any

from services.precision_ops.utils import (
    BASE_DATA_DIR,
    _atomic_write_json,
    ensure_data_dir,
    load_json_safe,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 参数合法范围（仅对数值参数做范围校验）
# ---------------------------------------------------------------------------
VALID_RANGES: dict[str, tuple[int, int]] = {
    "evaluation_window_days": (1, 30),
    "degradation_threshold_pct": (5, 50),
    "switch_margin_pct": (1, 30),
    "cooldown_hours": (1, 168),
    "min_valid_cycles": (1, 30),
    "shadow_timeout_seconds": (10, 600),
    "production_timeout_seconds": (10, 600),
    "max_shadow_versions": (2, 20),
    "rollback_window_hours": (1, 168),
}
"""
VALID_RANGES — 数值参数合法范围字典

键为参数名（snake_case），值为 (min, max) 闭区间整数元组。
该字典由 ConfigManager.validate_config() 遍历，任一字段越界则整体拒绝更新。
"""


# ---------------------------------------------------------------------------
# 槽位配置数据类
# ---------------------------------------------------------------------------
@dataclass
class SlotConfig:
    """
    SlotConfig — 单槽位配置快照

    每个槽位（slot）独立持有一份配置；字段含义见设计文档 §数据模型/Slot Config。
    所有字段均有默认值，存储不可用时退回默认实例。

    字段说明（英文 — 中文）：
      slot                         — 槽位名称（分区键），默认 "default"
      evaluation_window_days       — 评估窗口天数，范围 [1, 30]
      degradation_threshold_pct    — 退化阈值（相对百分比），范围 [5, 50]
      switch_margin_pct            — 切换分差（相对百分比），范围 [1, 30]
      cooldown_hours               — 冷却期小时数，范围 [1, 168]
      min_valid_cycles             — 最少有效周期数，范围 [1, 30]
      shadow_timeout_seconds       — 影子预测超时秒数，范围 [10, 600]
      production_timeout_seconds   — 生产预测超时秒数，范围 [10, 600]
      max_shadow_versions          — 最大影子版本数，范围 [2, 20]
      rollback_window_hours        — 回滚窗口小时数，范围 [1, 168]
      auto_switch_enabled          — 是否启用自动切换
      prediction_retention_days    — 预测结果保留天数
      min_eval_points              — 最少评估数据点数
      post_switch_observation_points — 切换后观察数据点数
      eval_window_points           — 评估窗口数据点数
    """

    slot: str = "default"

    # --- 有范围约束的数值参数 ---
    evaluation_window_days: int = 7
    degradation_threshold_pct: int = 15
    switch_margin_pct: int = 10
    cooldown_hours: int = 24
    min_valid_cycles: int = 3
    shadow_timeout_seconds: int = 300
    production_timeout_seconds: int = 120
    max_shadow_versions: int = 5
    rollback_window_hours: int = 48

    # --- 无范围约束的参数 ---
    auto_switch_enabled: bool = True
    prediction_retention_days: int = 90
    min_eval_points: int = 72
    post_switch_observation_points: int = 48
    eval_window_points: int = 168


# ---------------------------------------------------------------------------
# 配置管理器
# ---------------------------------------------------------------------------
class ConfigManager:
    """
    ConfigManager — 槽位配置加载、校验、原子更新

    存储路径：{BASE_DATA_DIR}/{slot}/config.json

    设计约定：
    - load_config  : 读取 JSON → 反序列化 → 越界字段用默认值替换；存储异常时降级为全默认。
    - save_config  : 通过 _atomic_write_json 原子写入，防止并发读取到半写文件。
    - validate_config: 遍历 VALID_RANGES，收集越界字段，返回 (is_valid, errors)。
    - update_config : 先在内存合并 + 校验，通过后才调用 save_config；失败不写磁盘。
    - to_dict       : dataclass → JSON 兼容字典（dataclasses.asdict）。
    """

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def load_config(self, slot: str) -> SlotConfig:
        """
        从 ``{BASE_DATA_DIR}/{slot}/config.json`` 加载配置。

        - 文件不存在 → 静默返回默认配置。
        - 文件解析失败或字段越界 → 用默认值填充，记录 ``degraded_config`` warning。

        :param slot: 槽位名称（分区键）
        :return: SlotConfig 实例
        """
        config_path = BASE_DATA_DIR / slot / "config.json"
        data = load_json_safe(config_path, default=None)

        if data is None:
            # 文件不存在时静默使用默认值（不记录 warning，属正常首次加载）
            return SlotConfig(slot=slot)

        if not isinstance(data, dict):
            logger.warning(
                "degraded_config: slot=%s config.json 内容不是字典，使用默认值", slot
            )
            return SlotConfig(slot=slot)

        return self._deserialize(slot, data)

    def save_config(self, slot: str, config: SlotConfig) -> None:
        """
        将配置原子写入 ``{BASE_DATA_DIR}/{slot}/config.json``。

        使用 ``_atomic_write_json``（先写临时文件后 os.replace），
        保证并发读取方不会观察到部分写入。

        :param slot: 槽位名称
        :param config: 要持久化的 SlotConfig 实例
        :raises OSError: 磁盘写入失败时透出
        """
        ensure_data_dir(slot)
        config_path = BASE_DATA_DIR / slot / "config.json"
        _atomic_write_json(config_path, self.to_dict(config))

    def validate_config(self, data: dict) -> tuple[bool, list[str]]:
        """
        校验配置字典中各数值参数是否在 ``VALID_RANGES`` 允许范围内。

        只校验 VALID_RANGES 中列出的字段；其余字段（如 auto_switch_enabled）不做范围检查。
        任一字段越界则 ``is_valid`` 为 ``False``，``errors`` 包含所有越界字段的说明。

        :param data: 待校验的字典（可以是部分字段，也可以是完整配置）
        :return: (is_valid, error_messages)
        """
        errors: list[str] = []
        for param, (lo, hi) in VALID_RANGES.items():
            if param not in data:
                continue  # 不要求字段必须存在（支持部分更新）
            value = data[param]
            if not isinstance(value, (int, float)):
                errors.append(
                    f"{param}: 期望数值类型，实际得到 {type(value).__name__}"
                )
                continue
            if not (lo <= value <= hi):
                errors.append(
                    f"{param}: 值 {value} 超出允许范围 [{lo}, {hi}]"
                )
        is_valid = len(errors) == 0
        return is_valid, errors

    def update_config(self, slot: str, updates: dict) -> SlotConfig:
        """
        加载当前配置，合并 updates，校验后原子保存。

        原子性保证：先在内存中合并 + 校验，校验通过才调用 save_config。
        任一字段越界则抛出 ValueError，当前存储的配置文件保持不变。

        :param slot: 槽位名称
        :param updates: 要更新的字段字典（partial update）
        :return: 更新后的 SlotConfig 实例
        :raises ValueError: updates 中任一参数越界时抛出，包含所有错误信息
        """
        # Step 1: 校验 updates（在合并到现有配置前，先对传入字段做范围检查）
        is_valid, errors = self.validate_config(updates)
        if not is_valid:
            raise ValueError(
                f"配置更新被拒绝（slot={slot}），以下字段越界：\n" + "\n".join(errors)
            )

        # Step 2: 加载现有配置，合并
        current = self.load_config(slot)
        merged_dict = self.to_dict(current)
        merged_dict.update(updates)

        # Step 3: 对合并后的完整配置再做一次全量校验（防止类型/格式异常）
        is_valid, errors = self.validate_config(merged_dict)
        if not is_valid:
            raise ValueError(
                f"配置更新被拒绝（slot={slot}），合并后仍有越界字段：\n"
                + "\n".join(errors)
            )

        # Step 4: 反序列化为 SlotConfig，保存
        new_config = self._deserialize(slot, merged_dict)
        self.save_config(slot, new_config)
        return new_config

    def to_dict(self, config: SlotConfig) -> dict[str, Any]:
        """
        将 SlotConfig 序列化为 JSON 兼容字典。

        :param config: SlotConfig 实例
        :return: 可直接传给 json.dump 的字典
        """
        return dataclasses.asdict(config)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _deserialize(self, slot: str, data: dict) -> SlotConfig:
        """
        将字典反序列化为 SlotConfig。

        越界或类型不匹配的字段使用 SlotConfig 的默认值替换，并记录 degraded_config warning。

        :param slot: 槽位名称（用于日志上下文）
        :param data: 从 JSON 文件读取的原始字典
        :return: SlotConfig 实例
        """
        defaults = SlotConfig(slot=slot)
        kwargs: dict[str, Any] = {"slot": slot}
        degraded_fields: list[str] = []

        for f in dataclasses.fields(SlotConfig):
            if f.name == "slot":
                continue
            if f.name not in data:
                # 字段缺失 → 用默认值
                kwargs[f.name] = getattr(defaults, f.name)
                continue

            raw = data[f.name]

            # 范围约束字段：越界则降级
            if f.name in VALID_RANGES:
                lo, hi = VALID_RANGES[f.name]
                try:
                    value = int(raw)
                    if lo <= value <= hi:
                        kwargs[f.name] = value
                    else:
                        degraded_fields.append(
                            f"{f.name}={raw}（越界，范围 [{lo},{hi}]）"
                        )
                        kwargs[f.name] = getattr(defaults, f.name)
                except (TypeError, ValueError):
                    degraded_fields.append(f"{f.name}={raw!r}（类型错误）")
                    kwargs[f.name] = getattr(defaults, f.name)
            elif f.type == "bool":
                # bool 字段
                if isinstance(raw, bool):
                    kwargs[f.name] = raw
                else:
                    degraded_fields.append(f"{f.name}={raw!r}（类型错误，期望 bool）")
                    kwargs[f.name] = getattr(defaults, f.name)
            else:
                # 其余字段（int/str）直接赋值，类型异常则降级
                try:
                    kwargs[f.name] = type(getattr(defaults, f.name))(raw)
                except (TypeError, ValueError):
                    degraded_fields.append(f"{f.name}={raw!r}（类型转换失败）")
                    kwargs[f.name] = getattr(defaults, f.name)

        if degraded_fields:
            logger.warning(
                "degraded_config: slot=%s，以下字段使用默认值：%s",
                slot,
                ", ".join(degraded_fields),
            )

        return SlotConfig(**kwargs)
