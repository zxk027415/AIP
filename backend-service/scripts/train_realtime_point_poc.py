# @AI_GENERATED
# -*- coding: utf-8 -*-
"""实时点路径 Phase 0 Causal TCN 训练 CLI。

PowerShell smoke 示例：
  python scripts/train_realtime_point_poc.py --dataset-dir backend-service/data/realtime_point_poc/datasets/point-w72-20260820085123-af8aae18 --target-mode last_point --epochs 1 --max-train-batches 2 --device cpu

  python scripts/train_realtime_point_poc.py --dataset-dir backend-service/data/realtime_point_poc/datasets/point-w72-20260820085123-af8aae18 --target-mode burn_in_multi_point --burn-in-points 60 --epochs 1 --max-train-batches 2 --device cpu
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s — %(message)s")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="训练实时点路径 Phase 0 Causal TCN")
    parser.add_argument("--dataset-dir", required=True, help="dataset_dir — 因果窗口数据集的项目根相对路径")
    parser.add_argument(
        "--output-root",
        default="backend-service/data/models/realtime_point_poc",
        help="output_root — 模型工件根目录的项目根相对路径",
    )
    parser.add_argument(
        "--target-mode",
        choices=["last_point", "burn_in_multi_point"],
        default="last_point",
        help="target_mode — 仅末点监督或 burn-in 后多点监督",
    )
    parser.add_argument("--burn-in-points", type=int, default=60, help="burn_in_points — 多点模式开始计 loss 的位置")
    parser.add_argument("--epochs", type=int, default=20, help="epochs — 训练轮数；按 val_loss 留最佳 checkpoint")
    parser.add_argument("--batch-size", type=int, default=64, help="batch_size — 批大小")
    parser.add_argument("--learning-rate", type=float, default=1e-3, help="learning_rate — AdamW 学习率")
    parser.add_argument("--hidden-channels", type=int, default=32, help="hidden_channels — TCN 隐藏通道数")
    parser.add_argument("--dropout", type=float, default=0.1, help="dropout — 残差块 dropout")
    parser.add_argument("--seed", type=int, default=42, help="seed — 可复现实验种子")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto", help="device — 训练设备")
    parser.add_argument(
        "--max-train-batches",
        type=int,
        default=None,
        help="max_train_batches — 每 epoch 最多训练 batch；仅 smoke 使用",
    )
    parser.add_argument(
        "--class-weight-mode",
        choices=["none", "balanced"],
        default="balanced",
        help="class_weight_mode — none 均等权重；balanced 按 train 监督点反频率加权",
    )
    parser.add_argument(
        "--loss-slot-mask",
        choices=["all", "daylight"],
        default="daylight",
        help="loss_slot_mask — all 用全部监督槽；daylight 只用 is_daylight=1 的槽",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    from services.iterative_labeling.realtime_point.trainer import RealtimePointTrainer

    trainer = RealtimePointTrainer(
        target_mode=args.target_mode,
        burn_in_points=args.burn_in_points,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        hidden_channels=args.hidden_channels,
        dropout=args.dropout,
        seed=args.seed,
        device=args.device,
        max_train_batches=args.max_train_batches,
        class_weight_mode=args.class_weight_mode,
        loss_slot_mask=args.loss_slot_mask,
    )
    result = trainer.train(dataset_dir=args.dataset_dir, output_root=args.output_root)
    print()
    print("=" * 72)
    print("实时点 Causal TCN 训练完成")
    print("=" * 72)
    print(f"  model_ref — 模型引用: {result['model_ref']}")
    print(f"  model_path — 工件目录: {result['model_path']}")
    print(f"  target_mode — 监督模式: {result['target_mode']}")
    print(f"  promotion_eligible — 是否可晋升: {result['promotion_eligible']}")
    print("  test_metrics — 测试指标:")
    print(json.dumps(result["test_metrics"], ensure_ascii=False, indent=2))
    print("  causal_audit — 模型因果审计:")
    print(json.dumps(result["causal_audit"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
