# -*- coding: utf-8 -*-
"""
services/db/adapter.py — DBAdapter 数据库适配器

DBAdapter: 管理 SQLAlchemy 连接池（同步 pymysql + 异步 aiomysql），提供健康检查、
指数退避重试、Session 工厂和生命周期管理。

用法示例：
    from services.db.config import DBConfig
    from services.db.adapter import DBAdapter

    cfg = DBConfig()
    adapter = DBAdapter(cfg)          # 初始化：建连接池、验证连接、执行迁移
    ok = adapter.health_check()       # 健康检查

    with adapter.get_sync_session() as session:
        session.execute(text("SELECT 1"))

    async with adapter.get_async_session() as session:
        await session.execute(text("SELECT 1"))

    adapter.dispose()                 # 关闭引擎和连接池

Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.9
"""

from __future__ import annotations

import logging
import subprocess
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.orm import Session, sessionmaker

from .config import DBConfig
from .exceptions import ConnectionExhaustedError, DBAdapterError, MigrationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 重试常量（固定，不可通过配置修改）
# ---------------------------------------------------------------------------
_RETRY_ATTEMPTS: int = 3      # 初始尝试之后最多重试 3 次（共 4 次尝试）
_RETRY_BASE_DELAY: float = 1.0  # 首次重试等待（秒）
_RETRY_MULTIPLIER: float = 2.0  # 退避乘数：1s → 2s → 4s
_RETRY_MAX_DELAY: float = 8.0   # 单次最大等待（秒）


class DBAdapter:
    """
    数据库适配器 — 管理连接池、引擎初始化、健康检查和 schema 迁移。

    同步模式使用 SQLAlchemy + pymysql；异步模式使用 sqlalchemy[asyncio] + aiomysql
    （若 aiomysql 未安装则跳过异步引擎初始化，仅同步功能可用）。

    初始化流程：
      1. 创建同步引擎（pymysql）
      2. 尝试创建异步引擎（aiomysql，可选）
      3. 验证同步连接（含指数退避重试）
      4. 执行 run_migrations()（当前为 stub，task 1.3 实现）
    """

    def __init__(self, config: DBConfig) -> None:
        self._config = config

        # --- 同步引擎（pymysql）---
        sync_url = self._ensure_sync_url(config.connection_url)
        self._sync_engine = create_engine(
            sync_url,
            pool_size=config.max_connections,
            pool_recycle=config.connection_lifetime,
            pool_timeout=config.pool_wait_timeout,
            pool_pre_ping=True,
        )
        self._sync_session_factory = sessionmaker(
            self._sync_engine,
            expire_on_commit=False,
        )

        # --- 异步引擎（aiomysql，可选）---
        self._async_engine: Optional[object] = None
        self._async_session_factory: Optional[object] = None
        self._init_async_engine(config, sync_url)

        # --- 验证连接（含指数退避重试）---
        self._connect_with_retry()

        # --- Schema 迁移（stub，task 1.3 实现）---
        self.run_migrations()

    # ------------------------------------------------------------------
    # 内部初始化方法
    # ------------------------------------------------------------------

    def _ensure_sync_url(self, url: str) -> str:
        """确保连接 URL 使用 pymysql 驱动前缀。"""
        if "mysql+aiomysql" in url:
            return url.replace("mysql+aiomysql", "mysql+pymysql")
        # mysql:// 无驱动后缀时补全
        if url.startswith("mysql://"):
            return "mysql+pymysql://" + url[len("mysql://"):]
        return url

    def _to_async_url(self, sync_url: str) -> str:
        """将 pymysql URL 转换为 aiomysql URL。"""
        return sync_url.replace("mysql+pymysql", "mysql+aiomysql")

    def _init_async_engine(self, config: DBConfig, sync_url: str) -> None:
        """
        尝试初始化异步引擎。

        aiomysql 未安装时记录警告并跳过，不抛出异常。
        """
        try:
            import aiomysql  # noqa: F401 — 仅用于存在性检测

            from sqlalchemy.ext.asyncio import (
                AsyncSession,
                async_sessionmaker,
                create_async_engine,
            )

            async_url = self._to_async_url(sync_url)
            self._async_engine = create_async_engine(
                async_url,
                pool_size=config.max_connections,
                pool_recycle=config.connection_lifetime,
                pool_timeout=config.pool_wait_timeout,
                pool_pre_ping=True,
            )
            self._async_session_factory = async_sessionmaker(
                self._async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            logger.debug("异步引擎（aiomysql）已初始化。")
        except ImportError:
            logger.warning(
                "aiomysql 未安装，异步引擎不可用。"
                "如需异步支持，请安装：pip install aiomysql"
            )

    def _connect_with_retry(self) -> None:
        """
        验证数据库连接，失败时指数退避重试。

        重试策略：
          - 初始尝试 + 最多 3 次重试，共 4 次尝试
          - 重试间隔：1s → 2s → 4s（上限 8s）
          - 全部失败后抛出 DBAdapterError

        Requirements: 1.4
        """
        delay = _RETRY_BASE_DELAY
        last_exc: Optional[Exception] = None

        for attempt in range(_RETRY_ATTEMPTS + 1):  # 0=初始, 1–3=重试
            try:
                with self._sync_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.debug("数据库连接验证通过（第 %d 次尝试）。", attempt + 1)
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < _RETRY_ATTEMPTS:
                    wait = min(delay, _RETRY_MAX_DELAY)
                    logger.warning(
                        "数据库连接失败（第 %d/%d 次），%.1f 秒后重试：%s",
                        attempt + 1,
                        _RETRY_ATTEMPTS + 1,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
                    delay = min(delay * _RETRY_MULTIPLIER, _RETRY_MAX_DELAY)

        raise DBAdapterError(
            f"数据库连接失败，已重试 {_RETRY_ATTEMPTS} 次：{last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """
        执行 SELECT 1 验证数据库可达性（一次性检查，不重试）。

        Returns:
            True  — 数据库正常响应。
            False — 连接失败或查询异常。

        Requirements: 1.7
        """
        try:
            with self._sync_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("health_check 失败：%s", exc)
            return False

    @contextmanager
    def get_sync_session(self) -> Generator[Session, None, None]:
        """
        同步 Session 工厂（contextmanager）。

        自动 commit（成功）/ rollback（异常）/ close。

        用法：
            with adapter.get_sync_session() as session:
                session.add(obj)

        Raises:
            ConnectionExhaustedError: 连接池耗尽，等待超时。

        Requirements: 1.6
        """
        try:
            session: Session = self._sync_session_factory()
        except SATimeoutError as exc:
            raise ConnectionExhaustedError(
                f"同步连接池耗尽，等待超时（{self._config.pool_wait_timeout}s）"
            ) from exc

        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def get_async_session(self):
        """
        异步 AsyncSession 工厂（async contextmanager）。

        需要 aiomysql 已安装；未安装时抛出 DBAdapterError。

        用法：
            async with adapter.get_async_session() as session:
                await session.execute(text("SELECT 1"))

        Raises:
            DBAdapterError: aiomysql 未安装，异步引擎不可用。
            ConnectionExhaustedError: 异步连接池耗尽，等待超时。

        Requirements: 1.6
        """
        if self._async_engine is None or self._async_session_factory is None:
            raise DBAdapterError(
                "异步引擎不可用：aiomysql 未安装。"
                "请先安装：pip install aiomysql"
            )

        try:
            session = self._async_session_factory()
        except SATimeoutError as exc:
            raise ConnectionExhaustedError(
                f"异步连接池耗尽，等待超时（{self._config.pool_wait_timeout}s）"
            ) from exc

        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    def run_migrations(self) -> None:
        """
        执行 Alembic schema 迁移（alembic upgrade head）。

        成功时静默返回；失败时抛出 MigrationError。

        Requirements: 1.7, 1.8
        """
        # alembic.ini 位于 backend-service/ 目录（本文件向上三级）
        _backend_dir = Path(__file__).resolve().parent.parent.parent

        # @AI_GENERATED: 支持环境变量跳过 alembic 迁移（DB 已经在 head 时避免 subprocess 卡住）
        import os as _os
        if _os.getenv("AIP_SKIP_ALEMBIC_MIGRATION", "").strip().lower() in ("1", "true", "yes"):
            logger.info(
                "Alembic 迁移跳过（AIP_SKIP_ALEMBIC_MIGRATION=1）。"
                "请手动确保 DB schema 已是最新（`python scripts/gen_autoresearch_migration.py --upgrade`）。"
            )
            return
        # @AI_GENERATED: end

        try:
            # @AI_GENERATED: 加 60 秒超时，避免子进程卡住父进程；超时视为非致命
            result = subprocess.run(
                ["alembic", "upgrade", "head"],
                cwd=str(_backend_dir),
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            # @AI_GENERATED: end
            logger.debug("Alembic 迁移完成：%s", result.stdout.strip())
        except subprocess.CalledProcessError as exc:
            revision = "head"
            logger.error("Alembic 迁移失败（revision=%s）：%s", revision, exc.stderr)
            raise MigrationError(revision, exc) from exc
        except FileNotFoundError as exc:
            raise MigrationError("head", exc) from exc
        except PermissionError as exc:
            # Windows 环境下 subprocess.run 可能因安全策略被拒绝（WinError 5）
            # Schema 通常已是最新，跳过迁移继续启动；记录警告而不中断服务
            logger.warning(
                "Alembic 迁移跳过（Windows 权限拒绝，subprocess 无法创建子进程）："
                " %s。如需手动迁移，请在终端执行 `alembic upgrade head`。",
                exc,
            )
        # @AI_GENERATED: 超时兜底 — alembic 卡住时 warning 跳过，让业务代码继续
        except subprocess.TimeoutExpired as exc:
            logger.warning(
                "Alembic 迁移子进程超时（>60s），跳过并继续启动。"
                "如需手动确认，请运行 `python scripts/gen_autoresearch_migration.py --current`。异常：%s",
                exc,
            )
        # @AI_GENERATED: end

    def dispose(self) -> None:
        """
        关闭所有数据库引擎和连接池。

        应在应用关闭时（FastAPI shutdown 事件）调用。
        同步引擎和异步引擎均会被 dispose。

        Requirements: 1.1
        """
        try:
            self._sync_engine.dispose()
            logger.debug("同步引擎（pymysql）已关闭。")
        except Exception as exc:  # noqa: BLE001
            logger.warning("关闭同步引擎时出错：%s", exc)

        if self._async_engine is not None:
            try:
                # SQLAlchemy 2.0 中 AsyncEngine.dispose() 是同步方法
                self._async_engine.dispose()
                logger.debug("异步引擎（aiomysql）已关闭。")
            except Exception as exc:  # noqa: BLE001
                logger.warning("关闭异步引擎时出错：%s", exc)
