# @AI_GENERATED
"""
序列标注候选模型库 — 逐点分类。

所有模型统一接口：
  forward(x: [B, L, C]) -> logits: [B, L, n_classes]
  predict(x) -> [B, L]  逐点预测类别

候选：
  unet1d   — 1D U-Net，编解码 + 跳跃连接，擅长分割
  tcn      — Temporal Conv Network，膨胀卷积扩大感受野，纯并行
  bilstm   — 双向 LSTM，序列依赖建模
  bilstm_attn — BiLSTM + 自注意力
  transformer — Transformer encoder，全局依赖
"""
from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------- U-Net
class ConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, k: int = 5):
        super().__init__()
        p = k // 2
        self.net = nn.Sequential(
            nn.Conv1d(in_ch, out_ch, k, padding=p), nn.BatchNorm1d(out_ch), nn.ReLU(inplace=True),
            nn.Conv1d(out_ch, out_ch, k, padding=p), nn.BatchNorm1d(out_ch), nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.net(x)


class UNet1D(nn.Module):
    """1D U-Net：下采样提上下文，上采样恢复逐点分辨率 + 跳跃连接。"""

    def __init__(self, in_channels: int = 2, n_classes: int = 13, base_filters: int = 16):
        super().__init__()
        f = base_filters
        self.enc1 = ConvBlock(in_channels, f)
        self.enc2 = ConvBlock(f, f * 2)
        self.enc3 = ConvBlock(f * 2, f * 4)
        self.pool = nn.MaxPool1d(2)
        self.up2 = nn.ConvTranspose1d(f * 4, f * 2, 2, stride=2)
        self.dec2 = ConvBlock(f * 4, f * 2)
        self.up1 = nn.ConvTranspose1d(f * 2, f, 2, stride=2)
        self.dec1 = ConvBlock(f * 2, f)
        self.out = nn.Conv1d(f, n_classes, 1)

    def forward(self, x):
        x = x.permute(0, 2, 1)
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        d2 = self.up2(e3)
        if d2.shape[2] != e2.shape[2]:
            d2 = F.pad(d2, (0, e2.shape[2] - d2.shape[2]))
        d2 = self.dec2(torch.cat([d2, e2], 1))
        d1 = self.up1(d2)
        if d1.shape[2] != e1.shape[2]:
            d1 = F.pad(d1, (0, e1.shape[2] - d1.shape[2]))
        d1 = self.dec1(torch.cat([d1, e1], 1))
        return self.out(d1).permute(0, 2, 1)

    def predict(self, x):
        with torch.no_grad():
            return self.forward(x).argmax(-1)


# ---------------------------------------------------------------- TCN
class Chomp1d(nn.Module):
    """裁掉膨胀卷积右侧多余的 padding，保持因果性与长度一致。"""

    def __init__(self, chomp_size: int):
        super().__init__()
        self.chomp_size = chomp_size

    def forward(self, x):
        return x[:, :, :-self.chomp_size].contiguous() if self.chomp_size > 0 else x


class TemporalBlock(nn.Module):
    def __init__(self, n_in: int, n_out: int, k: int, dilation: int, dropout: float = 0.2):
        super().__init__()
        pad = (k - 1) * dilation
        self.net = nn.Sequential(
            nn.Conv1d(n_in, n_out, k, padding=pad, dilation=dilation),
            Chomp1d(pad), nn.BatchNorm1d(n_out), nn.ReLU(), nn.Dropout(dropout),
            nn.Conv1d(n_out, n_out, k, padding=pad, dilation=dilation),
            Chomp1d(pad), nn.BatchNorm1d(n_out), nn.ReLU(), nn.Dropout(dropout),
        )
        self.downsample = nn.Conv1d(n_in, n_out, 1) if n_in != n_out else None
        self.relu = nn.ReLU()

    def forward(self, x):
        out = self.net(x)
        res = x if self.downsample is None else self.downsample(x)
        return self.relu(out + res)


class TCN(nn.Module):
    """
    Temporal Conv Network：膨胀卷积堆叠，感受野随层数指数增长。

    优势：纯卷积可并行（比 LSTM 快），感受野可控，梯度稳定。
    """

    def __init__(self, in_channels: int = 2, n_classes: int = 13,
                 hidden: int = 32, levels: int = 4, kernel_size: int = 3, dropout: float = 0.2):
        super().__init__()
        layers = []
        for i in range(levels):
            dil = 2 ** i
            n_in = in_channels if i == 0 else hidden
            layers.append(TemporalBlock(n_in, hidden, kernel_size, dil, dropout))
        self.tcn = nn.Sequential(*layers)
        self.out = nn.Conv1d(hidden, n_classes, 1)

    def forward(self, x):
        x = x.permute(0, 2, 1)
        h = self.tcn(x)
        return self.out(h).permute(0, 2, 1)

    def predict(self, x):
        with torch.no_grad():
            return self.forward(x).argmax(-1)


# ---------------------------------------------------------------- BiLSTM
class BiLSTM(nn.Module):
    """双向 LSTM：每个时间步的输出同时看到前后文。"""

    def __init__(self, in_channels: int = 2, n_classes: int = 13,
                 hidden: int = 64, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            in_channels, hidden, num_layers=num_layers, batch_first=True,
            bidirectional=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        self.dropout = nn.Dropout(dropout)
        self.out = nn.Linear(hidden * 2, n_classes)

    def forward(self, x):
        h, _ = self.lstm(x)          # [B, L, 2*hidden]
        return self.out(self.dropout(h))

    def predict(self, x):
        with torch.no_grad():
            return self.forward(x).argmax(-1)


# ---------------------------------------------------------------- BiLSTM + Attention
class BiLSTMAttn(nn.Module):
    """BiLSTM + 单头自注意力，增强长程依赖。"""

    def __init__(self, in_channels: int = 2, n_classes: int = 13,
                 hidden: int = 64, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            in_channels, hidden, num_layers=num_layers, batch_first=True,
            bidirectional=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        d = hidden * 2
        self.attn = nn.MultiheadAttention(d, num_heads=4, dropout=dropout, batch_first=True)
        self.norm = nn.LayerNorm(d)
        self.out = nn.Linear(d, n_classes)

    def forward(self, x):
        h, _ = self.lstm(x)
        a, _ = self.attn(h, h, h)
        h = self.norm(h + a)
        return self.out(h)

    def predict(self, x):
        with torch.no_grad():
            return self.forward(x).argmax(-1)


# ---------------------------------------------------------------- Transformer
class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 512):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len).unsqueeze(1).float()
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x):
        return x + self.pe[:, : x.size(1)]


class TransformerSeq(nn.Module):
    """Transformer encoder：自注意力建模全局依赖。"""

    def __init__(self, in_channels: int = 2, n_classes: int = 13,
                 d_model: int = 64, nhead: int = 4, num_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.proj = nn.Linear(in_channels, d_model)
        self.pos = PositionalEncoding(d_model)
        layer = nn.TransformerEncoderLayer(
            d_model, nhead, dim_feedforward=d_model * 4,
            dropout=dropout, batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers)
        self.out = nn.Linear(d_model, n_classes)

    def forward(self, x):
        h = self.pos(self.proj(x))
        h = self.encoder(h)
        return self.out(h)

    def predict(self, x):
        with torch.no_grad():
            return self.forward(x).argmax(-1)


# ---------------------------------------------------------------- 注册表
MODEL_REGISTRY = {
    "unet1d": {
        "cls": UNet1D,
        "params": {"base_filters": 16},
        "desc": "1D U-Net（编解码 + 跳跃连接，擅长分割）",
    },
    "unet1d_wide": {
        "cls": UNet1D,
        "params": {"base_filters": 32},
        "desc": "1D U-Net 宽版（base_filters=32）",
    },
    "tcn": {
        "cls": TCN,
        "params": {"hidden": 32, "levels": 4},
        "desc": "Temporal Conv Network（膨胀卷积，纯并行）",
    },
    "tcn_deep": {
        "cls": TCN,
        "params": {"hidden": 48, "levels": 6},
        "desc": "TCN 深版（6 层，感受野更大）",
    },
    "bilstm": {
        "cls": BiLSTM,
        "params": {"hidden": 64, "num_layers": 2},
        "desc": "双向 LSTM（序列依赖建模）",
    },
    "bilstm_attn": {
        "cls": BiLSTMAttn,
        "params": {"hidden": 64, "num_layers": 2},
        "desc": "BiLSTM + 自注意力",
    },
    "transformer": {
        "cls": TransformerSeq,
        "params": {"d_model": 64, "nhead": 4, "num_layers": 2},
        "desc": "Transformer encoder（全局自注意力）",
    },
}


def get_model(name: str, in_channels: int = 2, n_classes: int = 13, **overrides) -> nn.Module:
    """按名字实例化模型。"""
    if name not in MODEL_REGISTRY:
        raise ValueError(f"未知模型 {name}，可选: {sorted(MODEL_REGISTRY)}")
    entry = MODEL_REGISTRY[name]
    params = {**entry["params"], **overrides}
    return entry["cls"](in_channels=in_channels, n_classes=n_classes, **params)


def list_models() -> list:
    """返回所有候选模型名 + 描述。"""
    return [{"name": k, "desc": v["desc"]} for k, v in MODEL_REGISTRY.items()]
# @AI_GENERATED: end
