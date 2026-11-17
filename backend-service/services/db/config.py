# -*- coding: utf-8 -*-
"""
services/db/config.py — 数据库配置模块

DBConfig: 数据类，汇总所有数据库连接、连接池、调度器相关配置。

加载优先级（高 → 低）：
  1. 环境变量
  2. configs/db.yaml（相对于 backend-service/ 目录）
  3. 代码内默认值

超出允许范围的整型字段会抛出 ValidationError。

用法示例：
    from services.db.config import DBConfig
    cfg = DBConfig()
    print(cfg.engine, cfg.max_connections)
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置文件路径 — 相对于本文件所在的 services/db/ 目录向上两级，即 backend-service/
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent          # backend-service/services/db/
_BACKEND_DIR = _THIS_DIR.parent.parent               # backend-service/
_DEFAULT_CONFIG_PATH = _BACKEND_DIR / "configs" / "db.yaml"


class ValidationError(ValueError):
    """配置项超出允许范围时抛出"""
    pass


def _load_yaml_file(path: Path) -> dict:
    """尝试加载 YAML 配置文件；文件不存在时静默返回空字典。"""
    if not path.exists():
        return {}
    try:
        import yaml  # pyyaml，项目已有依赖
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        logger.debug("已加载数据库配置文件：%s", path)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("加载数据库配置文件失败（%s）：%s，使用默认值。", path, exc)
        return {}


def _get(env_key: str, file_data: dict, yaml_key: str, default):
    """
    按优先级取值：环境变量 > YAML 文件 > 代码默认值。

    - env_key   : 环境变量名，如 "DB_ENGINE"
    - file_data : 已解析的 YAML 字典
    - yaml_key  : YAML 中的字段名，如 "engine"
    - default   : 代码内默认值
    """
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return env_val
    return file_data.get(yaml_key, default)


def _get_int(env_key: str, file_data: dict, yaml_key: str, default: int) -> int:
    raw = _get(env_key, file_data, yaml_key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError(
            f"{env_key}/{yaml_key} 的值 {raw!r} 无法转换为整数"
        )


def _get_bool(env_key: str, file_data: dict, yaml_key: str, default: bool) -> bool:
    raw = _get(env_key, file_data, yaml_key, default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _validate_range(name: str, value: int, lo: int, hi: int) -> int:
    """确保 value 在 [lo, hi] 范围内，否则抛 ValidationError。"""
    if not (lo <= value <= hi):
        raise ValidationError(
            f"{name} 的值 {value} 超出允许范围 [{lo}, {hi}]"
        )
    return value


@dataclass
class DBConfig:
    """
    数据库及调度器配置数据类。

    实例化时自动从环境变量和 configs/db.yaml 加载，环境变量优先。
    整型字段超出范围时抛出 ValidationError。
    """

    # --- 数据库引擎 / 连接 ---
    engine: str = "mysql"
    """DB_ENGINE — 数据库引擎类型，默认 mysql"""

    connection_url: str = "mysql+pymysql://root@localhost:3306/aip_algo_platform"
    """DB_CONNECTION_URL — 完整连接字符串（pymysql 同步驱动）"""

    # --- 连接池参数 ---
    max_connections: int = 10
    """DB_POOL_MAX — 最大连接数，范围 [1, 100]"""

    idle_timeout: int = 300
    """DB_POOL_IDLE_TIMEOUT — 空闲连接超时（秒），范围 [10, 3600]"""

    connection_lifetime: int = 3600
    """DB_POOL_CONN_LIFETIME — 连接最大生存期（秒），范围 [60, 86400]"""

    pool_wait_timeout: int = 30
    """DB_POOL_WAIT_TIMEOUT — 池满时排队等待超时（秒），范围 [1, 120]"""

    # --- Schema 名称 ---
    lf_db_schema: str = "load_forecast"
    """LF_DB_SCHEMA — 负荷预测 MySQL 数据库名"""

    pv_db_schema: str = "pv_fault_diag"
    """PV_DB_SCHEMA — 光伏故障诊断 MySQL 数据库名"""

    # --- 功能开关 ---
    db_enabled: bool = True
    """DB_ENABLED — 总开关，false 时退化到文件存储"""

    dual_write: bool = True
    """DB_DUAL_WRITE — 双写开关，过渡期同时写数据库和文件"""

    # --- 调度器 cron 表达式 ---
    sched_lf_pull_cron: str = "0 1 * * *"
    """SCHED_LF_PULL_CRON — 负荷数据拉取 cron（默认每天 01:00）"""

    sched_lf_predict_cron: str = "30 1 * * *"
    """SCHED_LF_PREDICT_CRON — 负荷预测 cron（默认每天 01:30）"""

    sched_lf_backfill_cron: str = "0 3 * * *"
    """SCHED_LF_BACKFILL_CRON — 精度回填 cron（默认每天 03:00）"""

    sched_pv_pull_cron: str = "0 2 * * *"
    """SCHED_PV_PULL_CRON — PV 数据拉取 cron（默认每天 02:00）"""

    sched_pv_predict_cron: str = "30 2 * * *"
    """SCHED_PV_PREDICT_CRON — PV 预测 cron（默认每天 02:30）"""

    # @AI_GENERATED: PV 三产品槽的独立调度配置
    sched_pv_day_predict_cron: str = "0 3 * * *"
    """SCHED_PV_DAY_PREDICT_CRON — pv_day 日级工作流 cron（默认每天 03:00）"""

    sched_pv_point_replay_cron: str = "*/5 * * * *"
    """SCHED_PV_POINT_REPLAY_CRON — pv_point 事件时钟 replay cron（默认每 5 分钟）"""

    sched_pv_tsc_predict_cron: str = "0 4 * * *"
    """SCHED_PV_TSC_PREDICT_CRON — pv_tsc MultiRocket Challenger cron（默认每天 04:00）"""
    # @AI_GENERATED: end

    # @AI_GENERATED: 按日滚动预测生产表结构设计 —— mock 喂数据改为分钟级错峰释放
    sched_pv_mock_feed_cron: str = "*/12 * * * *"
    """SCHED_PV_MOCK_FEED_CRON — PV mock 错峰释放 cron（默认每 12 分钟一次 tick，
    每次只释放当前业务日里"计划批次已到"的一批设备，模拟真实场景下设备异步到达）。
    从"每天一次整批写入"改为"分钟级多批错峰释放"，见 PvFaultMockFeeder.release_next_batch_tick。
    """
    # @AI_GENERATED: end

    task_retry_delay: int = 60
    """SCHED_TASK_RETRY_DELAY — 任务失败重试延迟（秒），范围 [10, 600]"""

    # 内部：配置文件路径（不从环境变量加载，仅供测试覆盖）
    _config_path: Optional[Path] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        config_path = self._config_path or _DEFAULT_CONFIG_PATH
        file_data = _load_yaml_file(config_path)

        # --- 字符串字段 ---
        self.engine = _get("DB_ENGINE", file_data, "engine", self.engine)
        self.connection_url = _get(
            "DB_CONNECTION_URL", file_data, "connection_url", self.connection_url
        )
        self.lf_db_schema = _get("LF_DB_SCHEMA", file_data, "lf_db_schema", self.lf_db_schema)
        self.pv_db_schema = _get("PV_DB_SCHEMA", file_data, "pv_db_schema", self.pv_db_schema)

        # --- 整型字段（需范围校验）---
        self.max_connections = _validate_range(
            "max_connections",
            _get_int("DB_POOL_MAX", file_data, "max_connections", self.max_connections),
            1, 100,
        )
        self.idle_timeout = _validate_range(
            "idle_timeout",
            _get_int("DB_POOL_IDLE_TIMEOUT", file_data, "idle_timeout", self.idle_timeout),
            10, 3600,
        )
        self.connection_lifetime = _validate_range(
            "connection_lifetime",
            _get_int("DB_POOL_CONN_LIFETIME", file_data, "connection_lifetime", self.connection_lifetime),
            60, 86400,
        )
        self.pool_wait_timeout = _validate_range(
            "pool_wait_timeout",
            _get_int("DB_POOL_WAIT_TIMEOUT", file_data, "pool_wait_timeout", self.pool_wait_timeout),
            1, 120,
        )
        self.task_retry_delay = _validate_range(
            "task_retry_delay",
            _get_int("SCHED_TASK_RETRY_DELAY", file_data, "task_retry_delay", self.task_retry_delay),
            10, 600,
        )

        # --- 布尔字段 ---
        self.db_enabled = _get_bool("DB_ENABLED", file_data, "db_enabled", self.db_enabled)
        self.dual_write = _get_bool("DB_DUAL_WRITE", file_data, "dual_write", self.dual_write)

        # --- 调度器 cron（字符串，不校验格式，交给调度器层校验）---
        self.sched_lf_pull_cron = _get(
            "SCHED_LF_PULL_CRON", file_data, "sched_lf_pull_cron", self.sched_lf_pull_cron
        )
        self.sched_lf_predict_cron = _get(
            "SCHED_LF_PREDICT_CRON", file_data, "sched_lf_predict_cron", self.sched_lf_predict_cron
        )
        self.sched_lf_backfill_cron = _get(
            "SCHED_LF_BACKFILL_CRON", file_data, "sched_lf_backfill_cron", self.sched_lf_backfill_cron
        )
        self.sched_pv_pull_cron = _get(
            "SCHED_PV_PULL_CRON", file_data, "sched_pv_pull_cron", self.sched_pv_pull_cron
        )
        self.sched_pv_predict_cron = _get(
            "SCHED_PV_PREDICT_CRON", file_data, "sched_pv_predict_cron", self.sched_pv_predict_cron
        )
        # @AI_GENERATED: PV 三产品槽的独立调度配置
        self.sched_pv_day_predict_cron = _get(
            "SCHED_PV_DAY_PREDICT_CRON",
            file_data,
            "sched_pv_day_predict_cron",
            self.sched_pv_day_predict_cron,
        )
        self.sched_pv_point_replay_cron = _get(
            "SCHED_PV_POINT_REPLAY_CRON",
            file_data,
            "sched_pv_point_replay_cron",
            self.sched_pv_point_replay_cron,
        )
        self.sched_pv_tsc_predict_cron = _get(
            "SCHED_PV_TSC_PREDICT_CRON",
            file_data,
            "sched_pv_tsc_predict_cron",
            self.sched_pv_tsc_predict_cron,
        )
        # @AI_GENERATED: end
        # @AI_GENERATED: 按日滚动预测生产表结构设计
        self.sched_pv_mock_feed_cron = _get(
            "SCHED_PV_MOCK_FEED_CRON", file_data, "sched_pv_mock_feed_cron", self.sched_pv_mock_feed_cron
        )
        # @AI_GENERATED: end
