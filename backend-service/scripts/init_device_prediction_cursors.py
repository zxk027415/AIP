# @AI_GENERATED
"""
scripts/init_device_prediction_cursors.py — 初始化 device_prediction_cursor 表

从 training_samples 取所有去重的设备三元组 (site_id, device_id, branch_id)，
批量 upsert 到 device_prediction_cursor，last_predicted_time 统一设为
2021-11-24T23:50:00（与历史全局游标 prediction_cursor.json 的最后预测时刻对齐）。

目的：确保 pv_prediction 任务切换到按设备游标查询后，不会因为游标为空而
把 training_samples 里所有历史数据都重新跑一遍预测（那会产出大量重复的
PredictionRecord）。

幂等：已存在游标的设备行不会被覆盖（ON DUPLICATE KEY 只在 NULL 时写入）。
所以可以安全地多次运行：只补填缺失行，不改动已有游标。

用法：
  cd backend-service
  python scripts/init_device_prediction_cursors.py          # 实际写入
  python scripts/init_device_prediction_cursors.py --dry-run # 只打印，不写库
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.mysql import insert as mysql_insert

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.models.pv_fault import DevicePredictionCursor

# 与历史全局游标 prediction_cursor.json 对齐的初始时刻
_INITIAL_CURSOR_TIME = datetime(2021, 11, 24, 23, 50, 0)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run(dry_run: bool = False) -> None:
    adapter = DBAdapter(DBConfig())

    with adapter.get_sync_session() as session:
        # 从 training_samples 取所有去重设备三元组
        rows = session.execute(
            text(
                "SELECT DISTINCT site_id, device_id, branch_id FROM training_samples"
            )
        ).fetchall()

    if not rows:
        logger.info("training_samples 为空，没有设备需要初始化游标")
        adapter.dispose()
        return

    logger.info("从 training_samples 找到 %d 个设备三元组", len(rows))

    if dry_run:
        logger.info("--dry-run 模式，不写库，前 5 条示例：")
        for r in rows[:5]:
            logger.info("  site=%s device=%s branch=%s  → last_predicted_time=%s",
                        r[0], r[1], r[2], _INITIAL_CURSOR_TIME.isoformat())
        logger.info("共 %d 条，取消 --dry-run 后实际写入", len(rows))
        adapter.dispose()
        return

    now = datetime.utcnow()
    records = [
        {
            "site_id": r[0],
            "device_id": r[1],
            "branch_id": r[2],
            "last_predicted_time": _INITIAL_CURSOR_TIME,
            "last_predicted_at": None,
            "model_version_id": None,
            "updated_at": now,
        }
        for r in rows
    ]

    _BATCH = 500
    inserted = 0
    skipped = 0

    with adapter.get_sync_session() as session:
        for i in range(0, len(records), _BATCH):
            batch = records[i: i + _BATCH]
            stmt = mysql_insert(DevicePredictionCursor).values(batch)
            # 已存在的行（同样的主键）不覆盖——幂等保证
            stmt = stmt.on_duplicate_key_update(
                updated_at=stmt.inserted.updated_at,
                # 只有游标为 NULL（从未被任何任务写入）时才写初始值
                last_predicted_time=text(
                    "IF(device_prediction_cursor.last_predicted_time IS NULL, "
                    "VALUES(last_predicted_time), "
                    "device_prediction_cursor.last_predicted_time)"
                ),
            )
            result = session.execute(stmt)
            # MySQL ON DUPLICATE KEY UPDATE：rowcount=1 新插，rowcount=2 更新，rowcount=0 未变
            # 我们只统计真正被更新/插入的行
            inserted += result.rowcount

    skipped = len(records) - inserted
    logger.info(
        "完成：%d 条设备游标已写入或更新（rowcount）；另有 %d 条行为未变（已有非空游标）",
        inserted, max(0, skipped),
    )
    adapter.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="初始化 device_prediction_cursor 表")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
# @AI_GENERATED: end
