# -*- coding: utf-8 -*-
"""
precision_ops/_db_helper.py — DB 双写辅助（precision_ops 内部使用）

提供两个函数供 4 个 precision_ops 模块共享：
  - _is_db_enabled()  : 动态读取 DB_ENABLED，支持运行时切换
  - _get_lf_repo()    : 懒加载 LoadForecastRepository，DB 未启用或连接失败时返回 None

设计约束：
  - DB_ENABLED=false 时不导入任何 DB 模块，零副作用
  - 初始化失败后不重试（避免每次写入都触发重连延迟）
  - 所有函数只在 background thread 中被调用，不阻塞主写入路径
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_lf_repo_lock = threading.Lock()
_lf_repo = None          # type: ignore
_lf_repo_init_attempted = False


def _is_db_enabled() -> bool:
    """
    动态读取 DB_ENABLED（每次调用重新检查，支持运行时切换）。

    优先级：环境变量 > configs/db.yaml > 代码默认值（True）。
    任何异常均视为 False。
    """
    env_val = os.environ.get("DB_ENABLED")
    if env_val is not None:
        return str(env_val).strip().lower() in ("1", "true", "yes", "on")
    # 无环境变量时，读 DBConfig（会读 db.yaml）
    try:
        from services.db.config import DBConfig
        return DBConfig().db_enabled
    except Exception:
        return False


def set_lf_repo(repo) -> None:
    """
    由 main.py startup_event 调用，注入已初始化的 LoadForecastRepository。
    避免 _db_helper 自己创建第二个 DBAdapter 实例。
    """
    global _lf_repo, _lf_repo_init_attempted
    with _lf_repo_lock:
        _lf_repo = repo
        _lf_repo_init_attempted = True  # 防止后续懒加载覆盖注入的实例


def _get_lf_repo():
    """
    懒加载 LoadForecastRepository。

    - DB_ENABLED=false：立即返回 None，不触发任何 DB 连接
    - 初始化失败（MySQL 不可达）：记录 WARNING，返回 None，后续不重试
    - 初始化成功：缓存 repo 实例，后续直接返回

    Returns:
        LoadForecastRepository 实例，或 None（DB 未启用 / 初始化失败）
    """
    global _lf_repo, _lf_repo_init_attempted

    # 显式注入优先：set_lf_repo 已被调用时直接返回注入的实例（无视 DB_ENABLED）
    if _lf_repo_init_attempted:
        return _lf_repo

    if not _is_db_enabled():
        return None

    with _lf_repo_lock:
        if not _lf_repo_init_attempted:
            _lf_repo_init_attempted = True
            try:
                from services.db.adapter import DBAdapter
                from services.db.config import DBConfig
                from services.db.repositories.load_forecast import LoadForecastRepository

                _lf_repo = LoadForecastRepository(DBAdapter(DBConfig()))
                logger.info("precision_ops DB 双写：LoadForecastRepository 初始化成功。")
            except Exception as exc:
                logger.warning(
                    "precision_ops DB 双写：DB adapter 初始化失败，DB 写入不可用: %s",
                    exc,
                )
                _lf_repo = None

    return _lf_repo


def _parse_iso(s: Optional[str]):
    """
    ISO 8601 字符串 → datetime 对象，供 ORM 字段使用。

    转换失败时返回 None，不抛出异常。
    """
    if s is None:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
