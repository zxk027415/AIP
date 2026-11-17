# @AI_GENERATED
# -*- coding: utf-8 -*-
"""在新点路径快照上做小网格搜索，按 val 白天 binary F1 选配置。

固定：balanced 类别权重、daylight loss、seed=42。
感受野约 61 槽，因此 W=24/36 只跑 last_point；burn_in 只在 W=72。

  python scripts/run_realtime_point_param_search.py
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s — %(message)s")
logger = logging.getLogger("rtpoint_hparam")

SNAPSHOT = "backend-service/data/realtime_point_poc/snapshots/point-poc-20260821044728-684bf7f6"
W72 = "backend-service/data/realtime_point_poc/datasets/point-w72-20260821044748-96c36c53"
OUTPUT_ROOT = "backend-service/data/models/realtime_point_poc"
EXPERIMENT_ROOT = BACKEND / "data" / "realtime_point_poc" / "experiments"


def _slice(metrics: Dict[str, Any], name: str) -> Dict[str, Any]:
    daylight = metrics.get("daylight_subset") or {}
    return {
        f"{name}_binary_f1": metrics.get("binary_f1"),
        f"{name}_macro_f1": metrics.get("point_macro_f1"),
        f"{name}_accuracy": metrics.get("point_accuracy"),
        f"{name}_iou": metrics.get("fault_mask_iou"),
        f"{name}_daylight_binary_f1": daylight.get("binary_f1"),
        f"{name}_daylight_macro_f1": daylight.get("point_macro_f1"),
        f"{name}_daylight_accuracy": daylight.get("point_accuracy"),
        f"{name}_daylight_iou": daylight.get("fault_mask_iou"),
        f"{name}_segment_precision": (metrics.get("raw_labeled_segment_proxy") or {}).get("segment_precision_proxy"),
        f"{name}_segment_recall": (metrics.get("raw_labeled_segment_proxy") or {}).get("segment_recall_proxy"),
    }


def _score(row: Dict[str, Any]) -> Tuple[float, float, float]:
    return (
        float(row.get("val_daylight_binary_f1") or 0.0),
        float(row.get("val_daylight_macro_f1") or 0.0),
        -float(row.get("best_val_loss") or 1e9),
    )


def _ensure_window(snapshot: str, window_size: int) -> str:
    from services.iterative_labeling.seq_annotation.causal_window_builder import build_causal_windows

    result = build_causal_windows(snapshot_dir=snapshot, window_size=window_size, stride=6)
    dataset_dir = result["dataset_dir"]
    logger.info("窗口 W=%s 数据集: %s count=%s", window_size, dataset_dir, result["window_count"])
    return dataset_dir


def _train(trial: Dict[str, Any], dataset_dir: str) -> Dict[str, Any]:
    from services.iterative_labeling.realtime_point.trainer import RealtimePointTrainer

    trainer = RealtimePointTrainer(
        target_mode=trial["target_mode"],
        burn_in_points=int(trial.get("burn_in_points") or 60),
        epochs=int(trial["epochs"]),
        batch_size=64,
        learning_rate=float(trial["learning_rate"]),
        hidden_channels=int(trial["hidden_channels"]),
        dropout=0.1,
        seed=42,
        device="auto",
        class_weight_mode="balanced",
        loss_slot_mask="daylight",
    )
    result = trainer.train(dataset_dir=dataset_dir, output_root=OUTPUT_ROOT)
    row = {
        **trial,
        "dataset_dir": dataset_dir,
        "model_ref": result["model_ref"],
        "model_path": result["model_path"],
        "best_epoch": result["best_epoch"],
        "best_val_loss": result["best_val_loss"],
        "history": result["history"],
        **_slice(result["val_metrics"], "val"),
        **_slice(result["test_metrics"], "test"),
    }
    logger.info(
        "trial=%s best_epoch=%s val_daylight_binary_f1=%.4f test_daylight_binary_f1=%.4f",
        trial["name"],
        row["best_epoch"],
        row["val_daylight_binary_f1"],
        row["test_daylight_binary_f1"],
    )
    return row


def main() -> int:
    w72 = W72
    w36 = _ensure_window(SNAPSHOT, 36)
    w24 = _ensure_window(SNAPSHOT, 24)

    trials: List[Dict[str, Any]] = [
        {
            "name": "w72_last_lr1e3_h32_e20",
            "window_size": 72,
            "dataset_dir": w72,
            "target_mode": "last_point",
            "learning_rate": 1e-3,
            "hidden_channels": 32,
            "epochs": 20,
        },
        {
            "name": "w72_last_lr3e4_h32_e20",
            "window_size": 72,
            "dataset_dir": w72,
            "target_mode": "last_point",
            "learning_rate": 3e-4,
            "hidden_channels": 32,
            "epochs": 20,
        },
        {
            "name": "w36_last_lr1e3_h32_e20",
            "window_size": 36,
            "dataset_dir": w36,
            "target_mode": "last_point",
            "learning_rate": 1e-3,
            "hidden_channels": 32,
            "epochs": 20,
        },
        {
            "name": "w24_last_lr1e3_h32_e20",
            "window_size": 24,
            "dataset_dir": w24,
            "target_mode": "last_point",
            "learning_rate": 1e-3,
            "hidden_channels": 32,
            "epochs": 20,
        },
        {
            "name": "w72_burnin60_lr1e3_h32_e20",
            "window_size": 72,
            "dataset_dir": w72,
            "target_mode": "burn_in_multi_point",
            "burn_in_points": 60,
            "learning_rate": 1e-3,
            "hidden_channels": 32,
            "epochs": 20,
        },
        {
            "name": "w72_last_lr1e3_h64_e20",
            "window_size": 72,
            "dataset_dir": w72,
            "target_mode": "last_point",
            "learning_rate": 1e-3,
            "hidden_channels": 64,
            "epochs": 20,
        },
    ]

    rows: List[Dict[str, Any]] = []
    for trial in trials:
        rows.append(_train(trial, trial["dataset_dir"]))

    ranked = sorted(rows, key=_score, reverse=True)
    winner = ranked[0]
    report = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "selection": "max val_daylight_binary_f1, then val_daylight_macro_f1, then min best_val_loss",
        "fixed": {
            "class_weight_mode": "balanced",
            "loss_slot_mask": "daylight",
            "batch_size": 64,
            "dropout": 0.1,
            "seed": 42,
            "snapshot": SNAPSHOT,
        },
        "winner": {
            "name": winner["name"],
            "model_ref": winner["model_ref"],
            "window_size": winner["window_size"],
            "target_mode": winner["target_mode"],
            "learning_rate": winner["learning_rate"],
            "hidden_channels": winner["hidden_channels"],
            "epochs": winner["epochs"],
            "best_epoch": winner["best_epoch"],
            "val_daylight_binary_f1": winner["val_daylight_binary_f1"],
            "test_daylight_binary_f1": winner["test_daylight_binary_f1"],
        },
        "trials": [
            {
                **{key: value for key, value in row.items() if key != "history"},
                "history_val_loss": [item["val_loss"] for item in row["history"]],
            }
            for row in ranked
        ],
    }
    EXPERIMENT_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = EXPERIMENT_ROOT / f"hparam-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["winner"], ensure_ascii=False, indent=2))
    print(f"report={out_path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
