# @AI_GENERATED
"""
时序数据增强 — 用于序列标注训练集扩充。

参考文献：
  - "Data Augmentation for Time-Series Classification" (arxiv:2310.10060)
  - "Time Series Data Augmentation for Deep Learning: A Survey" (arxiv:2002.12478)

四种增强方式（全部不改变标签语义，只变换 X 不变 Y）：
  1. Jittering: 加高斯噪声
  2. Scaling: 幅度缩放
  3. Magnitude Warping: 非线性幅度扭曲（模拟信号漂移）
  4. Window Slicing: 子窗口裁剪（从 seq_len 取 sub_len 子段，标签同步）

不使用的增强（及原因）：
  - Time Warping: 扰乱段边界位置
  - Permutation: 破坏时序连续性
  - Mixup/CutMix: 不同故障混合无物理意义
  - GAN/VAE: 数据太少训不好生成器
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np


def jitter(
    x: np.ndarray, y: np.ndarray, sigma: float = 0.03,
    rng: Optional[np.random.Generator] = None,
    mask: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """加高斯噪声。sigma 相对于信号标准差的比例。

    ``mask`` 为 [seq_len] 的 1/0 数组时（1=实测），噪声只落在实测点上。
    网格对齐后夜间空槽被填成精确 0、白天空槽是插值出来的，给这些点加噪会把
    「补出来的点」伪造成有观测抖动的真实点，破坏掩码通道的语义。
    """
    rng = rng or np.random.default_rng()
    noise = rng.normal(0, sigma, size=x.shape).astype(x.dtype)
    if mask is not None:
        noise = noise * np.asarray(mask, dtype=x.dtype).reshape(-1, 1)
    return x + noise, y.copy()


def scaling(
    x: np.ndarray, y: np.ndarray, lo: float = 0.85, hi: float = 1.15,
    rng: Optional[np.random.Generator] = None,
    mask: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """幅度缩放（模拟不同容量设备）。零值点缩放后仍为零，无需 mask。"""
    rng = rng or np.random.default_rng()
    scale = rng.uniform(lo, hi)
    return (x * scale).astype(x.dtype), y.copy()


def magnitude_warp(
    x: np.ndarray, y: np.ndarray, n_knots: int = 4, sigma: float = 0.1,
    rng: Optional[np.random.Generator] = None,
    mask: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """非线性幅度扭曲：用平滑随机曲线乘以信号，模拟缓慢增益变化。"""
    rng = rng or np.random.default_rng()
    seq_len = x.shape[0]
    knots = rng.normal(1.0, sigma, size=n_knots)
    warp = np.interp(
        np.linspace(0, 1, seq_len),
        np.linspace(0, 1, n_knots),
        knots,
    ).astype(x.dtype)
    return x * warp[:, np.newaxis], y.copy()


def window_slice(
    x: np.ndarray, y: np.ndarray, target_len: int = 100,
    rng: Optional[np.random.Generator] = None,
    mask: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """子窗口裁剪：随机取 target_len 点子段，标签同步。

    注意：网格对齐后序列下标即时钟槽位，裁剪会破坏「下标 144 = 12:00」的契约，
    因此不在 ``augment_batch`` 的默认方法里启用。
    """
    rng = rng or np.random.default_rng()
    seq_len = x.shape[0]
    if seq_len <= target_len:
        return x.copy(), y.copy()
    max_start = seq_len - target_len
    start = rng.integers(0, max_start + 1)
    return x[start:start + target_len].copy(), y[start:start + target_len].copy()


# ---- 组合接口 ----

AUGMENT_METHODS = {
    "jitter": jitter,
    "scaling": scaling,
    "magnitude_warp": magnitude_warp,
    "window_slice": window_slice,
}


def augment_one(
    x: np.ndarray, y: np.ndarray, method: str,
    rng: Optional[np.random.Generator] = None,
    mask: Optional[np.ndarray] = None,
    **kwargs
) -> Tuple[np.ndarray, np.ndarray]:
    """对单条序列做指定增强。``mask`` 透传给支持掩码的方法（当前只有 jitter 使用）。"""
    if method not in AUGMENT_METHODS:
        raise ValueError(f"未知增强方法: {method}，可选: {sorted(AUGMENT_METHODS)}")
    return AUGMENT_METHODS[method](x, y, rng=rng, mask=mask, **kwargs)


def augment_batch(
    X: List[np.ndarray], Y: List[np.ndarray],
    n_augments: int = 4,
    methods: Optional[List[str]] = None,
    seed: int = 42,
    masks: Optional[List[Optional[np.ndarray]]] = None,
) -> Tuple[List[np.ndarray], List[np.ndarray], List[str]]:
    """
    对一批序列做增强，返回增强后的 X, Y, 方法名列表。

    每条原始序列产出 n_augments 条增强序列，输出顺序为
    ``第 i 条原始序列 → 下标 i*n_augments .. i*n_augments+n_augments-1``，
    调用方依赖这个顺序回溯 source_idx，不要改动。
    方法从 methods 列表中轮流选取（不含 window_slice，因为它改变长度）。

    Parameters
    ----------
    masks:
        与 ``X`` 等长的掩码列表（每项 [seq_len] 的 1/0 数组，1=实测）。
        传入后 jitter 只对实测点加噪，不污染网格补出的槽位。

    Returns
    -------
    aug_X, aug_Y, aug_methods
    """
    methods = methods or ["jitter", "scaling", "magnitude_warp"]
    rng = np.random.default_rng(seed)
    if masks is not None and len(masks) != len(X):
        raise ValueError("masks 与 X 数量不一致")

    aug_X, aug_Y, aug_methods = [], [], []
    for i, (x, y) in enumerate(zip(X, Y)):
        mask = masks[i] if masks is not None else None
        for j in range(n_augments):
            m = methods[(i * n_augments + j) % len(methods)]
            xa, ya = augment_one(x, y, m, rng=rng, mask=mask)
            aug_X.append(xa)
            aug_Y.append(ya)
            aug_methods.append(m)

    return aug_X, aug_Y, aug_methods
# @AI_GENERATED: end
