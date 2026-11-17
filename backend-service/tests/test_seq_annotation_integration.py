# -*- coding: utf-8 -*-
# @AI_GENERATED
"""序列标注工件、全天标签规则与逐点预测契约的聚焦测试。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

import services.iterative_labeling.seq_annotation.predictor as predictor_module
import services.iterative_labeling.seq_annotation.trainer as trainer_module
from services.iterative_labeling.seq_annotation.augmentation import jitter
from services.iterative_labeling.seq_annotation.dataset_builder import _load_one_indexed
from services.iterative_labeling.seq_annotation.grid_align import (
    IGNORE_LABEL,
    SLOTS_PER_DAY,
    align_day_to_grid,
    grid_contract,
    slot_of,
)
from services.iterative_labeling.seq_annotation.models import get_model
from services.iterative_labeling.seq_annotation.predictor import SeqAnnotationPredictor
from services.iterative_labeling.seq_annotation.trainer import SeqAnnotationTrainer


def _write_model_artifact(
    root: Path,
    *,
    seq_len: int = 288,
    trained_full_day: bool = True,
    grid_aligned: bool = False,
    labels: list[int] | None = None,
) -> Path:
    """写入可加载的小型模型工件；默认模拟旧两通道工件。"""
    artifact = root / "artifact"
    artifact.mkdir(parents=True)
    labels = labels or [0, 1]
    channels = ["value", "i_cal", "is_measured"] if grid_aligned else ["value", "i_cal"]
    model = get_model("unet1d", in_channels=len(channels), n_classes=len(labels))
    weight_path = artifact / "model.pt"
    torch.save(model.state_dict(), weight_path)
    metadata = {
        "schema_version": 1,
        "artifact_format": "torch_state_dict_dir",
        "modeling_path": "seq_annotation",
        "model_ref": "artifact",
        "model_name": "unet1d",
        "n_classes": len(labels),
        "labels": labels,
        "class_index_to_label": labels,
        "channels": channels,
        "seq_len": seq_len,
        "trained_full_day": trained_full_day,
        "daylight_start_hour": 0 if trained_full_day else 7,
        "daylight_end_hour": 24 if trained_full_day else 17,
        "normalization": "per_sequence_channel_zscore",
        "model_sha256": hashlib.sha256(weight_path.read_bytes()).hexdigest(),
    }
    if grid_aligned:
        metadata["grid_contract"] = grid_contract()
        metadata["normalization_exclude_channels"] = ["is_measured"]
        metadata["mask_channel"] = "is_measured"
    (artifact / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )
    return artifact


def _sparse_full_day_frame(day: str = "2026-08-01") -> pd.DataFrame:
    """构造白天 5 分钟、夜间 10 分钟采样的物理完整自然日（204 个实测槽）。"""
    full = pd.date_range(day, periods=SLOTS_PER_DAY, freq="5min")
    daytime = (full.hour >= 7) & (full.hour < 17)
    keep = daytime | ((full.minute % 10) == 0)
    times = full[keep]
    slot = slot_of(times).astype(np.float32)
    return pd.DataFrame(
        {
            "time": times,
            "value": slot,
            "i_cal": slot * 2.0 + 1.0,
        }
    )


def test_predictor_fails_closed_when_artifact_is_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(predictor_module, "_BACKEND_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="模型目录不存在"):
        SeqAnnotationPredictor("missing-artifact")


def test_legacy_predictor_keeps_original_row_alignment_path(tmp_path: Path, monkeypatch):
    """旧两通道工件没有 grid_contract，继续走历史兼容路径。"""
    _write_model_artifact(tmp_path)
    monkeypatch.setattr(predictor_module, "_BACKEND_DIR", tmp_path)
    predictor = SeqAnnotationPredictor("artifact")
    timestamps = pd.date_range("2026-08-01", periods=288, freq="5min")
    frame = pd.DataFrame(
        {
            "time": timestamps,
            "value": np.sin(np.linspace(0, 8, 288)).astype(np.float32) + 2.0,
            "i_cal": np.cos(np.linspace(0, 8, 288)).astype(np.float32) + 2.0,
        }
    )

    result = predictor.predict_device_day(frame, include_night=True)

    assert result["error"] is None
    assert result["n_points_predicted"] == 288
    assert len(result["timestamps"]) == 288
    assert len(result["point_predictions"]) == 288
    assert len(result["point_confidences"]) == 288
    assert sum(segment["n_points"] for segment in result["segment_predictions"]) == 288
    assert result["trained_full_day"] is True
    assert result["grid_aligned"] is False


def test_grid_predictor_derives_mask_and_reports_288_clock_slots(
    tmp_path: Path, monkeypatch
):
    """新工件接受稀疏完整日，不要求调用方提供 mask，并保持 12:00 在槽 144。"""
    _write_model_artifact(tmp_path, grid_aligned=True)
    monkeypatch.setattr(predictor_module, "_BACKEND_DIR", tmp_path)
    predictor = SeqAnnotationPredictor("artifact")
    frame = _sparse_full_day_frame()

    result = predictor.predict_device_day(frame, include_night=True)

    assert result["error"] is None
    assert result["grid_aligned"] is True
    assert result["n_points_predicted"] == SLOTS_PER_DAY
    assert result["n_points_measured"] == len(frame)
    assert len(result["point_is_measured"]) == SLOTS_PER_DAY
    assert result["point_is_measured"][1] == 0  # 00:05 是夜间补零槽
    assert result["point_is_measured"][144] == 1  # 12:00 是实测槽
    assert result["timestamps"][144].startswith("2026-08-01T12:00:00")


def test_predictor_maps_contiguous_class_index_back_to_jump_business_label(
    tmp_path: Path, monkeypatch
):
    """模型类别 1 必须映射成业务 label=5，而不是错误返回整数 1。"""
    _write_model_artifact(tmp_path, grid_aligned=True, labels=[0, 5])
    monkeypatch.setattr(predictor_module, "_BACKEND_DIR", tmp_path)
    predictor = SeqAnnotationPredictor("artifact")

    class FixedClassOne(torch.nn.Module):
        def forward(self, tensor):
            logits = torch.zeros(
                (tensor.shape[0], tensor.shape[1], 2), dtype=tensor.dtype
            )
            logits[:, :, 1] = 10.0
            return logits

    predictor._model = FixedClassOne()
    result = predictor.predict_device_day(_sparse_full_day_frame(), include_night=True)

    assert result["error"] is None
    assert result["predicted_label"] == 5
    assert set(result["point_predictions"]) == {5}


def test_predictor_rejects_multiple_natural_days_in_one_grid_request(
    tmp_path: Path, monkeypatch
):
    """多天同钟点不能覆盖进同一 288 槽，避免跨日数据混合。"""
    _write_model_artifact(tmp_path, grid_aligned=True)
    monkeypatch.setattr(predictor_module, "_BACKEND_DIR", tmp_path)
    predictor = SeqAnnotationPredictor("artifact")
    frame = pd.concat(
        [_sparse_full_day_frame("2026-08-01"), _sparse_full_day_frame("2026-08-02")],
        ignore_index=True,
    )

    result = predictor.predict_device_day(frame, include_night=True)

    assert result["n_points_predicted"] == 0
    assert "单个自然日" in result["error"]


def test_predictor_rejects_night_mode_for_daylight_only_model(tmp_path: Path, monkeypatch):
    _write_model_artifact(tmp_path, seq_len=120, trained_full_day=False)
    monkeypatch.setattr(predictor_module, "_BACKEND_DIR", tmp_path)
    predictor = SeqAnnotationPredictor("artifact")
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-08-01", periods=288, freq="5min"),
            "value": np.arange(288, dtype=np.float32),
            "i_cal": np.arange(288, dtype=np.float32) + 1,
        }
    )
    with pytest.raises(ValueError, match="禁止执行夜间诊断"):
        predictor.predict_device_day(frame, include_night=True)


def test_sparse_full_day_aligns_to_clock_grid_with_zero_fill_and_mask():
    """204 行物理完整日应保留为 288 槽，而不是被原始行数门槛误杀。"""
    frame = _sparse_full_day_frame()
    aligned = align_day_to_grid(
        frame["time"],
        frame[["value", "i_cal"]].to_numpy(),
    )

    assert aligned.ok is True
    assert aligned.values.shape == (SLOTS_PER_DAY, 2)
    assert aligned.measured_mask.shape == (SLOTS_PER_DAY,)
    assert aligned.occupied_slots == 204
    assert aligned.hours_covered == 24
    assert aligned.is_full_day is True
    assert aligned.values[1].tolist() == [0.0, 0.0]  # 夜间 00:05 空槽
    assert aligned.measured_mask[1] == 0
    assert aligned.values[144, 0] == pytest.approx(144.0)  # 12:00 的时钟位置不漂移


def test_daytime_short_gap_interpolates_but_long_gap_is_rejected():
    frame = _sparse_full_day_frame()
    short_gap = frame[frame["time"] != pd.Timestamp("2026-08-01 12:05:00")]
    aligned = align_day_to_grid(
        short_gap["time"], short_gap[["value", "i_cal"]].to_numpy()
    )
    assert aligned.ok is True
    assert aligned.measured_mask[145] == 0
    assert aligned.values[145, 0] == pytest.approx(145.0)
    assert aligned.values[145, 1] == pytest.approx(291.0)

    gap_times = pd.date_range("2026-08-01 12:00:00", periods=7, freq="5min")
    long_gap = frame[~frame["time"].isin(gap_times)]
    rejected = align_day_to_grid(
        long_gap["time"], long_gap[["value", "i_cal"]].to_numpy()
    )
    assert rejected.ok is False
    assert rejected.reason == "daytime_gap_too_long"
    assert rejected.longest_daytime_gap == 7


def test_daylight_only_rows_are_rejected_and_not_claimed_as_full_day():
    frame = _sparse_full_day_frame()
    daylight = frame[(frame["time"].dt.hour >= 7) & (frame["time"].dt.hour < 17)]
    rejected = align_day_to_grid(
        daylight["time"], daylight[["value", "i_cal"]].to_numpy()
    )

    assert rejected.ok is False
    assert rejected.reason == "occupancy_below_threshold"
    assert rejected.hours_covered == 10
    assert rejected.is_full_day is False


def test_unlabeled_slots_remain_ignored_without_label_extrapolation():
    """显式标签只约束自身槽位；白天、夜间的未标注槽都保持忽略。"""
    times = pd.to_datetime(["2026-08-01 12:00:00"])
    aligned = align_day_to_grid(
        times,
        np.asarray([[5.0, 6.0]], dtype=np.float32),
        np.asarray([1], dtype=np.int64),
        min_occupied_slots=1,
        min_daytime_occupancy=0.0,
        max_daytime_gap_slots=SLOTS_PER_DAY,
        require_all_hours_covered=False,  # 这条测试关注标签规则，不是覆盖率
    )
    assert aligned.ok is True
    assert aligned.labels[145] == IGNORE_LABEL  # 12:05 未显式标注
    assert aligned.labels[1] == IGNORE_LABEL  # 夜间也不得由物理先验制造监督标签


def test_pure_day_label_is_rejected_and_only_explicit_points_are_consumed():
    day = pd.Timestamp("2026-08-01").date()
    key = ("s1", "d1", "b1", day)
    frame = _sparse_full_day_frame()
    measurements = {key: frame}

    weak_labels = {
        key: pd.DataFrame(
            {
                "time": frame["time"],
                "label_id": np.ones(len(frame), dtype=np.int64),
                "source": ["day_label"] * len(frame),
            }
        )
    }
    _, _, weak_reason, ok = _load_one_indexed(
        measurements,
        weak_labels,
        "s1",
        "d1",
        "b1",
        day,
        use_labels=True,
    )
    assert ok is False
    assert weak_reason["reason"] == "pure_day_label_not_allowed_for_seq"

    sources = np.full(len(frame), "day_label", dtype=object)
    night_explicit = frame["time"].isin(
        [pd.Timestamp("2026-08-01 01:00:00"), pd.Timestamp("2026-08-01 20:00:00")]
    )
    sources[night_explicit.to_numpy()] = "human_range"
    explicit_labels = {
        key: pd.DataFrame(
            {
                "time": frame["time"],
                "label_id": np.ones(len(frame), dtype=np.int64),
                "source": sources,
            }
        )
    }
    _, explicit_y, _, ok = _load_one_indexed(
        measurements,
        explicit_labels,
        "s1",
        "d1",
        "b1",
        day,
        use_labels=True,
    )
    assert ok is True
    assert explicit_y[12] == 1
    assert explicit_y[96] == -1
    assert explicit_y[240] == 1


def test_jitter_does_not_modify_imputed_slots_and_trainer_keeps_mask_binary():
    x = np.zeros((8, 2), dtype=np.float32)
    x[:, 0] = np.arange(8, dtype=np.float32)
    mask = np.asarray([1, 0, 1, 0, 1, 0, 1, 0], dtype=np.float32)
    augmented, _ = jitter(
        x,
        np.zeros(8, dtype=np.int64),
        sigma=1.0,
        rng=np.random.default_rng(9),
        mask=mask,
    )
    assert np.array_equal(augmented[mask == 0], x[mask == 0])
    assert not np.array_equal(augmented[mask == 1], x[mask == 1])

    trainer = SeqAnnotationTrainer(epochs=1, device="cpu")
    trainer._norm_exclude = (2,)
    sequence = np.concatenate(
        [x[np.newaxis], mask[np.newaxis, :, np.newaxis]], axis=2
    )
    normalized = trainer._normalize(sequence)
    assert np.array_equal(normalized[0, :, 2], mask)
    assert set(np.unique(normalized[0, :, 2])) == {0.0, 1.0}


def test_trainer_persists_relative_directory_artifact(tmp_path: Path, monkeypatch):
    backend = tmp_path / "backend-service"
    dataset_dir = backend / "data" / "seq_annotation_datasets" / "snapshots" / "snap-test"
    dataset_dir.mkdir(parents=True)
    rng = np.random.default_rng(7)
    X = rng.normal(size=(8, 16, 2)).astype(np.float32)
    Y = np.zeros((8, 16), dtype=np.int64)
    Y[1::2, 6:11] = 1
    meta = pd.DataFrame(
        {
            "site_id": ["s1"] * 8,
            "device_id": [f"d{i // 2}" for i in range(8)],
            "branch_id": ["b1"] * 8,
            "is_augmented": [False] * 8,
            "sample_weight": [1.0] * 8,
            "data_type": ["segment_boundary" if i % 2 else "whole_day_normal" for i in range(8)],
        }
    )
    np.savez_compressed(dataset_dir / "dataset.npz", X=X, Y=Y)
    meta.to_parquet(dataset_dir / "meta.parquet", index=False)
    (dataset_dir / "build_config.json").write_text(
        json.dumps(
            {
                "version": "snap-test",
                "seq_len": 16,
                "channels": ["value", "i_cal"],
                "daylight_hours": [7, 17],
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "build_report.json").write_text(
        json.dumps(
            {
                "version": "snap-test",
                "seq_len": 16,
                "labels": [0, 1],
                "label_snapshot_hash": "hash-test",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(trainer_module, "_BACKEND_DIR", backend)
    monkeypatch.setattr(
        trainer_module,
        "_DEFAULT_MODELS_DIR",
        backend / "data" / "models" / "seq_annotation",
    )
    trainer = SeqAnnotationTrainer(
        model_name="unet1d",
        epochs=1,
        batch_size=4,
        test_ratio=0.25,
        random_state=3,
        device="cpu",
    )
    result = trainer.train(
        "data/seq_annotation_datasets/snapshots/snap-test"
    )

    assert result["model_path"].startswith("data/models/seq_annotation/")
    assert not Path(result["model_path"]).is_absolute()
    artifact = backend / result["model_path"]
    assert (artifact / "model.pt").is_file()
    metadata = json.loads((artifact / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["artifact_format"] == "torch_state_dict_dir"
    assert metadata["trained_full_day"] is False
    assert metadata["training_config"]["loss"] == "cross_entropy"
    assert metadata["training_config"]["sampler"] == "uniform_shuffle"
    assert metadata["training_config"]["tier_sample_weight"] is False
    assert metadata["model_sha256"] == hashlib.sha256(
        (artifact / "model.pt").read_bytes()
    ).hexdigest()


# ============================================================================
# 安全修复回归测试（2026-08-12）：
#   R1 标签 ID 跳号 → 类别映射正确，绝不预测注册表不存在的类别
#   R2 半日补零不得被误标为全天 288 点模型（缺 real 全天网格验证即拒绝）
#   R3 fault_mask_iou 是故障点掩码 IoU，而非伪分段 IoU
# ============================================================================


def _write_jump_label_dataset(
    root: Path,
    *,
    seq_len: int = 288,
    labels: list[int] | None = None,
    full_day_grid_validated: bool = False,
    daylight_hours: list[int] | None = None,
) -> Path:
    """构造一个标签跳号（label id 非连续）的小型快照目录。"""
    labels = labels if labels is not None else [0, 2, 5]  # 刻意跳号：缺 1/3/4
    n_classes = len(labels)
    dataset_dir = root / "data" / "seq_annotation_datasets" / "snapshots" / "snap-jump"
    dataset_dir.mkdir(parents=True)
    rng = np.random.default_rng(11)
    n_seq = 6
    X = rng.normal(size=(n_seq, seq_len, 2)).astype(np.float32)
    # 每序列用真实业务标签填充，覆盖全部跳号类
    Y = np.tile(np.asarray(labels, dtype=np.int64), (n_seq, 1))
    while Y.shape[1] < seq_len:
        Y = np.concatenate([Y, Y], axis=1)
    Y = Y[:, :seq_len]
    meta = pd.DataFrame(
        {
            "site_id": ["s1"] * n_seq,
            "device_id": [f"d{i}" for i in range(n_seq)],
            "branch_id": ["b1"] * n_seq,
            "is_augmented": [False] * n_seq,
            "sample_weight": [1.0] * n_seq,
            "data_type": [
                "segment_boundary" if i % 2 else "whole_day_normal"
                for i in range(n_seq)
            ],
        }
    )
    np.savez_compressed(dataset_dir / "dataset.npz", X=X, Y=Y)
    meta.to_parquet(dataset_dir / "meta.parquet", index=False)
    (dataset_dir / "build_config.json").write_text(
        json.dumps(
            {
                "version": "snap-jump",
                "seq_len": seq_len,
                "channels": ["value", "i_cal"],
                "daylight_hours": daylight_hours if daylight_hours is not None else [0, 24],
            }
        ),
        encoding="utf-8",
    )
    report = {
        "version": "snap-jump",
        "seq_len": seq_len,
        "labels": labels,
        "label_snapshot_hash": "hash-jump",
    }
    if full_day_grid_validated:
        report["full_day_grid_validated"] = True
    (dataset_dir / "build_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    return dataset_dir


def test_label_jump_is_mapped_to_contiguous_classes_not_business_ids(
    tmp_path: Path, monkeypatch
):
    """R1：跳号业务标签必须映射到连续类别索引，n_classes 只统计出现过的标签。"""
    backend = tmp_path / "backend-service"
    dataset_dir = _write_jump_label_dataset(backend, seq_len=288, labels=[0, 2, 5])
    monkeypatch.setattr(trainer_module, "_BACKEND_DIR", backend)
    monkeypatch.setattr(
        trainer_module,
        "_DEFAULT_MODELS_DIR",
        backend / "data" / "models" / "seq_annotation",
    )
    trainer = SeqAnnotationTrainer(
        model_name="unet1d",
        epochs=1,
        batch_size=4,
        test_ratio=0.4,
        random_state=5,
        device="cpu",
    )
    result = trainer.train(
        "data/seq_annotation_datasets/snapshots/snap-jump"
    )

    # 标签空间保留业务 ID（跳号 0/2/5），不补成 0..5 全连续
    snapshot = result["label_space_snapshot"]
    assert snapshot["labels"] == [0, 2, 5]
    assert snapshot["n_classes"] == 3
    assert snapshot["class_index_to_label"] == [0, 2, 5]

    artifact_dir = backend / result["model_path"]
    metadata = json.loads(
        (artifact_dir / "metadata.json").read_text(encoding="utf-8")
    )
    # 模型类别数 = 3（连续索引 0/1/2），业务 label = [0,2,5]
    assert metadata["n_classes"] == 3
    assert metadata["labels"] == [0, 2, 5]
    assert metadata["class_index_to_label"] == [0, 2, 5]


def test_half_day_zero_padded_is_not_marked_full_day_without_grid_validation(
    tmp_path: Path, monkeypatch
):
    """R2：即使 seq_len==288 且 daylight=[0,24]，缺真实全天网格验证仍不得标为全天。"""
    backend = tmp_path / "backend-service"
    dataset_dir = _write_jump_label_dataset(
        backend,
        seq_len=288,
        labels=[0, 2, 5],
        full_day_grid_validated=False,  # 未提供真实全天网格验证结果
        daylight_hours=[0, 24],
    )
    monkeypatch.setattr(trainer_module, "_BACKEND_DIR", backend)
    monkeypatch.setattr(
        trainer_module,
        "_DEFAULT_MODELS_DIR",
        backend / "data" / "models" / "seq_annotation",
    )
    trainer = SeqAnnotationTrainer(
        model_name="unet1d", epochs=1, batch_size=4, test_ratio=0.4,
        random_state=5, device="cpu",
    )
    result = trainer.train("data/seq_annotation_datasets/snapshots/snap-jump")

    assert result["sequence_contract"]["trained_full_day"] is False
    assert result["sample_strategy"]["trained_full_day"] is False

    artifact_dir = backend / result["model_path"]
    metadata = json.loads(
        (artifact_dir / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["trained_full_day"] is False
    assert metadata["full_day_grid_validated"] is False


def test_full_day_requires_explicit_grid_validation(tmp_path: Path, monkeypatch):
    """R2 正例：完整网格结构 + 覆盖证据同时满足 → 才标全天。"""
    backend = tmp_path / "backend-service"
    dataset_dir = _write_jump_label_dataset(
        backend,
        seq_len=288,
        labels=[0, 2, 5],
        full_day_grid_validated=True,
        daylight_hours=[0, 24],
    )
    # 正例必须同时有完整网格结构，不能只靠布尔值蒙混过关。
    config_path = dataset_dir / "build_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["channels"] = ["value", "i_cal", "is_measured"]
    config["grid_contract"] = {
        "grid_aligned": True,
        "slots_per_day": 288,
        "slot_minutes": 5,
        "require_all_hours_covered": True,
        "mask_channel": "is_measured",
        "full_day_grid_validated": True,
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    # dataset X 通道数须匹配 channels
    data = np.load(dataset_dir / "dataset.npz")
    X_old = data["X"]
    mask_channel = np.ones((*X_old.shape[:2], 1), dtype=np.float32)
    X_new = np.concatenate([X_old, mask_channel], axis=-1)
    np.savez_compressed(dataset_dir / "dataset.npz", X=X_new, Y=data["Y"])

    monkeypatch.setattr(trainer_module, "_BACKEND_DIR", backend)
    monkeypatch.setattr(
        trainer_module,
        "_DEFAULT_MODELS_DIR",
        backend / "data" / "models" / "seq_annotation",
    )
    trainer = SeqAnnotationTrainer(
        model_name="unet1d", epochs=1, batch_size=4, test_ratio=0.4,
        random_state=5, device="cpu",
    )
    result = trainer.train("data/seq_annotation_datasets/snapshots/snap-jump")
    assert result["sequence_contract"]["trained_full_day"] is True
    metadata = json.loads(
        ((backend / result["model_path"]) / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["trained_full_day"] is True
    assert metadata["full_day_grid_validated"] is True


def test_fault_mask_iou_is_point_mask_iou(tmp_path: Path, monkeypatch):
    """R3：fault_mask_iou 必须等于故障点掩码 IoU（交集/并集），不是段级伪指标。"""
    backend = tmp_path / "backend-service"
    monkeypatch.setattr(trainer_module, "_BACKEND_DIR", backend)
    monkeypatch.setattr(
        trainer_module,
        "_DEFAULT_MODELS_DIR",
        backend / "data" / "models" / "seq_annotation",
    )
    trainer = SeqAnnotationTrainer(
        model_name="unet1d", epochs=1, batch_size=4, test_ratio=0.4,
        random_state=5, device="cpu",
    )

    # 构造确定性的真值：business label = [0, 2, 5]，连续类别映射 0->0, 2->1, 5->2
    # 单条序列，便于精确验证 IoU 语义（_evaluate 按整个 batch 展平计算）
    X = np.random.default_rng(3).normal(size=(1, 64, 2)).astype(np.float32)
    Y = np.zeros((1, 64), dtype=np.int64)
    Y[0, 5:10] = 2   # 连续类别 1 的故障点（5 点）
    labels_model = [0, 2, 5]
    business_to_class = {0: 0, 2: 1, 5: 2}
    Y_model = np.full(Y.shape, trainer_module.IGNORE_INDEX, dtype=np.int64)
    for biz, cls in business_to_class.items():
        Y_model[Y == biz] = cls

    # fake 模型：predict 返回连续类别索引。
    class FakeModel:
        def __init__(self, prediction_class):
            self._pred = prediction_class

        def eval(self):
            return self

        def predict(self, tensor):
            n = tensor.shape[0]
            arr = np.full((n, 64), self._pred, dtype=np.int64)
            return torch.from_numpy(arr)

    # 场景 A：真值有 5 个故障点，预测全正常（类别 0 -> 业务 label 0）
    #   intersection = 0, union = 5, iou = 0.0
    model_all_normal = FakeModel(prediction_class=0)
    metrics_normal = trainer._evaluate(model_all_normal, X, Y_model, labels_model)
    assert metrics_normal["fault_mask_iou"] == 0.0

    # 场景 B：真值 5:10 是故障（5 点），预测 5:12 是故障（类别 1 -> label 2，7 点）
    #   intersection=5, union=7, iou=5/7
    class FakeModelExact:
        def eval(self):
            return self

        def predict(self, tensor):
            n = tensor.shape[0]
            arr = np.zeros((n, 64), dtype=np.int64)
            arr[0, 5:12] = 1  # 连续类别 1 -> 业务 label 2
            return torch.from_numpy(arr)

    metrics_exact = trainer._evaluate(FakeModelExact(), X, Y_model, labels_model)
    assert metrics_exact["fault_mask_iou"] == pytest.approx(5 / 7)

    # 完整训练产物：accuracy_record 含 fault_mask_iou 且不含旧 segment_iou
    dataset_dir = _write_jump_label_dataset(backend, seq_len=288, labels=[0, 2, 5])
    result = trainer.train("data/seq_annotation_datasets/snapshots/snap-jump")
    acc = result["accuracy_record"]
    assert "fault_mask_iou" in acc
    assert "segment_iou" not in acc
    assert 0.0 <= acc["fault_mask_iou"] <= 1.0
# @AI_GENERATED: end
