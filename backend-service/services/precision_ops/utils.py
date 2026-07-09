"""
precision_ops/utils.py — 精度运营公共工具函数

提供：
  - BASE_DATA_DIR   : 数据根目录（相对于本文件位置动态计算）
  - _atomic_write_json : 原子写 JSON（先写临时文件后 os.replace）
  - load_json_safe     : 安全读取 JSON，失败返回 default
  - ensure_data_dir    : 确保 data/precision_ops/{slot}/ 目录存在
  - generate_event_id  : 生成唯一事件 ID，格式 {prefix}-{date}-{short_hash}
  - now_iso            : 当前时间 ISO 8601 字符串（带时区）
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
# 本文件位于 backend-service/services/precision_ops/utils.py
# 向上两级到 backend-service/，再拼上 data/precision_ops/
_THIS_DIR = Path(__file__).resolve().parent            # .../services/precision_ops/
_BACKEND_DIR = _THIS_DIR.parent.parent                 # .../backend-service/
BASE_DATA_DIR: Path = _BACKEND_DIR / "data" / "precision_ops"
"""
BASE_DATA_DIR — 精度运营数据根目录

指向 backend-service/data/precision_ops/，
所有槽位（slot）数据均存于此目录的子目录中。
该路径由 utils.py 所在位置动态计算，不硬编码绝对路径。
"""


# ---------------------------------------------------------------------------
# 公共工具函数
# ---------------------------------------------------------------------------

def _atomic_write_json(path: os.PathLike | str, data: Any) -> None:
    """
    原子写入 JSON 文件。

    先将序列化内容写入同目录下的临时文件，再通过 os.replace()
    原子替换目标文件，确保并发读取方不会观察到部分写入状态。

    :param path: 目标文件路径（字符串或 Path）
    :param data: 可 JSON 序列化的 Python 对象
    :raises OSError: 磁盘写入或替换失败时抛出
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 在同一文件系统上创建临时文件，保证 os.replace 是原子操作
    dir_str = str(path.parent)
    fd, tmp_path = tempfile.mkstemp(dir=dir_str, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # 写入失败时清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_json_safe(
    path: os.PathLike | str,
    default: Optional[Any] = None,
) -> Any:
    """
    安全读取 JSON 文件。

    读取或解析失败时返回 default 而不抛出异常，并记录 warning。

    :param path: JSON 文件路径
    :param default: 读取失败时的回退值，默认 None
    :return: 解析后的 Python 对象，或 default
    """
    path = Path(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("load_json_safe: 无法读取 %s: %s", path, exc)
        return default


def ensure_data_dir(slot: str) -> Path:
    """
    确保槽位数据目录存在。

    创建 BASE_DATA_DIR/{slot}/ 目录（含所有中间目录），并返回该路径。

    :param slot: 槽位名称（分区键），如 "default"
    :return: 槽位数据目录的 Path 对象
    """
    slot_dir = BASE_DATA_DIR / slot
    slot_dir.mkdir(parents=True, exist_ok=True)
    return slot_dir


def generate_event_id(prefix: str = "sw-evt") -> str:
    """
    生成格式为 ``{prefix}-{date}-{short_hash}`` 的唯一事件 ID。

    - ``date`` 格式为 ``YYYYMMDD``（UTC）
    - ``short_hash`` 为基于当前时间（纳秒）的 8 位十六进制字符串，
      保证同毫秒内多次调用不冲突

    示例：``sw-evt-20260608-a3f91c4b``

    :param prefix: ID 前缀，默认 "sw-evt"
    :return: 唯一事件 ID 字符串
    """
    now_utc = datetime.now(tz=timezone.utc)
    date_str = now_utc.strftime("%Y%m%d")
    # 加入纳秒级时间戳确保唯一性
    raw = f"{time.time_ns()}-{os.getpid()}"
    short_hash = hashlib.sha1(raw.encode()).hexdigest()[:8]
    return f"{prefix}-{date_str}-{short_hash}"


def now_iso() -> str:
    """
    返回当前时间的 ISO 8601 字符串（含 UTC 时区偏移）。

    示例：``"2026-06-08T10:30:00+00:00"``

    :return: 带时区信息的 ISO 8601 字符串
    """
    return datetime.now(tz=timezone.utc).isoformat()
