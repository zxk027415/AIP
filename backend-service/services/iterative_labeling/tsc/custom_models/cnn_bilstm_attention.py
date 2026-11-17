# @AI_GENERATED
"""
CNN-BiLSTM-Attention 时序分类器（Tier 3）。

架构:
  多尺度并行卷积(kernel=3/7/15/31) → Concat →
  BiLSTM(128, return_sequences=True) →
  TemporalAttention → 加权上下文向量 →
  Dense(128) → ReLU → Dropout → Dense(n_classes) → Softmax

需要 PyTorch。sklearn 兼容接口: fit(X, y) / predict(X) / predict_proba(X)
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


class CnnBiLstmAttentionClassifier:
    """
    CNN-BiLSTM-Attention 故障诊断分类器。

    Parameters
    ----------
    cnn_filters : list[int]
        每个分支的卷积 filter 数量，默认 [64, 128, 256]。
        实际用第一个值作为每分支 filter 数。
    kernel_sizes : list[int]
        多尺度卷积核大小，默认 [3, 7, 15, 31]。
    lstm_units : int
        BiLSTM 隐层维度（每方向）。
    attention_heads : int
        时间注意力头数。
    dropout : float
        Dropout 比例。
    n_epochs : int
        训练轮数。
    batch_size : int
        批大小。
    lr : float
        学习率。
    patience : int
        Early stopping patience。
    """

    def __init__(
        self,
        cnn_filters: Optional[List[int]] = None,
        kernel_sizes: Optional[List[int]] = None,
        lstm_units: int = 128,
        attention_heads: int = 4,
        dropout: float = 0.3,
        n_epochs: int = 200,
        batch_size: int = 32,
        lr: float = 1e-3,
        patience: int = 10,
    ):
        if not HAS_TORCH:
            raise ImportError("CNN-BiLSTM-Attention 需要 PyTorch，请先安装: pip install torch")

        self.cnn_filters = cnn_filters or [64, 128, 256]
        self.kernel_sizes = kernel_sizes or [3, 7, 15, 31]
        self.lstm_units = lstm_units
        self.attention_heads = attention_heads
        self.dropout = dropout
        self.n_epochs = n_epochs
        self.batch_size = batch_size
        self.lr = lr
        self.patience = patience
        self._model: Optional[nn.Module] = None
        self._classes: Optional[np.ndarray] = None
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def fit(self, X: np.ndarray, y: np.ndarray) -> "CnnBiLstmAttentionClassifier":
        """训练。X: [n_samples, series_length, n_channels] (time-first)"""
        self._classes = np.unique(y)
        n_classes = len(self._classes)
        n_channels = X.shape[2] if X.ndim == 3 else 1
        seq_len = X.shape[1]

        label_map = {c: i for i, c in enumerate(self._classes)}
        y_mapped = np.array([label_map[yi] for yi in y], dtype=np.int64)

        class_counts = np.bincount(y_mapped, minlength=n_classes).astype(np.float32)
        class_weights = 1.0 / np.maximum(class_counts, 1.0)
        class_weights = class_weights / class_weights.sum() * n_classes
        weight_tensor = torch.tensor(class_weights, dtype=torch.float32).to(self._device)

        branch_filters = self.cnn_filters[0] if self.cnn_filters else 64
        self._model = _CnnBiLstmAttentionNet(
            n_channels=n_channels,
            n_classes=n_classes,
            branch_filters=branch_filters,
            kernel_sizes=self.kernel_sizes,
            lstm_units=self.lstm_units,
            attention_heads=self.attention_heads,
            dropout=self.dropout,
        ).to(self._device)

        optimizer = torch.optim.Adam(self._model.parameters(), lr=self.lr)
        criterion = nn.CrossEntropyLoss(weight=weight_tensor)

        X_t = torch.tensor(X, dtype=torch.float32)
        if X_t.ndim == 2:
            X_t = X_t.unsqueeze(-1)
        X_t = X_t.permute(0, 2, 1)  # [n, C, T]
        y_t = torch.tensor(y_mapped, dtype=torch.long)

        dataset = TensorDataset(X_t, y_t)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        best_loss = float("inf")
        patience_counter = 0

        self._model.train()
        for epoch in range(self.n_epochs):
            epoch_loss = 0.0
            for xb, yb in loader:
                xb, yb = xb.to(self._device), yb.to(self._device)
                optimizer.zero_grad()
                logits = self._model(xb)
                loss = criterion(logits, yb)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item() * len(xb)
            epoch_loss /= len(dataset)

            if epoch_loss < best_loss - 1e-4:
                best_loss = epoch_loss
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= self.patience:
                    logger.info("Early stopping at epoch %d", epoch)
                    break

        self._model.eval()
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        proba = self.predict_proba(X)
        return self._classes[proba.argmax(axis=1)]

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        self._model.eval()
        X_t = torch.tensor(X, dtype=torch.float32)
        if X_t.ndim == 2:
            X_t = X_t.unsqueeze(-1)
        X_t = X_t.permute(0, 2, 1).to(self._device)
        with torch.no_grad():
            logits = self._model(X_t)
            return torch.softmax(logits, dim=1).cpu().numpy()


if HAS_TORCH:
    class _TemporalAttention(nn.Module):
        """时间维度注意力：学习每个时间步的重要性权重。"""

        def __init__(self, hidden_dim: int):
            super().__init__()
            self.attn = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.Tanh(),
                nn.Linear(hidden_dim // 2, 1, bias=False),
            )

        def forward(self, lstm_out: torch.Tensor) -> torch.Tensor:
            # lstm_out: [batch, T, hidden_dim]
            scores = self.attn(lstm_out).squeeze(-1)  # [batch, T]
            weights = torch.softmax(scores, dim=1).unsqueeze(-1)  # [batch, T, 1]
            context = (lstm_out * weights).sum(dim=1)  # [batch, hidden_dim]
            return context

    class _CnnBiLstmAttentionNet(nn.Module):
        """完整网络。"""

        def __init__(
            self,
            n_channels: int,
            n_classes: int,
            branch_filters: int,
            kernel_sizes: List[int],
            lstm_units: int,
            attention_heads: int,
            dropout: float,
        ):
            super().__init__()
            # 多尺度并行卷积分支
            self.branches = nn.ModuleList()
            for ks in kernel_sizes:
                branch = nn.Sequential(
                    nn.Conv1d(n_channels, branch_filters, kernel_size=ks, padding=ks // 2),
                    nn.BatchNorm1d(branch_filters),
                    nn.ReLU(),
                )
                self.branches.append(branch)

            concat_dim = branch_filters * len(kernel_sizes)

            # BiLSTM
            self.lstm = nn.LSTM(
                input_size=concat_dim,
                hidden_size=lstm_units,
                batch_first=True,
                bidirectional=True,
            )

            lstm_out_dim = lstm_units * 2  # 双向

            # 时间注意力
            self.attention = _TemporalAttention(lstm_out_dim)

            # 分类头
            self.classifier = nn.Sequential(
                nn.Linear(lstm_out_dim, 128),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(128, n_classes),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            # x: [batch, C, T]
            branch_outs = [branch(x) for branch in self.branches]  # each [batch, filters, T]
            fused = torch.cat(branch_outs, dim=1)  # [batch, concat_dim, T]
            fused = fused.permute(0, 2, 1)  # [batch, T, concat_dim]

            lstm_out, _ = self.lstm(fused)  # [batch, T, lstm_units*2]
            context = self.attention(lstm_out)  # [batch, lstm_units*2]
            logits = self.classifier(context)  # [batch, n_classes]
            return logits
# @AI_GENERATED: end
