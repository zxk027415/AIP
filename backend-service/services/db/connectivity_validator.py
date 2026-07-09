# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/db/connectivity_validator.py — 数据库连通性验证器

在系统启动阶段主动校验 MySQL 数据库配置与连通性，返回结构化 `ValidationResult`，
供 `/api/system/db-health` 端点与主入口 `main.py` 启动流程消费。

设计参考：`.kiro/specs/algorithm-deployment-refactor/design.md` →
    "Data Models" → "数据库配置模型（已有，复用 services/db/config.py）"

对外主要成员：
  - ``ValidationResult``（结构化校验结果）
    - ``status``              — 状态字符串（healthy/unhealthy/config_error/skipped）
    - ``error_type``          — 错误类型枚举字符串，成功/跳过时为 None
    - ``message``             — 面向 UI/日志的人类可读消息（中文）
    - ``missing_vars``        — 缺失的必需环境变量名称列表
    - ``latency_ms``          — 探测 SELECT 1 的耗时（毫秒），成功时填充
    - ``engine``              — 数据库引擎（如 "mysql"），成功时填充
    - ``connection_url_masked`` — 已脱敏（密码替换为 ``***``）的连接串
  - ``DBConnectivityValidator``.``validate_config(config=None)``
    - 若 ``config`` 为空则调用 ``DBConfig()`` 加载环境变量 / YAML / 默认值
    - 若 ``DB_ENABLED=false`` → 返回 ``status='skipped'``，不发起连接
    - 若 ``REQUIRED_VARS`` 中任何变量未通过 env 或 yaml 提供 → 返回 ``status='config_error'``
    - 否则尝试执行 ``SELECT 1``，并按 SQLAlchemy 异常内容归类为
      ``connection_timeout`` / ``auth_failure`` / ``database_not_found`` / ``unknown``
  - ``validate_at_startup(fatal_on_missing_vars=True)``
    - 在 FastAPI 主入口调用；当 ``fatal_on_missing_vars=True`` 且发现缺失变量时立即抛出
      ``RuntimeError``，与需求 8.6 "启动阶段立即报错并列出所有缺失的变量名" 一致。

Requirements: 8.4, 8.5, 8.6
"""

import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from .config import DBConfig

logger = logging.getLogger(__name__)

# DBConfig.connection_url 的代码默认值 — 与 ``services/db/config.py`` 保持一致。
# 用于判定 "用户是否真的通过 env 或 yaml 覆盖了 connection_url"：
# 若 env 未设置且值仍等于该默认，则视为 "未配置"，避免用无意义默认值发起连接。
_DEFAULT_CONNECTION_URL = "mysql+pymysql://root@localhost:3306/aip_algo_platform"


@dataclass
class ValidationResult:
    """数据库连通性校验的结构化结果。"""

    # status — 状态：'healthy' 连通正常 / 'unhealthy' 连通失败 /
    #                'config_error' 必需变量缺失 / 'skipped' DB_ENABLED=false
    status: str

    # error_type — 错误类型（成功或跳过时为 None）
    error_type: Optional[str] = None

    # message — 面向 UI/日志的人类可读中文描述
    message: str = ""

    # missing_vars — 缺失的必需环境变量名列表（仅 config_error 时非空）
    missing_vars: List[str] = field(default_factory=list)

    # latency_ms — SELECT 1 探测耗时（毫秒），仅 healthy 时填充
    latency_ms: Optional[float] = None

    # engine — 数据库引擎（如 "mysql"），仅 healthy 时填充
    engine: Optional[str] = None

    # connection_url_masked — 密码脱敏后的连接串，仅非 config_error/skipped 时填充
    connection_url_masked: Optional[str] = None

    def to_dict(self) -> dict:
        """转为 API/日志可序列化的 dict（保留 None 字段便于前端固定字段展示）。"""
        return asdict(self)


class DBConnectivityValidator:
    """数据库连通性验证器 — 启动阶段主动校验。

    Attributes:
        REQUIRED_VARS: 最低必需环境变量名列表；缺失时立即报错，不尝试连接。
                       与 design.md 中 ``DBConnectivityValidator`` 一致，最小集合为
                       ``DB_CONNECTION_URL``（完整连接串即可涵盖 host/port/user/pw/db）。
    """

    REQUIRED_VARS: Tuple[str, ...] = ("DB_CONNECTION_URL",)

    # 建立连接时的探测超时（秒），避免验证器长时间阻塞启动流程。
    CONNECT_TIMEOUT_SECONDS: int = 5

    def validate_config(self, config: Optional[DBConfig] = None) -> ValidationResult:
        """校验配置完整性 + 连通性。

        Args:
            config: 已加载的 ``DBConfig``；为 None 时自动 ``DBConfig()`` 触发
                    env + yaml + 默认值三级加载。

        Returns:
            ``ValidationResult``，其中 ``status`` ∈
            ``{'healthy','unhealthy','config_error','skipped'}``。
        """
        # 1) 加载配置（未传入时按三级优先级重新加载）
        if config is None:
            try:
                config = DBConfig()
            except Exception as exc:  # noqa: BLE001 — 配置校验错误也算 config_error
                logger.error("加载 DBConfig 失败：%s", exc)
                return ValidationResult(
                    status="config_error",
                    error_type="config_load_error",
                    message=f"加载数据库配置失败：{exc}",
                    missing_vars=[],
                )

        # 2) 总开关：DB_ENABLED=false 时直接跳过，不发起连接
        if not config.db_enabled:
            logger.info("DB_ENABLED=false，跳过数据库连通性验证，使用文件存储。")
            return ValidationResult(
                status="skipped",
                error_type=None,
                message="DB 已禁用，使用文件存储",
                missing_vars=[],
                engine=config.engine,
            )

        # 3) 必需变量检查（env 未设置 且 config 仍为代码默认值 → 视为缺失）
        missing_vars = self._detect_missing_required_vars(config)
        if missing_vars:
            logger.error(
                "数据库配置缺少必需变量：%s（请通过环境变量或 configs/db.yaml 提供）。",
                ", ".join(missing_vars),
            )
            return ValidationResult(
                status="config_error",
                error_type="missing_env_vars",
                message="缺少必需环境变量",
                missing_vars=missing_vars,
            )

        # 4) 探测连接：SELECT 1
        masked_url = _mask_connection_url(config.connection_url)
        try:
            latency_ms = _probe_connection(
                config.connection_url,
                connect_timeout=self.CONNECT_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 — 分类到具体 error_type
            error_type, message = _classify_connection_error(exc, config.connection_url)
            logger.warning(
                "数据库连通性验证失败：error_type=%s message=%s（原始异常：%r）",
                error_type, message, exc,
            )
            return ValidationResult(
                status="unhealthy",
                error_type=error_type,
                message=message,
                missing_vars=[],
                engine=config.engine,
                connection_url_masked=masked_url,
            )

        logger.info(
            "数据库连通性验证通过：engine=%s latency=%.1fms url=%s",
            config.engine, latency_ms, masked_url,
        )
        return ValidationResult(
            status="healthy",
            error_type=None,
            message="数据库连通正常",
            missing_vars=[],
            latency_ms=round(latency_ms, 2),
            engine=config.engine,
            connection_url_masked=masked_url,
        )

    # ------------------------------------------------------------------ #
    # 内部：必需变量缺失检测                                              #
    # ------------------------------------------------------------------ #
    def _detect_missing_required_vars(self, config: DBConfig) -> List[str]:
        """判定 REQUIRED_VARS 中哪些变量视为 "未提供"。

        判定规则（env OR yaml 任一提供即视为已配置）：
          - 若 ``os.environ[name]`` 非空 → 已配置
          - 否则若对应 config 字段值 != 代码默认值 → 视为 yaml 提供 → 已配置
          - 否则 → 缺失
        """
        missing: List[str] = []
        for name in self.REQUIRED_VARS:
            env_val = os.environ.get(name, "").strip()
            if env_val:
                continue
            if name == "DB_CONNECTION_URL":
                # 若 yaml 或运行时已覆盖为非默认值，视为已配置
                if config.connection_url and config.connection_url != _DEFAULT_CONNECTION_URL:
                    continue
            missing.append(name)
        return missing


# ---------------------------------------------------------------------------- #
# 顶层工具函数                                                                 #
# ---------------------------------------------------------------------------- #

def validate_at_startup(fatal_on_missing_vars: bool = True) -> ValidationResult:
    """FastAPI 主入口调用：执行连通性验证，缺失变量时按需抛出致命错误。

    Args:
        fatal_on_missing_vars: 当结果为 ``config_error``（缺失必需变量）时是否
            立即抛出 ``RuntimeError``。生产环境建议 True，避免服务以半配置状态启动；
            测试或本地调试可设 False 以拿到结果继续排查。

    Returns:
        ``ValidationResult`` — 未抛出时的最终结果。

    Raises:
        RuntimeError: 当 ``fatal_on_missing_vars=True`` 且检测到缺失必需变量。
    """
    result = DBConnectivityValidator().validate_config()
    if result.status == "config_error" and fatal_on_missing_vars:
        raise RuntimeError(
            "数据库启动校验失败：缺少必需环境变量 "
            f"{result.missing_vars}。请在环境变量或 configs/db.yaml 中配置后重试。"
        )
    return result


# ---------------------------------------------------------------------------- #
# 内部工具：连接探测 / URL 脱敏 / 异常归类                                     #
# ---------------------------------------------------------------------------- #

def _probe_connection(connection_url: str, connect_timeout: int) -> float:
    """建立一次性 SQLAlchemy 引擎并执行 ``SELECT 1``，返回耗时（毫秒）。"""
    # 延迟导入 sqlalchemy — 避免 import 阶段的重解释器代价，也让本模块在无
    # sqlalchemy 环境下仍可被静态解析（例如仅需要 ValidationResult 数据结构）。
    from sqlalchemy import create_engine, text  # noqa: WPS433 — intentional lazy import

    engine = create_engine(
        connection_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": connect_timeout},
    )
    try:
        t0 = time.perf_counter()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return (time.perf_counter() - t0) * 1000.0
    finally:
        try:
            engine.dispose()
        except Exception:  # noqa: BLE001 — dispose 失败不影响主流程结果
            logger.debug("探测引擎 dispose() 失败，忽略。", exc_info=True)


def _classify_connection_error(exc: Exception, connection_url: str) -> Tuple[str, str]:
    """根据 SQLAlchemy 异常内容归类为 4 种 error_type。

    覆盖需求 8.5 与 design 表格中的错误矩阵：
      - connection_timeout（连接超时/无法连接）
      - auth_failure（认证失败）
      - database_not_found（数据库不存在）
      - unknown（兜底）
    """
    text_lower = str(exc).lower()

    if _is_timeout_or_unreachable(text_lower):
        host_port = _extract_host_port(connection_url)
        return "connection_timeout", f"连接超时：无法连接到 {host_port}"

    if _is_auth_failure(text_lower):
        return "auth_failure", "数据库认证失败，请检查 DB_USER/DB_PASSWORD"

    if _is_database_not_found(text_lower):
        db_name = _extract_db_name(connection_url) or "<unknown>"
        return "database_not_found", f"数据库 {db_name} 不存在"

    return "unknown", f"数据库连接异常：{exc}"


def _is_timeout_or_unreachable(msg: str) -> bool:
    keywords = (
        "timeout",
        "timed out",
        "can't connect",
        "cannot connect",
        "connection refused",
        "no route to host",
        "host is unreachable",
        "unknown server host",
        "unknown host",
    )
    return any(k in msg for k in keywords)


def _is_auth_failure(msg: str) -> bool:
    keywords = (
        "access denied",
        "authentication failed",
        "password authentication failed",
        "auth failed",
        "1045",  # MySQL 认证失败错误码
    )
    return any(k in msg for k in keywords)


def _is_database_not_found(msg: str) -> bool:
    keywords = (
        "unknown database",
        "database does not exist",
        "no such database",
        "1049",  # MySQL "Unknown database" 错误码
    )
    return any(k in msg for k in keywords)


def _mask_connection_url(url: str) -> str:
    """将连接串中的密码替换为 ``***``；无密码时原样返回。

    示例：
      - ``mysql+pymysql://user:pw@host:3306/db`` → ``mysql+pymysql://user:***@host:3306/db``
      - ``mysql+pymysql://root@localhost:3306/db`` → 保持不变（无密码）
    """
    if not url:
        return url
    try:
        parsed = urlsplit(url)
    except Exception:  # noqa: BLE001
        return "***"

    # 没有认证部分或没有密码 — 无需脱敏
    if parsed.password is None:
        return url

    user = parsed.username or ""
    host = parsed.hostname or ""
    port_part = f":{parsed.port}" if parsed.port else ""
    auth_part = f"{user}:***@" if user else "***@"
    masked_netloc = f"{auth_part}{host}{port_part}"
    return urlunsplit((parsed.scheme, masked_netloc, parsed.path, parsed.query, parsed.fragment))


def _extract_host_port(url: str) -> str:
    """从连接串抽取 ``host:port`` 用于错误消息拼装；解析失败时返回 ``<unknown>``。"""
    try:
        parsed = urlsplit(url)
    except Exception:  # noqa: BLE001
        return "<unknown>"
    host = parsed.hostname or "<unknown>"
    if parsed.port:
        return f"{host}:{parsed.port}"
    return host


def _extract_db_name(url: str) -> Optional[str]:
    """从连接串抽取数据库名（path 段第一节）。"""
    try:
        parsed = urlsplit(url)
    except Exception:  # noqa: BLE001
        return None
    path = (parsed.path or "").lstrip("/")
    if not path:
        return None
    # 有些方言允许 ``/db?charset=utf8mb4``，query 已被 urlsplit 分离；这里再兜底一次
    return path.split("/", 1)[0] or None
# @AI_GENERATED: end
