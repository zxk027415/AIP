# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
scripts/build_seq_annotation_dataset.py — 构建/重建序列标注数据集

用法::

    # 构建（默认参数）
    python scripts/build_seq_annotation_dataset.py

    # 自定义
    python scripts/build_seq_annotation_dataset.py --max-fault 200 --max-normal 300

    # 放宽/收紧网格覆盖门槛（默认 173/288 ≈ 60%）
    python scripts/build_seq_annotation_dataset.py --min-occupied-slots 216

产出目录: data/seq_annotation_datasets/snapshots/<version>/
  - dataset.npz       X[N,288,3]（value / i_cal / is_measured）+ Y[N,288]
  - meta.parquet      每条序列的设备信息与网格占有率
  - build_config.json 构建参数（含 grid_contract）
  - build_report.json 统计报告

序列长度固定为 288（自然日 5 分钟槽位），不可配置：网格对齐依赖「下标 i = 当天第 i
个 5 分钟槽」这一契约，改长度会破坏位置语义。要控制收多少天，请调覆盖率门槛。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.iterative_labeling.seq_annotation.grid_align import (  # noqa: E402
    MAX_DAYTIME_GAP_SLOTS,
    MIN_DAYTIME_OCCUPANCY,
    MIN_OCCUPIED_SLOTS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("build_dataset")


def main() -> int:
    ap = argparse.ArgumentParser(description="构建序列标注数据集")
    ap.add_argument("--max-fault", type=int, default=200, help="每个故障 label 最多整天故障天数")
    ap.add_argument("--max-normal", type=int, default=300, help="正常天最多取多少")
    ap.add_argument(
        "--min-occupied-slots",
        type=int,
        default=MIN_OCCUPIED_SLOTS,
        help=f"288 槽里至少多少个实测槽（默认 {MIN_OCCUPIED_SLOTS} ≈ 60%%）",
    )
    ap.add_argument(
        "--min-daytime-occupancy",
        type=float,
        default=MIN_DAYTIME_OCCUPANCY,
        help=f"白天时段实测占有率下限（默认 {MIN_DAYTIME_OCCUPANCY}）",
    )
    ap.add_argument(
        "--max-daytime-gap-slots",
        type=int,
        default=MAX_DAYTIME_GAP_SLOTS,
        help=f"白天允许的最长连续空槽（默认 {MAX_DAYTIME_GAP_SLOTS} 槽 = 30 分钟）",
    )
    ap.add_argument("--seed", type=int, default=42, help="随机种子")
    args = ap.parse_args()

    from services.iterative_labeling.seq_annotation.dataset_builder import build_dataset

    result = build_dataset(
        max_whole_day_per_label=args.max_fault,
        max_normal_days=args.max_normal,
        min_occupied_slots=args.min_occupied_slots,
        min_daytime_occupancy=args.min_daytime_occupancy,
        max_daytime_gap_slots=args.max_daytime_gap_slots,
        random_state=args.seed,
    )

    report = result["report"]
    print()
    print("=" * 70)
    print("数据集构建完成")
    print("=" * 70)
    print(f"  版本: {result['version']}")
    print(f"  路径: {result['output_dir']}")
    print(f"  总序列数: {report['n_sequences']}")
    print(f"  类别数: {report['n_classes']}")
    print(f"  seq_len: {report['seq_len']}")
    print(f"  通道: {report.get('channels')}")
    print(f"  故障点占比: {report['fault_point_ratio']:.1%}")
    print(f"  全天网格验证: {report.get('full_day_grid_validated')}")
    print(
        f"  原始序列中全天天数: {report.get('n_full_day_original')} / {report.get('n_original')}"
    )
    print()
    print("  数据来源:")
    for dt, cnt in report["data_type_counts"].items():
        print(f"    {dt}: {cnt}")
    print()
    skip_reasons = (report.get("quality_filter") or {}).get("skip_reasons") or {}
    if skip_reasons:
        print("  网格对齐拒绝原因:")
        for reason, cnt in skip_reasons.items():
            print(f"    {reason}: {cnt}")
        print()
    print("  类别分布 (点数):")
    for lbl in sorted(report["class_distribution"], key=lambda k: int(k)):
        print(f"    label={int(lbl):>3}: {report['class_distribution'][lbl]:>8} 点")
    print()
    print(f"  label_snapshot_hash: {report['label_snapshot_hash']}")
    print(f"  （下次 point_labels 变化后重新构建，hash 会变）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
