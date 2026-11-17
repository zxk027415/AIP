# @AI_GENERATED
"""
1D U-Net 序列标注模型 — 逐点分类。

输入: [batch, seq_len, n_channels]
输出: [batch, seq_len, n_classes]  逐点分类 logits

结构：编码器（下采样提取上下文）→ 解码器（上采样恢复逐点分辨率）+ 跳跃连接。
参数量约 2~3 万，CPU 几秒能训完。

适配 120 点输入（白天时段 07:00~17:00 @ 5min = 120 点）：
  120 → pool(2) → 60 → pool(2) → 30 → up(2) → 60 → up(2) → 120
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class ConvBlock(nn.Module):
    """Conv1D + BN + ReLU × 2"""

    def __init__(self, in_ch: int, out_ch: int, kernel_size: int = 5):
        super().__init__()
        pad = kernel_size // 2
        self.conv = nn.Sequential(
            nn.Conv1d(in_ch, out_ch, kernel_size, padding=pad),
            nn.BatchNorm1d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv1d(out_ch, out_ch, kernel_size, padding=pad),
            nn.BatchNorm1d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.conv(x)


class UNet1D(nn.Module):
    """
    1D U-Net for sequence labeling.

    Parameters
    ----------
    in_channels : int
        输入通道数（2 = value + i_cal）
    n_classes : int
        输出类别数（0=正常 + 各故障类型）
    base_filters : int
        第一层卷积核数，后续层翻倍
    """

    def __init__(self, in_channels: int = 2, n_classes: int = 8, base_filters: int = 16):
        super().__init__()

        f = base_filters
        # 编码器
        self.enc1 = ConvBlock(in_channels, f)
        self.enc2 = ConvBlock(f, f * 2)
        self.enc3 = ConvBlock(f * 2, f * 4)  # 瓶颈

        self.pool = nn.MaxPool1d(2)

        # 解码器
        self.up2 = nn.ConvTranspose1d(f * 4, f * 2, kernel_size=2, stride=2)
        self.dec2 = ConvBlock(f * 4, f * 2)  # concat 后通道翻倍

        self.up1 = nn.ConvTranspose1d(f * 2, f, kernel_size=2, stride=2)
        self.dec1 = ConvBlock(f * 2, f)

        # 输出
        self.out_conv = nn.Conv1d(f, n_classes, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [batch, seq_len, in_channels]

        Returns:
            logits: [batch, seq_len, n_classes]
        """
        # Conv1d expects [batch, channels, seq_len]
        x = x.permute(0, 2, 1)

        # 编码
        e1 = self.enc1(x)           # [B, f, L]
        e2 = self.enc2(self.pool(e1))  # [B, 2f, L/2]
        e3 = self.enc3(self.pool(e2))  # [B, 4f, L/4]

        # 解码 + 跳跃连接
        d2 = self.up2(e3)  # [B, 2f, L/2]
        # 处理奇数长度导致的 size 不匹配
        if d2.shape[2] != e2.shape[2]:
            d2 = F.pad(d2, (0, e2.shape[2] - d2.shape[2]))
        d2 = self.dec2(torch.cat([d2, e2], dim=1))  # [B, 2f, L/2]

        d1 = self.up1(d2)  # [B, f, L]
        if d1.shape[2] != e1.shape[2]:
            d1 = F.pad(d1, (0, e1.shape[2] - d1.shape[2]))
        d1 = self.dec1(torch.cat([d1, e1], dim=1))  # [B, f, L]

        out = self.out_conv(d1)  # [B, n_classes, L]
        return out.permute(0, 2, 1)  # [B, L, n_classes]

    def predict(self, x: torch.Tensor) -> torch.Tensor:
        """返回逐点预测类别 [batch, seq_len]。"""
        with torch.no_grad():
            logits = self.forward(x)
            return logits.argmax(dim=-1)
# @AI_GENERATED: end
