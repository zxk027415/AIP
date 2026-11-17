# @AI_GENERATED
# -*- coding: utf-8 -*-
"""实时点路径 Phase 0 Causal TCN 训练、评估、因果审计和工件发布。"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import random
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, f1_score
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from .model import CausalTCNRealtime

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parents[3]
_PROJECT_ROOT = _BACKEND.parent
_DEFAULT_OUTPUT_ROOT = _BACKEND / "data" / "models" / "realtime_point_poc"
IGNORE_LABEL = -1
_DEVICE_COLUMNS = ["site_id", "device_id", "branch_id"]
_ALLOWED_TARGET_MODES = {"last_point", "burn_in_multi_point"}
_ALLOWED_CLASS_WEIGHT_MODES = {"none", "balanced"}
_ALLOWED_LOSS_SLOT_MASKS = {"all", "daylight"}


def _normalise_relative_arg(path: str, param_name: str) -> str:
    if not path or Path(path).is_absolute() or os.path.isabs(path):
        raise ValueError(f"参数 {param_name} 必须是项目根相对路径: {path!r}")
    normalised = Path(path.replace("\\", "/")).as_posix()
    resolved = (_PROJECT_ROOT / normalised).resolve()
    try:
        resolved.relative_to(_PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"参数 {param_name} 越界项目根: {path}") from exc
    return normalised


def _resolve_relative(path: str, param_name: str) -> Path:
    return (_PROJECT_ROOT / _normalise_relative_arg(path, param_name)).resolve()


def _to_project_relative(path: Path) -> str:
    return path.resolve().relative_to(_PROJECT_ROOT.resolve()).as_posix()


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_write(path: Path, payload: Dict[str, Any]) -> None:
    tagged = {"_comment": "@AI_GENERATED", **payload, "_comment_end": "@AI_GENERATED: end"}
    path.write_text(json.dumps(tagged, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


class FixedRobustScaler:
    """只在 train split 拟合的固定通道 scaler，不使用单窗口未来统计。"""

    _ALLOWED_TRANSFORMS = frozenset({"identity", "robust", "log1p_robust"})
    _ROBUST_SCALE_FLOOR = 1e-6
    _LOG1P_SCALE_FLOOR = float(np.log(2.0))

    def __init__(self, channels: Sequence[str]) -> None:
        self.channels = list(channels)
        self.center = np.zeros(len(self.channels), dtype=np.float32)
        self.scale = np.ones(len(self.channels), dtype=np.float32)
        self.transforms = ["identity"] * len(self.channels)
        self._fitted = False

    def fit(self, x_train: np.ndarray) -> "FixedRobustScaler":
        if x_train.ndim != 3 or x_train.shape[-1] != len(self.channels):
            raise ValueError("FixedRobustScaler 输入形状与 channels 不一致")
        measured_index = self.channels.index("is_measured")
        measured_mask = x_train[:, :, measured_index] > 0.5
        for channel_name in ["value", "i_cal"]:
            index = self.channels.index(channel_name)
            values = x_train[:, :, index][measured_mask]
            self._fit_channel(index, values, transform="robust")
        if "time_since_measured" in self.channels:
            index = self.channels.index("time_since_measured")
            values = np.log1p(np.maximum(x_train[:, :, index].reshape(-1), 0.0))
            self._fit_channel(index, values, transform="log1p_robust")
        self._fitted = True
        return self

    def _fit_channel(self, index: int, values: np.ndarray, *, transform: str) -> None:
        finite = np.asarray(values, dtype=np.float64)
        finite = finite[np.isfinite(finite)]
        if finite.size == 0:
            raise ValueError(f"归一化通道 {self.channels[index]} 没有有限 train 值")
        q25, median, q75 = np.percentile(finite, [25.0, 50.0, 75.0])
        minimum_scale = (
            self._LOG1P_SCALE_FLOOR
            if transform == "log1p_robust"
            else self._ROBUST_SCALE_FLOOR
        )
        self.center[index] = float(median)
        self.scale[index] = float(max(q75 - q25, minimum_scale))
        self.transforms[index] = transform

    def transform(self, x: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("FixedRobustScaler 尚未拟合")
        if x.ndim != 3 or x.shape[-1] != len(self.channels):
            raise ValueError("FixedRobustScaler 输入形状与持久化 channels 不一致")
        out = np.asarray(x, dtype=np.float32).copy()
        for index, transform in enumerate(self.transforms):
            if transform == "identity":
                continue
            values = out[:, :, index]
            if transform == "log1p_robust":
                values = np.log1p(np.maximum(values, 0.0))
            out[:, :, index] = (values - self.center[index]) / self.scale[index]
        if not np.isfinite(out).all():
            raise ValueError("FixedRobustScaler 输出包含非有限值，拒绝静默替换")
        return out.astype(np.float32)

    def state_dict(self) -> Dict[str, Any]:
        if not self._fitted:
            raise RuntimeError("FixedRobustScaler 尚未拟合")
        return {
            "type": "train_only_fixed_robust",
            "channels": self.channels,
            "center": self.center.tolist(),
            "scale": self.scale.tolist(),
            "transforms": self.transforms,
            "scale_floor_by_transform": {
                "robust": self._ROBUST_SCALE_FLOOR,
                "log1p_robust": self._LOG1P_SCALE_FLOOR,
            },
        }

    @classmethod
    def from_state_dict(cls, state: Dict[str, Any]) -> "FixedRobustScaler":
        """严格恢复并校验持久化 scaler，坏工件 fail closed。"""
        if not isinstance(state, dict) or state.get("type") != "train_only_fixed_robust":
            raise ValueError("不支持的 FixedRobustScaler state")
        channels = state.get("channels")
        center = np.asarray(state.get("center"), dtype=np.float32)
        scale = np.asarray(state.get("scale"), dtype=np.float32)
        transforms = state.get("transforms")
        if not isinstance(channels, list) or not channels or len(set(channels)) != len(channels):
            raise ValueError("scaler channels 必须是非空、无重复列表")
        if not isinstance(transforms, list) or len(transforms) != len(channels):
            raise ValueError("scaler transforms 与 channels 长度不一致")
        if center.shape != (len(channels),) or scale.shape != (len(channels),):
            raise ValueError("scaler center/scale 与 channels 长度不一致")
        if not np.isfinite(center).all() or not np.isfinite(scale).all() or np.any(scale <= 0):
            raise ValueError("scaler center/scale 包含非法值")
        if any(not isinstance(channel, str) or not channel for channel in channels):
            raise ValueError("scaler channels 必须是非空字符串")
        if any(transform not in cls._ALLOWED_TRANSFORMS for transform in transforms):
            raise ValueError("scaler 包含不支持的 transform")
        for index, transform in enumerate(transforms):
            minimum_scale = (
                cls._LOG1P_SCALE_FLOOR
                if transform == "log1p_robust"
                else cls._ROBUST_SCALE_FLOOR
            )
            if transform != "identity" and float(scale[index]) < minimum_scale:
                raise ValueError(
                    f"scaler 通道 {channels[index]} 的 scale 低于 {transform} 安全下限"
                )
        scaler = cls(channels)
        scaler.center = center
        scaler.scale = scale
        scaler.transforms = [str(transform) for transform in transforms]
        scaler._fitted = True
        return scaler


class RealtimePointTrainer:
    """在已发布设备隔离 split 上训练并评估实时点 Causal TCN。"""

    def __init__(
        self,
        *,
        target_mode: str = "last_point",
        burn_in_points: int = 60,
        epochs: int = 3,
        batch_size: int = 64,
        learning_rate: float = 1e-3,
        hidden_channels: int = 32,
        dropout: float = 0.1,
        seed: int = 42,
        device: str = "auto",
        max_train_batches: Optional[int] = None,
        class_weight_mode: str = "balanced",
        loss_slot_mask: str = "all",
    ) -> None:
        if target_mode not in _ALLOWED_TARGET_MODES:
            raise ValueError(f"target_mode 必须属于 {sorted(_ALLOWED_TARGET_MODES)}")
        if class_weight_mode not in _ALLOWED_CLASS_WEIGHT_MODES:
            raise ValueError(f"class_weight_mode 必须属于 {sorted(_ALLOWED_CLASS_WEIGHT_MODES)}")
        if loss_slot_mask not in _ALLOWED_LOSS_SLOT_MASKS:
            raise ValueError(f"loss_slot_mask 必须属于 {sorted(_ALLOWED_LOSS_SLOT_MASKS)}")
        if epochs <= 0 or batch_size <= 0 or learning_rate <= 0:
            raise ValueError("epochs、batch_size、learning_rate 必须为正")
        if burn_in_points < 0:
            raise ValueError("burn_in_points 不能小于 0")
        if max_train_batches is not None and max_train_batches <= 0:
            raise ValueError("max_train_batches 必须为正或 None")
        self.target_mode = target_mode
        self.burn_in_points = int(burn_in_points)
        self.epochs = int(epochs)
        self.batch_size = int(batch_size)
        self.learning_rate = float(learning_rate)
        self.hidden_channels = int(hidden_channels)
        self.dropout = float(dropout)
        self.seed = int(seed)
        self.max_train_batches = max_train_batches
        self.class_weight_mode = class_weight_mode
        self.loss_slot_mask = loss_slot_mask
        self._daylight_index: Optional[int] = None
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise ValueError("请求 cuda，但当前 PyTorch 不可用 CUDA")
        self.device = torch.device(device)

    def train(self, *, dataset_dir: str, output_root: Optional[str] = None) -> Dict[str, Any]:
        started = time.time()
        self._set_seed()
        dataset_dir = _normalise_relative_arg(dataset_dir, "dataset_dir")
        output_root = (
            _normalise_relative_arg(output_root, "output_root")
            if output_root is not None
            else _to_project_relative(_DEFAULT_OUTPUT_ROOT)
        )
        dataset_path = _resolve_relative(dataset_dir, "dataset_dir")
        output_path = _resolve_relative(output_root, "output_root")
        x, y_business, meta, report, channels = self._load_dataset(dataset_path)
        if "is_daylight" not in channels:
            raise ValueError("数据集缺少 is_daylight 通道，无法按白天槽掩码 loss")
        self._daylight_index = channels.index("is_daylight")
        missing_value_policy = self._missing_value_policy(report)
        window_size = int(x.shape[1])
        if self.target_mode == "burn_in_multi_point" and self.burn_in_points >= window_size:
            raise ValueError("burn_in_points 必须小于窗口长度")

        split_indices = {
            split: np.flatnonzero(meta["split"].astype(str).to_numpy() == split)
            for split in ["train", "val", "test"]
        }
        if any(len(indices) == 0 for indices in split_indices.values()):
            raise ValueError("train/val/test 任一 split 为空")
        self._assert_device_isolation(meta)

        train_x = x[split_indices["train"]]
        train_y = y_business[split_indices["train"]]
        train_target_mask = self._target_mask_numpy(train_y, train_x)
        train_targets = train_y[train_target_mask]
        labels = sorted(int(value) for value in np.unique(train_targets))
        if len(labels) < 2 or 0 not in labels:
            raise ValueError("实时点 train 监督点至少需要正常类 0 和一个故障类")
        unseen_labels_by_split = self._unseen_labels_by_split(
            y_business,
            x,
            split_indices,
            labels,
        )
        evaluation_unseen = {
            split: detail
            for split, detail in unseen_labels_by_split.items()
            if split in {"val", "test"} and detail["point_count"] > 0
        }
        if evaluation_unseen:
            logger.warning(
                "val/test 出现 train 未见业务标签，已从评估目标中剔除（不加入类别空间）: %s",
                evaluation_unseen,
            )
            supported = np.asarray(labels, dtype=np.int64)
            for split in ("val", "test"):
                indices = split_indices[split]
                rows = y_business[indices]
                mask = self._target_mask_numpy(rows, x[indices])
                unseen = mask & ~np.isin(rows, supported)
                if unseen.any():
                    y_business[indices] = np.where(unseen, IGNORE_LABEL, rows)
            unseen_labels_by_split = self._unseen_labels_by_split(
                y_business,
                x,
                split_indices,
                labels,
            )
            evaluation_unseen = {
                split: detail
                for split, detail in unseen_labels_by_split.items()
                if split in {"val", "test"} and detail["point_count"] > 0
            }
            if evaluation_unseen:
                raise ValueError(
                    "val/test 存在 train 未见业务标签，按 fail-closed 契约拒绝训练: "
                    f"{evaluation_unseen}"
                )
        label_to_index = {label: index for index, label in enumerate(labels)}
        y_model = np.full(y_business.shape, IGNORE_LABEL, dtype=np.int64)
        for label, class_index in label_to_index.items():
            y_model[y_business == label] = class_index

        scaler = FixedRobustScaler(channels).fit(x[split_indices["train"]])
        x_scaled = scaler.transform(x)
        train_mask = self._target_mask_numpy(y_model[split_indices["train"]], train_x)
        class_counts = np.bincount(
            y_model[split_indices["train"]][train_mask], minlength=len(labels)
        ).astype(np.int64)
        if class_counts.sum() == 0 or np.count_nonzero(class_counts) < 2:
            raise ValueError("当前 target_mode 在 train split 中没有足够监督类别")
        class_weights = self._class_weights(class_counts, mode=self.class_weight_mode)

        model = CausalTCNRealtime(
            in_channels=x.shape[2],
            n_classes=len(labels),
            hidden_channels=self.hidden_channels,
            dilations=(1, 2, 4, 8),
            dropout=self.dropout,
        ).to(self.device)
        if self.target_mode == "burn_in_multi_point" and self.burn_in_points < model.receptive_field_points - 1:
            raise ValueError(
                f"burn_in_points={self.burn_in_points} 小于完整感受野要求 "
                f"{model.receptive_field_points - 1}"
            )

        criterion = nn.CrossEntropyLoss(
            weight=torch.from_numpy(class_weights).float().to(self.device),
            reduction="none",
        )
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.learning_rate, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.epochs)
        train_loader = self._loader(x_scaled, y_model, split_indices["train"], shuffle=True)
        val_loader = self._loader(x_scaled, y_model, split_indices["val"], shuffle=False)

        best_state: Optional[Dict[str, torch.Tensor]] = None
        best_val_loss = float("inf")
        best_epoch = -1
        history: List[Dict[str, Any]] = []
        optimizer_steps = 0
        for epoch in range(self.epochs):
            train_loss, steps = self._run_epoch(
                model,
                train_loader,
                criterion,
                optimizer=optimizer,
                max_batches=self.max_train_batches,
            )
            optimizer_steps += steps
            val_loss, _ = self._run_epoch(model, val_loader, criterion, optimizer=None)
            scheduler.step()
            if not np.isfinite(train_loss) or not np.isfinite(val_loss):
                raise RuntimeError(f"训练 loss 非有限值: train={train_loss}, val={val_loss}")
            history.append(
                {
                    "epoch": epoch + 1,
                    "train_loss": train_loss,
                    "val_loss": val_loss,
                    "optimizer_steps": steps,
                }
            )
            logger.info(
                "epoch=%d train_loss=%.6f val_loss=%.6f steps=%d",
                epoch + 1,
                train_loss,
                val_loss,
                steps,
            )
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_epoch = epoch + 1
                best_state = copy.deepcopy(model.state_dict())
        if optimizer_steps == 0 or best_state is None:
            raise RuntimeError("训练未产生任何 optimizer step 或 best checkpoint")
        model.load_state_dict(best_state)

        val_metrics = self._evaluate(
            model,
            x_scaled,
            y_business,
            meta,
            split_indices["val"],
            labels,
            slot_minutes=int(report["slot_minutes"]),
            stride=int(report["stride"]),
        )
        test_metrics = self._evaluate(
            model,
            x_scaled,
            y_business,
            meta,
            split_indices["test"],
            labels,
            slot_minutes=int(report["slot_minutes"]),
            stride=int(report["stride"]),
        )
        causal_audit = self._causal_audit(
            model,
            scaler,
            x[split_indices["test"][:2]],
        )

        snapshot_manifest = self._load_source_snapshot_manifest(report)
        run_kind = "smoke" if self.max_train_batches is not None else "full_offline_poc"
        elapsed = round(time.time() - started, 3)
        output_path.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="rtpoint-tcn-tmp-", dir=str(output_path)))
        try:
            data_contract = {
                "dataset_version": report["dataset_version"],
                "source_snapshot_version": report["source_snapshot_version"],
                "context_length": window_size,
                "slot_minutes": int(report["slot_minutes"]),
                "channels": channels,
                "missing_value_policy": missing_value_policy,
            }
            checkpoint = {
                "state_dict": {key: value.detach().cpu() for key, value in model.state_dict().items()},
                "constructor_config": model.constructor_config(),
                "model_config": model.model_config(),
                "normalization": scaler.state_dict(),
                "class_index_to_label": labels,
                "data_contract": data_contract,
            }
            torch.save(checkpoint, temp_dir / "model.pt")
            model_sha256 = _sha256_file(temp_dir / "model.pt")
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            model_ref = f"rtpoint-tcn-{self.target_mode}-{timestamp}-{model_sha256[:8]}"
            final_dir = output_path / model_ref
            if final_dir.exists():
                raise FileExistsError(f"模型工件已存在，拒绝覆盖: {_to_project_relative(final_dir)}")

            metadata = {
                "schema_version": "realtime-point-model-v2",
                "artifact_format": "torch_state_dict_dir",
                "modeling_path": "pv_fault_realtime",
                "model_ref": model_ref,
                "model_name": "causal_tcn_realtime",
                "causal": True,
                "context_length": window_size,
                "slot_minutes": int(report["slot_minutes"]),
                "channels": channels,
                "n_classes": len(labels),
                "labels": labels,
                "class_index_to_label": labels,
                "constructor_config": model.constructor_config(),
                "model_config": model.model_config(),
                "normalization": scaler.state_dict(),
                "data_contract": data_contract,
                "missing_value_policy": missing_value_policy,
                "label_space_contract": {
                    "source": "train_target_mask_only",
                    "evaluation_unseen_policy": "fail_closed",
                    "unseen_labels_by_split": unseen_labels_by_split,
                },
                "target_mode": self.target_mode,
                "burn_in_points": self.burn_in_points if self.target_mode == "burn_in_multi_point" else window_size - 1,
                "loss_config": {
                    "name": "cross_entropy",
                    "class_weight_mode": self.class_weight_mode,
                    "loss_slot_mask": self.loss_slot_mask,
                    "ignore_index": IGNORE_LABEL,
                    "train_class_counts": class_counts.tolist(),
                    "class_weights": class_weights.tolist(),
                    "missing_train_labels": [labels[i] for i, count in enumerate(class_counts) if count == 0],
                },
                "training_config": {
                    "run_kind": run_kind,
                    "epochs": self.epochs,
                    "batch_size": self.batch_size,
                    "learning_rate": self.learning_rate,
                    "optimizer": "AdamW",
                    "gradient_clip_norm": 1.0,
                    "seed": self.seed,
                    "device": str(self.device),
                    "max_train_batches": self.max_train_batches,
                    "best_epoch": best_epoch,
                    "best_val_loss": best_val_loss,
                    "optimizer_steps": optimizer_steps,
                },
                "dataset_version": report["dataset_version"],
                "dataset_path": dataset_dir,
                "source_snapshot_version": report["source_snapshot_version"],
                "label_snapshot_hash": snapshot_manifest.get("label_snapshot_hash"),
                "dataset_artifacts": report["artifacts"],
                "evaluation_record": {"val": val_metrics, "test": test_metrics},
                "causal_audit": {
                    "preprocessing": report["causal_audit"],
                    "model_and_normalizer": causal_audit,
                    "all_passed": bool(
                        report["causal_audit"].get("all_passed")
                        and causal_audit.get("all_passed")
                    ),
                },
                "alarm_policy": {
                    "enabled": False,
                    "reason": "offline_phase0_poc",
                },
                "promotion_eligible": False,
                "promotion_block_reason": (
                    "smoke_run_not_accuracy_evidence"
                    if run_kind == "smoke"
                    else "phase0_offline_model_requires_window_and_loss_comparison"
                ),
                "model_path": _to_project_relative(final_dir / "model.pt"),
                "model_sha256": model_sha256,
                "trained_at": datetime.utcnow().isoformat() + "Z",
                "train_time_sec": elapsed,
            }
            if not metadata["causal_audit"]["all_passed"]:
                raise RuntimeError("模型或预处理因果审计未通过，禁止发布工件")
            _json_write(temp_dir / "metadata.json", metadata)
            _json_write(temp_dir / "training_history.json", {"history": history})
            temp_dir.rename(final_dir)
        except BaseException:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        relative_model_path = _to_project_relative(final_dir)
        return {
            "model_ref": model_ref,
            "model_path": relative_model_path,
            "target_mode": self.target_mode,
            "promotion_eligible": False,
            "best_epoch": best_epoch,
            "best_val_loss": best_val_loss,
            "history": history,
            "val_metrics": val_metrics,
            "test_metrics": test_metrics,
            "causal_audit": metadata["causal_audit"],
        }

    def _load_dataset(
        self,
        dataset_path: Path,
    ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame, Dict[str, Any], List[str]]:
        report_path = dataset_path / "build_report.json"
        if not report_path.is_file():
            raise FileNotFoundError(f"数据集缺少 build_report.json: {_to_project_relative(dataset_path)}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for filename, record in (report.get("artifacts") or {}).items():
            artifact_path = _resolve_relative(str(record["path"]), f"artifacts.{filename}.path")
            if artifact_path.parent != dataset_path.resolve():
                raise ValueError(f"数据 artifact 越界数据集目录: {record['path']}")
            if _sha256_file(artifact_path) != record.get("sha256"):
                raise RuntimeError(f"数据 artifact digest 不匹配: {filename}")
        window_size = int(report["window_size"])
        npz_path = dataset_path / f"windows_w{window_size}.npz"
        meta_path = dataset_path / f"window_meta_w{window_size}.parquet"
        data = np.load(npz_path, allow_pickle=False)
        x = data["X"].astype(np.float32)
        y = data["Y"].astype(np.int64)
        channels = [str(value) for value in data["channels"].tolist()]
        meta = pd.read_parquet(meta_path)
        if x.ndim != 3 or y.ndim != 2 or x.shape[:2] != y.shape:
            raise ValueError(f"实时点数据形状不一致: X={x.shape}, Y={y.shape}")
        if len(x) != len(meta) or len(x) != int(report["window_count"]):
            raise ValueError("X/Y/meta/build_report 行数不一致")
        if channels != list(report["channels"]) or len(channels) != x.shape[2]:
            raise ValueError("NPZ channels 与 build_report 或 X 通道数不一致")
        if not report.get("causal_audit", {}).get("all_passed"):
            raise ValueError("上游数据层因果审计未通过")
        required_meta = {*_DEVICE_COLUMNS, "split", "target_time", "start_time"}
        missing = sorted(required_meta - set(meta.columns))
        if missing:
            raise ValueError(f"窗口 meta 缺少字段: {missing}")
        meta["target_time"] = pd.to_datetime(meta["target_time"])
        meta["start_time"] = pd.to_datetime(meta["start_time"])
        return x, y, meta, report, channels

    @staticmethod
    def _missing_value_policy(report: Dict[str, Any]) -> Dict[str, Any]:
        """读取或从旧版平铺字段恢复数据集缺测契约。"""
        policy = report.get("missing_value_policy") or {
            "mode": "past_only_forward_fill_then_zero",
            "max_forward_fill_slots": int(report["max_forward_fill_slots"]),
            "remaining_fill_value": 0.0,
            "measurement_mask_channel": "is_measured",
            "time_since_channel": "time_since_measured",
            "uses_future_values": False,
        }
        required = {
            "mode",
            "max_forward_fill_slots",
            "remaining_fill_value",
            "measurement_mask_channel",
            "time_since_channel",
            "uses_future_values",
        }
        missing = sorted(required - set(policy))
        if missing:
            raise ValueError(f"missing_value_policy 缺少字段: {missing}")
        if policy["mode"] != "past_only_forward_fill_then_zero":
            raise ValueError(f"不支持的 missing_value_policy.mode: {policy['mode']}")
        if policy["uses_future_values"] is not False:
            raise ValueError("缺测策略使用未来值，拒绝训练实时点模型")
        if int(policy["max_forward_fill_slots"]) != int(report["max_forward_fill_slots"]):
            raise ValueError("missing_value_policy 与数据集 max_forward_fill_slots 不一致")
        return dict(policy)

    def _load_source_snapshot_manifest(self, report: Dict[str, Any]) -> Dict[str, Any]:
        snapshot_path = _resolve_relative(str(report["source_snapshot"]), "source_snapshot")
        return json.loads((snapshot_path / "manifest.json").read_text(encoding="utf-8"))

    def _set_seed(self) -> None:
        random.seed(self.seed)
        np.random.seed(self.seed)
        torch.manual_seed(self.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(self.seed)

    def _assert_device_isolation(self, meta: pd.DataFrame) -> None:
        sets = {
            split: set(map(tuple, group[_DEVICE_COLUMNS].drop_duplicates().to_numpy()))
            for split, group in meta.groupby("split")
        }
        for left, right in [("train", "val"), ("train", "test"), ("val", "test")]:
            if sets.get(left, set()) & sets.get(right, set()):
                raise RuntimeError(f"数据 split 设备泄漏: {left}/{right}")

    def _target_mask_numpy(self, y: np.ndarray, x: Optional[np.ndarray] = None) -> np.ndarray:
        valid = y != IGNORE_LABEL
        positions = np.arange(y.shape[1])
        if self.target_mode == "last_point":
            selected = positions == y.shape[1] - 1
        else:
            selected = positions >= self.burn_in_points
        mask = valid & selected[None, :]
        if self.loss_slot_mask == "daylight":
            if x is None or self._daylight_index is None:
                raise ValueError("daylight loss 需要 is_daylight 通道")
            mask = mask & (x[:, :, self._daylight_index] > 0.5)
        return mask

    def _target_mask_torch(self, y: torch.Tensor, x: Optional[torch.Tensor] = None) -> torch.Tensor:
        positions = torch.arange(y.shape[1], device=y.device)
        if self.target_mode == "last_point":
            selected = positions == y.shape[1] - 1
        else:
            selected = positions >= self.burn_in_points
        mask = (y != IGNORE_LABEL) & selected.unsqueeze(0)
        if self.loss_slot_mask == "daylight":
            if x is None or self._daylight_index is None:
                raise ValueError("daylight loss 需要 is_daylight 通道")
            mask = mask & (x[:, :, self._daylight_index] > 0.5)
        return mask

    def _unseen_labels_by_split(
        self,
        y_business: np.ndarray,
        x: np.ndarray,
        split_indices: Dict[str, np.ndarray],
        labels: Sequence[int],
    ) -> Dict[str, Dict[str, Any]]:
        """统计目标监督位置中不属于 train 标签空间的业务标签。"""
        supported = np.asarray(labels, dtype=np.int64)
        result: Dict[str, Dict[str, Any]] = {}
        for split, indices in split_indices.items():
            rows = y_business[indices]
            targets = rows[self._target_mask_numpy(rows, x[indices])]
            unseen = targets[~np.isin(targets, supported)]
            values, counts = np.unique(unseen, return_counts=True)
            result[split] = {
                "labels": [int(value) for value in values],
                "counts": {str(int(value)): int(count) for value, count in zip(values, counts)},
                "point_count": int(len(unseen)),
            }
        return result

    @staticmethod
    def _class_weights(counts: np.ndarray, *, mode: str = "balanced") -> np.ndarray:
        if mode == "none":
            return np.ones(len(counts), dtype=np.float32)
        weights = np.zeros(len(counts), dtype=np.float32)
        nonzero = counts > 0
        weights[nonzero] = counts[nonzero].sum() / (nonzero.sum() * counts[nonzero])
        weights[nonzero] /= weights[nonzero].mean()
        return weights

    def _loader(
        self,
        x: np.ndarray,
        y: np.ndarray,
        indices: np.ndarray,
        *,
        shuffle: bool,
    ) -> DataLoader:
        dataset = TensorDataset(
            torch.from_numpy(x[indices]).float(),
            torch.from_numpy(y[indices]).long(),
        )
        generator = torch.Generator().manual_seed(self.seed)
        return DataLoader(
            dataset,
            batch_size=self.batch_size,
            shuffle=shuffle,
            generator=generator if shuffle else None,
        )

    def _run_epoch(
        self,
        model: CausalTCNRealtime,
        loader: DataLoader,
        criterion: nn.Module,
        *,
        optimizer: Optional[torch.optim.Optimizer],
        max_batches: Optional[int] = None,
    ) -> Tuple[float, int]:
        training = optimizer is not None
        model.train(training)
        total_loss = 0.0
        total_points = 0
        optimizer_steps = 0
        for batch_index, (x_batch, y_batch) in enumerate(loader):
            if max_batches is not None and batch_index >= max_batches:
                break
            x_batch = x_batch.to(self.device)
            y_batch = y_batch.to(self.device)
            with torch.set_grad_enabled(training):
                logits = model(x_batch)
                mask = self._target_mask_torch(y_batch, x_batch)
                if not mask.any():
                    continue
                losses = criterion(logits[mask], y_batch[mask])
                loss = losses.mean()
                if training:
                    optimizer.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    optimizer_steps += 1
            point_count = int(mask.sum().item())
            total_loss += float(loss.detach().cpu()) * point_count
            total_points += point_count
        if total_points == 0:
            raise ValueError(f"{self.target_mode} 在当前 loader 中没有有效监督点")
        return total_loss / total_points, optimizer_steps

    def _predict(self, model: CausalTCNRealtime, x: np.ndarray, indices: np.ndarray) -> np.ndarray:
        model.eval()
        outputs: List[np.ndarray] = []
        loader = DataLoader(
            TensorDataset(torch.from_numpy(x[indices]).float()),
            batch_size=self.batch_size,
            shuffle=False,
        )
        with torch.no_grad():
            for (x_batch,) in loader:
                outputs.append(model(x_batch.to(self.device)).argmax(dim=-1).cpu().numpy())
        return np.concatenate(outputs, axis=0)

    def _evaluate(
        self,
        model: CausalTCNRealtime,
        x: np.ndarray,
        y_business: np.ndarray,
        meta: pd.DataFrame,
        indices: np.ndarray,
        labels: Sequence[int],
        *,
        slot_minutes: int,
        stride: int,
    ) -> Dict[str, Any]:
        pred_class = self._predict(model, x, indices)
        class_to_label = np.asarray(labels, dtype=np.int64)
        records: Dict[Tuple[str, str, str, pd.Timestamp], Dict[str, Any]] = {}
        duplicate_predictions = 0
        saved_mask = self.loss_slot_mask
        self.loss_slot_mask = "all"
        try:
            for local_index, global_index in enumerate(indices):
                y_row = y_business[global_index]
                x_row = x[global_index]
                valid_positions = np.flatnonzero(
                    self._target_mask_numpy(y_row[None, :], x_row[None, :])[0]
                )
                meta_row = meta.iloc[global_index]
                target_time = pd.Timestamp(meta_row["target_time"])
                for position in valid_positions:
                    event_time = target_time - pd.Timedelta(
                        minutes=(len(y_row) - 1 - int(position)) * slot_minutes
                    )
                    key = (
                        str(meta_row["site_id"]),
                        str(meta_row["device_id"]),
                        str(meta_row["branch_id"]),
                        event_time,
                    )
                    record = {
                        "site_id": key[0],
                        "device_id": key[1],
                        "branch_id": key[2],
                        "time": event_time,
                        "true": int(y_row[position]),
                        "pred": int(class_to_label[pred_class[local_index, position]]),
                        "is_daylight": bool(x_row[int(position), self._daylight_index] > 0.5),
                    }
                    previous = records.get(key)
                    if previous is not None:
                        duplicate_predictions += 1
                        if previous["true"] != record["true"] or previous["pred"] != record["pred"]:
                            raise RuntimeError(f"重叠窗口对同一事件点预测不一致: {key}")
                    else:
                        records[key] = record
        finally:
            self.loss_slot_mask = saved_mask
        if not records:
            raise ValueError("评估 split 没有唯一监督事件点")
        frame = pd.DataFrame(records.values()).sort_values([*_DEVICE_COLUMNS, "time"])
        cadence_minutes = slot_minutes if self.target_mode == "burn_in_multi_point" else slot_minutes * stride
        daylight_frame = frame.loc[frame["is_daylight"]].copy()
        return {
            **self._slice_metrics(frame, labels, cadence_minutes),
            "duplicate_window_predictions_deduplicated": int(duplicate_predictions),
            "daylight_subset": self._slice_metrics(daylight_frame, labels, cadence_minutes),
            "night_point_count": int((~frame["is_daylight"]).sum()),
        }

    def _slice_metrics(
        self,
        frame: pd.DataFrame,
        labels: Sequence[int],
        cadence_minutes: int,
    ) -> Dict[str, Any]:
        if frame.empty:
            return {
                "unique_labeled_points": 0,
                "point_macro_f1": 0.0,
                "binary_f1": 0.0,
                "point_accuracy": 0.0,
                "fault_mask_iou": 0.0,
                "raw_labeled_segment_proxy": {
                    "metric_scope": "raw_argmax_sparse_labeled_segment_proxy_not_alarm_policy",
                    "true_fault_segments_proxy": 0,
                    "pred_fault_segments_proxy": 0,
                    "matched_fault_segments_proxy": 0,
                    "segment_precision_proxy": 0.0,
                    "segment_recall_proxy": 0.0,
                    "onset_delay_median_minutes_proxy": None,
                    "onset_delay_p90_minutes_proxy": None,
                    "eligible_matched_segments_proxy": 0,
                    "unmatched_pred_segments_per_evaluable_labeled_device_day_proxy": None,
                    "evaluable_labeled_normal_device_days_proxy": 0,
                    "matching_contract": "binary_segment_iou_greedy_min_0.1",
                },
                "evidence_limitations": [
                    "raw_labeled_segment_proxy 仅基于稀疏已标注点和 raw argmax，不是生产告警指标",
                    "该切片没有监督点",
                ],
            }
        y_true = frame["true"].to_numpy(dtype=np.int64)
        y_pred = frame["pred"].to_numpy(dtype=np.int64)
        true_fault = y_true != 0
        pred_fault = y_pred != 0
        intersection = int(np.logical_and(true_fault, pred_fault).sum())
        union = int(np.logical_or(true_fault, pred_fault).sum())
        return {
            "unique_labeled_points": int(len(frame)),
            "point_macro_f1": float(
                f1_score(y_true, y_pred, labels=list(labels), average="macro", zero_division=0)
            ),
            "binary_f1": float(f1_score(true_fault, pred_fault, zero_division=0)),
            "point_accuracy": float(accuracy_score(y_true, y_pred)),
            "fault_mask_iou": float(intersection / union) if union else 0.0,
            "raw_labeled_segment_proxy": self._raw_labeled_segment_proxy(
                frame,
                cadence_minutes=cadence_minutes,
            ),
            "evidence_limitations": [
                "raw_labeled_segment_proxy 仅基于稀疏已标注点和 raw argmax，不是生产告警指标",
                "旧 POC 快照若未按 point_rest_normal 重导，框外正常仍可能缺失",
                "真实有监督跨午夜窗口为 0，跨午夜仅通过合成契约审计",
            ],
        }

    @staticmethod
    def _extract_events(
        frame: pd.DataFrame,
        value_column: str,
        cadence: pd.Timedelta,
    ) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for device_key, group in frame.groupby(_DEVICE_COLUMNS, sort=False):
            group = group.sort_values("time")
            start: Optional[pd.Timestamp] = None
            previous: Optional[pd.Timestamp] = None
            for row in group.itertuples(index=False):
                timestamp = pd.Timestamp(row.time)
                active = int(getattr(row, value_column)) != 0
                contiguous = previous is not None and timestamp - previous <= cadence
                if active and (start is None or not contiguous):
                    if start is not None and previous is not None:
                        events.append({"device": tuple(device_key), "start": start, "end": previous + cadence})
                    start = timestamp
                elif not active and start is not None:
                    events.append({"device": tuple(device_key), "start": start, "end": timestamp})
                    start = None
                previous = timestamp
            if start is not None and previous is not None:
                events.append({"device": tuple(device_key), "start": start, "end": previous + cadence})
        return events

    @classmethod
    def _raw_labeled_segment_proxy(
        cls,
        frame: pd.DataFrame,
        *,
        cadence_minutes: int,
    ) -> Dict[str, Any]:
        cadence = pd.Timedelta(minutes=cadence_minutes)
        true_events = cls._extract_events(frame, "true", cadence)
        pred_events = cls._extract_events(frame, "pred", cadence)
        candidates: List[Tuple[float, int, int]] = []
        for true_index, true_event in enumerate(true_events):
            for pred_index, pred_event in enumerate(pred_events):
                if true_event["device"] != pred_event["device"]:
                    continue
                overlap = max(
                    pd.Timedelta(0),
                    min(true_event["end"], pred_event["end"])
                    - max(true_event["start"], pred_event["start"]),
                )
                if overlap <= pd.Timedelta(0):
                    continue
                union = max(true_event["end"], pred_event["end"]) - min(
                    true_event["start"], pred_event["start"]
                )
                iou = overlap / union
                if iou >= 0.1:
                    candidates.append((float(iou), true_index, pred_index))
        matched_true = set()
        matched_pred = set()
        onset_delays: List[float] = []
        for _, true_index, pred_index in sorted(candidates, reverse=True):
            if true_index in matched_true or pred_index in matched_pred:
                continue
            matched_true.add(true_index)
            matched_pred.add(pred_index)
            delay = (
                pred_events[pred_index]["start"] - true_events[true_index]["start"]
            ).total_seconds() / 60.0
            onset_delays.append(max(0.0, delay))
        eligible_normal_days = int(
            frame.loc[frame["true"] == 0]
            .assign(date=frame.loc[frame["true"] == 0, "time"].dt.date)
            [[*_DEVICE_COLUMNS, "date"]]
            .drop_duplicates()
            .shape[0]
        )
        return {
            "metric_scope": "raw_argmax_sparse_labeled_segment_proxy_not_alarm_policy",
            "true_fault_segments_proxy": len(true_events),
            "pred_fault_segments_proxy": len(pred_events),
            "matched_fault_segments_proxy": len(matched_true),
            "segment_precision_proxy": len(matched_pred) / len(pred_events) if pred_events else 0.0,
            "segment_recall_proxy": len(matched_true) / len(true_events) if true_events else 0.0,
            "onset_delay_median_minutes_proxy": (
                float(np.median(onset_delays)) if onset_delays else None
            ),
            "onset_delay_p90_minutes_proxy": (
                float(np.percentile(onset_delays, 90)) if onset_delays else None
            ),
            "eligible_matched_segments_proxy": len(onset_delays),
            "unmatched_pred_segments_per_evaluable_labeled_device_day_proxy": (
                (len(pred_events) - len(matched_pred)) / eligible_normal_days
                if eligible_normal_days
                else None
            ),
            "evaluable_labeled_normal_device_days_proxy": eligible_normal_days,
            "matching_contract": "binary_segment_iou_greedy_min_0.1",
        }

    def _causal_audit(
        self,
        model: CausalTCNRealtime,
        scaler: FixedRobustScaler,
        raw_samples: np.ndarray,
    ) -> Dict[str, Any]:
        if len(raw_samples) == 0:
            raise ValueError("模型因果审计没有样本")
        model.eval()
        window_size = raw_samples.shape[1]
        positions = sorted(
            {
                0,
                min(window_size - 2, model.receptive_field_points - 2),
                min(window_size - 2, model.receptive_field_points - 1),
                window_size - 2,
            }
        )
        blocks_tested = 0
        for position in positions:
            original = raw_samples.copy()
            mutated = raw_samples.copy()
            if position + 1 < window_size:
                rng = np.random.default_rng(self.seed + position)
                mutated[:, position + 1 :, :] += rng.normal(
                    loc=1000.0,
                    scale=100.0,
                    size=mutated[:, position + 1 :, :].shape,
                ).astype(np.float32)
            original_scaled = scaler.transform(original)
            mutated_scaled = scaler.transform(mutated)
            if not np.array_equal(
                original_scaled[:, : position + 1],
                mutated_scaled[:, : position + 1],
            ):
                raise RuntimeError(f"固定归一化因果审计失败: position={position}")
            left = torch.from_numpy(original_scaled).float().to(self.device).transpose(1, 2)
            right = torch.from_numpy(mutated_scaled).float().to(self.device).transpose(1, 2)
            with torch.no_grad():
                for block in model.blocks:
                    left = block(left)
                    right = block(right)
                    torch.testing.assert_close(
                        left[:, :, : position + 1],
                        right[:, :, : position + 1],
                        rtol=0.0,
                        atol=1e-6,
                    )
                    blocks_tested += 1
                left_logits = model.classifier(left).transpose(1, 2)
                right_logits = model.classifier(right).transpose(1, 2)
                torch.testing.assert_close(
                    left_logits[:, : position + 1],
                    right_logits[:, : position + 1],
                    rtol=0.0,
                    atol=1e-6,
                )
        return {
            "scope": "fixed_normalizer_each_tcn_block_and_full_logits",
            "tested_positions": positions,
            "tested_samples": int(len(raw_samples)),
            "block_checks": blocks_tested,
            "rtol": 0.0,
            "atol": 1e-6,
            "all_passed": True,
        }
# @AI_GENERATED: end
