# @AI_GENERATED
"""激活 load_forecast 运营指标，并可选按「自然日」推进威海 CSV mock 喂数。

防数据穿越（硬约束）：
  1. 平台预测路径禁止直读 CSV；只能读 mock 公司库里「已喂出」的行。
  2. --feed-days 每次只推进 1 个完整业务日，禁止一次性灌入全部历史。
  3. 日滚仍走 lf_daily_rolling 的 gap-1：训练/特征硬截止 T-1，预测 T+1。
  4. --activate-metrics 只改 accuracy_metrics.json 状态，便于劣化注入演示；
     它不写入未来真值、不改 StationData，也不得当作「已通过真实回填验收」。

用法（在 backend-service/ 下，conda cp_web）：
  set PYTHONPATH=.
  python scripts/bootstrap_load_forecast_slot.py --activate-metrics
  python scripts/bootstrap_load_forecast_slot.py --feed-days 40
  python scripts/bootstrap_load_forecast_slot.py --activate-metrics --feed-days 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def activate_metrics(slot: str, min_valid_cycles: int) -> dict:
    from services.accuracy_operations.degradation_experiment import activate_slot_metrics_from_deployment
    from services.deployment import DeploymentSlotStore
    from services.precision_ops.accuracy_tracker import AccuracyTracker

    tracker = AccuracyTracker()
    slot_store = DeploymentSlotStore()
    result = activate_slot_metrics_from_deployment(
        slot=slot,
        tracker=tracker,
        slot_store=slot_store,
        min_valid_cycles=min_valid_cycles,
    )
    print(f"[activate] slot={slot} activated={result.get('count')}")
    print(
        "[activate] 注意：这是运营演示前置（指标 active），"
        "不是真实回填证据；真实链路仍须日滚 gap-1 + backfill。"
    )
    for item in result.get("activated") or []:
        print(
            f"  - {item['workflow_id']}@{item['version_tag']} "
            f"mape={item['rolling_mape']} cycles={item['valid_cycle_count']}"
        )
    return result


def feed_days(slot: str, days: int) -> None:
    """按自然日推进 mock；每天最多暴露 1 个业务日，避免未来行提前可见。"""
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    from services.db.datasources.local_db_mock import (
        LocalDbMockDataSource,
        build_default_mock_feeder,
    )
    from services.scheduler.tasks.load_forecast_tasks import make_data_pull_task

    if days > 400:
        raise ValueError(
            f"--feed-days={days} 过大；请分批推进，避免误把长时间跨度当成一次灌库"
        )

    adapter = DBAdapter(DBConfig())
    feeder = build_default_mock_feeder(adapter)
    feeder.ensure_tables()
    source = LocalDbMockDataSource(adapter)
    # before_pull=None：喂数与拉取分离，平台侧只拉已暴露水位
    pull = make_data_pull_task(source, None, slot)

    for i in range(max(0, days)):
        preview = feeder.preview_next_feed()
        exhausted = bool(getattr(preview, "exhausted", False))
        if hasattr(preview, "as_dict"):
            exhausted = bool(preview.as_dict().get("exhausted"))
        elif isinstance(preview, dict):
            exhausted = bool(preview.get("exhausted"))
        if exhausted:
            print(f"[feed] day {i + 1}/{days}: CSV exhausted, stop")
            break

        result = feeder.feed_next_batch()
        # feed_next_batch 对调度器可能返回 int；手动路径返回 MockFeedResult
        if hasattr(result, "as_dict"):
            as_dict = result.as_dict()
            print(
                f"[feed] day {i + 1}/{days}: business_date={as_dict.get('business_date')} "
                f"rows={as_dict.get('inserted_row_count')} complete={as_dict.get('is_complete_day')}"
            )
            if as_dict.get("exhausted"):
                print("[feed] source exhausted after this day")
                break
        else:
            print(f"[feed] day {i + 1}/{days}: inserted={result}")

        try:
            pull_result = pull()
            print(f"[pull] {pull_result}")
        except Exception as exc:
            print(f"[pull] failed (non-fatal): {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap load_forecast ops（禁止数据穿越：按日喂数 + gap-1 日滚）"
    )
    parser.add_argument("--slot", default="load_forecast")
    parser.add_argument(
        "--activate-metrics",
        action="store_true",
        help="演示用：把部署版本指标写成 active（不写入未来真值，不作真实回填验收）",
    )
    parser.add_argument("--min-valid-cycles", type=int, default=3)
    parser.add_argument(
        "--feed-days",
        type=int,
        default=0,
        help="按自然日推进 mock 喂数+pull 的天数（每天 1 日，禁止整表灌入）",
    )
    args = parser.parse_args()

    if not args.activate_metrics and args.feed_days <= 0:
        parser.print_help()
        print("\n至少指定 --activate-metrics 或 --feed-days N")
        return 2

    if args.activate_metrics:
        activate_metrics(args.slot, args.min_valid_cycles)
    if args.feed_days > 0:
        try:
            feed_days(args.slot, args.feed_days)
        except Exception as exc:
            print(f"[feed] aborted: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# @AI_GENERATED: end
