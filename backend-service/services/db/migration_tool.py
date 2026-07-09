# -*- coding: utf-8 -*-
"""
services/db/migration_tool.py — 历史数据迁移工具

MigrationTool: 将现有 precision_ops JSON / predictions.db SQLite / Parquet
历史数据一次性导入新的 MySQL 数据库。

三个迁移方法：
  migrate_precision_ops_json  — precision_ops 各 slot 下的 JSON → load_forecast 表
  migrate_predictions_db      — predictions.db SQLite → load_forecast.prediction_result
  migrate_parquet             — all_labeled_combined.parquet → pv_fault_diag.training_samples

CLI 接口：
  python -m services.db.migration_tool [--precision-ops] [--predictions-db] [--parquet]

错误处理：
  - 单个文件损坏：log ERROR，skip，继续处理其余文件
  - 目标 schema 不存在：raise MigrationError

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.dialects.mysql import insert as mysql_insert

from .adapter import DBAdapter
from .exceptions import MigrationError
from .models.load_forecast import (
    AccuracyMetric,
    PrelaunchQueue,
    PredictionResult,
    VersionRegistry,
)
from .repositories.load_forecast import LoadForecastRepository
from .repositories.pv_fault import PVFaultRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
# __file__ → backend-service/services/db/migration_tool.py
# 向上三级 → backend-service/
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Parquet 默认路径：相对于 backend-service/ 的上级目录（即项目根 AIP/）
_DEFAULT_PARQUET_PATH = (
    _BACKEND_DIR.parent
    / "fault-diag-algo-release-3.1"
    / "相关数据"
    / "all_labeled_combined.parquet"
)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """
    将 ISO 8601 字符串解析为无时区 datetime（MySQL DateTime 不存储时区）。
    值为 None 或无法解析时返回 None。
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # 将 tz-aware 转为 UTC naive，避免 MySQL 存储错误
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# MigrationTool
# ---------------------------------------------------------------------------

class MigrationTool:
    """
    历史数据迁移工具。

    所有迁移方法均幂等：使用自然键检测重复，多次运行不产生重复记录。
    单个源文件损坏时 log ERROR 并跳过，继续处理其余文件。
    目标 schema 不存在时抛出 MigrationError。

    用法：
        from services.db.config import DBConfig
        from services.db.adapter import DBAdapter
        from services.db.migration_tool import MigrationTool

        adapter = DBAdapter(DBConfig())
        tool = MigrationTool(adapter)
        result = tool.migrate_precision_ops_json()
        print(result)  # {"migrated": 12, "skipped": 3, "files_processed": 6, "elapsed_s": 0.45}
    """

    def __init__(self, adapter: DBAdapter) -> None:
        self._adapter = adapter
        self._lf_repo = LoadForecastRepository(adapter)
        self._pv_repo = PVFaultRepository(adapter)

    # ------------------------------------------------------------------
    # Schema 存在性检查
    # ------------------------------------------------------------------

    def _check_lf_schema(self) -> None:
        """
        验证 load_forecast schema（数据库）及核心表是否可访问。
        不可访问时抛出 MigrationError，不修改任何数据。
        """
        try:
            with self._adapter.get_sync_session() as session:
                session.execute(
                    text("SELECT 1 FROM `load_forecast`.`accuracy_metric` LIMIT 1")
                )
        except Exception as exc:
            raise MigrationError("load_forecast", exc) from exc

    def _check_pv_schema(self) -> None:
        """
        验证 pv_fault_diag schema（数据库）及核心表是否可访问。
        不可访问时抛出 MigrationError，不修改任何数据。
        """
        try:
            with self._adapter.get_sync_session() as session:
                session.execute(
                    text("SELECT 1 FROM `pv_fault_diag`.`training_samples` LIMIT 1")
                )
        except Exception as exc:
            raise MigrationError("pv_fault_diag", exc) from exc

    # ------------------------------------------------------------------
    # 1. migrate_precision_ops_json
    # ------------------------------------------------------------------

    def migrate_precision_ops_json(
        self, data_dir: str = "data/precision_ops"
    ) -> dict:
        """
        扫描 data_dir/{slot}/ 下的 JSON 文件，迁移到 load_forecast 表。

        文件映射（natural key）：
          accuracy_metrics.json  → accuracy_metric   (slot + workflow_id)
          prelaunch_queue.json   → prelaunch_queue    (id)
          version_registry.json  → version_registry   (slot + workflow_id + version_tag)

        幂等：使用 INSERT IGNORE，自然键冲突时静默跳过，rowcount=0 计入 skipped。
        源文件损坏：log ERROR，跳过该文件，继续。
        目标 schema 不存在：raise MigrationError。

        Args:
            data_dir: 相对于 backend-service/ 的 precision_ops 数据根目录，
                      默认 "data/precision_ops"。

        Returns:
            {"migrated": n, "skipped": m, "files_processed": k, "elapsed_s": t}
        """
        self._check_lf_schema()

        start = time.time()
        migrated = skipped = files_processed = 0

        data_path = _BACKEND_DIR / data_dir
        if not data_path.exists():
            logger.info(
                "migrate_precision_ops_json: 目录不存在，返回空摘要: %s", data_path
            )
            return {
                "migrated": 0,
                "skipped": 0,
                "files_processed": 0,
                "elapsed_s": round(time.time() - start, 3),
            }

        for slot_dir in sorted(data_path.iterdir()):
            if not slot_dir.is_dir():
                continue
            slot = slot_dir.name

            # --- accuracy_metrics.json → accuracy_metric ---
            am_path = slot_dir / "accuracy_metrics.json"
            if am_path.exists():
                files_processed += 1
                try:
                    raw = json.loads(am_path.read_text(encoding="utf-8"))
                    metrics_dict: Dict = raw.get("metrics", {})
                    for workflow_id, entry in metrics_dict.items():
                        row = {
                            "slot": slot,
                            "workflow_id": workflow_id,
                            "rolling_mape": entry.get("rolling_mape"),
                            "rolling_mae": entry.get("rolling_mae"),
                            "valid_cycle_count": entry.get("valid_cycle_count"),
                            "total_cycle_count": entry.get("total_cycle_count"),
                            "status": entry.get("status", "insufficient_data"),
                            "last_evaluated_at": _parse_dt(
                                entry.get("last_evaluated_at")
                            ),
                        }
                        row_count = 0
                        with self._adapter.get_sync_session() as session:
                            stmt = (
                                mysql_insert(AccuracyMetric)
                                .prefix_with("IGNORE")
                                .values(**row)
                            )
                            result = session.execute(stmt)
                            row_count = result.rowcount
                        if row_count > 0:
                            migrated += 1
                        else:
                            skipped += 1
                except Exception as exc:
                    logger.error(
                        "migrate_precision_ops_json: 跳过损坏文件 %s: %s",
                        am_path,
                        exc,
                    )

            # --- prelaunch_queue.json → prelaunch_queue ---
            pq_path = slot_dir / "prelaunch_queue.json"
            if pq_path.exists():
                files_processed += 1
                try:
                    items = json.loads(pq_path.read_text(encoding="utf-8"))
                    if not isinstance(items, list):
                        raise ValueError("prelaunch_queue.json 应为列表格式")
                    for item in items:
                        item_id = item.get("id")
                        if not item_id:
                            skipped += 1
                            continue
                        row = {
                            "id": item_id,
                            "slot": item.get("slot", slot),
                            "candidate_id": item.get("candidate_id", ""),
                            "workflow_id": item.get("workflow_id", ""),
                            "version_tag": item.get("version_tag", ""),
                            "status": item.get("status", "observing"),
                            "observation_days": int(
                                item.get("observation_days", 7)
                            ),
                            "graduate_tolerance_pct": float(
                                item.get("graduate_tolerance_pct", 5.0)
                            ),
                            "current_rolling_mape": item.get("current_rolling_mape"),
                            "production_rolling_mape": item.get(
                                "production_rolling_mape"
                            ),
                            "evaluated_cycles": int(
                                item.get("evaluated_cycles", 0) or 0
                            ),
                            "started_at": _parse_dt(item.get("started_at")),
                            "graduated_at": _parse_dt(item.get("graduated_at")),
                            "failed_at": _parse_dt(item.get("failed_at")),
                        }
                        row_count = 0
                        with self._adapter.get_sync_session() as session:
                            stmt = (
                                mysql_insert(PrelaunchQueue)
                                .prefix_with("IGNORE")
                                .values(**row)
                            )
                            result = session.execute(stmt)
                            row_count = result.rowcount
                        if row_count > 0:
                            migrated += 1
                        else:
                            skipped += 1
                except Exception as exc:
                    logger.error(
                        "migrate_precision_ops_json: 跳过损坏文件 %s: %s",
                        pq_path,
                        exc,
                    )

            # --- version_registry.json → version_registry ---
            vr_path = slot_dir / "version_registry.json"
            if vr_path.exists():
                files_processed += 1
                try:
                    raw = json.loads(vr_path.read_text(encoding="utf-8"))
                    versions = raw.get("versions", [])
                    if not isinstance(versions, list):
                        raise ValueError(
                            "version_registry.json 中 versions 字段应为列表"
                        )
                    for v in versions:
                        wf_id = v.get("workflow_id")
                        vtag = v.get("version_tag")
                        if not (wf_id and vtag):
                            skipped += 1
                            continue
                        row = {
                            "slot": v.get("slot", slot),
                            "workflow_id": wf_id,
                            "version_tag": vtag,
                            "status": v.get("status", "retired"),
                            "source_run_id": v.get("source_run_id"),
                            "source_candidate_id": v.get("source_candidate_id"),
                            "baseline_mape": v.get("baseline_mape"),
                            "registered_at": _parse_dt(v.get("registered_at")),
                        }
                        row_count = 0
                        with self._adapter.get_sync_session() as session:
                            stmt = (
                                mysql_insert(VersionRegistry)
                                .prefix_with("IGNORE")
                                .values(**row)
                            )
                            result = session.execute(stmt)
                            row_count = result.rowcount
                        if row_count > 0:
                            migrated += 1
                        else:
                            skipped += 1
                except Exception as exc:
                    logger.error(
                        "migrate_precision_ops_json: 跳过损坏文件 %s: %s",
                        vr_path,
                        exc,
                    )

        elapsed = round(time.time() - start, 3)
        logger.info(
            "migrate_precision_ops_json: migrated=%d skipped=%d files=%d elapsed=%.3fs",
            migrated,
            skipped,
            files_processed,
            elapsed,
        )
        return {
            "migrated": migrated,
            "skipped": skipped,
            "files_processed": files_processed,
            "elapsed_s": elapsed,
        }

    # ------------------------------------------------------------------
    # 2. migrate_predictions_db
    # ------------------------------------------------------------------

    def migrate_predictions_db(
        self, sqlite_path: str = "data/predictions.db"
    ) -> dict:
        """
        读取 predictions.db SQLite 的 predictions 表，迁移到
        load_forecast.prediction_result。

        幂等：先获取目标表中所有已存在的 (slot, prediction_cycle_id) 组合，
        跳过源表中 (slot, prediction_cycle_id) 已存在的行（整个周期跳过）。

        目标 schema 不存在时 raise MigrationError。

        Args:
            sqlite_path: 相对于 backend-service/ 的 SQLite 路径，
                         默认 "data/predictions.db"。

        Returns:
            {"migrated": n, "skipped": m, "files_processed": k, "elapsed_s": t}
        """
        self._check_lf_schema()

        start = time.time()
        db_path = _BACKEND_DIR / sqlite_path

        if not db_path.exists():
            logger.warning(
                "migrate_predictions_db: 文件不存在，跳过: %s", db_path
            )
            return {
                "migrated": 0,
                "skipped": 0,
                "files_processed": 0,
                "elapsed_s": round(time.time() - start, 3),
            }

        # 读取 SQLite 源数据
        try:
            src_conn = sqlite3.connect(str(db_path), timeout=30.0)
            src_conn.row_factory = sqlite3.Row
            src_rows = src_conn.execute(
                "SELECT slot, workflow_id, version_tag, prediction_cycle_id, "
                "forecast_timestamp, predicted_value, actual_value, status "
                "FROM predictions"
            ).fetchall()
            src_conn.close()
        except Exception as exc:
            logger.error("migrate_predictions_db: 读取 SQLite 失败: %s", exc)
            return {
                "migrated": 0,
                "skipped": 0,
                "files_processed": 1,
                "elapsed_s": round(time.time() - start, 3),
            }

        if not src_rows:
            return {
                "migrated": 0,
                "skipped": 0,
                "files_processed": 1,
                "elapsed_s": round(time.time() - start, 3),
            }

        # 获取目标表中已存在的 (slot, prediction_cycle_id) 集合
        try:
            with self._adapter.get_sync_session() as session:
                existing_pairs: Set[Tuple[str, str]] = {
                    (r[0], r[1])
                    for r in session.execute(
                        text(
                            "SELECT DISTINCT slot, prediction_cycle_id "
                            "FROM `load_forecast`.`prediction_result`"
                        )
                    ).fetchall()
                }
        except Exception as exc:
            raise MigrationError("load_forecast", exc) from exc

        # 过滤出尚未迁移的行
        batch = []
        skipped = 0
        for row in src_rows:
            if (row["slot"], row["prediction_cycle_id"]) in existing_pairs:
                skipped += 1
                continue
            ft = _parse_dt(str(row["forecast_timestamp"]))
            if ft is None:
                skipped += 1
                continue
            batch.append(
                {
                    "slot": row["slot"],
                    "workflow_id": row["workflow_id"],
                    "version_tag": row["version_tag"],
                    "prediction_cycle_id": row["prediction_cycle_id"],
                    "forecast_timestamp": ft,
                    "predicted_value": row["predicted_value"],
                    "actual_value": row["actual_value"],
                    "status": row["status"] or "predicted",
                    "is_shadow": False,
                }
            )

        migrated = 0
        if batch:
            try:
                with self._adapter.get_sync_session() as session:
                    session.execute(
                        mysql_insert(PredictionResult).prefix_with("IGNORE"),
                        batch,
                    )
                migrated = len(batch)
            except Exception as exc:
                logger.error("migrate_predictions_db: 批量写入失败: %s", exc)

        elapsed = round(time.time() - start, 3)
        logger.info(
            "migrate_predictions_db: migrated=%d skipped=%d elapsed=%.3fs",
            migrated,
            skipped,
            elapsed,
        )
        return {
            "migrated": migrated,
            "skipped": skipped,
            "files_processed": 1,
            "elapsed_s": elapsed,
        }

    # ------------------------------------------------------------------
    # 3. migrate_parquet
    # ------------------------------------------------------------------

    def migrate_parquet(
        self, parquet_path: Optional[str] = None
    ) -> dict:
        """
        导入 all_labeled_combined.parquet → pv_fault_diag.training_samples。

        委托 PVFaultRepository.ingest_parquet() 执行，内置 INSERT IGNORE 去重，
        按复合键 (time, site_id, device_id, branch_id) 幂等写入。

        目标 schema 不存在时 raise MigrationError。

        Args:
            parquet_path: 相对于 backend-service/ 的 Parquet 文件路径，
                          None 时使用默认路径
                          ../fault-diag-algo-release-3.1/相关数据/all_labeled_combined.parquet

        Returns:
            {"migrated": n, "skipped": m, "files_processed": k, "elapsed_s": t}
        """
        self._check_pv_schema()

        start = time.time()

        if parquet_path is None:
            resolved = _DEFAULT_PARQUET_PATH
        else:
            resolved = _BACKEND_DIR / parquet_path

        if not resolved.exists():
            logger.warning("migrate_parquet: 文件不存在，跳过: %s", resolved)
            return {
                "migrated": 0,
                "skipped": 0,
                "files_processed": 0,
                "elapsed_s": round(time.time() - start, 3),
            }

        try:
            result = self._pv_repo.ingest_parquet(str(resolved))
        except Exception as exc:
            logger.error("migrate_parquet: 导入失败 %s: %s", resolved, exc)
            return {
                "migrated": 0,
                "skipped": 0,
                "files_processed": 1,
                "elapsed_s": round(time.time() - start, 3),
            }

        elapsed = round(time.time() - start, 3)
        migrated = result.get("inserted", 0)
        skipped = result.get("skipped", 0)
        logger.info(
            "migrate_parquet: migrated=%d skipped=%d elapsed=%.3fs",
            migrated,
            skipped,
            elapsed,
        )
        return {
            "migrated": migrated,
            "skipped": skipped,
            "files_processed": 1,
            "elapsed_s": elapsed,
        }


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m services.db.migration_tool",
        description="将历史 JSON/SQLite/Parquet 数据迁移到 MySQL 数据库",
    )
    parser.add_argument(
        "--precision-ops",
        action="store_true",
        help=(
            "迁移 precision_ops JSON 文件"
            "（accuracy_metrics, prelaunch_queue, version_registry）"
        ),
    )
    parser.add_argument(
        "--predictions-db",
        action="store_true",
        help="迁移 predictions.db SQLite → load_forecast.prediction_result",
    )
    parser.add_argument(
        "--parquet",
        action="store_true",
        help="迁移 all_labeled_combined.parquet → pv_fault_diag.training_samples",
    )
    return parser


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = _build_parser()
    args = parser.parse_args()

    if not any([args.precision_ops, args.predictions_db, args.parquet]):
        parser.print_help()
        sys.exit(0)

    # 延迟导入，避免在 __main__ 以外的上下文循环依赖
    from services.db.config import DBConfig  # noqa: PLC0415
    from services.db.adapter import DBAdapter  # noqa: PLC0415

    cfg = DBConfig()
    adapter = DBAdapter(cfg)
    tool = MigrationTool(adapter)

    try:
        if args.precision_ops:
            r = tool.migrate_precision_ops_json()
            print(f"[precision-ops] 迁移完成: {r}")
        if args.predictions_db:
            r = tool.migrate_predictions_db()
            print(f"[predictions-db] 迁移完成: {r}")
        if args.parquet:
            r = tool.migrate_parquet()
            print(f"[parquet] 迁移完成: {r}")
    except MigrationError as exc:
        logger.error("迁移中止：目标 schema 不存在或不可访问: %s", exc)
        sys.exit(1)
    finally:
        adapter.dispose()
