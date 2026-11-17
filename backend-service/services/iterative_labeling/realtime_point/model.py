# @AI_GENERATED
# -*- coding: utf-8 -*-
"""严格因果的实时点 TCN。

所有卷积只做左侧 padding；TemporalLayerNorm 只在同一时刻的通道维归一化，
不会汇总未来时间位置。输入为 [B,W,C]，输出为 [B,W,K]。
"""
from __future__ import annotations

from typing import Sequence

import torch
from torch import nn
from torch.nn import functional as F


class CausalConv1d(nn.Module):
    """仅在左侧补零的一维膨胀卷积。"""

    def __init__(self, in_channels: int, out_channels: int, kernel_size: int, dilation: int) -> None:
        super().__init__()
        if kernel_size <= 0 or dilation <= 0:
            raise ValueError("kernel_size 和 dilation 必须为正整数")
        self.left_padding = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(
            in_channels,
            out_channels,
            kernel_size=kernel_size,
            dilation=dilation,
            padding=0,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(F.pad(x, (self.left_padding, 0)))


class TemporalLayerNorm(nn.Module):
    """每个时刻独立在 hidden channel 维执行 LayerNorm。"""

    def __init__(self, channels: int) -> None:
        super().__init__()
        self.norm = nn.LayerNorm(channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.norm(x.transpose(1, 2)).transpose(1, 2)


class CausalResidualBlock(nn.Module):
    """两层因果卷积、逐时刻归一化和残差连接。"""

    def __init__(
        self,
        in_channels: int,
        hidden_channels: int,
        *,
        kernel_size: int,
        dilation: int,
        dropout: float,
    ) -> None:
        super().__init__()
        self.conv1 = CausalConv1d(in_channels, hidden_channels, kernel_size, dilation)
        self.norm1 = TemporalLayerNorm(hidden_channels)
        self.conv2 = CausalConv1d(hidden_channels, hidden_channels, kernel_size, dilation)
        self.norm2 = TemporalLayerNorm(hidden_channels)
        self.activation = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.residual = (
            nn.Conv1d(in_channels, hidden_channels, kernel_size=1)
            if in_channels != hidden_channels
            else nn.Identity()
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = self.residual(x)
        hidden = self.dropout(self.activation(self.norm1(self.conv1(x))))
        hidden = self.dropout(self.activation(self.norm2(self.conv2(hidden))))
        return self.activation(hidden + residual)


class CausalTCNRealtime(nn.Module):
    """实时逐点分类 TCN，输出每个输入槽的类别 logits。"""

    def __init__(
        self,
        *,
        in_channels: int,
        n_classes: int,
        hidden_channels: int = 32,
        kernel_size: int = 3,
        dilations: Sequence[int] = (1, 2, 4, 8),
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        if in_channels <= 0 or n_classes <= 1 or hidden_channels <= 0:
            raise ValueError("in_channels/hidden_channels 必须为正，n_classes 必须大于 1")
        if not dilations or any(int(value) <= 0 for value in dilations):
            raise ValueError("dilations 必须是非空正整数序列")
        self.in_channels = int(in_channels)
        self.n_classes = int(n_classes)
        self.hidden_channels = int(hidden_channels)
        self.kernel_size = int(kernel_size)
        self.dilations = tuple(int(value) for value in dilations)
        self.dropout_rate = float(dropout)

        blocks = []
        current_channels = self.in_channels
        for dilation in self.dilations:
            blocks.append(
                CausalResidualBlock(
                    current_channels,
                    self.hidden_channels,
                    kernel_size=self.kernel_size,
                    dilation=dilation,
                    dropout=self.dropout_rate,
                )
            )
            current_channels = self.hidden_channels
        self.blocks = nn.ModuleList(blocks)
        self.classifier = nn.Conv1d(self.hidden_channels, self.n_classes, kernel_size=1)
        self._reset_parameters()

    @property
    def receptive_field_points(self) -> int:
        return 1 + 2 * (self.kernel_size - 1) * sum(self.dilations)

    def constructor_config(self) -> dict:
        """返回仅包含构造器可接收字段的恢复配置。"""
        return {
            "in_channels": self.in_channels,
            "n_classes": self.n_classes,
            "hidden_channels": self.hidden_channels,
            "kernel_size": self.kernel_size,
            "dilations": list(self.dilations),
            "dropout": self.dropout_rate,
        }

    def model_config(self) -> dict:
        return {
            **self.constructor_config(),
            "normalization": "per_timestep_layer_norm",
            "receptive_field_points": self.receptive_field_points,
        }

    def _reset_parameters(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Conv1d):
                nn.init.kaiming_normal_(module.weight, nonlinearity="relu")
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 3 or x.shape[-1] != self.in_channels:
            raise ValueError(
                f"CausalTCNRealtime 期望 [B,W,{self.in_channels}]，收到 {tuple(x.shape)}"
            )
        hidden = x.transpose(1, 2)
        for block in self.blocks:
            hidden = block(hidden)
        return self.classifier(hidden).transpose(1, 2)

    def predict(self, x: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            return self.forward(x).argmax(dim=-1)
# @AI_GENERATED: end
