# -*- coding: utf-8 -*-
"""
services/db/dual_write.py — 过渡期双写代理

DualWriteProxy: 根据 DB_ENABLED / DB_DUAL_WRITE 配置，
在 DB 和文件两种存储之间透明路由读写操作。

写入行为：
  - DB_ENABLED=false              → 只走 file_write_fn，透明降级
  - DB_ENABLED=true, DUAL=true   → db 先写，再写 file；任一失败只 log WARNING，不回滚
  - DB_ENABLED=true, DUAL=false  → 只走 db_write_fn

读取行为：
  - DB_ENABLED=false              → 只走 file_read_fn
  - DB_ENABLED=true               → 优先 db_read_fn；5s 内连接失败（OperationalError /
                                     DBAdapterError）降级到 file_read_fn；
                                     两者都不可用则抛 RuntimeError

配置动态更新：每次调用时重读 DB_ENABLED / DB_DUAL_WRITE 环境变量，无需重启进程。

Requirements: 7.1, 7.2, 7.3
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, TypeVar

from sqlalchemy.exc import OperationalError

from .config import DBConfig
from .exceptions import DBAdapterError

logger = logging.getLogger(__name__)

_DB_READ_TIMEOUT: float = 5.0  # seconds
T = TypeVar("T")


def _fallback_to_file(target: str, file_read_fn: Callable) -> object:
    """DB 读取不可用时回退到文件读取；两者都失败则抛 RuntimeError。"""
    try:
        return file_read_fn()
    except Exception as file_exc:  # noqa: BLE001
        raise RuntimeError(
            f"[DualWriteProxy] {target}: DB read (connection failure) "
            "and file read both unavailable"
        ) from file_exc


def _read_bool_env(key: str) -> bool | None:
    """从环境变量读取布尔值；未设置时返回 None。"""
    raw = os.environ.get(key)
    if raw is None:
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


class DualWriteProxy:
    """过渡期双写代理，根据配置透明路由读写操作。"""

    def __init__(self, config: DBConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # 内部配置读取（每次调用重读环境变量，支持动态更新）
    # ------------------------------------------------------------------

    def _db_enabled(self) -> bool:
        val = _read_bool_env("DB_ENABLED")
        return val if val is not None else self._config.db_enabled

    def _dual_write(self) -> bool:
        val = _read_bool_env("DB_DUAL_WRITE")
        return val if val is not None else self._config.dual_write

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def write(self, target: str, db_write_fn: Callable, file_write_fn: Callable) -> None:
        """
        根据配置路由写入操作。

        target — 操作描述，用于日志。
        """
        if not self._db_enabled():
            file_write_fn()
            return

        if self._dual_write():
            # 先写 DB，再写 file；任一失败只 log WARNING，不回滚另一侧
            try:
                db_write_fn()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[DualWriteProxy] %s: DB write failed: %s", target, exc)
            try:
                file_write_fn()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[DualWriteProxy] %s: file write failed: %s", target, exc)
        else:
            db_write_fn()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def read(self, target: str, db_read_fn: Callable[[], T], file_read_fn: Callable[[], T]) -> T:
        """
        根据配置路由读取操作。

        返回 db_read_fn() 或 file_read_fn() 的结果。
        DB_ENABLED=true 时优先走 DB；连接失败（OperationalError / DBAdapterError）
        或超过 5s 未响应，则降级到 file_read_fn()。
        两者都不可用时抛 RuntimeError。
        """
        if not self._db_enabled():
            return file_read_fn()

        # 优先走 DB，5s 超时 + 连接失败时降级
        result_holder: list = [None]
        exc_holder: list = [None]

        def _run() -> None:
            try:
                result_holder[0] = db_read_fn()
            except Exception as e:  # noqa: BLE001
                exc_holder[0] = e

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=_DB_READ_TIMEOUT)

        if t.is_alive():
            logger.warning(
                "[DualWriteProxy] %s: DB read timed out after %.0fs, falling back to file",
                target,
                _DB_READ_TIMEOUT,
            )
            return _fallback_to_file(target, file_read_fn)

        exc = exc_holder[0]
        if exc is not None:
            if isinstance(exc, (OperationalError, DBAdapterError)):
                logger.warning(
                    "[DualWriteProxy] %s: DB read connection error, falling back to file: %s",
                    target,
                    exc,
                )
                return _fallback_to_file(target, file_read_fn)
            raise exc  # 非连接错误直接传播，不降级

        return result_holder[0]
