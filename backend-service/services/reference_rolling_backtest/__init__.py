# -*- coding: utf-8 -*-
"""
参考滚动日回测（与 load_forecast_refactored/run_weihai_backtest.py 行为对齐，代码部署在 backend 内，不依赖本地开发目录）。
"""
from .config import ReferenceBacktestConfig
from .engine import run_from_file, run_rolling_backtest, to_platform_daily_results

__all__ = [
    "ReferenceBacktestConfig",
    "run_from_file",
    "run_rolling_backtest",
    "to_platform_daily_results",
]
