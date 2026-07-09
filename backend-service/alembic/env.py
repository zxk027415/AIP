"""
alembic/env.py — Alembic 运行环境配置

从 DBConfig 读取连接串，支持 online/offline 两种迁移模式。
target_metadata 暂设为 None（ORM 模型创建后替换为 Base.metadata）。

Requirements: 1.7, 1.8
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# 确保 backend-service/ 在 sys.path，以便导入 services.db.config
# ---------------------------------------------------------------------------
_this_file = Path(__file__).resolve()
_backend_dir = _this_file.parent.parent  # alembic/env.py -> alembic/ -> backend-service/
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from services.db.config import DBConfig  # noqa: E402
from services.db.models.base import Base  # noqa: E402
import services.db.models.load_forecast  # noqa: E402, F401 — 注册负荷预测 ORM 模型到 Base.metadata
import services.db.models.pv_fault       # noqa: E402, F401 — 注册光伏故障诊断 ORM 模型到 Base.metadata
# @AI_GENERATED: AutoResearch MySQL 迁移相关模型
import services.db.models.autoresearch   # noqa: E402, F401 — AutoResearch 明细表（trial/decision/job/verification/promotion）
import services.db.models.deployment     # noqa: E402, F401 — 部署链路表（slot/model_version/switch_event/scheduler_task）
import services.db.models.registry       # noqa: E402, F401 — 静态配置镜像表（B' 类：search_space/feature_recipe/production_workflow_registry）
# @AI_GENERATED: end

# ---------------------------------------------------------------------------
# Alembic Config 对象，提供对 .ini 文件中值的访问
# ---------------------------------------------------------------------------
alembic_config = context.config

# 配置日志（使用 alembic.ini 中 [loggers] 节配置）
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# ---------------------------------------------------------------------------
# ORM 元数据 — 包含 load_forecast 下的 8 张表，供 Alembic autogenerate 使用
# ---------------------------------------------------------------------------
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# include_name：只追踪目标 schema，过滤 mysql/performance_schema/sys/information_schema 等系统库
# ---------------------------------------------------------------------------
_TARGET_SCHEMAS = {"aip_algo_platform"}


def _include_name(name, type_, parent_names):
    """autogenerate 过滤器 — 只追踪 aip_algo_platform 库的表/索引。"""
    if type_ == "schema":
        return name in _TARGET_SCHEMAS or name is None
    return True


# ---------------------------------------------------------------------------
# 注入真实连接串（覆盖 alembic.ini 中的占位符）
# 优先使用调用方（DBAdapter）已注入的值；若未注入则从 DBConfig 读取
#
# @AI_GENERATED: configparser BasicInterpolation 会把 URL-encoded 字符（如密码里的
# `%40` = `@`）当作 %(...)s 变量占位符前缀，抛 invalid interpolation syntax。
# 这里把 `%` 转义为 `%%`（configparser 会在读取时自动还原）。
def _escape_percent_for_configparser(value: str) -> str:
    return value.replace("%", "%%")
# @AI_GENERATED: end

_current_url = alembic_config.get_main_option("sqlalchemy.url", default="")
if not _current_url or _current_url.startswith("driver://"):
    _db_config = DBConfig()
    alembic_config.set_main_option(
        "sqlalchemy.url",
        _escape_percent_for_configparser(_db_config.connection_url),
    )


# ---------------------------------------------------------------------------
# offline 模式：生成 SQL 脚本，不实际连接数据库
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """offline 模式迁移 — 将 SQL DDL 输出到 stdout，不建立真实连接。"""
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=_include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# online 模式：连接数据库并直接执行 DDL
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    """online 模式迁移 — 建立真实连接后执行迁移脚本。"""
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # 迁移只需一次性连接，不保留连接池
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=_include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
