# @AI_GENERATED
"""
services/db/datasources/pv_mock_feeder.py — 光伏故障诊断 Mock 喂数据器

职责：
  模拟公司数据库每天按自然日向平台推送光伏观测数据。
  从 dataset_combined.parquet 按自然日分批，每次触发时：
    1. 取下一个自然日的所有行（site_id/device_id/branch_id/time/value/i_cal）
    2. 将 label 列**清空（NULL）**，模拟未来无标签到达的新观测
    3. INSERT IGNORE 写入 training_samples 表

调用方式：
  - 由 main.py 注册 "pv_mock_data_feed" cron 任务，直写 training_samples
  - 也可以通过调度 API 手动触发

路径约定：
  - parquet 文件路径相对于项目根目录
  - 游标状态持久化到 backend-service/data/pv_scheduler/mock_feed_cursor.json
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_BACKEND_SERVICE_DIR = Path(__file__).resolve().parents[3]
_PROJECT_ROOT = _BACKEND_SERVICE_DIR.parent

_DEFAULT_PARQUET_PATH = "backend-service/datasets/dataset_combined.parquet"
_CURSOR_PATH = _BACKEND_SERVICE_DIR / "data" / "pv_scheduler" / "mock_feed_cursor.json"


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        Path(tmp).replace(path)
    except Exception:
        try:
            Path(tmp).unlink(missing_ok=True)
        except OSError:
            pass
        raise


class PVMockFeeder:
    """按自然日从 parquet 向 training_samples 表喂入无标签光伏观测。

    每次调用 feed_next_day() 时：
    - 查找游标指向日期的下一个自然日
    - 取出该日所有行，label 清空为 NULL
    - INSERT IGNORE 写入 training_samples
    - 推进游标

    游标文件格式：
    {
        "last_fed_date": "2020-05-06",
        "last_fed_at": "2026-07-15T08:00:00",
        "total_rows_fed": 1234
    }
    """

    def __init__(
        self,
        pv_repo,
        parquet_path: str = _DEFAULT_PARQUET_PATH,
        cursor_path: Optional[Path] = None,
    ) -> None:
        self._pv_repo = pv_repo
        self._parquet_path = _PROJECT_ROOT / parquet_path
        self._cursor_path = cursor_path or _CURSOR_PATH
        self._df: Optional[pd.DataFrame] = None  # 惰性加载

    def _load_df(self) -> pd.DataFrame:
        if self._df is None:
            if not self._parquet_path.exists():
                raise FileNotFoundError(
                    f"光伏 mock 数据文件不存在: {self._parquet_path}"
                )
            df = pd.read_parquet(self._parquet_path)
            df["time"] = pd.to_datetime(df["time"])
            if df["time"].dt.tz is not None:
                df["time"] = df["time"].dt.tz_convert("UTC").dt.tz_localize(None)
            df = df.sort_values("time").reset_index(drop=True)
            self._df = df
            logger.info(
                "PVMockFeeder: 加载 parquet 完成，共 %d 行，日期范围 %s ~ %s",
                len(df),
                df["time"].min().date(),
                df["time"].max().date(),
            )
        return self._df

    def _load_cursor(self) -> Optional[date]:
        """读取游标：上次已喂入的最后日期。"""
        if not self._cursor_path.exists():
            return None
        try:
            payload = json.loads(self._cursor_path.read_text(encoding="utf-8"))
            raw = payload.get("last_fed_date")
            return date.fromisoformat(raw) if raw else None
        except Exception as exc:
            logger.warning("PVMockFeeder: 游标读取失败，将从头开始: %s", exc)
            return None

    def _save_cursor(self, fed_date: date, rows_fed: int, total: int) -> None:
        _atomic_write_json(
            self._cursor_path,
            {
                "last_fed_date": fed_date.isoformat(),
                "last_fed_at": datetime.utcnow().isoformat(),
                "rows_fed_this_batch": rows_fed,
                "total_rows_fed": total,
            },
        )

    def get_status(self) -> Dict[str, Any]:
        """返回当前喂数据进度，供前端调度面板展示。"""
        try:
            df = self._load_df()
            all_dates = sorted(df["time"].dt.date.unique())
        except Exception as exc:
            return {"error": str(exc)}

        last_fed = self._load_cursor()
        if last_fed is None:
            next_date = all_dates[0] if all_dates else None
            fed_dates = 0
        else:
            future = [d for d in all_dates if d > last_fed]
            next_date = future[0] if future else None
            fed_dates = sum(1 for d in all_dates if d <= last_fed)

        return {
            "total_dates": len(all_dates),
            "fed_dates": fed_dates,
            "last_fed_date": last_fed.isoformat() if last_fed else None,
            "next_date": next_date.isoformat() if next_date else None,
            "exhausted": next_date is None,
            "parquet_path": str(self._parquet_path.relative_to(_PROJECT_ROOT)),
        }

    def feed_next_day(self) -> Dict[str, Any]:
        """喂入下一个自然日的数据（label 清空为 NULL）。

        返回 {date, inserted, skipped, exhausted, total_rows_in_day}。
        """
        df = self._load_df()
        all_dates = sorted(df["time"].dt.date.unique())
        if not all_dates:
            return {"exhausted": True, "date": None, "inserted": 0, "skipped": 0}

        last_fed = self._load_cursor()
        if last_fed is None:
            target_date = all_dates[0]
        else:
            future = [d for d in all_dates if d > last_fed]
            if not future:
                logger.info("PVMockFeeder: 所有数据已喂完（%d 天）", len(all_dates))
                return {
                    "exhausted": True,
                    "date": last_fed.isoformat(),
                    "inserted": 0,
                    "skipped": 0,
                }
            target_date = future[0]

        day_df = df[df["time"].dt.date == target_date].copy()
        total_rows = len(day_df)

        # 关键：清空 label — 模拟未来到达的无标签观测
        day_df["label"] = None

        # 确保列齐全
        for col in ("value", "i_cal"):
            if col not in day_df.columns:
                day_df[col] = 0.0

        # 写入 training_samples（INSERT IGNORE 去重）
        fd, tmp_path = tempfile.mkstemp(suffix=".parquet")
        os.close(fd)
        try:
            day_df[["time", "site_id", "device_id", "branch_id", "value", "i_cal", "label"]].to_parquet(
                tmp_path, index=False
            )
            result = self._pv_repo.ingest_parquet(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        inserted = result["inserted"]
        skipped = result["skipped"]

        # 读取游标中旧 total
        old_total = 0
        if self._cursor_path.exists():
            try:
                old_total = json.loads(self._cursor_path.read_text(encoding="utf-8")).get("total_rows_fed", 0)
            except Exception:
                pass

        self._save_cursor(target_date, inserted, old_total + inserted)

        logger.info(
            "PVMockFeeder: 喂入 %s — total=%d inserted=%d skipped=%d",
            target_date,
            total_rows,
            inserted,
            skipped,
        )
        return {
            "exhausted": False,
            "date": target_date.isoformat(),
            "total_rows_in_day": total_rows,
            "inserted": inserted,
            "skipped": skipped,
        }

    def reset_cursor(self) -> None:
        """重置游标，下次将从第一天重新开始喂数据（用于测试）。"""
        if self._cursor_path.exists():
            self._cursor_path.unlink()
        logger.info("PVMockFeeder: 游标已重置")
# @AI_GENERATED: end
