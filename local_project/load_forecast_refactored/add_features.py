"""
Compatibility layer for feature helpers.

The refactored ``features/engine.py`` still imports a set of feature helper
functions from ``add_features`` for historical reasons. In this repository, the
high-level time / holiday / shift features are implemented directly in
``features/engine.py``.

This module provides lightweight, no-leakage-safe stubs so the pipeline can run
end-to-end. You can replace these stubs with your full feature implementation
later (lag/rolling/diff/stat features, etc.).
"""

from __future__ import annotations

import pandas as pd


def _ensure_df(df: pd.DataFrame) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)


def get_stat_features(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    return _ensure_df(df)


def get_rolling_features(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    return _ensure_df(df)


def get_hist_period_statis(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    return _ensure_df(df)


def get_same_moment_window_statis(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    return _ensure_df(df)


def get_period_load_rate(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    return _ensure_df(df)


def get_diff_features(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    return _ensure_df(df)


def get_pct_rate_feature(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    return _ensure_df(df)

