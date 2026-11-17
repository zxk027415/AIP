# @AI_GENERATED
# -*- coding: utf-8 -*-
"""实时点路径 Phase 0 POC 构建 CLI。

PowerShell 示例：

仅校验，不连接 DB、不写文件：
  python scripts/build_realtime_point_poc.py --source fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet --index backend-service/data/seq_annotation_datasets/snapshots/snap-20260818050952-ee3323/meta.parquet --context-length 72 --dry-run

构建不可变快照和 W=72 因果窗口：
  python scripts/build_realtime_point_poc.py --source fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet --index backend-service/data/seq_annotation_datasets/snapshots/snap-20260818050952-ee3323/meta.parquet --context-length 72 --build-windows

从已有快照单独构建窗口：
  python scripts/build_realtime_point_poc.py --snapshot-dir backend-service/data/realtime_point_poc/snapshots/point-poc-... --context-length 72 --build-windows
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s — %(message)s")
logger = logging.getLogger("build_realtime_point_poc")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="构建实时点路径 Phase 0 不可变快照和因果窗口")
    parser.add_argument(
        "--source",
        help="source — 外部共享 parquet 的项目根相对路径；从已有快照构建窗口时可省略",
    )
    parser.add_argument(
        "--index",
        help="index — 374 original 设备日 meta.parquet 的项目根相对路径",
    )
    parser.add_argument(
        "--output-root",
        help="output_root — 快照输出根的项目根相对路径；默认写入点 POC 独立 snapshots 目录",
    )
    parser.add_argument(
        "--dataset-output-root",
        help="dataset_output_root — 因果窗口数据集输出根的项目根相对路径",
    )
    parser.add_argument(
        "--snapshot-dir",
        help="snapshot_dir — 已有不可变快照的项目根相对路径；仅配合 --build-windows 使用",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="dry_run — 只检查索引、上下文测量和源摘要；禁止 DB 和任何文件写入",
    )
    parser.add_argument(
        "--snapshot-only",
        action="store_true",
        help="snapshot_only — 只构建快照；这是未传 --build-windows 时的默认行为",
    )
    parser.add_argument(
        "--build-windows",
        action="store_true",
        help="build_windows — 新快照发布后或从 --snapshot-dir 构建独立因果窗口数据集",
    )
    parser.add_argument(
        "--context-length",
        type=int,
        default=72,
        help="context_length — 快照前置历史上限和窗口长度，默认 72 槽（6 小时）",
    )
    parser.add_argument(
        "--training-stride",
        type=int,
        default=6,
        help="training_stride — 训练窗口目标时刻步长，默认 6 槽（30 分钟）",
    )
    parser.add_argument(
        "--slot-minutes",
        type=int,
        default=5,
        help="slot_minutes — 时钟槽宽度，默认 5 分钟",
    )
    parser.add_argument(
        "--min-measured-ratio",
        type=float,
        default=0.6,
        help="min_measured_ratio — 窗口最低实测比例，默认 0.6",
    )
    parser.add_argument(
        "--max-forward-fill-slots",
        type=int,
        default=2,
        help="max_forward_fill_slots — 只用过去值前向填充的最大槽数，默认 2",
    )
    parser.add_argument(
        "--max-gap-multiplier",
        type=int,
        default=6,
        help="max_gap_multiplier — 单窗口允许的最长连续缺测槽数，默认 6",
    )
    parser.add_argument("--seed", type=int, default=42, help="seed — 设备隔离 split 的确定性种子")
    return parser


def _validate_mode(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.snapshot_only and args.build_windows:
        parser.error("--snapshot-only 与 --build-windows 互斥")
    if args.dry_run and (args.snapshot_dir or args.build_windows):
        parser.error("--dry-run 禁止与 --snapshot-dir 或 --build-windows 组合，避免意外写入")
    if args.snapshot_dir:
        if not args.build_windows:
            parser.error("--snapshot-dir 必须显式配合 --build-windows")
        return
    if not args.source or not args.index:
        parser.error("构建新快照或 dry-run 时必须同时提供 --source 和 --index")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _validate_mode(parser, args)

    snapshot_dir = args.snapshot_dir
    if snapshot_dir is None:
        from services.iterative_labeling.seq_annotation.point_poc_snapshot import build_snapshot

        snapshot_result = build_snapshot(
            source_path=args.source,
            index_path=args.index,
            output_root=args.output_root,
            context_length=args.context_length,
            slot_minutes=args.slot_minutes,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            print()
            print("=" * 68)
            print("DRY-RUN 校验通过")
            print("=" * 68)
            print(f"  original_count — 原始设备日数: {snapshot_result['original_count']}")
            print(f"  source_hit — 命中设备日数: {snapshot_result['source_hit']}")
            print(f"  source_rows — 快照测量行数: {snapshot_result['source_rows']}")
            print(f"  context_rows — 前一日上下文行数: {snapshot_result['context_rows']}")
            print(f"  source_sha256 — 外部源摘要: {snapshot_result['source_sha256']}")
            print("  db_connection — DB 连接: 未执行")
            print("  file_write — 文件写入: 未执行")
            return 0

        snapshot_dir = snapshot_result["snapshot_dir"]
        manifest = snapshot_result["manifest"]
        print()
        print("=" * 68)
        print("点路径不可变快照构建完成")
        print("=" * 68)
        print(f"  snapshot_dir — 快照目录: {snapshot_dir}")
        print(f"  measurement_rows — 测量行数: {manifest['measurement_rows']}")
        print(f"  point_label_rows — 逐点标签行数: {manifest['point_label_rows']}")
        print(f"  label_op_rows — 相关生效操作数: {manifest['label_op_rows']}")
        print(f"  label_snapshot_hash — 标签快照指纹: {manifest['label_snapshot_hash']}")

    if args.build_windows:
        from services.iterative_labeling.seq_annotation.causal_window_builder import build_causal_windows

        dataset_result = build_causal_windows(
            snapshot_dir=snapshot_dir,
            output_root=args.dataset_output_root,
            window_size=args.context_length,
            stride=args.training_stride,
            slot_minutes=args.slot_minutes,
            min_measured_ratio=args.min_measured_ratio,
            max_forward_fill_slots=args.max_forward_fill_slots,
            max_gap_multiplier=args.max_gap_multiplier,
            seed=args.seed,
        )
        audit = dataset_result["build_report"]["causal_audit"]
        print()
        print("=" * 68)
        print("点路径因果窗口数据集构建完成")
        print("=" * 68)
        print(f"  dataset_dir — 数据集目录: {dataset_result['dataset_dir']}")
        print(f"  window_count — 窗口总数: {dataset_result['window_count']}")
        print(f"  split_counts — 各集合窗口数: {dataset_result['split_counts']}")
        print(
            "  causal_audit — 数据层因果审计: "
            f"{audit['passed_device_days']}/{audit['tested_device_days']} passed"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
