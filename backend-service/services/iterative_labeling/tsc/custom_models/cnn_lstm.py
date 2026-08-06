# @AI_GENERATED
"""
CNN-LSTM 时序分类器（Tier 3）。

架构:
  Conv1D(64, k=7) → BN → ReLU →
  Conv1D(128, k=5) → BN → ReLU → MaxPool(2) → Dropout(0.2) →
  LSTM(64) → Dropout(0.3) →
  Dense(64) → ReLU → Dropout(0.3) →
  Dense(n_classes) → Softmax

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


class CnnLstmClassifier:
    """
    CNN-LSTM 故障诊断分类器。

    Parameters
    ----------
    cnn_filters : list[int]
        卷积层 filter 数量，默认 [64, 128]。
    lstm_units : int
        LSTM 隐层维度。
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
        lstm_units: int = 64,
        dropout: float = 0.3,
        n_epochs: int = 200,
        batch_size: int = 32,
        lr: float = 1e-3,
        patience: int = 10,
    ):
        if not HAS_TORCH:
            raise ImportError("CNN-LSTM 需要 PyTorch，请先安装: pip install torch")

        self.cnn_filters = cnn_filters or [64, 128]
        self.lstm_units = lstm_units
        self.dropout = dropout
        self.n_epochs = n_epochs
        self.batch_size = batch_size
        self.lr = lr
        self.patience = patience
        self._model: Optional[nn.Module] = None
        self._classes: Optional[np.ndarray] = None
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def fit(self, X: np.ndarray, y: np.ndarray) -> "CnnLstmClassifier":
        """
        训练。X shape: [n_samples, series_length, n_channels] (time-first)
        """
        self._classes = np.unique(y)
        n_classes = len(self._classes)
        n_channels = X.shape[2] if X.ndim == 3 else 1
        seq_len = X.shape[1]

        # label → 连续 0..n_classes-1
        label_map = {c: i for i, c in enumerate(self._classes)}
        y_mapped = np.array([label_map[yi] for yi in y], dtype=np.int64)

        # class weights
        class_counts = np.bincount(y_mapped, minlength=n_classes).astype(np.float32)
        class_weights = 1.0 / np.maximum(class_counts, 1.0)
        class_weights = class_weights / class_weights.sum() * n_classes
        weight_tensor = torch.tensor(class_weights, dtype=torch.float32).to(self._device)

        # 构建网络
        self._model = _CnnLstmNet(
            n_channels=n_channels,
            seq_len=seq_len,
            n_classes=n_classes,
            cnn_filters=self.cnn_filters,
            lstm_units=self.lstm_units,
            dropout=self.dropout,
        ).to(self._device)

        optimizer = torch.optim.Adam(self._model.parameters(), lr=self.lr)
        criterion = nn.CrossEntropyLoss(weight=weight_tensor)

        # 转 tensor: [n, seq_len, n_channels] → [n, n_channels, seq_len] for Conv1d
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
                    logger.info("Early stopping at epoch %d (best_loss=%.4f)", epoch, best_loss)
                    break

        self._model.eval()
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别。"""
        proba = self.predict_proba(X)
        indices = proba.argmax(axis=1)
        return self._classes[indices]

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率。"""
        self._model.eval()
        X_t = torch.tensor(X, dtype=torch.float32)
        if X_t.ndim == 2:
            X_t = X_t.unsqueeze(-1)
        X_t = X_t.permute(0, 2, 1).to(self._device)

        with torch.no_grad():
            logits = self._model(X_t)
            proba = torch.softmax(logits, dim=1).cpu().numpy()
        return proba


if HAS_TORCH:
    class _CnnLstmNet(nn.Module):
        """CNN-LSTM 网络结构。"""

        def __init__(
            self,
            n_channels: int,
            seq_len: int,
            n_classes: int,
            cnn_filters: List[int],
            lstm_units: int,
            dropout: float,
        ):
            super().__init__()
            layers = []
            in_ch = n_channels
            for f in cnn_filters:
                layers.extend([
                    nn.Conv1d(in_ch, f, kernel_size=7 if in_ch == n_channels else 5, padding="same"),
                    nn.BatchNorm1d(f),
                    nn.ReLU(),
                ])
                in_ch = f
            layers.append(nn.MaxPool1d(2))
            layers.append(nn.Dropout(dropout * 0.6))
            self.cnn = nn.Sequential(*layers)

            self.lstm = nn.LSTM(
                input_size=in_ch,
                hidden_size=lstm_units,
                batch_first=True,
            )
            self.dropout = nn.Dropout(dropout)
            self.fc1 = nn.Linear(lstm_units, 64)
            self.fc2 = nn.Linear(64, n_classes)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            # x: [batch, C, T]
            x = self.cnn(x)           # [batch, filters[-1], T//2]
            x = x.permute(0, 2, 1)    # [batch, T//2, filters[-1]]
            _, (h_n, _) = self.lstm(x)  # h_n: [1, batch, lstm_units]
            x = h_n.squeeze(0)        # [batch, lstm_units]
            x = self.dropout(x)
            x = torch.relu(self.fc1(x))
            x = self.dropout(x)
            x = self.fc2(x)
            return x
# @AI_GENERATED: end
