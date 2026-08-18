# -*- coding: utf-8 -*-
# @AI_GENERATED
"""序列标注正式训练器：评估设备隔离泛化，并保存可审计模型工件。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit
from torch.utils.data import DataLoader, TensorDataset

from services.iterative_labeling.seq_annotation.grid_align import (
    MASK_CHANNEL,
    SLOT_MINUTES,
    SLOTS_PER_DAY,
    split_mask_channel,
)
from services.iterative_labeling.seq_annotation.models import get_model
from services.iterative_labeling.seq_annotation.postprocessing import (
    build_postprocessing_contract,
    postprocess_point_predictions,
)
from services.iterative_labeling.seq_annotation.production_contract import (
    FINAL_MODEL_NAME,
    FINAL_SEGMENT_BOUNDARY_WEIGHT,
)

IGNORE_INDEX = -1
DEFAULT_CHANNELS = ("value", "i_cal")
DEFAULT_SEGMENT_BOUNDARY_WEIGHT = FINAL_SEGMENT_BOUNDARY_WEIGHT
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_DEFAULT_DATASETS_DIR = _BACKEND_DIR / "data" / "seq_annotation_datasets"
_DEFAULT_MODELS_DIR = _BACKEND_DIR / "data" / "models" / "seq_annotation"


def _is_full_day_grid_validated(
    *,
    report: Dict[str, Any],
    grid_contract: Dict[str, Any],
    channels: Sequence[str],
    seq_len: int,
) -> bool:
    """判定快照是否真的具备全天网格证据（训练器与累计训练服务共用）。

    要求同时满足：288 槽 5 分钟网格、声明 ``grid_aligned``、执行 24 小时覆盖门控、
    存在 ``is_measured`` 掩码通道，且报告与契约都没有否认全天验证结果。
    任一缺失即 fail closed，避免半天或旧口径数据冒充全天模型。
    """
    contract = dict(grid_contract or {})
    structure_ok = (
        int(seq_len) == SLOTS_PER_DAY
        and contract.get("grid_aligned") is True
        and int(contract.get("slots_per_day") or 0) == SLOTS_PER_DAY
        and int(contract.get("slot_minutes") or 0) == SLOT_MINUTES
        and contract.get("require_all_hours_covered") is True
        and MASK_CHANNEL in [str(name) for name in channels]
    )
    contract_validation = contract.get("full_day_grid_validated")
    declared = report.get("full_day_grid_validated") is True and (
        contract_validation is None or contract_validation is True
    )
    return bool(structure_ok and declared)


class SeqAnnotationTrainer:
    """训练逐点分类模型，返回与累计重训流程兼容的模型产物契约。"""

    def __init__(
        self,
        *,
        model_name: str = FINAL_MODEL_NAME,
        epochs: int = 100,
        batch_size: int = 32,
        learning_rate: float = 1e-3,
        test_ratio: float = 0.3,
        random_state: int = 42,
        device: Optional[str] = None,
        segment_boundary_weight: float = DEFAULT_SEGMENT_BOUNDARY_WEIGHT,
        postprocessing_enabled: bool = True,
        postprocess_min_fault_segment_points: int = 3,
    ) -> None:
        self.model_name = str(model_name)
        self.epochs = max(1, int(epochs))
        self.batch_size = max(1, int(batch_size))
        self.learning_rate = float(learning_rate)
        self.test_ratio = float(test_ratio)
        self.random_state = int(random_state)
        self.segment_boundary_weight = float(segment_boundary_weight)
        if self.segment_boundary_weight < 1.0:
            raise ValueError("segment_boundary_weight 不能小于 1.0")
        self.postprocessing_contract = build_postprocessing_contract(
            enabled=postprocessing_enabled,
            min_fault_segment_points=postprocess_min_fault_segment_points,
        )
        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        # 归一化时需要跳过的通道下标（is_measured 掩码通道）。
        # 掩码是 0/1 语义，做逐序列 z-score 会在「全部实测」的天里 std=0 而被抹成 0，
        # 与部分实测的天不可比，等于把这条信息毁掉。
        self._norm_exclude: Tuple[int, ...] = ()

    def train(
        self,
        dataset_path: Optional[str] = None,
        *,
        output_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        """训练并持久化模型；路径参数相对 ``backend-service`` 解析。"""
        # 所有路径在训练/写盘前完成边界校验，失败时不遗留孤儿工件。
        dataset_dir = self._resolve_dataset_dir(dataset_path)
        models_root = self._resolve_output_root(output_root)
        X, Y, meta, report = self._load_dataset(dataset_dir)
        self._validate_dataset(X, Y, meta, report)

        # build_config 必须在训练前读取：归一化要跳过 is_measured 掩码通道，
        # 而掩码通道的位置只能从数据集契约里得到。
        build_config = json.loads(
            (dataset_dir / "build_config.json").read_text(encoding="utf-8")
        )
        channels = list(build_config.get("channels") or list(DEFAULT_CHANNELS))
        if len(channels) != X.shape[2]:
            raise ValueError(
                f"build_config.channels 数量({len(channels)})与 dataset.npz 通道数({X.shape[2]})不一致"
            )
        _, mask_channel_index = split_mask_channel(channels)
        self._norm_exclude = () if mask_channel_index is None else (int(mask_channel_index),)

        # 在评估前冻结与最终工件完全相同的全天/后处理契约，避免评估使用处理后
        # 指标、实际工件却因全天证据不足而关闭后处理。
        seq_len = int(X.shape[1])
        daylight_hours = list(build_config.get("daylight_hours") or [7, 17])
        dataset_grid_contract = dict(
            report.get("grid_contract") or build_config.get("grid_contract") or {}
        )
        full_day_grid_validated = _is_full_day_grid_validated(
            report=report,
            grid_contract=dataset_grid_contract,
            channels=channels,
            seq_len=seq_len,
        )
        trained_full_day = (
            seq_len == SLOTS_PER_DAY
            and daylight_hours == [0, 24]
            and full_day_grid_validated
        )
        artifact_postprocessing_contract = dict(self.postprocessing_contract)
        artifact_postprocessing_contract["enabled"] = bool(
            artifact_postprocessing_contract.get("enabled") and trained_full_day
        )

        labels = sorted(int(value) for value in np.unique(Y[Y != IGNORE_INDEX]))
        if 0 not in labels:
            raise ValueError("序列标注数据集必须包含业务正常标签 0")
        label_to_class_index = {label: index for index, label in enumerate(labels)}
        Y_model = np.full(Y.shape, IGNORE_INDEX, dtype=np.int64)
        for label, class_index in label_to_class_index.items():
            Y_model[Y == label] = class_index
        n_classes = len(labels)
        train_idx, test_idx = self._device_isolated_split(meta)
        original_test = ~meta.iloc[test_idx]["is_augmented"].astype(bool).to_numpy()
        test_idx = test_idx[original_test]
        if len(test_idx) == 0:
            raise ValueError("设备隔离测试集没有原始序列，拒绝产出不可验证模型")

        started = time.time()
        eval_model = get_model(
            self.model_name,
            in_channels=X.shape[2],
            n_classes=n_classes,
        ).to(self.device)
        self._fit(
            eval_model,
            X[train_idx],
            Y_model[train_idx],
            meta.iloc[train_idx],
            n_classes=n_classes,
        )
        metrics = self._evaluate(
            eval_model,
            X[test_idx],
            Y_model[test_idx],
            labels,
            postprocessing_contract=artifact_postprocessing_contract,
        )

        # 评估完成后使用全部累计数据重训正式工件；增强数据仅进入训练，不进入上方测试。
        final_model = get_model(
            self.model_name,
            in_channels=X.shape[2],
            n_classes=n_classes,
        ).to(self.device)
        self._fit(final_model, X, Y_model, meta, n_classes=n_classes)

        dataset_version = str(report.get("version") or dataset_dir.name)
        label_hash = str(report.get("label_snapshot_hash") or "unknown")
        model_ref = (
            f"seqann-{self.model_name}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-"
            f"{uuid.uuid4().hex[:6]}"
        )
        artifact_dir = models_root / model_ref
        artifact_dir.mkdir(parents=True, exist_ok=False)

        elapsed = round(time.time() - started, 3)

        metadata = {
            "schema_version": 3,
            "artifact_format": "torch_state_dict_dir",
            "modeling_path": "seq_annotation",
            "model_ref": model_ref,
            "model_name": self.model_name,
            "n_classes": n_classes,
            "labels": labels,
            "class_index_to_label": labels,
            "channels": channels,
            "seq_len": seq_len,
            "trained_full_day": trained_full_day,
            "full_day_grid_validated": full_day_grid_validated,
            "daylight_start_hour": int(daylight_hours[0]),
            "daylight_end_hour": int(daylight_hours[1]),
            "normalization": "per_sequence_channel_zscore",
            # 掩码通道不参与 z-score，推理侧必须用同一口径，否则输入分布不一致。
            "normalization_exclude_channels": [
                channels[index] for index in self._norm_exclude
            ],
            "mask_channel": MASK_CHANNEL if MASK_CHANNEL in channels else None,
            # 生产推理必须读取该契约复现实验验证过的夜间/短段清理；旧工件缺字段时禁用。
            "postprocessing": artifact_postprocessing_contract,
            # 把数据集的网格契约原样带进模型工件，推理侧据此复用同一套对齐门槛。
            "grid_contract": dataset_grid_contract or None,
            "sampling_interval_minutes": 5,
            "dataset_version": dataset_version,
            "dataset_path": self._to_backend_relative(dataset_dir),
            "label_snapshot_hash": label_hash,
            "training_config": {
                # 消融实测 CE + 类别权重 + 均匀 shuffle 明显优于把 Focal、
                # WeightedRandomSampler 和 tier 权重捆绑启用的方案，因此正式训练器
                # 保持胜出配置，不让实验脚本里的劣化组合悄悄成为生产默认。
                "loss": "cross_entropy",
                "class_weight": "inverse_frequency",
                "sampler": "uniform_shuffle",
                "tier_sample_weight": False,
                "sequence_weighting": {
                    "field": "data_type",
                    "match": "segment_boundary",
                    "multiplier": self.segment_boundary_weight,
                    "normalization": "weighted_valid_point_mean",
                },
                "epochs": self.epochs,
                "batch_size": self.batch_size,
                "learning_rate": self.learning_rate,
                "random_state": self.random_state,
                "device": str(self.device),
            },
            "accuracy_record": {
                **metrics,
                "n_samples": int(len(X)),
                "n_test_sequences": int(len(test_idx)),
                "n_test_points": int((Y[test_idx] != IGNORE_INDEX).sum()),
            },
            "trained_at": datetime.utcnow().isoformat(),
            "train_time_sec": elapsed,
        }

        state = {key: value.detach().cpu() for key, value in final_model.state_dict().items()}
        torch.save(state, artifact_dir / "model.pt")
        self._atomic_write_json(artifact_dir / "metadata.json", metadata)
        model_sha256 = self._sha256_file(artifact_dir / "model.pt")
        metadata["model_sha256"] = model_sha256
        self._atomic_write_json(artifact_dir / "metadata.json", metadata)

        model_path = self._to_backend_relative(artifact_dir)
        return {
            "model_ref": model_ref,
            "model_path": model_path,
            "artifact_format": "torch_state_dict_dir",
            "modeling_path": "seq_annotation",
            "accuracy_record": metadata["accuracy_record"],
            "label_space_snapshot": {
                "labels": labels,
                "n_classes": n_classes,
                "class_index_to_label": labels,
            },
            "label_snapshot_hash": label_hash,
            "sample_strategy": {
                "split_mode": "seq_annotation",
                "seq_len": seq_len,
                "channels": channels,
                "trained_full_day": trained_full_day,
            },
            "sequence_contract": {
                "model_name": self.model_name,
                "loss": metadata["training_config"]["loss"],
                "seq_len": seq_len,
                "channels": channels,
                "trained_full_day": trained_full_day,
                "full_day_grid_validated": full_day_grid_validated,
                "grid_aligned": dataset_grid_contract.get("grid_aligned") is True,
                "sampling_interval_minutes": 5,
                "normalization": metadata["normalization"],
                "sequence_weighting": metadata["training_config"]["sequence_weighting"],
                "postprocessing": metadata["postprocessing"],
            },
        }

    def _fit(
        self,
        model: torch.nn.Module,
        X: np.ndarray,
        Y: np.ndarray,
        meta: pd.DataFrame,
        *,
        n_classes: int,
    ) -> None:
        X_tensor = torch.from_numpy(self._normalize(X)).float()
        Y_tensor = torch.from_numpy(Y).long()
        if len(meta) != len(X):
            raise ValueError("训练 X 与 meta 数量不一致")
        sequence_weights_np = np.where(
            meta["data_type"].astype(str).to_numpy() == "segment_boundary",
            self.segment_boundary_weight,
            1.0,
        ).astype(np.float32)
        sequence_weights = torch.from_numpy(sequence_weights_np).float()
        dataset = TensorDataset(X_tensor, Y_tensor, sequence_weights)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        # 采用消融胜出的 CE + 训练集内逆频率类别权重。类别统计只读取当前传入的
        # 训练分片，不会使用测试集标签；正式全量重训阶段则自然使用全量数据。
        # 权重长度必须固定为模型输出类别数：设备隔离切分不按类别分层，最稀有的
        # 最高类别可能整类落在测试设备上，此时按分片最大值取长度会让 weight 少一维，
        # PyTorch 会直接抛 "weight tensor should be defined either for all N classes"。
        valid_labels = Y[Y != IGNORE_INDEX]
        class_counts = np.bincount(
            valid_labels,
            minlength=int(n_classes),
        ).astype(float)
        class_counts[class_counts == 0] = 1.0
        class_weights = 1.0 / class_counts
        class_weights = class_weights / class_weights.sum() * len(class_weights)
        criterion = torch.nn.CrossEntropyLoss(
            weight=torch.from_numpy(class_weights).float().to(self.device),
            ignore_index=IGNORE_INDEX,
            reduction="none",
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=self.learning_rate)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.epochs)

        model.train()
        for _ in range(self.epochs):
            for xb, yb, sequence_weight in loader:
                xb, yb = xb.to(self.device), yb.to(self.device)
                sequence_weight = sequence_weight.to(self.device)
                logits = model(xb)
                targets = yb.reshape(-1)
                valid = targets != IGNORE_INDEX
                if not valid.any():
                    continue
                point_loss = criterion(
                    logits.reshape(-1, logits.shape[-1])[valid],
                    targets[valid],
                )
                point_weights = (
                    sequence_weight.unsqueeze(1)
                    .expand_as(yb)
                    .reshape(-1)[valid]
                )
                loss = (point_loss * point_weights).sum() / point_weights.sum().clamp_min(1e-8)
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
            scheduler.step()

    def _evaluate(
        self,
        model: torch.nn.Module,
        X: np.ndarray,
        Y: np.ndarray,
        labels: list[int],
        *,
        postprocessing_contract: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        """在连续模型类别上推理，再映射回业务 label_id 计算指标。"""
        model.eval()
        with torch.no_grad():
            pred_class = model.predict(
                torch.from_numpy(self._normalize(X)).float().to(self.device)
            ).cpu().numpy()
        class_index_to_label = np.asarray(labels, dtype=np.int64)
        valid = Y != IGNORE_INDEX
        business_pred_raw = class_index_to_label[pred_class]
        postprocessed_rows = []
        changed_points = 0
        evaluation_contract = dict(
            postprocessing_contract or build_postprocessing_contract(enabled=False)
        )
        for row in business_pred_raw:
            cleaned, audit = postprocess_point_predictions(
                row,
                evaluation_contract,
            )
            postprocessed_rows.append(cleaned)
            changed_points += int(audit["changed_points"])
        business_pred = np.stack(postprocessed_rows, axis=0)

        y_true = class_index_to_label[Y[valid]]
        y_pred_raw = business_pred_raw[valid]
        y_pred = business_pred[valid]
        true_fault, pred_fault = y_true != 0, y_pred != 0
        raw_pred_fault = y_pred_raw != 0
        intersection = np.logical_and(true_fault, pred_fault).sum()
        union = np.logical_or(true_fault, pred_fault).sum()
        raw_intersection = np.logical_and(true_fault, raw_pred_fault).sum()
        raw_union = np.logical_or(true_fault, raw_pred_fault).sum()

        true_day = [
            self._majority_label(class_index_to_label[row[row != IGNORE_INDEX]])
            for row in Y
        ]
        pred_day = [
            self._majority_label(pred_row[y_row != IGNORE_INDEX])
            for pred_row, y_row in zip(business_pred, Y)
        ]
        point_macro_f1 = float(
            f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
        )
        point_accuracy = float(accuracy_score(y_true, y_pred))
        return {
            "point_macro_f1": point_macro_f1,
            "binary_f1": float(f1_score(true_fault, pred_fault, zero_division=0)),
            "point_accuracy": point_accuracy,
            "fault_mask_iou": float(intersection / union) if union else 0.0,
            "day_majority_macro_f1": float(
                f1_score(true_day, pred_day, labels=labels, average="macro", zero_division=0)
            ),
            "postprocessing_changed_points": int(changed_points),
            "raw_point_macro_f1": float(
                f1_score(y_true, y_pred_raw, labels=labels, average="macro", zero_division=0)
            ),
            "raw_binary_f1": float(
                f1_score(true_fault, raw_pred_fault, zero_division=0)
            ),
            "raw_point_accuracy": float(accuracy_score(y_true, y_pred_raw)),
            "raw_fault_mask_iou": (
                float(raw_intersection / raw_union) if raw_union else 0.0
            ),
            # 兼容累计训练公共展示字段；主字段使用与生产一致的后处理口径。
            "macro_f1_mean": point_macro_f1,
            "accuracy_mean": point_accuracy,
        }

    def _device_isolated_split(self, meta: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        groups = (
            meta["site_id"].astype(str)
            + "|"
            + meta["device_id"].astype(str)
            + "|"
            + meta["branch_id"].astype(str)
        ).to_numpy()
        splitter = GroupShuffleSplit(
            n_splits=1,
            test_size=self.test_ratio,
            random_state=self.random_state,
        )
        train_idx, test_idx = next(splitter.split(np.arange(len(meta)), groups=groups))
        if set(groups[train_idx]).intersection(groups[test_idx]):
            raise RuntimeError("设备隔离切分失败：训练集和测试集存在设备重叠")
        return train_idx, test_idx

    @staticmethod
    def _majority_label(values: np.ndarray) -> int:
        if len(values) == 0:
            return 0
        labels, counts = np.unique(values, return_counts=True)
        return int(labels[np.argmax(counts)])

    def _normalize(self, X: np.ndarray) -> np.ndarray:
        """逐序列逐通道 z-score；``self._norm_exclude`` 里的通道保持原值。

        掩码通道必须原样保留 0/1：它的绝对取值本身就是信息（该槽是实测还是补出），
        z-score 会让「整天全实测」的序列 std=0 从而整列变成 0，和部分实测的序列
        不可比。测量通道仍按原有 ``per_sequence_channel_zscore`` 契约处理。
        """
        mean = np.nanmean(X, axis=1, keepdims=True)
        std = np.nanstd(X, axis=1, keepdims=True)
        normalized = (X - mean) / np.maximum(std, 1e-8)
        normalized = np.nan_to_num(normalized, nan=0.0, posinf=0.0, neginf=0.0)
        for channel_index in self._norm_exclude:
            normalized[:, :, channel_index] = np.nan_to_num(
                X[:, :, channel_index], nan=0.0, posinf=0.0, neginf=0.0
            )
        return normalized.astype(np.float32)

    @staticmethod
    def _load_dataset(dataset_dir: Path) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame, Dict[str, Any]]:
        required = ["dataset.npz", "meta.parquet", "build_config.json", "build_report.json"]
        missing = [name for name in required if not (dataset_dir / name).is_file()]
        if missing:
            raise FileNotFoundError(f"序列标注快照缺少文件: {', '.join(missing)}")
        data = np.load(dataset_dir / "dataset.npz")
        return (
            data["X"],
            data["Y"],
            pd.read_parquet(dataset_dir / "meta.parquet"),
            json.loads((dataset_dir / "build_report.json").read_text(encoding="utf-8")),
        )

    @staticmethod
    def _validate_dataset(
        X: np.ndarray,
        Y: np.ndarray,
        meta: pd.DataFrame,
        report: Dict[str, Any],
    ) -> None:
        if X.ndim != 3 or Y.ndim != 2 or X.shape[:2] != Y.shape:
            raise ValueError(f"序列数据形状不一致: X={X.shape}, Y={Y.shape}")
        if len(X) != len(meta) or len(X) < 2:
            raise ValueError("序列数据与 meta 数量不一致或样本不足")
        required_columns = {
            "site_id",
            "device_id",
            "branch_id",
            "is_augmented",
            "sample_weight",
            "data_type",
        }
        missing = required_columns.difference(meta.columns)
        if missing:
            raise ValueError(f"meta 缺少字段: {sorted(missing)}")
        labels = np.unique(Y[Y != IGNORE_INDEX])
        if len(labels) < 2 or 0 not in labels:
            raise ValueError("训练集必须同时包含正常类 0 和至少一个故障类")
        if int(report.get("seq_len") or 0) != X.shape[1]:
            raise ValueError("build_report.seq_len 与 dataset.npz 不一致")

    def _resolve_dataset_dir(self, dataset_path: Optional[str]) -> Path:
        if dataset_path:
            candidate = Path(dataset_path)
            if not candidate.is_absolute():
                candidate = _BACKEND_DIR / candidate
            resolved = candidate.resolve()
            # P2 修复：在加载数据之前就拒绝越界路径，避免训练完才失败。
            try:
                resolved.relative_to(_BACKEND_DIR)
            except ValueError as exc:
                raise ValueError(
                    "dataset_path 必须位于 backend-service 内部"
                ) from exc
            return resolved
        registry = json.loads(
            (_DEFAULT_DATASETS_DIR / "registry.json").read_text(encoding="utf-8")
        )
        return (_DEFAULT_DATASETS_DIR / "snapshots" / registry["current_version"]).resolve()

    @staticmethod
    def _resolve_output_root(output_root: Optional[str]) -> Path:
        if not output_root:
            return _DEFAULT_MODELS_DIR
        candidate = Path(output_root)
        if not candidate.is_absolute():
            candidate = _BACKEND_DIR / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(_BACKEND_DIR)
        except ValueError as exc:
            raise ValueError("模型目录必须位于 backend-service 内") from exc
        return resolved

    @staticmethod
    def _to_backend_relative(path: Path) -> str:
        try:
            return path.resolve().relative_to(_BACKEND_DIR).as_posix()
        except ValueError as exc:
            raise ValueError("持久化路径必须位于 backend-service 内") from exc

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temp_name).replace(path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise
# @AI_GENERATED: end
