# @AI_GENERATED
"""
Focal Loss for sequence labeling — 处理极度类别不平衡。

参考：Lin et al., "Focal Loss for Dense Object Detection" (ICCV 2017, Facebook AI Research)

核心思想：在标准 CE 前加调制因子 (1-p_t)^γ，当模型对某样本已很自信时
（p_t 接近 1），该样本的 loss 被压到接近 0。效果：
  - γ=0: 退化为标准 CE
  - γ=2（推荐）: p_t=0.9 的样本 loss 降为 CE 的 1%，模型精力集中在难样本
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class FocalLoss(nn.Module):
    """
    Multi-class Focal Loss for point-level sequence labeling.

    Parameters
    ----------
    alpha : Tensor of shape [n_classes], optional
        每类权重（通常用逆频率归一化）。None 则不加权。
    gamma : float
        聚焦参数。0=标准CE，2=推荐值。
    ignore_index : int
        忽略的标签值（padding），不参与 loss 计算。
    """

    def __init__(
        self,
        alpha: torch.Tensor = None,
        gamma: float = 2.0,
        ignore_index: int = -1,
        reduction: str = "mean",
    ):
        super().__init__()
        self.gamma = gamma
        self.ignore_index = ignore_index
        self.reduction = reduction
        if alpha is not None:
            self.register_buffer("alpha", alpha.float())
        else:
            self.alpha = None

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """
        Args:
            logits: [N, C] — 未 softmax 的 logits（N=展平后的点数，C=类数）
            targets: [N] — 真实标签

        Returns:
            scalar loss
        """
        # 过滤 ignore_index
        mask = targets != self.ignore_index
        logits = logits[mask]
        targets = targets[mask]

        if logits.numel() == 0:
            return torch.tensor(0.0, device=logits.device, requires_grad=True)

        # softmax 概率
        probs = F.softmax(logits, dim=-1)
        # 取目标类的概率 p_t
        targets_one_hot = F.one_hot(targets, num_classes=logits.size(-1)).float()
        p_t = (probs * targets_one_hot).sum(dim=-1)  # [N]

        # focal 调制因子
        focal_weight = (1.0 - p_t) ** self.gamma

        # CE loss（不 reduce）
        ce = F.cross_entropy(logits, targets, reduction="none")

        # 加 alpha 权重
        if self.alpha is not None:
            alpha_t = self.alpha[targets]
            focal_weight = focal_weight * alpha_t

        loss = focal_weight * ce

        if self.reduction == "mean":
            return loss.mean()
        elif self.reduction == "sum":
            return loss.sum()
        return loss
# @AI_GENERATED: end
