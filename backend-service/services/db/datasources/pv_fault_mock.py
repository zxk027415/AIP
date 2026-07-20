# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
services/db/datasources/pv_fault_mock.py — 光伏故障诊断 Mock 喂数据器

与负荷预测的 CsvMockCompanyFeeder 平行设计：
  - 每次 cron 触发只喂一个自然日的数据（以 time 列的 date 为边界）
  - 跨日必须人工确认（requires_advance_confirmation）才能推进
  - 写入时 label = NULL，模拟真实场景下数据库新收到的原始光伏观测
  - 源数据来自 datasets/dataset_combined.parquet（可通过环境变量覆盖）

与负荷预测 feeder 的主要差异：
  - 数据源是 Parquet（多设备多列），而非 CSV（单设备单列）
  - 目标表是 training_samples（多列：site_id/device_id/branch_id/value/i_cal），
    而非 station_observations（单列：value）
  - 每天行数约为 devices × time_points_per_day（可能是数千行），
    expected_points_per_day 用来标记当天是否完整

持久化路径：所有状态通过数据库游标（MAX source_row_index）和目标表推断，
不依赖外部文件，符合项目相对路径规范。
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from services.db.adapter import DBAdapter
from services.db.exceptions import DataSourceError, IngestionError

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PARQUET_PATH = "datasets/dataset_combined.parquet"

# training_samples 表结构（与 PVFaultRepository.ingest_parquet 一致）
_SCHEMA = "aip_algo_platform"
_CURSOR_TABLE = "pv_mock_feed_cursor"


def _project_relative_parquet_path(path: Path) -> str:
    """返回相对于项目根（backend-service 父目录）的 POSIX 路径。"""
    project_root = _BACKEND_ROOT.parent
    try:
        return path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(_BACKEND_ROOT).as_posix()
        except ValueError:
            return path.name


def compute_pv_source_fingerprint(parquet_path: Optional[str] = None) -> Dict[str, Any]:
    """计算当前 mock 数据源指纹（相对路径 + 日期范围 + 行数）。

    换文件或同路径覆盖成另一套日历时，指纹会变化，供预测游标自动重置。
    """
    import hashlib

    raw = parquet_path or os.environ.get("PV_MOCK_PARQUET_PATH", _DEFAULT_PARQUET_PATH)
    resolved = _resolve_path(raw)
    if not resolved.exists():
        raise DataSourceError(f"PV mock 数据文件不存在: {resolved}")

    df = pd.read_parquet(resolved, columns=["time"])
    times = pd.to_datetime(df["time"])
    if getattr(times.dt, "tz", None) is not None:
        times = times.dt.tz_convert("UTC").dt.tz_localize(None)
    if times.empty:
        raise DataSourceError(f"PV mock parquet 无 time 数据: {resolved}")

    date_min = times.min().date().isoformat()
    date_max = times.max().date().isoformat()
    row_count = int(len(times))
    source_path = _project_relative_parquet_path(resolved)
    digest = hashlib.sha256(
        f"{source_path}|{date_min}|{date_max}|{row_count}".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "source_path": source_path,
        "date_min": date_min,
        "date_max": date_max,
        "row_count": row_count,
        "fingerprint": digest,
    }


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return _BACKEND_ROOT / p


# ---------------------------------------------------------------------------
# Result dataclasses（与 CsvMockCompanyFeeder 的 MockFeedResult/Preview 平行）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PvMockFeedResult:
    """喂数据结果：一次 feed 的元数据。"""
    business_date: Optional[date]
    source_row_count: int
    inserted_row_count: int
    skipped_row_count: int
    device_count: int
    exhausted: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "business_date": self.business_date.isoformat() if self.business_date else None,
            "source_row_count": self.source_row_count,
            "inserted_row_count": self.inserted_row_count,
            "skipped_row_count": self.skipped_row_count,
            "device_count": self.device_count,
            "exhausted": self.exhausted,
        }


@dataclass(frozen=True)
class PvMockFeedPreview:
    """人工确认前的只读状态（供调度 UI 展示）。"""
    state: str                          # initial_feed / continue_current / confirmation_required / exhausted
    current_business_date: Optional[date]
    next_business_date: Optional[date]
    next_source_row_count: int
    next_device_count: int
    requires_advance_confirmation: bool
    exhausted: bool
    source_fingerprint: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "current_business_date": (
                self.current_business_date.isoformat() if self.current_business_date else None
            ),
            "next_business_date": (
                self.next_business_date.isoformat() if self.next_business_date else None
            ),
            "next_source_row_count": self.next_source_row_count,
            "next_device_count": self.next_device_count,
            "requires_advance_confirmation": self.requires_advance_confirmation,
            "exhausted": self.exhausted,
            "source_fingerprint": self.source_fingerprint,
        }


# ---------------------------------------------------------------------------
# PvFaultMockFeeder
# ---------------------------------------------------------------------------

class PvFaultMockFeeder:
    """从 Parquet 文件按自然日向 training_samples 表喂光伏观测数据。

    喂数据时 label 列强制设为 NULL，模拟真实场景下数据库新收到的原始观测。
    源数据中的 label 列仅用于验证数据完整性，不会被写入 training_samples。

    跨日推进需要人工确认（requires_advance_confirmation=True），
    与负荷预测 CsvMockCompanyFeeder.feed_manually(advance=True) 语义完全一致。
    """

    def __init__(
        self,
        adapter: DBAdapter,
        parquet_path: str = _DEFAULT_PARQUET_PATH,
    ) -> None:
        self._adapter = adapter
        self._parquet_path = _resolve_path(parquet_path)
        self._df: Optional[pd.DataFrame] = None          # 懒加载，首次 feed 时读取
        self._df_dates: Optional[List[date]] = None      # 所有自然日列表（有序）
        self._feed_lock = threading.RLock()
        self._last_feed_result: Optional[PvMockFeedResult] = None

    @property
    def last_feed_result(self) -> Optional[PvMockFeedResult]:
        return self._last_feed_result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_df(self) -> pd.DataFrame:
        """懒加载 Parquet，转换时间列，按 time 排序。"""
        if self._df is None:
            if not self._parquet_path.exists():
                raise DataSourceError(f"PV mock 数据文件不存在: {self._parquet_path}")
            df = pd.read_parquet(self._parquet_path)
            required = {"time", "site_id", "device_id", "branch_id", "value", "i_cal"}
            missing = required - set(df.columns)
            if missing:
                raise DataSourceError(f"PV mock parquet 缺少列 {sorted(missing)}: {self._parquet_path}")
            df["time"] = pd.to_datetime(df["time"])
            if df["time"].dt.tz is not None:
                df["time"] = df["time"].dt.tz_convert("UTC").dt.tz_localize(None)
            df = df.sort_values("time").reset_index(drop=True)
            df["_date"] = df["time"].dt.date
            self._df = df
            self._df_dates = sorted(df["_date"].unique().tolist())
        return self._df

    def _ensure_cursor_table(self) -> None:
        """创建 pv_mock_feed_cursor 游标表（如不存在）。"""
        with self._adapter.get_sync_session() as session:
            session.execute(text(f"CREATE DATABASE IF NOT EXISTS `{_SCHEMA}` DEFAULT CHARSET utf8mb4"))
            session.execute(text(f"""
                CREATE TABLE IF NOT EXISTS `{_SCHEMA}`.`{_CURSOR_TABLE}` (
                    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
                    business_date   DATE NOT NULL,
                    fed_at          DATETIME NOT NULL,
                    row_count       INT NOT NULL,
                    UNIQUE KEY uq_pv_cursor_date (business_date)
                )
            """))

    def _last_fed_date(self) -> Optional[date]:
        """返回上次成功喂完的最新自然日，没有则返回 None。"""
        self._ensure_cursor_table()
        with self._adapter.get_sync_session() as session:
            result = session.execute(
                text(f"SELECT MAX(business_date) FROM `{_SCHEMA}`.`{_CURSOR_TABLE}`")
            ).scalar()
        return result  # 已是 date 类型或 None

    def _mark_date_fed(self, business_date: date, row_count: int) -> None:
        """记录当日已喂完（幂等 upsert）。"""
        with self._adapter.get_sync_session() as session:
            session.execute(text(f"""
                INSERT INTO `{_SCHEMA}`.`{_CURSOR_TABLE}` (business_date, fed_at, row_count)
                VALUES (:d, :now, :cnt)
                ON DUPLICATE KEY UPDATE fed_at = :now, row_count = :cnt
            """), {"d": business_date, "now": datetime.utcnow(), "cnt": row_count})

    def _rows_for_date(self, business_date: date) -> pd.DataFrame:
        df = self._load_df()
        return df[df["_date"] == business_date].copy()

    def _next_unfed_date(self) -> Optional[date]:
        """返回下一个还没喂过的自然日。"""
        df = self._load_df()
        last = self._last_fed_date()
        for d in self._df_dates:  # type: ignore[union-attr]
            if last is None or d > last:
                return d
        return None  # exhausted

    # ------------------------------------------------------------------
    # Public API（与 CsvMockCompanyFeeder 接口对齐）
    # ------------------------------------------------------------------

    def ensure_tables(self) -> None:
        """确保游标表存在（main.py 启动时调用）。"""
        self._ensure_cursor_table()

    def get_manual_feed_preview(self) -> PvMockFeedPreview:
        """返回下一次喂数据的只读预览，不修改任何状态。"""
        with self._feed_lock:
            return self._build_preview()

    def get_source_fingerprint(self) -> Dict[str, Any]:
        """返回当前 parquet 数据源指纹，供预测游标对齐。"""
        return compute_pv_source_fingerprint(str(self._parquet_path))

    def _build_preview(self) -> PvMockFeedPreview:
        self._load_df()
        last_date = self._last_fed_date()
        next_date = self._next_unfed_date()
        try:
            source_fp = self.get_source_fingerprint()
        except Exception:
            source_fp = None

        if next_date is None:
            return PvMockFeedPreview(
                state="exhausted",
                current_business_date=last_date,
                next_business_date=None,
                next_source_row_count=0,
                next_device_count=0,
                requires_advance_confirmation=False,
                exhausted=True,
                source_fingerprint=source_fp,
            )

        next_rows = self._rows_for_date(next_date)
        next_device_count = int(next_rows["device_id"].nunique())

        if last_date is None:
            state = "initial_feed"
            requires_confirm = False
        else:
            # 跨日需要人工确认
            requires_confirm = True
            state = "confirmation_required"

        return PvMockFeedPreview(
            state=state,
            current_business_date=last_date,
            next_business_date=next_date,
            next_source_row_count=int(len(next_rows)),
            next_device_count=next_device_count,
            requires_advance_confirmation=requires_confirm,
            exhausted=False,
            source_fingerprint=source_fp,
        )

    def feed_manually(self, advance: bool = False) -> Tuple[PvMockFeedPreview, Optional[PvMockFeedResult]]:
        """人工触发：需要 advance=True 才能跨日推进。"""
        with self._feed_lock:
            preview = self._build_preview()
            if preview.exhausted:
                return preview, None
            if preview.requires_advance_confirmation and not advance:
                # 返回 preview 让 UI 显示"需要确认"，不喂数据
                return preview, None
            result = self._feed_date_locked(preview.next_business_date)
            return self._build_preview(), result

    def feed_next_batch(self) -> int:
        """调度 cron 触发：自动喂下一日（首次无需确认，跨日也自动推进）。

        返回插入行数（兼容 SchedulerEngine.register_task 的调用约定）。
        """
        with self._feed_lock:
            next_date = self._next_unfed_date()
            if next_date is None:
                logger.info("pv_mock_feed: source exhausted")
                self._last_feed_result = PvMockFeedResult(
                    business_date=None,
                    source_row_count=0,
                    inserted_row_count=0,
                    skipped_row_count=0,
                    device_count=0,
                    exhausted=True,
                )
                return 0
            result = self._feed_date_locked(next_date)
            return result.inserted_row_count if result else 0

    # ------------------------------------------------------------------
    # Core insert
    # ------------------------------------------------------------------

    def _feed_date_locked(self, business_date: date) -> PvMockFeedResult:
        """把 business_date 当天的所有观测写入 training_samples（label=NULL）。"""
        rows_df = self._rows_for_date(business_date)
        if rows_df.empty:
            self._last_feed_result = PvMockFeedResult(
                business_date=business_date,
                source_row_count=0,
                inserted_row_count=0,
                skipped_row_count=0,
                device_count=0,
                exhausted=False,
            )
            return self._last_feed_result

        # 构造写入字段：label 强制 NULL（模拟无标签的新到观测）
        write_df = rows_df[["time", "site_id", "device_id", "branch_id", "value", "i_cal"]].copy()
        write_df["label"] = None   # 原始观测不带标签

        # 类型归一化
        write_df["time"] = pd.to_datetime(write_df["time"])
        if write_df["time"].dt.tz is not None:
            write_df["time"] = write_df["time"].dt.tz_convert("UTC").dt.tz_localize(None)
        write_df["branch_id"] = write_df["branch_id"].astype(str)
        write_df["label"] = write_df["label"].astype(object)

        # 批量写入 training_samples，复用 PVFaultRepository 的 INSERT IGNORE 逻辑
        from sqlalchemy import insert as sa_insert
        from services.db.models.pv_fault import TrainingSample

        records = write_df.where(pd.notnull(write_df), None).to_dict(orient="records")
        # branch_id 是 Int，还原为 int 或 None
        for rec in records:
            if rec.get("branch_id") is not None:
                try:
                    rec["branch_id"] = str(rec["branch_id"])
                except (TypeError, ValueError):
                    pass

        _BATCH_SIZE = 500
        total_inserted = 0
        with self._adapter.get_sync_session() as session:
            for i in range(0, len(records), _BATCH_SIZE):
                batch = records[i: i + _BATCH_SIZE]
                stmt = sa_insert(TrainingSample).prefix_with("IGNORE").values(batch)
                result = session.execute(stmt)
                total_inserted += int(result.rowcount or 0)

        skipped = len(records) - total_inserted
        device_count = int(write_df["device_id"].nunique())

        # 记录游标
        self._mark_date_fed(business_date, len(records))

        feed_result = PvMockFeedResult(
            business_date=business_date,
            source_row_count=len(records),
            inserted_row_count=total_inserted,
            skipped_row_count=skipped,
            device_count=device_count,
            exhausted=False,
        )
        self._last_feed_result = feed_result

        logger.info(
            "pv_mock_feed: business_date=%s source_rows=%d inserted=%d skipped=%d devices=%d",
            business_date.isoformat(),
            len(records),
            total_inserted,
            skipped,
            device_count,
        )
        return feed_result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_pv_mock_feeder(adapter: DBAdapter) -> PvFaultMockFeeder:
    """构造光伏 mock feeder（路径可通过环境变量覆盖）。"""
    parquet_path = os.environ.get("PV_MOCK_PARQUET_PATH", _DEFAULT_PARQUET_PATH)
    return PvFaultMockFeeder(adapter=adapter, parquet_path=parquet_path)
# @AI_GENERATED: end
