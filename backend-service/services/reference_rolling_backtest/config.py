# -*- coding: utf-8 -*-
"""
Reference rolling backtest configuration (aligned with local run_weihai_backtest.py).
All fields optional in API; defaults match the reference script.
"""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ReferenceBacktestConfig:
    """控制与本地威海滚动回测脚本一致的行为，便于算子/平台复用。"""

    train_days: int = 30
    daily_horizon: int = 96
    n_splits: int = 5
    bo_init_points: int = 3
    bo_n_iter: int = 12
    xgb_n_estimators: int = 200
    n_estimators_final: int = 200
    # 与本地脚本一致：XGB + LGB + CatBoost + Ridge 自适应集成
    models: Tuple[str, ...] = ("xgb", "lgb", "catb", "ridge")
    use_bayesian_tuning: bool = True
    # 长表筛选（与模板 load_csv + row_filter 一致）
    parent_id: Optional[str] = None
    child_id: Optional[str] = None
    time_field: str = "record_time"
    load_field: str = "load"
    # 回测起止日（含 start，不含 end 的最后一日预测逻辑由引擎按天迭代）
    min_train_row_frac: float = 0.7  # 与本地 TRAIN_DAYS * 96 * 0.7 一致
    # @AI_GENERATED
    gap_days: int = 1  # 训练数据截止到 pred_day - 1 - gap_days（默认 1，即 D-2）
    # 业务含义：D 日执行预测时，D-1 日数据尚未采集完成，因此训练数据只能用到 D-2
    # 设为 0 则退化为原始无 gap 逻辑（训练截止到 pred_day - 1）
    # @AI_GENERATED: end
