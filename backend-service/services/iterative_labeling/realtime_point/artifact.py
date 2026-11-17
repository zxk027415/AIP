# @AI_GENERATED
# -*- coding: utf-8 -*-
"""实时点 Causal TCN 工件的严格恢复入口。"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import torch

from .model import CausalTCNRealtime
from .trainer import FixedRobustScaler

_BACKEND = Path(__file__).resolve().parents[3]
_PROJECT_ROOT = _BACKEND.parent
_REQUIRED_CHECKPOINT_KEYS = {
    "state_dict",
    "constructor_config",
    "model_config",
    "normalization",
    "class_index_to_label",
    "data_contract",
}


def _resolve_artifact_dir(path: str) -> Path:
    if not path or Path(path).is_absolute() or os.path.isabs(path):
        raise ValueError(f"artifact_dir 必须是项目根相对路径: {path!r}")
    resolved = (_PROJECT_ROOT / Path(path.replace("\\", "/"))).resolve()
    try:
        resolved.relative_to(_PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"artifact_dir 越界项目根: {path}") from exc
    return resolved


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class LoadedRealtimePointArtifact:
    """已恢复的模型、固定 scaler、标签映射和审计元数据。"""

    model: CausalTCNRealtime
    scaler: FixedRobustScaler
    class_index_to_label: Tuple[int, ...]
    metadata: Dict[str, Any]
    device: torch.device

    def forward(self, raw_windows: np.ndarray) -> torch.Tensor:
        """对原始 `[B,W,C]` 窗口执行固定归一化并返回 logits。"""
        expected_window = int(self.metadata["context_length"])
        if raw_windows.ndim != 3 or raw_windows.shape[1] != expected_window:
            raise ValueError(
                f"实时点工件期望窗口 [B,{expected_window},C]，收到 {raw_windows.shape}"
            )
        scaled = self.scaler.transform(raw_windows)
        tensor = torch.from_numpy(scaled).float().to(self.device)
        with torch.no_grad():
            logits = self.model(tensor)
        if not torch.isfinite(logits).all():
            raise RuntimeError("恢复模型 forward 产生非有限 logits")
        return logits


def load_realtime_point_artifact(
    artifact_dir: str,
    *,
    device: str = "cpu",
) -> LoadedRealtimePointArtifact:
    """从项目根相对目录恢复并完整校验 realtime-point-model-v2 工件。"""
    artifact_path = _resolve_artifact_dir(artifact_dir)
    metadata_path = artifact_path / "metadata.json"
    model_path = artifact_path / "model.pt"
    if not artifact_path.is_dir() or not metadata_path.is_file() or not model_path.is_file():
        raise FileNotFoundError(f"实时点模型工件不完整: {artifact_dir}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_contract = {
        "schema_version": "realtime-point-model-v2",
        "artifact_format": "torch_state_dict_dir",
        "modeling_path": "pv_fault_realtime",
        "model_name": "causal_tcn_realtime",
        "causal": True,
    }
    for field, expected in expected_contract.items():
        if metadata.get(field) != expected:
            raise ValueError(
                f"模型工件契约字段 {field} 不匹配: "
                f"expected={expected!r}, actual={metadata.get(field)!r}"
            )
    if metadata.get("promotion_eligible") is not False:
        raise ValueError("Phase 0 实时点工件不得标记为可晋升")
    policy = metadata.get("missing_value_policy") or {}
    expected_policy = {
        "mode": "past_only_forward_fill_then_zero",
        "remaining_fill_value": 0.0,
        "measurement_mask_channel": "is_measured",
        "time_since_channel": "time_since_measured",
        "uses_future_values": False,
    }
    for field, expected in expected_policy.items():
        if policy.get(field) != expected:
            raise ValueError(f"missing_value_policy.{field} 不符合实时因果契约")
    if not isinstance(policy.get("max_forward_fill_slots"), int) or policy["max_forward_fill_slots"] < 0:
        raise ValueError("missing_value_policy.max_forward_fill_slots 非法")
    label_contract = metadata.get("label_space_contract") or {}
    if (
        label_contract.get("source") != "train_target_mask_only"
        or label_contract.get("evaluation_unseen_policy") != "fail_closed"
    ):
        raise ValueError("label_space_contract 未声明 train-only/fail-closed")
    unseen_by_split = label_contract.get("unseen_labels_by_split") or {}
    if any((unseen_by_split.get(split) or {}).get("point_count") != 0 for split in ["val", "test"]):
        raise ValueError("工件包含 train 未见的 val/test 标签")

    expected_path = metadata.get("model_path")
    if not isinstance(expected_path, str) or _resolve_artifact_dir(expected_path) != model_path:
        raise ValueError("metadata.model_path 与工件目录中的 model.pt 不一致")
    expected_sha = metadata.get("model_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError("metadata.model_sha256 缺失或格式错误")
    actual_sha = _sha256_file(model_path)
    if actual_sha != expected_sha:
        raise RuntimeError("model.pt SHA-256 与 metadata 不一致")

    checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict):
        raise ValueError("model.pt 顶层必须是字典")
    missing_keys = sorted(_REQUIRED_CHECKPOINT_KEYS - set(checkpoint))
    if missing_keys:
        raise ValueError(f"model.pt 缺少字段: {missing_keys}")
    for field in [
        "constructor_config",
        "model_config",
        "normalization",
        "class_index_to_label",
        "data_contract",
    ]:
        if checkpoint[field] != metadata.get(field):
            raise ValueError(f"model.pt 与 metadata 的 {field} 不一致")

    constructor_config = checkpoint["constructor_config"]
    allowed_constructor_keys = {
        "in_channels",
        "n_classes",
        "hidden_channels",
        "kernel_size",
        "dilations",
        "dropout",
    }
    if not isinstance(constructor_config, dict) or set(constructor_config) != allowed_constructor_keys:
        raise ValueError("constructor_config 字段集合不符合 CausalTCNRealtime 构造契约")
    model = CausalTCNRealtime(**constructor_config)
    if model.model_config() != checkpoint["model_config"]:
        raise ValueError("model_config 派生字段与构造结果不一致")
    model.load_state_dict(checkpoint["state_dict"], strict=True)

    scaler = FixedRobustScaler.from_state_dict(checkpoint["normalization"])
    labels = tuple(int(value) for value in checkpoint["class_index_to_label"])
    if len(labels) != model.n_classes or len(set(labels)) != len(labels):
        raise ValueError("class_index_to_label 与模型类别数不一致或包含重复标签")
    if list(labels) != metadata.get("labels") or scaler.channels != metadata.get("channels"):
        raise ValueError("标签/通道映射与 metadata 不一致")
    if metadata.get("n_classes") != model.n_classes:
        raise ValueError("metadata.n_classes 与恢复模型类别数不一致")
    if len(scaler.channels) != model.in_channels:
        raise ValueError("metadata/scaler channels 与恢复模型输入通道数不一致")
    context_length = metadata.get("context_length")
    slot_minutes = metadata.get("slot_minutes")
    if not isinstance(context_length, int) or context_length <= 0:
        raise ValueError("metadata.context_length 必须是正整数")
    # slot_minutes=0 表示 event-time 点路径（无固定 grid）；legacy pv_fault grid 仍要求 >0
    if not isinstance(slot_minutes, int) or slot_minutes < 0:
        raise ValueError("metadata.slot_minutes 必须是非负整数")
    data_contract = checkpoint["data_contract"]
    expected_data_contract = {
        "dataset_version": metadata.get("dataset_version"),
        "source_snapshot_version": metadata.get("source_snapshot_version"),
        "context_length": context_length,
        "slot_minutes": slot_minutes,
        "channels": metadata.get("channels"),
        "missing_value_policy": metadata.get("missing_value_policy"),
    }
    if not isinstance(data_contract, dict) or data_contract != expected_data_contract:
        raise ValueError("checkpoint.data_contract 与 metadata 训练数据契约不一致")
    if not isinstance(data_contract["dataset_version"], str) or not data_contract["dataset_version"]:
        raise ValueError("data_contract.dataset_version 缺失")
    if (
        not isinstance(data_contract["source_snapshot_version"], str)
        or not data_contract["source_snapshot_version"]
    ):
        raise ValueError("data_contract.source_snapshot_version 缺失")
    target_mode = metadata.get("target_mode")
    burn_in_points = metadata.get("burn_in_points")
    if target_mode not in {"last_point", "burn_in_multi_point"}:
        raise ValueError("metadata.target_mode 不受支持")
    if not isinstance(burn_in_points, int) or not 0 <= burn_in_points < context_length:
        raise ValueError("metadata.burn_in_points 与 context_length 不一致")
    if target_mode == "last_point" and burn_in_points != context_length - 1:
        raise ValueError("last_point 工件的 burn_in_points 必须等于窗口末点")
    if target_mode == "burn_in_multi_point" and burn_in_points < model.receptive_field_points - 1:
        raise ValueError("burn-in 工件在完整感受野之前产生监督")
    causal_audit = metadata.get("causal_audit") or {}
    if (
        causal_audit.get("all_passed") is not True
        or (causal_audit.get("preprocessing") or {}).get("all_passed") is not True
        or (causal_audit.get("model_and_normalizer") or {}).get("all_passed") is not True
    ):
        raise ValueError("工件因果审计未全部通过")
    if (metadata.get("alarm_policy") or {}).get("enabled") is not False:
        raise ValueError("Phase 0 工件不得启用告警策略")

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("请求 cuda，但当前 PyTorch 不可用 CUDA")
    target_device = torch.device(device)
    model.to(target_device)
    model.eval()
    return LoadedRealtimePointArtifact(
        model=model,
        scaler=scaler,
        class_index_to_label=labels,
        metadata=metadata,
        device=target_device,
    )
# @AI_GENERATED: end
