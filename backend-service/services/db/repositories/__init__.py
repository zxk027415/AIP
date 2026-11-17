# -*- coding: utf-8 -*-
"""services/db/repositories — 数据仓库包

# @AI_GENERATED
本包提供 CRUD Repository 集合和「惰性单例 + 双写开关」基础设施：

  - 惰性构造 DBAdapter，避免每次调用都重新初始化连接池
  - 环境变量 `AUTORESEARCH_DB_DUAL_WRITE` 控制双写全局开关
      * 1 (默认): 开启双写，业务代码同时写 JSON 和 DB
      * 0        : 关闭双写，业务代码只写 JSON，方便测试/降级
  - 获取失败静默返回 None，让业务代码 try/except 后降级 warning，不阻塞主流程

外部使用示例：
    from services.db.repositories import get_autoresearch_repo, is_dual_write_enabled
    if is_dual_write_enabled():
        repo = get_autoresearch_repo()
        if repo is not None:
            try:
                repo.upsert_run({...})
            except Exception as exc:
                logger.warning("dual write to experiment_run failed: %s", exc)

关联文档：docs/specs/autoresearch-mysql-migration/plan.md Phase 1
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 惰性单例状态
# ---------------------------------------------------------------------------
_lock = threading.RLock()  # RLock: 允许同线程多次获取，避免 get_repo → _get_adapter 内层死锁
_shared_adapter = None                # type: Optional["DBAdapter"]
_autoresearch_repo = None             # type: Optional["AutoResearchRepository"]
_deployment_repo = None               # type: Optional["DeploymentRepository"]
_registry_sync_repo = None            # type: Optional["RegistrySyncRepository"]

# 记录初始化失败：一旦失败，后续调用直接返回 None，避免反复报错拖慢主流程
_init_failed = False


def is_dual_write_enabled() -> bool:
    """全局双写开关。默认 1（开启），设置为 0 关闭双写。

    典型场景：
      - 测试环境：AUTORESEARCH_DB_DUAL_WRITE=0 只写 JSON，避免污染真实 DB
      - 数据库故障：临时置 0 让服务不受影响
      - Phase 3 完成后：改用 DB_ONLY 模式，本变量废弃
    """
    value = os.getenv("AUTORESEARCH_DB_DUAL_WRITE", "1").strip().lower()
    return value in ("1", "true", "yes", "on")


def is_db_read_enabled() -> bool:
    """全局读切换开关（Phase 2）。默认 0（关闭），业务代码读 JSON（现状）。

    设为 1 时，改造过的 load()/list() 方法会「DB 优先，miss/异常兜底 JSON」。

    分阶段策略：
      - Phase 1（双写观察期）：保持 0，只写不读 DB，验证双写数据是否正确
      - Phase 2（读切换）：确认 DB 数据无误后置 1，读走 DB
      - Phase 3（停 JSON 写）：DB 成为唯一源，本变量废弃
    """
    value = os.getenv("AUTORESEARCH_DB_READ", "0").strip().lower()
    return value in ("1", "true", "yes", "on")


class _LightweightAdapter:
    """轻量 DBAdapter 替代：只提供 `get_sync_session()` 接口。

    动机：完整 DBAdapter.__init__ 会走 subprocess 跑 alembic upgrade head，
    在 Windows 上有权限拒绝/子进程卡住/编码错误等一堆坑。Repository 层实际上
    只用 `adapter.get_sync_session()`，其他方法不需要。所以双写路径用这个轻量
    版：直接建 sync engine + session factory，绕开 alembic subprocess。

    Schema 迁移由 `scripts/gen_autoresearch_migration.py` 显式执行，不在启动时做。
    """

    def __init__(self, connection_url: str) -> None:
        from contextlib import contextmanager
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        self._engine = create_engine(
            connection_url,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)
        self._contextmanager = contextmanager

    def get_sync_session(self):
        """按 DBAdapter 的接口约定返回一个 context manager。"""
        @self._contextmanager
        def _wrapper():
            session = self._session_factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        return _wrapper()


def _get_adapter():
    """惰性构造共享轻量 adapter。失败时返回 None（缓存失败标记，不反复重试）。"""
    global _shared_adapter, _init_failed
    if _init_failed:
        return None
    if _shared_adapter is not None:
        return _shared_adapter
    with _lock:
        if _shared_adapter is not None:
            return _shared_adapter
        if _init_failed:
            return None
        try:
            from ..config import DBConfig
            cfg = DBConfig()
            _shared_adapter = _LightweightAdapter(cfg.connection_url)
            return _shared_adapter
        except Exception as exc:
            logger.warning(
                "db.repositories: adapter init failed, dual-write disabled: %s", exc
            )
            _init_failed = True
            return None


def get_autoresearch_repo():
    """获取 AutoResearchRepository 单例。初始化失败返回 None。"""
    global _autoresearch_repo
    if _autoresearch_repo is not None:
        return _autoresearch_repo
    with _lock:
        if _autoresearch_repo is not None:
            return _autoresearch_repo
        adapter = _get_adapter()
        if adapter is None:
            return None
        try:
            from .autoresearch import AutoResearchRepository
            _autoresearch_repo = AutoResearchRepository(adapter)
            return _autoresearch_repo
        except Exception as exc:
            logger.warning("db.repositories: AutoResearchRepository init failed: %s", exc)
            return None


def get_deployment_repo():
    """获取 DeploymentRepository 单例。初始化失败返回 None。"""
    global _deployment_repo
    if _deployment_repo is not None:
        return _deployment_repo
    with _lock:
        if _deployment_repo is not None:
            return _deployment_repo
        adapter = _get_adapter()
        if adapter is None:
            return None
        try:
            from .deployment import DeploymentRepository
            _deployment_repo = DeploymentRepository(adapter)
            return _deployment_repo
        except Exception as exc:
            logger.warning("db.repositories: DeploymentRepository init failed: %s", exc)
            return None


def get_registry_sync_repo():
    """获取 RegistrySyncRepository 单例。初始化失败返回 None。"""
    global _registry_sync_repo
    if _registry_sync_repo is not None:
        return _registry_sync_repo
    with _lock:
        if _registry_sync_repo is not None:
            return _registry_sync_repo
        adapter = _get_adapter()
        if adapter is None:
            return None
        try:
            from .registry_sync import RegistrySyncRepository
            _registry_sync_repo = RegistrySyncRepository(adapter)
            return _registry_sync_repo
        except Exception as exc:
            logger.warning("db.repositories: RegistrySyncRepository init failed: %s", exc)
            return None


def reset_shared_state() -> None:
    """重置所有单例状态（仅用于测试）。生产代码不应调用。"""
    global _shared_adapter, _autoresearch_repo, _deployment_repo, _registry_sync_repo, _init_failed
    with _lock:
        _shared_adapter = None
        _autoresearch_repo = None
        _deployment_repo = None
        _registry_sync_repo = None
        _init_failed = False

# @AI_GENERATED: end
