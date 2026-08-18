# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
services/scheduler/pv_dual_path/config.py — 双路径完整性闸门配置

DualPathConfig（双路径可配阈值）承载 Completeness_Gate（完整性闸门）所需的两个
可配项，供 seq_annotation（全天序列路径）严格门控与 legacy_day（传统按天路径）
宽松放行共用。

字段（英文名 — 中文含义）：
  - completeness_ratio      — 完整性阈值比例，范围 [0.0, 1.0]，默认 0.9。
                              判定 point_count / expected_point_count >= 该比例为达标。
                              环境变量覆盖：PV_COMPLETENESS_RATIO。
  - expected_point_count    — 期望点数（一天满格的时钟槽数），范围 [1, 288]，默认 288。
                              环境变量覆盖：PV_EXPECTED_POINT_COUNT。
  以下 12 项为任务 2.3 新增，覆盖 Req11/13/14/15 涉及的单轮上限、历史回看、
  容量预留、Shadow 准入、重训触发和退化恢复阈值，详见各字段 docstring。

加载优先级（高 → 低）：
  1. 环境变量（如 PV_COMPLETENESS_RATIO / PV_EXPECTED_POINT_COUNT）
  2. 配置文件 config/pv_dual_path.yaml（相对于 backend-service/ 目录）
  3. 代码内默认值（0.9 / 288 等）

越界回退语义（对应需求 4.2 / 4.5，及新增字段各自对应需求）：
  - completeness_ratio 不在 [0.0, 1.0]（含无法解析为浮点） → 回退默认 0.9。
  - expected_point_count <= 0 或不在 [1, 288]（含无法解析为整数） → 回退默认 288。
  - 新增 12 项字段各自越界（含无法解析）时同样记 warning 并回退默认值，
    不抛异常，保证调度不因坏配置中断。`recent_window_backfill_days` 的
    上界是同一次加载中已解析生效的 `max_backfill_days`（先解析
    max_backfill_days，再用其生效值校验 recent_window_backfill_days）。

路径与介质：配置文件路径相对 backend-service/，实际是否存在由部署决定；文件缺失时
静默使用默认值。所有持久化/引用路径均为相对路径，符合项目路径规范。

用法示例：
    from services.scheduler.pv_dual_path.config import load_dual_path_config
    cfg = load_dual_path_config()
    print(cfg.completeness_ratio, cfg.expected_point_count)
"""

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置文件路径 — 相对于本文件向上四级到 backend-service/，再拼 config/pv_dual_path.yaml
#   config.py 位于 backend-service/services/scheduler/pv_dual_path/
#   parents[0]=pv_dual_path parents[1]=scheduler parents[2]=services parents[3]=backend-service
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parents[3]          # backend-service/
_DEFAULT_CONFIG_PATH = _BACKEND_DIR / "config" / "pv_dual_path.yaml"

# --- 默认值与合法范围（单一事实来源）---
_DEFAULT_COMPLETENESS_RATIO = 0.9
_RATIO_MIN = 0.0
_RATIO_MAX = 1.0

_DEFAULT_EXPECTED_POINT_COUNT = 288
_EXPECTED_MIN = 1
_EXPECTED_MAX = 288

# --- 环境变量键 ---
_ENV_RATIO = "PV_COMPLETENESS_RATIO"
_ENV_EXPECTED = "PV_EXPECTED_POINT_COUNT"

# --- 任务 2.3 新增 12 项：默认值、合法范围、环境变量键（单一事实来源）---

# max_device_days_per_cycle — Seq 单轮设备日上限，整数 [1, 1000]，默认 50。
_DEFAULT_MAX_DEVICE_DAYS_PER_CYCLE = 50
_MAX_DEVICE_DAYS_PER_CYCLE_MIN = 1
_MAX_DEVICE_DAYS_PER_CYCLE_MAX = 1000
_ENV_MAX_DEVICE_DAYS_PER_CYCLE = "PV_MAX_DEVICE_DAYS_PER_CYCLE"

# max_backfill_days — full_backfill/recent_window 最大回看天数，整数 [1, 3650]，默认 14。
_DEFAULT_MAX_BACKFILL_DAYS = 14
_MAX_BACKFILL_DAYS_MIN = 1
_MAX_BACKFILL_DAYS_MAX = 3650
_ENV_MAX_BACKFILL_DAYS = "PV_MAX_BACKFILL_DAYS"

# recent_window_backfill_days — recent_window 启用模式默认回看天数，整数
# [1, max_backfill_days 当前生效值]，默认 7。上界依赖同一次加载解析出的
# max_backfill_days，不是固定常量。
_DEFAULT_RECENT_WINDOW_BACKFILL_DAYS = 7
_RECENT_WINDOW_BACKFILL_DAYS_MIN = 1
_ENV_RECENT_WINDOW_BACKFILL_DAYS = "PV_RECENT_WINDOW_BACKFILL_DAYS"

# production_capacity_reserved_ratio — 历史回放不得占用的生产预留容量比例，
# 浮点 [0.0, 1.0]，默认 0.8。
_DEFAULT_PRODUCTION_CAPACITY_RESERVED_RATIO = 0.8
_PRODUCTION_CAPACITY_RESERVED_RATIO_MIN = 0.0
_PRODUCTION_CAPACITY_RESERVED_RATIO_MAX = 1.0
_ENV_PRODUCTION_CAPACITY_RESERVED_RATIO = "PV_PRODUCTION_CAPACITY_RESERVED_RATIO"

# shadow_report_valid_days — Cross-Path Shadow 报告有效期，整数 [1, 3650]，默认 14。
_DEFAULT_SHADOW_REPORT_VALID_DAYS = 14
_SHADOW_REPORT_VALID_DAYS_MIN = 1
_SHADOW_REPORT_VALID_DAYS_MAX = 3650
_ENV_SHADOW_REPORT_VALID_DAYS = "PV_SHADOW_REPORT_VALID_DAYS"

# min_comparable_device_days — 跨路径切换准入要求的最少可比设备日数，
# 整数 >= 0，默认 200。
_DEFAULT_MIN_COMPARABLE_DEVICE_DAYS = 200
_MIN_COMPARABLE_DEVICE_DAYS_MIN = 0
_ENV_MIN_COMPARABLE_DEVICE_DAYS = "PV_MIN_COMPARABLE_DEVICE_DAYS"

# min_shadow_coverage_rate — 跨路径切换准入要求的最小 Shadow 覆盖率，
# 浮点 [0.0, 1.0]，默认 0.9。
_DEFAULT_MIN_SHADOW_COVERAGE_RATE = 0.9
_MIN_SHADOW_COVERAGE_RATE_MIN = 0.0
_MIN_SHADOW_COVERAGE_RATE_MAX = 1.0
_ENV_MIN_SHADOW_COVERAGE_RATE = "PV_MIN_SHADOW_COVERAGE_RATE"

# retrain_change_threshold — 触发自动重训的累计变动单元阈值，整数 >= 0，默认 200。
_DEFAULT_RETRAIN_CHANGE_THRESHOLD = 200
_RETRAIN_CHANGE_THRESHOLD_MIN = 0
_ENV_RETRAIN_CHANGE_THRESHOLD = "PV_RETRAIN_CHANGE_THRESHOLD"

# retrain_period_days — 触发自动重训的周期天数，整数 >= 0，默认 7。
_DEFAULT_RETRAIN_PERIOD_DAYS = 7
_RETRAIN_PERIOD_DAYS_MIN = 0
_ENV_RETRAIN_PERIOD_DAYS = "PV_RETRAIN_PERIOD_DAYS"

# promotion_margin — 路径内 Challenger 晋升所需的严格优于 Champion 的边际，
# 浮点 >= 0.0，默认 0.0。
_DEFAULT_PROMOTION_MARGIN = 0.0
_PROMOTION_MARGIN_MIN = 0.0
_ENV_PROMOTION_MARGIN = "PV_PROMOTION_MARGIN"

# no_coverage_failure_cycles — CompletenessGate 连续无覆盖多少轮才计入
# 整路径不可用判定，整数 >= 1，默认 24。
_DEFAULT_NO_COVERAGE_FAILURE_CYCLES = 24
_NO_COVERAGE_FAILURE_CYCLES_MIN = 1
_ENV_NO_COVERAGE_FAILURE_CYCLES = "PV_NO_COVERAGE_FAILURE_CYCLES"

# path_failed_cycles — 路径连续失败多少轮才计入整路径不可用判定，
# 整数 >= 1，默认 3。
_DEFAULT_PATH_FAILED_CYCLES = 3
_PATH_FAILED_CYCLES_MIN = 1
_ENV_PATH_FAILED_CYCLES = "PV_PATH_FAILED_CYCLES"


def _load_yaml_file(path: Path) -> dict:
    """尝试加载 YAML 配置文件；文件不存在或解析失败时静默返回空字典。"""
    if not path.exists():
        return {}
    try:
        import yaml  # pyyaml，项目已有依赖
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            logger.warning("双路径配置文件内容非字典（%s），忽略并使用默认值。", path)
            return {}
        logger.debug("已加载双路径配置文件：%s", path)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("加载双路径配置文件失败（%s）：%s，使用默认值。", path, exc)
        return {}


def _raw_value(env_key: str, file_data: dict, yaml_key: str):
    """按优先级取原始值：环境变量 > YAML 文件 > None（表示用默认）。"""
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return env_val
    if yaml_key in file_data:
        return file_data.get(yaml_key)
    return None


def _resolve_ratio(raw) -> float:
    """
    解析并校验 completeness_ratio。

    raw 为 None（无配置）时返回默认 0.9；无法解析为浮点或越界 [0.0, 1.0] 时
    记 warning 并回退默认 0.9（对应需求 4.2）。
    """
    if raw is None:
        return _DEFAULT_COMPLETENESS_RATIO
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "completeness_ratio 配置值 %r 无法解析为浮点，回退默认 %s。",
            raw, _DEFAULT_COMPLETENESS_RATIO,
        )
        return _DEFAULT_COMPLETENESS_RATIO
    if not (_RATIO_MIN <= value <= _RATIO_MAX):
        logger.warning(
            "completeness_ratio 配置值 %s 超出范围 [%s, %s]，回退默认 %s。",
            value, _RATIO_MIN, _RATIO_MAX, _DEFAULT_COMPLETENESS_RATIO,
        )
        return _DEFAULT_COMPLETENESS_RATIO
    return value


def _resolve_expected(raw) -> int:
    """
    解析并校验 expected_point_count。

    raw 为 None（无配置）时返回默认 288；无法解析为整数或越界 [1, 288]
    （含 <= 0）时记 warning 并回退默认 288（对应需求 4.5）。
    """
    if raw is None:
        return _DEFAULT_EXPECTED_POINT_COUNT
    try:
        # 先转 float 再转 int，兼容 "288" / "288.0" / 288.0 等写法；
        # 但拒绝带小数部分的值以避免歧义。
        as_float = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "expected_point_count 配置值 %r 无法解析为整数，回退默认 %s。",
            raw, _DEFAULT_EXPECTED_POINT_COUNT,
        )
        return _DEFAULT_EXPECTED_POINT_COUNT
    if as_float != int(as_float):
        logger.warning(
            "expected_point_count 配置值 %r 含小数部分，回退默认 %s。",
            raw, _DEFAULT_EXPECTED_POINT_COUNT,
        )
        return _DEFAULT_EXPECTED_POINT_COUNT
    value = int(as_float)
    if not (_EXPECTED_MIN <= value <= _EXPECTED_MAX):
        logger.warning(
            "expected_point_count 配置值 %s 超出范围 [%s, %s]，回退默认 %s。",
            value, _EXPECTED_MIN, _EXPECTED_MAX, _DEFAULT_EXPECTED_POINT_COUNT,
        )
        return _DEFAULT_EXPECTED_POINT_COUNT
    return value


def _resolve_int_in_range(
    raw,
    field_name: str,
    default: int,
    minimum: Optional[int],
    maximum: Optional[int],
) -> int:
    """
    通用整数校验：raw 为 None 时返回 default；无法解析为不含小数部分的整数，
    或解析结果不在 [minimum, maximum]（任一端为 None 表示该侧不限）时，
    记 warning 并回退 default。

    复用给 max_device_days_per_cycle、max_backfill_days、
    min_comparable_device_days、retrain_change_threshold、
    retrain_period_days、no_coverage_failure_cycles、path_failed_cycles、
    shadow_report_valid_days 等纯整数配置，减少重复解析代码。
    """
    if raw is None:
        return default
    try:
        as_float = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "%s 配置值 %r 无法解析为整数，回退默认 %s。",
            field_name, raw, default,
        )
        return default
    if as_float != int(as_float):
        logger.warning(
            "%s 配置值 %r 含小数部分，回退默认 %s。",
            field_name, raw, default,
        )
        return default
    value = int(as_float)
    if minimum is not None and value < minimum:
        logger.warning(
            "%s 配置值 %s 小于下界 %s，回退默认 %s。",
            field_name, value, minimum, default,
        )
        return default
    if maximum is not None and value > maximum:
        logger.warning(
            "%s 配置值 %s 大于上界 %s，回退默认 %s。",
            field_name, value, maximum, default,
        )
        return default
    return value


def _resolve_float_in_range(
    raw,
    field_name: str,
    default: float,
    minimum: Optional[float],
    maximum: Optional[float],
) -> float:
    """
    通用浮点校验：raw 为 None 时返回 default；无法解析为浮点，或解析结果
    不在 [minimum, maximum]（任一端为 None 表示该侧不限）时，记 warning
    并回退 default。

    复用给 production_capacity_reserved_ratio、min_shadow_coverage_rate、
    promotion_margin 等浮点配置。
    """
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "%s 配置值 %r 无法解析为浮点，回退默认 %s。",
            field_name, raw, default,
        )
        return default
    if minimum is not None and value < minimum:
        logger.warning(
            "%s 配置值 %s 小于下界 %s，回退默认 %s。",
            field_name, value, minimum, default,
        )
        return default
    if maximum is not None and value > maximum:
        logger.warning(
            "%s 配置值 %s 大于上界 %s，回退默认 %s。",
            field_name, value, maximum, default,
        )
        return default
    return value


def _resolve_max_device_days_per_cycle(raw) -> int:
    """解析并校验 max_device_days_per_cycle：整数 [1, 1000]，默认 50（Req13.9）。"""
    return _resolve_int_in_range(
        raw, "max_device_days_per_cycle",
        _DEFAULT_MAX_DEVICE_DAYS_PER_CYCLE,
        _MAX_DEVICE_DAYS_PER_CYCLE_MIN, _MAX_DEVICE_DAYS_PER_CYCLE_MAX,
    )


def _resolve_max_backfill_days(raw) -> int:
    """解析并校验 max_backfill_days：整数 [1, 3650]，默认 14（Req14.12）。"""
    return _resolve_int_in_range(
        raw, "max_backfill_days",
        _DEFAULT_MAX_BACKFILL_DAYS,
        _MAX_BACKFILL_DAYS_MIN, _MAX_BACKFILL_DAYS_MAX,
    )


def _resolve_recent_window_backfill_days(raw, effective_max_backfill_days: int) -> int:
    """
    解析并校验 recent_window_backfill_days：整数
    [1, effective_max_backfill_days]（Req14.4，上界为同一次加载中已生效的
    max_backfill_days，而非固定常量），默认 7。
    """
    return _resolve_int_in_range(
        raw, "recent_window_backfill_days",
        _DEFAULT_RECENT_WINDOW_BACKFILL_DAYS,
        _RECENT_WINDOW_BACKFILL_DAYS_MIN, effective_max_backfill_days,
    )


def _resolve_production_capacity_reserved_ratio(raw) -> float:
    """解析并校验 production_capacity_reserved_ratio：浮点 [0.0, 1.0]，默认 0.8（Req14.13）。"""
    return _resolve_float_in_range(
        raw, "production_capacity_reserved_ratio",
        _DEFAULT_PRODUCTION_CAPACITY_RESERVED_RATIO,
        _PRODUCTION_CAPACITY_RESERVED_RATIO_MIN, _PRODUCTION_CAPACITY_RESERVED_RATIO_MAX,
    )


def _resolve_shadow_report_valid_days(raw) -> int:
    """解析并校验 shadow_report_valid_days：整数 [1, 3650]，默认 14（Req7.11）。"""
    return _resolve_int_in_range(
        raw, "shadow_report_valid_days",
        _DEFAULT_SHADOW_REPORT_VALID_DAYS,
        _SHADOW_REPORT_VALID_DAYS_MIN, _SHADOW_REPORT_VALID_DAYS_MAX,
    )


def _resolve_min_comparable_device_days(raw) -> int:
    """解析并校验 min_comparable_device_days：整数 >= 0，默认 200（Req6.5/15.11）。"""
    return _resolve_int_in_range(
        raw, "min_comparable_device_days",
        _DEFAULT_MIN_COMPARABLE_DEVICE_DAYS,
        _MIN_COMPARABLE_DEVICE_DAYS_MIN, None,
    )


def _resolve_min_shadow_coverage_rate(raw) -> float:
    """解析并校验 min_shadow_coverage_rate：浮点 [0.0, 1.0]，默认 0.9（Req6.5/15.11）。"""
    return _resolve_float_in_range(
        raw, "min_shadow_coverage_rate",
        _DEFAULT_MIN_SHADOW_COVERAGE_RATE,
        _MIN_SHADOW_COVERAGE_RATE_MIN, _MIN_SHADOW_COVERAGE_RATE_MAX,
    )


def _resolve_retrain_change_threshold(raw) -> int:
    """解析并校验 retrain_change_threshold：整数 >= 0，默认 200（Req11.1/11.8）。"""
    return _resolve_int_in_range(
        raw, "retrain_change_threshold",
        _DEFAULT_RETRAIN_CHANGE_THRESHOLD,
        _RETRAIN_CHANGE_THRESHOLD_MIN, None,
    )


def _resolve_retrain_period_days(raw) -> int:
    """解析并校验 retrain_period_days：整数 >= 0，默认 7（Req11.1/11.8）。"""
    return _resolve_int_in_range(
        raw, "retrain_period_days",
        _DEFAULT_RETRAIN_PERIOD_DAYS,
        _RETRAIN_PERIOD_DAYS_MIN, None,
    )


def _resolve_promotion_margin(raw) -> float:
    """解析并校验 promotion_margin：浮点 >= 0.0，默认 0.0（Req11.4/11.9）。"""
    return _resolve_float_in_range(
        raw, "promotion_margin",
        _DEFAULT_PROMOTION_MARGIN,
        _PROMOTION_MARGIN_MIN, None,
    )


def _resolve_no_coverage_failure_cycles(raw) -> int:
    """解析并校验 no_coverage_failure_cycles：整数 >= 1，默认 24（Req15.11）。"""
    return _resolve_int_in_range(
        raw, "no_coverage_failure_cycles",
        _DEFAULT_NO_COVERAGE_FAILURE_CYCLES,
        _NO_COVERAGE_FAILURE_CYCLES_MIN, None,
    )


def _resolve_path_failed_cycles(raw) -> int:
    """解析并校验 path_failed_cycles：整数 >= 1，默认 3（Req15.11）。"""
    return _resolve_int_in_range(
        raw, "path_failed_cycles",
        _DEFAULT_PATH_FAILED_CYCLES,
        _PATH_FAILED_CYCLES_MIN, None,
    )


@dataclass(frozen=True)
class DualPathConfig:
    """
    双路径完整性闸门配置（不可变）。

    通过 load_dual_path_config() 构造，自动应用「环境变量 > 配置文件 > 默认值」
    优先级并对越界值回退默认。直接实例化时不做校验，仅用于测试注入已知合法值；
    生产路径应统一走 load_dual_path_config()。
    """

    completeness_ratio: float = _DEFAULT_COMPLETENESS_RATIO
    """完整性阈值比例，范围 [0.0, 1.0]，默认 0.9。"""

    expected_point_count: int = _DEFAULT_EXPECTED_POINT_COUNT
    """期望点数（满格时钟槽数），范围 [1, 288]，默认 288。"""

    # 任务 2.3 新增 12 项字段（design.md 全部设计默认值）
    max_device_days_per_cycle: int = _DEFAULT_MAX_DEVICE_DAYS_PER_CYCLE
    """Seq 单轮设备日上限，整数 [1, 1000]，默认 50（Req13.8-13.10）。"""

    max_backfill_days: int = _DEFAULT_MAX_BACKFILL_DAYS
    """full_backfill/recent_window 最大回看天数，整数 [1, 3650]，默认 14（Req14.4, 14.12）。"""

    recent_window_backfill_days: int = _DEFAULT_RECENT_WINDOW_BACKFILL_DAYS
    """recent_window 启用模式默认回看天数，整数 [1, max_backfill_days 当前生效值]，默认 7（Req14.4）。"""

    production_capacity_reserved_ratio: float = _DEFAULT_PRODUCTION_CAPACITY_RESERVED_RATIO
    """历史回放不得占用的生产预留容量比例，浮点 [0.0, 1.0]，默认 0.8（Req14.13）。"""

    shadow_report_valid_days: int = _DEFAULT_SHADOW_REPORT_VALID_DAYS
    """Cross-Path Shadow 报告有效期天数，整数 [1, 3650]，默认 14（Req7.11）。"""

    min_comparable_device_days: int = _DEFAULT_MIN_COMPARABLE_DEVICE_DAYS
    """跨路径切换准入要求的最少可比设备日数，整数 >= 0，默认 200（Req6.5, 15.11）。"""

    min_shadow_coverage_rate: float = _DEFAULT_MIN_SHADOW_COVERAGE_RATE
    """跨路径切换准入要求的最小 Shadow 覆盖率，浮点 [0.0, 1.0]，默认 0.9（Req6.5, 15.11）。"""

    retrain_change_threshold: int = _DEFAULT_RETRAIN_CHANGE_THRESHOLD
    """触发自动重训的累计变动单元阈值，整数 >= 0，默认 200（Req11.1, 11.8）。"""

    retrain_period_days: int = _DEFAULT_RETRAIN_PERIOD_DAYS
    """触发自动重训的周期天数，整数 >= 0，默认 7（Req11.1, 11.8）。"""

    promotion_margin: float = _DEFAULT_PROMOTION_MARGIN
    """路径内 Challenger 晋升所需严格优于 Champion 的边际，浮点 >= 0.0，默认 0.0（Req11.4, 11.9）。"""

    no_coverage_failure_cycles: int = _DEFAULT_NO_COVERAGE_FAILURE_CYCLES
    """CompletenessGate 连续无覆盖多少轮计入整路径不可用判定，整数 >= 1，默认 24（Req15.11）。"""

    path_failed_cycles: int = _DEFAULT_PATH_FAILED_CYCLES
    """路径连续失败多少轮计入整路径不可用判定，整数 >= 1，默认 3（Req15.11）。"""


def load_dual_path_config(config_path: Optional[Path] = None) -> DualPathConfig:
    """
    加载双路径配置，应用优先级与越界回退。

    参数：
      - config_path — 可选，覆盖默认配置文件路径（供测试注入）；缺省时用
                      backend-service/config/pv_dual_path.yaml。

    返回：DualPathConfig，字段均为已校验/回退后的合法值。
    """
    path = config_path or _DEFAULT_CONFIG_PATH
    file_data = _load_yaml_file(path)

    ratio = _resolve_ratio(_raw_value(_ENV_RATIO, file_data, "completeness_ratio"))
    expected = _resolve_expected(_raw_value(_ENV_EXPECTED, file_data, "expected_point_count"))

    # 任务 2.3 新增 12 项字段的加载与越界回退
    # recent_window_backfill_days 的上界依赖同一次加载中已生效的 max_backfill_days，
    # 因此必须先解析 max_backfill_days，再用其生效值校验 recent_window_backfill_days。
    max_device_days_per_cycle = _resolve_max_device_days_per_cycle(
        _raw_value(_ENV_MAX_DEVICE_DAYS_PER_CYCLE, file_data, "max_device_days_per_cycle")
    )
    max_backfill_days = _resolve_max_backfill_days(
        _raw_value(_ENV_MAX_BACKFILL_DAYS, file_data, "max_backfill_days")
    )
    recent_window_backfill_days = _resolve_recent_window_backfill_days(
        _raw_value(_ENV_RECENT_WINDOW_BACKFILL_DAYS, file_data, "recent_window_backfill_days"),
        max_backfill_days,
    )
    production_capacity_reserved_ratio = _resolve_production_capacity_reserved_ratio(
        _raw_value(_ENV_PRODUCTION_CAPACITY_RESERVED_RATIO, file_data, "production_capacity_reserved_ratio")
    )
    shadow_report_valid_days = _resolve_shadow_report_valid_days(
        _raw_value(_ENV_SHADOW_REPORT_VALID_DAYS, file_data, "shadow_report_valid_days")
    )
    min_comparable_device_days = _resolve_min_comparable_device_days(
        _raw_value(_ENV_MIN_COMPARABLE_DEVICE_DAYS, file_data, "min_comparable_device_days")
    )
    min_shadow_coverage_rate = _resolve_min_shadow_coverage_rate(
        _raw_value(_ENV_MIN_SHADOW_COVERAGE_RATE, file_data, "min_shadow_coverage_rate")
    )
    retrain_change_threshold = _resolve_retrain_change_threshold(
        _raw_value(_ENV_RETRAIN_CHANGE_THRESHOLD, file_data, "retrain_change_threshold")
    )
    retrain_period_days = _resolve_retrain_period_days(
        _raw_value(_ENV_RETRAIN_PERIOD_DAYS, file_data, "retrain_period_days")
    )
    promotion_margin = _resolve_promotion_margin(
        _raw_value(_ENV_PROMOTION_MARGIN, file_data, "promotion_margin")
    )
    no_coverage_failure_cycles = _resolve_no_coverage_failure_cycles(
        _raw_value(_ENV_NO_COVERAGE_FAILURE_CYCLES, file_data, "no_coverage_failure_cycles")
    )
    path_failed_cycles = _resolve_path_failed_cycles(
        _raw_value(_ENV_PATH_FAILED_CYCLES, file_data, "path_failed_cycles")
    )

    return DualPathConfig(
        completeness_ratio=ratio,
        expected_point_count=expected,
        max_device_days_per_cycle=max_device_days_per_cycle,
        max_backfill_days=max_backfill_days,
        recent_window_backfill_days=recent_window_backfill_days,
        production_capacity_reserved_ratio=production_capacity_reserved_ratio,
        shadow_report_valid_days=shadow_report_valid_days,
        min_comparable_device_days=min_comparable_device_days,
        min_shadow_coverage_rate=min_shadow_coverage_rate,
        retrain_change_threshold=retrain_change_threshold,
        retrain_period_days=retrain_period_days,
        promotion_margin=promotion_margin,
        no_coverage_failure_cycles=no_coverage_failure_cycles,
        path_failed_cycles=path_failed_cycles,
    )
# @AI_GENERATED: end
