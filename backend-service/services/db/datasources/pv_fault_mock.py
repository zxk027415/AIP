# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
services/db/datasources/pv_fault_mock.py — 光伏故障诊断 Mock 喂数据器

与负荷预测的 CsvMockCompanyFeeder 平行设计：
  - 手动"喂入首日/推进下一天"按钮：一次性把整个业务日写入（跨日需人工确认）
  - 自动 cron 路径（``release_next_batch_tick``）：模拟真实场景下设备异步到达——
    每次 tick 只释放当前业务日里"计划批次已到、尚未释放"的一批设备数据，
    不需要人工确认即可跨日自动推进（与旧版 ``feed_next_batch`` 语义一致）。
  - 写入时 label = NULL，模拟真实场景下数据库新收到的原始光伏观测，
    ``data_source`` 列固定写 ``"mock"``。
  - 源数据默认 datasets/pv_mock_feed_source.parquet（约 35 天，可用 PV_MOCK_PARQUET_PATH 覆盖）

错峰释放计划（``PvMockReleaseSchedule``，mock 专用表）：
  - 每个业务日首次被处理时，一次性为当天全部设备生成释放计划（确定性随机，
    以 business_date 做种子，重复调用不会产生不同结果——同一业务日重复生成的
    设备集合、每台设备延迟/缺失归类以及释放顺序均逐项一致，见 Req8.6）。
  - 设备被均匀分配到若干释放批次（``_RELEASE_BATCH_COUNT``），
    约 ``_DELAY_RATIO`` 比例的设备额外延迟 1~2 个批次到达（延迟到达占比落在
    4%~6% 区间，见 Req8.1），
    约 ``_DROP_RATIO`` 比例的设备当天完全缺失（当天缺失占比落在 0.5%~1.5%
    区间，模拟采集器故障，见 Req8.1）。
  - 每次写入 ``training_samples`` 后同步调用 ``IngestionTrackerRepository``
    更新设备-天完整性进度，供预测任务和前端"数据到达"面板消费；单个设备-天的
    完整性更新在 ``record_arrival`` 的单事务内完成，失败即回滚不产生部分更新，
    并抛出标明所涉设备-天的错误（见 Req8.4）。

点级错峰（Req8.5，本轮不实现）：
  - 当前只做**设备级错峰**（整台设备整天一次性释放）。点级错峰（同一设备当天
    的 288 个测点分批错峰到达）仅对 ``Legacy_Day_Strategy``（传统按天路径，可
    增量拉取当天已到达测点）有意义；对 ``Seq_Daily_Strategy``（全天序列路径，
    按整天检测、要求当天近完整）无意义。故点级错峰列为可选低优先能力，本轮不实现。

与负荷预测 feeder 的主要差异：
  - 数据源是 Parquet（多设备多列），而非 CSV（单设备单列）
  - 目标表是 training_samples（多列：site_id/device_id/branch_id/value/i_cal），
    而非 station_observations（单列：value）

持久化路径：所有状态通过数据库游标/释放计划表和目标表推断，
不依赖外部文件，符合项目相对路径规范。
"""

from __future__ import annotations

import logging
import json
import os
import random
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import func, select, text, update

from services.db.adapter import DBAdapter
from services.db.exceptions import DataSourceError, IngestionError
from services.db.models.pv_fault import PvMockReleaseSchedule, TrainingSample
from services.db.repositories.ingestion_tracker import (
    DEFAULT_EXPECTED_POINT_COUNT,
    IngestionTrackerRepository,
)

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PARQUET_PATH = "datasets/pv_mock_feed_source.parquet"

# training_samples 表结构（与 PVFaultRepository.ingest_parquet 一致）
_SCHEMA = "aip_algo_platform"
_CURSOR_TABLE = "pv_mock_feed_cursor"

# 错峰释放计划参数（可按需调整；用常量而非硬编码，便于测试覆盖）
# Req8.1 口径：延迟到达设备占比落在 4%~6%（5%±1%），当天缺失设备占比落在
# 0.5%~1.5%（1%±0.5%）。下列默认值取各区间中心，落在合法区间内。
_RELEASE_BATCH_COUNT = 7      # 一天分 7 批释放（约 10~15 分钟一批，覆盖 1~2 小时）
_DELAY_RATIO = 0.05           # 5% 设备额外延迟（合法区间 [0.04, 0.06]，Req8.1）
_DELAY_TICKS_RANGE = (1, 2)   # 延迟 1~2 个批次
_DROP_RATIO = 0.01            # 1% 设备当天完全缺失（合法区间 [0.005, 0.015]，Req8.1）

# Req8.1 占比区间（供确定性校准与单元测试断言口径引用）
_DELAY_RATIO_RANGE = (0.04, 0.06)   # 延迟到达设备占比合法区间
_DROP_RATIO_RANGE = (0.005, 0.015)  # 当天缺失设备占比合法区间

# 启动即断言默认占比落在 Req8.1 区间内，避免误改常量后偏离需求口径。
assert _DELAY_RATIO_RANGE[0] <= _DELAY_RATIO <= _DELAY_RATIO_RANGE[1], (
    f"_DELAY_RATIO={_DELAY_RATIO} 超出 Req8.1 延迟占比区间 {_DELAY_RATIO_RANGE}"
)
assert _DROP_RATIO_RANGE[0] <= _DROP_RATIO <= _DROP_RATIO_RANGE[1], (
    f"_DROP_RATIO={_DROP_RATIO} 超出 Req8.1 缺失占比区间 {_DROP_RATIO_RANGE}"
)

# 进程内缓存：避免每次 feed-status / 指纹都扫百万行 parquet（会拖死单进程 uvicorn）
_FINGERPRINT_CACHE: Dict[str, Any] = {"key": None, "value": None}
_META_CACHE: Dict[str, Any] = {"key": None, "value": None}


def _meta_path_for(parquet_path: Path) -> Path:
    return parquet_path.with_suffix(parquet_path.suffix + ".meta.json")


def _file_cache_key(path: Path) -> Tuple[str, int, int]:
    st = path.stat()
    return (str(path.resolve()), int(st.st_mtime_ns), int(st.st_size))


def load_pv_mock_source_meta(parquet_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """读取 build 脚本旁路写出的 meta；没有则返回 None。"""
    raw = parquet_path or os.environ.get("PV_MOCK_PARQUET_PATH", _DEFAULT_PARQUET_PATH)
    resolved = _resolve_path(raw)
    meta_file = _meta_path_for(resolved)
    if not meta_file.exists():
        return None
    key = _file_cache_key(meta_file) + _file_cache_key(resolved)
    if _META_CACHE["key"] == key and isinstance(_META_CACHE["value"], dict):
        return _META_CACHE["value"]
    try:
        payload = json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    _META_CACHE["key"] = key
    _META_CACHE["value"] = payload
    return payload


def write_pv_mock_source_meta(
    parquet_path: Path,
    *,
    unique_dates: List[str],
    row_count: int,
    built_from: str = "",
) -> Path:
    """写出喂数源旁路 meta，供指纹/预览快速读取。"""
    dates = sorted({str(d)[:10] for d in unique_dates if d})
    payload = {
        "source_path": _project_relative_parquet_path(parquet_path),
        "built_from": built_from,
        "row_count": int(row_count),
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "unique_days": len(dates),
        "unique_dates": dates,
        "updated_at": datetime.utcnow().isoformat(),
    }
    out = _meta_path_for(parquet_path)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _META_CACHE["key"] = None
    _META_CACHE["value"] = None
    _FINGERPRINT_CACHE["key"] = None
    _FINGERPRINT_CACHE["value"] = None
    return out


def compute_pv_source_fingerprint(parquet_path: Optional[str] = None) -> Dict[str, Any]:
    """计算当前 mock 数据源指纹（相对路径 + 日期范围 + 行数）。

    优先读旁路 meta + 文件 size/mtime，避免每次全表扫描 time 列。
    """
    import hashlib

    raw = parquet_path or os.environ.get("PV_MOCK_PARQUET_PATH", _DEFAULT_PARQUET_PATH)
    resolved = _resolve_path(raw)
    if not resolved.exists():
        raise DataSourceError(f"PV mock 数据文件不存在: {resolved}")

    cache_key = _file_cache_key(resolved)
    if _FINGERPRINT_CACHE["key"] == cache_key and isinstance(_FINGERPRINT_CACHE["value"], dict):
        return dict(_FINGERPRINT_CACHE["value"])

    source_path = _project_relative_parquet_path(resolved)
    meta = load_pv_mock_source_meta(str(resolved))
    if meta and meta.get("date_min") and meta.get("date_max") and meta.get("row_count") is not None:
        date_min = str(meta["date_min"])
        date_max = str(meta["date_max"])
        row_count = int(meta["row_count"])
    else:
        # 回退：只读 time 列（慢，仅 meta 缺失时）
        df = pd.read_parquet(resolved, columns=["time"])
        times = pd.to_datetime(df["time"])
        if getattr(times.dt, "tz", None) is not None:
            times = times.dt.tz_convert("UTC").dt.tz_localize(None)
        if times.empty:
            raise DataSourceError(f"PV mock parquet 无 time 数据: {resolved}")
        date_min = times.min().date().isoformat()
        date_max = times.max().date().isoformat()
        row_count = int(len(times))

    st = resolved.stat()
    digest = hashlib.sha256(
        f"{source_path}|{date_min}|{date_max}|{row_count}|{int(st.st_size)}".encode("utf-8")
    ).hexdigest()[:16]
    payload = {
        "source_path": source_path,
        "date_min": date_min,
        "date_max": date_max,
        "row_count": row_count,
        "fingerprint": digest,
    }
    _FINGERPRINT_CACHE["key"] = cache_key
    _FINGERPRINT_CACHE["value"] = dict(payload)
    return payload


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


def _coerce_date(value: Any) -> Optional[date]:
    """把 MySQL/驱动返回的 date/datetime/str 统一成 date，避免跨日比较 TypeError。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        return date.fromisoformat(text_value[:10])
    return None


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
    """喂数据结果：一次 feed（或一次批次 tick）的元数据。"""
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
    # @AI_GENERATED: 按日滚动预测 —— 当前正在自动错峰释放的业务日的批次进度
    release_progress: Optional[Dict[str, Any]] = None
    # @AI_GENERATED: end

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
            "release_progress": self.release_progress,
        }


# ---------------------------------------------------------------------------
# PvFaultMockFeeder
# ---------------------------------------------------------------------------

class PvFaultMockFeeder:
    """从 Parquet 文件按自然日向 training_samples 表喂光伏观测数据。

    喂数据时 label 列强制设为 NULL，模拟真实场景下数据库新收到的原始观测；
    ``data_source`` 列固定写 ``"mock"``。源数据中的 label 列仅用于验证数据
    完整性，不会被写入 training_samples。

    两条写入路径：
      - ``feed_manually`` / ``_feed_date_locked``：人工触发，一次性把整个
        业务日写完（跨日推进需要 ``advance=True`` 人工确认），
        与旧版行为完全一致，供"喂入首日/推进下一天"按钮使用。
      - ``release_next_batch_tick``：cron 自动触发，每次只释放当前业务日
        里"计划批次已到"的一批设备，不需要人工确认即可跨日自动推进
        （与旧版 ``feed_next_batch`` 的自动推进语义一致），用来模拟真实
        场景下设备异步到达、偶发延迟/缺失。
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
        self._tracker = IngestionTrackerRepository(adapter)

    @property
    def last_feed_result(self) -> Optional[PvMockFeedResult]:
        return self._last_feed_result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_df(self) -> pd.DataFrame:
        """懒加载 Parquet（仅真正喂数时调用；预览尽量走 meta + 按日过滤）。"""
        if self._df is None:
            if not self._parquet_path.exists():
                raise DataSourceError(f"PV mock 数据文件不存在: {self._parquet_path}")
            logger.info("pv_mock_feed: loading full parquet into memory path=%s", self._parquet_path)
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

    def _unique_dates(self) -> List[date]:
        """优先读 meta 中的日期列表，避免预览时全表加载。"""
        if self._df_dates is not None:
            return list(self._df_dates)
        meta = load_pv_mock_source_meta(str(self._parquet_path))
        if meta and isinstance(meta.get("unique_dates"), list) and meta["unique_dates"]:
            dates = [_coerce_date(d) for d in meta["unique_dates"]]
            self._df_dates = [d for d in dates if d is not None]
            return list(self._df_dates)
        self._load_df()
        return list(self._df_dates or [])

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
        """返回上次成功喂完（该业务日全部非缺失设备已释放）的最新自然日。"""
        self._ensure_cursor_table()
        with self._adapter.get_sync_session() as session:
            result = session.execute(
                text(f"SELECT MAX(business_date) FROM `{_SCHEMA}`.`{_CURSOR_TABLE}`")
            ).scalar()
        return _coerce_date(result)

    def _mark_date_fed(self, business_date: date, row_count: int) -> None:
        """记录当日已喂完（幂等 upsert）。"""
        normalized = _coerce_date(business_date)
        if normalized is None:
            raise IngestionError(f"无效的 business_date: {business_date!r}")
        with self._adapter.get_sync_session() as session:
            session.execute(text(f"""
                INSERT INTO `{_SCHEMA}`.`{_CURSOR_TABLE}` (business_date, fed_at, row_count)
                VALUES (:d, :now, :cnt)
                ON DUPLICATE KEY UPDATE fed_at = :now, row_count = :cnt
            """), {"d": normalized, "now": datetime.utcnow(), "cnt": row_count})

    def _rows_for_date(self, business_date: date) -> pd.DataFrame:
        """按自然日取行：内存已缓存则切片，否则用 parquet filter 只读一天。"""
        target = _coerce_date(business_date)
        if target is None:
            return pd.DataFrame()
        if self._df is not None:
            return self._df[self._df["_date"] == target].copy()

        start = pd.Timestamp(target)
        end = start + pd.Timedelta(days=1)
        try:
            df = pd.read_parquet(
                self._parquet_path,
                filters=[("time", ">=", start), ("time", "<", end)],
            )
        except Exception:
            # 某些引擎不支持 filters 时回退全表（慢路径）
            return self._load_df()[self._load_df()["_date"] == target].copy()

        if df.empty:
            return df
        df["time"] = pd.to_datetime(df["time"])
        if getattr(df["time"].dt, "tz", None) is not None:
            df["time"] = df["time"].dt.tz_convert("UTC").dt.tz_localize(None)
        df["_date"] = df["time"].dt.date
        return df[df["_date"] == target].copy()

    def _devices_for_date(self, business_date: date) -> List[Tuple[str, str, str]]:
        """该业务日的全部设备三元组（site_id, device_id, branch_id），去重排序。"""
        rows_df = self._rows_for_date(business_date)
        if rows_df.empty:
            return []
        triples = (
            rows_df[["site_id", "device_id", "branch_id"]]
            .astype(str)
            .drop_duplicates()
            .itertuples(index=False, name=None)
        )
        return sorted(triples)

    def _next_unfed_date(self) -> Optional[date]:
        """返回下一个还没"整体喂完"的自然日（当前正在被自动释放或等待人工确认的那天）。"""
        last = self._last_fed_date()
        for d in self._unique_dates():
            day = _coerce_date(d)
            if day is None:
                continue
            if last is None or day > last:
                return day
        return None  # exhausted

    # ------------------------------------------------------------------
    # 错峰释放计划（PvMockReleaseSchedule）—— mock 专用
    # ------------------------------------------------------------------

    def _ensure_release_schedule(self, business_date: date) -> None:
        """为该业务日生成错峰释放计划（幂等；已存在则不重新生成）。

        确定性随机：以 business_date 做种子，同一天多次调用产出相同计划，
        便于测试和排错复现。
        """
        with self._adapter.get_sync_session() as session:
            exists = session.execute(
                select(func.count()).select_from(PvMockReleaseSchedule)
                .where(PvMockReleaseSchedule.business_date == business_date)
            ).scalar()
        if exists:
            return

        devices = self._devices_for_date(business_date)
        if not devices:
            return

        rng = random.Random(f"pv-mock-release|{business_date.isoformat()}")
        shuffled = list(devices)
        rng.shuffle(shuffled)

        rows = []
        now = datetime.utcnow()
        for idx, (site_id, device_id, branch_id) in enumerate(shuffled):
            is_dropped = rng.random() < _DROP_RATIO
            delay_ticks = 0
            if not is_dropped and rng.random() < _DELAY_RATIO:
                delay_ticks = rng.randint(*_DELAY_TICKS_RANGE)
            rows.append({
                "business_date": business_date,
                "site_id": site_id,
                "device_id": device_id,
                "branch_id": branch_id,
                "planned_batch_index": idx % _RELEASE_BATCH_COUNT,
                "delay_ticks": delay_ticks,
                "is_dropped": is_dropped,
                "released_at": None,
                "created_at": now,
            })

        from sqlalchemy import insert as sa_insert
        with self._adapter.get_sync_session() as session:
            stmt = sa_insert(PvMockReleaseSchedule).prefix_with("IGNORE").values(rows)
            session.execute(stmt)
        logger.info(
            "pv_mock_feed: 业务日 %s 释放计划已生成 devices=%d batches=%d",
            business_date.isoformat(), len(rows), _RELEASE_BATCH_COUNT,
        )

    def _release_progress_for_date(self, business_date: date) -> Optional[Dict[str, Any]]:
        """返回该业务日释放计划的进度摘要（供预览/前端展示）；无计划返回 None。"""
        with self._adapter.get_sync_session() as session:
            rows = session.execute(
                select(
                    PvMockReleaseSchedule.is_dropped,
                    PvMockReleaseSchedule.released_at,
                ).where(PvMockReleaseSchedule.business_date == business_date)
            ).all()
        if not rows:
            return None
        total = len(rows)
        dropped = sum(1 for r in rows if r[0])
        released = sum(1 for r in rows if r[1] is not None and not r[0])
        pending = total - dropped - released
        return {
            "devices_total": total,
            "devices_dropped": dropped,
            "devices_released": released,
            "devices_pending": pending,
            "batches_total": _RELEASE_BATCH_COUNT,
        }

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
        next_device_count = int(next_rows["device_id"].nunique()) if not next_rows.empty else 0
        release_progress = self._release_progress_for_date(next_date)

        if last_date is None:
            state = "initial_feed"
            requires_confirm = False
        else:
            # 跨日需要人工确认（仅约束手动按钮；自动 cron 路径不受此约束）
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
            release_progress=release_progress,
        )

    def feed_manually(self, advance: bool = False) -> Tuple[PvMockFeedPreview, Optional[PvMockFeedResult]]:
        """人工触发：需要 advance=True 才能跨日推进。一次性写完整个业务日。"""
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
        """兼容旧接口：委托给 ``release_next_batch_tick``，返回本次插入行数。"""
        result = self.release_next_batch_tick()
        return result.inserted_row_count if result else 0

    def release_next_batch_tick(self) -> PvMockFeedResult:
        """cron 自动触发：释放当前业务日里"计划批次已到"的下一批设备数据。

        不需要人工确认即可跨日自动推进（与旧版 ``feed_next_batch`` 一致）。
        每次调用只处理一批，模拟设备异步到达；当某业务日全部非缺失设备都
        释放完毕后自动标记该日"已喂完"，下次调用推进到下一个自然日。
        """
        with self._feed_lock:
            active_date = self._next_unfed_date()
            if active_date is None:
                logger.info("pv_mock_feed: source exhausted")
                self._last_feed_result = PvMockFeedResult(
                    business_date=None,
                    source_row_count=0,
                    inserted_row_count=0,
                    skipped_row_count=0,
                    device_count=0,
                    exhausted=True,
                )
                return self._last_feed_result

            self._ensure_release_schedule(active_date)

            with self._adapter.get_sync_session() as session:
                max_released_batch = session.execute(
                    select(func.max(PvMockReleaseSchedule.planned_batch_index))
                    .where(
                        PvMockReleaseSchedule.business_date == active_date,
                        PvMockReleaseSchedule.released_at.is_not(None),
                    )
                ).scalar()
            pointer = 0 if max_released_batch is None else int(max_released_batch) + 1

            with self._adapter.get_sync_session() as session:
                due_rows = session.execute(
                    select(PvMockReleaseSchedule).where(
                        PvMockReleaseSchedule.business_date == active_date,
                        PvMockReleaseSchedule.released_at.is_(None),
                        PvMockReleaseSchedule.is_dropped.is_(False),
                        (
                            PvMockReleaseSchedule.planned_batch_index
                            + PvMockReleaseSchedule.delay_ticks
                        ) <= pointer,
                    )
                ).scalars().all()
                due_keys = {(r.site_id, r.device_id, r.branch_id) for r in due_rows}

            result = self._release_due_devices(active_date, due_keys)
            self._maybe_mark_day_fed(active_date)
            self._last_feed_result = result
            return result

    def _release_due_devices(
        self, business_date: date, due_keys: set,
    ) -> PvMockFeedResult:
        """把 due_keys 对应设备当天的观测写入 training_samples 并更新完整性表。"""
        if not due_keys:
            return PvMockFeedResult(
                business_date=business_date,
                source_row_count=0,
                inserted_row_count=0,
                skipped_row_count=0,
                device_count=0,
                exhausted=False,
            )

        rows_df = self._rows_for_date(business_date)
        if rows_df.empty:
            return PvMockFeedResult(
                business_date=business_date,
                source_row_count=0,
                inserted_row_count=0,
                skipped_row_count=0,
                device_count=0,
                exhausted=False,
            )

        key_series = list(zip(
            rows_df["site_id"].astype(str),
            rows_df["device_id"].astype(str),
            rows_df["branch_id"].astype(str),
        ))
        mask = [k in due_keys for k in key_series]
        subset = rows_df[mask].copy()
        if subset.empty:
            return PvMockFeedResult(
                business_date=business_date,
                source_row_count=0,
                inserted_row_count=0,
                skipped_row_count=0,
                device_count=0,
                exhausted=False,
            )

        inserted, skipped = self._write_training_samples(subset)
        now = datetime.utcnow()

        with self._adapter.get_sync_session() as session:
            for site_id, device_id, branch_id in due_keys:
                session.execute(
                    update(PvMockReleaseSchedule)
                    .where(
                        PvMockReleaseSchedule.business_date == business_date,
                        PvMockReleaseSchedule.site_id == site_id,
                        PvMockReleaseSchedule.device_id == device_id,
                        PvMockReleaseSchedule.branch_id == branch_id,
                    )
                    .values(released_at=now)
                )

        # 按设备三元组分组更新完整性表（Req8.3）。
        # Req8.4：单个设备-天的完整性更新在 record_arrival 的单事务内完成，
        # 失败即回滚（不产生部分更新）；此处把底层异常包装成标明所涉设备-天的
        # IngestionError 后向上抛出，供调用方定位失败设备-天。
        for (site_id, device_id, branch_id), grp in subset.groupby(
            ["site_id", "device_id", "branch_id"]
        ):
            try:
                self._tracker.record_arrival(
                    str(site_id), str(device_id), str(branch_id), business_date,
                    point_delta=len(grp),
                    expected_point_count=DEFAULT_EXPECTED_POINT_COUNT,
                    arrived_at=now,
                )
            except Exception as exc:  # noqa: BLE001 - 需保留原因并附设备-天上下文
                raise IngestionError(
                    "record_arrival 更新完整性失败 "
                    f"device=({site_id},{device_id},{branch_id}) "
                    f"business_date={business_date.isoformat()}: {exc}"
                ) from exc

        device_count = len(due_keys)
        logger.info(
            "pv_mock_feed: 业务日 %s 释放 %d 台设备 rows=%d inserted=%d skipped=%d",
            business_date.isoformat(), device_count, len(subset), inserted, skipped,
        )
        return PvMockFeedResult(
            business_date=business_date,
            source_row_count=len(subset),
            inserted_row_count=inserted,
            skipped_row_count=skipped,
            device_count=device_count,
            exhausted=False,
        )

    def _maybe_mark_day_fed(self, business_date: date) -> None:
        """若该业务日全部非缺失设备均已释放，标记该日"已喂完"。"""
        with self._adapter.get_sync_session() as session:
            remaining = session.execute(
                select(func.count()).select_from(PvMockReleaseSchedule).where(
                    PvMockReleaseSchedule.business_date == business_date,
                    PvMockReleaseSchedule.released_at.is_(None),
                    PvMockReleaseSchedule.is_dropped.is_(False),
                )
            ).scalar()
        if remaining:
            return
        rows_df = self._rows_for_date(business_date)
        self._mark_date_fed(business_date, len(rows_df))
        logger.info("pv_mock_feed: 业务日 %s 全部设备已释放，标记为已喂完", business_date.isoformat())

    # ------------------------------------------------------------------
    # Core insert
    # ------------------------------------------------------------------

    def _write_training_samples(self, rows_df: pd.DataFrame) -> Tuple[int, int]:
        """把测量行写入 training_samples（label=NULL，data_source='mock'）。

        Returns:
            (inserted_row_count, skipped_row_count)
        """
        write_df = rows_df[["time", "site_id", "device_id", "branch_id", "value", "i_cal"]].copy()
        write_df["label"] = None   # 原始观测不带标签

        write_df["time"] = pd.to_datetime(write_df["time"])
        if write_df["time"].dt.tz is not None:
            write_df["time"] = write_df["time"].dt.tz_convert("UTC").dt.tz_localize(None)
        write_df["branch_id"] = write_df["branch_id"].astype(str)
        write_df["label"] = write_df["label"].astype(object)
        # @AI_GENERATED: 按日滚动预测 —— 标记数据来源为 mock
        write_df["data_source"] = "mock"
        # @AI_GENERATED: end

        from sqlalchemy import insert as sa_insert

        records = write_df.where(pd.notnull(write_df), None).to_dict(orient="records")
        for rec in records:
            if rec.get("branch_id") is not None:
                try:
                    rec["branch_id"] = str(rec["branch_id"])
                except (TypeError, ValueError):
                    pass
            if rec.get("data_source") is None:
                rec["data_source"] = "mock"

        _BATCH_SIZE = 500
        total_inserted = 0
        with self._adapter.get_sync_session() as session:
            for i in range(0, len(records), _BATCH_SIZE):
                batch = records[i: i + _BATCH_SIZE]
                stmt = sa_insert(TrainingSample).prefix_with("IGNORE").values(batch)
                result = session.execute(stmt)
                total_inserted += int(result.rowcount or 0)

        skipped = len(records) - total_inserted
        return total_inserted, skipped

    def _feed_date_locked(self, business_date: date) -> PvMockFeedResult:
        """人工"喂入首日/推进下一天"：一次性把当天全部非缺失设备写完。

        内部仍走释放计划表记账（避免与自动 cron 路径产生重复释放/重复计数），
        但不受批次/延迟节奏限制——所有未释放且非缺失的设备立即全部释放。
        """
        self._ensure_release_schedule(business_date)

        with self._adapter.get_sync_session() as session:
            pending_rows = session.execute(
                select(PvMockReleaseSchedule).where(
                    PvMockReleaseSchedule.business_date == business_date,
                    PvMockReleaseSchedule.released_at.is_(None),
                    PvMockReleaseSchedule.is_dropped.is_(False),
                )
            ).scalars().all()
            due_keys = {(r.site_id, r.device_id, r.branch_id) for r in pending_rows}

        if not due_keys:
            # 该日全部设备已释放过（比如之前 cron 已经喂完，或该日在 parquet 中无设备）
            rows_df = self._rows_for_date(business_date)
            self._last_feed_result = PvMockFeedResult(
                business_date=business_date,
                source_row_count=0,
                inserted_row_count=0,
                skipped_row_count=0,
                device_count=0,
                exhausted=False,
            )
            if not rows_df.empty:
                self._maybe_mark_day_fed(business_date)
            return self._last_feed_result

        result = self._release_due_devices(business_date, due_keys)
        self._maybe_mark_day_fed(business_date)
        self._last_feed_result = result

        logger.info(
            "pv_mock_feed: business_date=%s（人工全量释放）source_rows=%d inserted=%d skipped=%d devices=%d",
            business_date.isoformat(),
            result.source_row_count,
            result.inserted_row_count,
            result.skipped_row_count,
            result.device_count,
        )
        return result

    def reset_feed_cursor(self, reason: str = "manual_reset") -> Dict[str, Any]:
        """清空喂数游标与释放计划，下次可从 parquet 首日重新推进。

        已写入 ``training_samples`` 的行仍受 INSERT IGNORE 保护（不会重复插入），
        但会重新生成释放计划并重新走一遍完整性/游标记账流程。
        """
        with self._feed_lock:
            self._ensure_cursor_table()
            previous = self._last_fed_date()
            with self._adapter.get_sync_session() as session:
                result = session.execute(
                    text(f"DELETE FROM `{_SCHEMA}`.`{_CURSOR_TABLE}`")
                )
                deleted = int(result.rowcount or 0)
                session.execute(text("DELETE FROM pv_mock_release_schedule"))
                session.execute(text("DELETE FROM measurement_ingestion_daily"))
            preview = self._build_preview()
            logger.info(
                "pv_mock_feed: cursor reset reason=%s deleted_rows=%d previous=%s next=%s",
                reason,
                deleted,
                previous.isoformat() if previous else None,
                preview.next_business_date.isoformat() if preview.next_business_date else None,
            )
            return {
                "status": "reset",
                "reason": reason,
                "deleted_cursor_rows": deleted,
                "previous_business_date": previous.isoformat() if previous else None,
                "preview": preview.as_dict(),
            }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_pv_mock_feeder(adapter: DBAdapter) -> PvFaultMockFeeder:
    """构造光伏 mock feeder（路径可通过环境变量覆盖）。"""
    parquet_path = os.environ.get("PV_MOCK_PARQUET_PATH", _DEFAULT_PARQUET_PATH)
    return PvFaultMockFeeder(adapter=adapter, parquet_path=parquet_path)
# @AI_GENERATED: end
