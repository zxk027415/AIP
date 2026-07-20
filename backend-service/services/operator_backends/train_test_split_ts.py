# @AI_GENERATED
"""
train_test_split_ts operator backend — Splits time series data into train/test sets.

Maintains time order (no shuffle). Supports split_date (takes priority over ratio).
Params: train_ratio (default 0.8), val_ratio (default 0.1), split_date (optional).
Advanced params: time_field, target_column, task_type, forecast_horizon.

新增参数（mode）：
  - mode = "split"（默认）— 按 train_ratio/split_date 切分，返回 train + test
  - mode = "all_train"   — 不做任何切分，全部数据当训练集，test_features/test_target 返回空。
                           生产 cron `lf_daily_rolling` 触发时使用此模式：
                           训练窗口已由 `compute_training_window` 从外部确定，
                           无需再在 workflow 内部切分测试集（避免浪费 20% 数据）。

向后兼容：不传 mode 或传 mode="split" 时行为与旧版完全相同。
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "train_test_split_ts"

DEFAULT_EXCLUDE_FEATURE_COLUMNS = (
    "id",
    "parent_id",
    "child_id",
    "feature_name",
    "create_time",
    "updated_at",
    "update_time",
    "date",
)


def _parse_column_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [c.strip() for c in value.split(",") if c.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(c).strip() for c in value if str(c).strip()]
    return []


def _pick_target_column(df: pd.DataFrame, primary: str, fallbacks: list[str]) -> str:
    """Pick a valid target column, preferring the primary one."""
    candidates = [primary] + [c for c in fallbacks if c and c != primary]
    best_col = None
    best_score = -1
    for col in candidates:
        if col not in df.columns:
            continue
        score = int(pd.to_numeric(df[col], errors="coerce").notna().sum())
        if score > best_score:
            best_col = col
            best_score = score
    return best_col or primary


def execute(params: dict, inputs: dict) -> dict:
    """
    Split time series data into train/test sets preserving time order.

    Args:
        params: Operator parameters including:
            - mode (str, optional): 执行模式。
                "split"（默认）— 按 train_ratio/split_date 切分训练集和测试集。
                "all_train"     — 全部数据作为训练集，test_features/test_target 返回空。
                                  生产 cron 使用：训练窗口由外部 compute_training_window 确定。
            - train_ratio (float, optional): Training set ratio. Default 0.8.
            - val_ratio (float, optional): Validation set ratio. Default 0.1.
            - split_date (str, optional): Date to split on. Takes priority over ratios.
            - time_field (str, optional): Timestamp column name. Default "record_time".
            - target_column (str, optional): Target column name. Default "load".
            - task_type (str, optional): Forecast task type (DI/D/WI/W/MI/M).
            - forecast_horizon (int, optional): Forecast horizon length.
        inputs: {"data": DataFrame}

    Returns:
        {"train_features": DataFrame, "train_target": ndarray,
         "test_features": DataFrame, "test_target": ndarray}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # Parse options
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    # @AI_GENERATED: mode 参数 — all_train 模式下跳过切分
    mode = str(params.get("mode") or options.get("mode") or "split").strip().lower()
    # @AI_GENERATED: end

    train_ratio = float(params.get("train_ratio") or options.get("train_ratio") or 0.8)
    val_ratio = float(params.get("val_ratio") or options.get("val_ratio") or 0.1)
    split_date = params.get("split_date") or options.get("split_date")
    time_field = params.get("time_field") or options.get("time_field") or "record_time"
    target_column = params.get("target_column") or options.get("target_column") or "load"
    forecast_horizon = params.get("forecast_horizon") or options.get("forecast_horizon")
    gcfg = params.get("_global_config") or {}
    if (
        not split_date
        and isinstance(gcfg, dict)
        and str(gcfg.get("operate_status", "")).lower() == "backtest"
        and gcfg.get("backtest_split_date")
    ):
        split_date = gcfg.get("backtest_split_date")

    df = data.copy()

    if df.empty:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input DataFrame is empty"
        )

    fallback_target_cols = [
        params.get("load_field"),
        options.get("load_field"),
        "value",
        "load",
    ]
    resolved_target_column = _pick_target_column(df, target_column, fallback_target_cols)
    if resolved_target_column != target_column:
        logger.warning(
            f"[{OPERATOR_ID}] 目标列从 '{target_column}' 自动回退为 '{resolved_target_column}'"
        )
        target_column = resolved_target_column

    if target_column not in df.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"Target column '{target_column}' not found. "
            f"Available columns: {list(df.columns)}",
        )

    # Sort by time field if present
    if time_field in df.columns:
        df[time_field] = pd.to_datetime(df[time_field], errors="coerce")
        df = df.sort_values(by=time_field).reset_index(drop=True)

    # @AI_GENERATED: online forecast split and all-train compatibility
    if mode == "online_forecast":
        import numpy as np

        forecast_marker = "__aip_online_forecast_row"
        if forecast_marker not in df.columns:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "InputError",
                f"mode=online_forecast requires '{forecast_marker}' marker column",
            )

        future_mask = pd.to_numeric(df[forecast_marker], errors="coerce").fillna(0).astype(float) > 0
        train_mask = ~future_mask
        training_start_raw = params.get("online_training_start") or options.get("online_training_start")
        if training_start_raw and time_field in df.columns:
            training_start = pd.to_datetime(training_start_raw, errors="coerce")
            if pd.isna(training_start):
                raise OperatorExecutionError(
                    OPERATOR_ID,
                    "ParameterError",
                    f"Invalid online_training_start: {training_start_raw!r}",
                )
            train_mask &= df[time_field] >= training_start

        training_end_raw = params.get("online_training_end") or options.get("online_training_end")
        if training_end_raw and time_field in df.columns:
            training_end = pd.to_datetime(training_end_raw, errors="coerce")
            if pd.isna(training_end):
                raise OperatorExecutionError(
                    OPERATOR_ID,
                    "ParameterError",
                    f"Invalid online_training_end: {training_end_raw!r}",
                )
            train_mask &= df[time_field] <= training_end

        train_df = df.loc[train_mask].copy()
        forecast_df = df.loc[future_mask].copy()
        if train_df.empty or forecast_df.empty:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "InputError",
                "mode=online_forecast requires both historical training rows and future forecast rows",
            )

        train_target = pd.to_numeric(train_df[target_column], errors="coerce").values.astype(float)
        if int(pd.Series(train_target).notna().sum()) <= 1:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "InputError",
                "mode=online_forecast has insufficient finite training targets",
            )

        exclude_cols = list(DEFAULT_EXCLUDE_FEATURE_COLUMNS)
        exclude_cols.extend(_parse_column_list(params.get("exclude_feature_columns")))
        exclude_cols.extend(_parse_column_list(options.get("exclude_feature_columns")))
        if isinstance(gcfg, dict):
            exclude_cols.extend(_parse_column_list(gcfg.get("exclude_feature_columns")))
        exclude_cols = sorted(set(exclude_cols) - {time_field})

        train_features = train_df.drop(columns=[target_column, forecast_marker], errors="ignore")
        test_features = forecast_df.drop(columns=[target_column, forecast_marker], errors="ignore")
        drop_cols = [
            column
            for column in exclude_cols
            if column in train_features.columns or column in test_features.columns
        ]
        if drop_cols:
            train_features = train_features.drop(
                columns=[column for column in drop_cols if column in train_features.columns]
            )
            test_features = test_features.drop(
                columns=[column for column in drop_cols if column in test_features.columns]
            )

        logger.info(
            f"[{OPERATOR_ID}] mode=online_forecast: train={len(train_features)}, "
            f"forecast={len(test_features)}; future labels are excluded from training"
        )
        return {
            "train_features": train_features,
            "train_target": train_target,
            "test_features": test_features,
            "test_target": np.array([], dtype=float),
        }

    if mode == "all_train":
        import numpy as np
        train_target_series = pd.to_numeric(df[target_column], errors="coerce")
        train_target = train_target_series.fillna(0).values.astype(float)
        exclude_cols = list(DEFAULT_EXCLUDE_FEATURE_COLUMNS)
        exclude_cols.extend(_parse_column_list(params.get("exclude_feature_columns")))
        exclude_cols.extend(_parse_column_list(options.get("exclude_feature_columns")))
        if isinstance(gcfg, dict):
            exclude_cols.extend(_parse_column_list(gcfg.get("exclude_feature_columns")))
        exclude_cols = sorted(set(exclude_cols) - {time_field})
        train_features = df.drop(columns=[target_column])
        drop_cols = [c for c in exclude_cols if c in train_features.columns]
        if drop_cols:
            train_features = train_features.drop(columns=drop_cols)
        logger.info(
            f"[{OPERATOR_ID}] mode=all_train: 使用全部 {len(df)} 行作为训练集，test 置空"
        )
        return {
            "train_features": train_features,
            "train_target": train_target,
            "test_features": pd.DataFrame(columns=train_features.columns),
            "test_target": np.array([], dtype=float),
        }
    # @AI_GENERATED: end

    n = len(df)

    # Determine split index
    if split_date:
        # split_date takes priority over ratio
        split_dt = pd.to_datetime(split_date)
        if pd.isna(split_dt):
            logger.warning(
                f"[{OPERATOR_ID}] split_date={split_date} 解析失败，回退到 train_ratio={train_ratio}"
            )
            split_idx = int(n * train_ratio)
        elif time_field in df.columns:
            train_mask = df[time_field] <= split_dt
            split_idx = train_mask.sum()
        else:
            # Fallback: use ratio if no time field
            split_idx = int(n * train_ratio)
        logger.info(f"[{OPERATOR_ID}] Using split_date={split_date}, split_idx={split_idx}")
    else:
        # Use train_ratio (val_ratio is informational for downstream use)
        split_idx = int(n * train_ratio)
        logger.info(
            f"[{OPERATOR_ID}] Using train_ratio={train_ratio}, "
            f"val_ratio={val_ratio}, split_idx={split_idx}"
        )

    # Clamp split index
    split_idx = max(1, min(split_idx, n - 1))

    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    # 回测模式：测试集只取 pred_start ~ pred_end 范围（排除 gap 期间的数据）
    if (
        isinstance(gcfg, dict)
        and str(gcfg.get("operate_status", "")).lower() == "backtest"
        and time_field in test_df.columns
    ):
        pred_start_s = gcfg.get("backtest_pred_start")
        pred_end_s = gcfg.get("backtest_pred_end")
        if pred_start_s:
            pred_start_dt = pd.to_datetime(pred_start_s, errors="coerce")
            if not pd.isna(pred_start_dt):
                test_df = test_df[test_df[time_field] >= pred_start_dt]
        if pred_end_s:
            pred_end_dt = pd.to_datetime(pred_end_s, errors="coerce")
            if not pd.isna(pred_end_dt):
                test_df = test_df[test_df[time_field] < pred_end_dt]
        test_df = test_df.reset_index(drop=True)
        logger.info(
            f"[{OPERATOR_ID}] 回测模式：测试集裁剪到 {pred_start_s} ~ {pred_end_s}，"
            f"test_rows={len(test_df)}"
        )

    # Separate features and target
    helper_target_col = "__backtest_true_target"
    logger.info(
        f"[{OPERATOR_ID}] helper_col '{helper_target_col}' exists={helper_target_col in df.columns}, "
        f"target_col='{target_column}', columns_sample={list(df.columns)[:15]}"
    )
    train_target_series = pd.to_numeric(train_df[target_column], errors="coerce")
    train_target = train_target_series.values.astype(float)
    train_finite_pre = int(train_target_series.notna().sum())
    if train_finite_pre == 0 and helper_target_col in train_df.columns:
        helper_series = pd.to_numeric(train_df[helper_target_col], errors="coerce")
        helper_finite = int(helper_series.notna().sum())
        if helper_finite > 0:
            logger.warning(
                f"[{OPERATOR_ID}] 训练标签列 '{target_column}' 无有效值，"
                f"已回退使用 '{helper_target_col}'（valid={helper_finite}）"
            )
            train_target = helper_series.values.astype(float)
    if helper_target_col in test_df.columns:
        test_target = pd.to_numeric(test_df[helper_target_col], errors="coerce").values.astype(float)
    else:
        test_target = test_df[target_column].values.astype(float)

    train_features = train_df.drop(columns=[target_column])
    test_features = test_df.drop(columns=[target_column])
    if helper_target_col in train_features.columns:
        train_features = train_features.drop(columns=[helper_target_col])
    if helper_target_col in test_features.columns:
        test_features = test_features.drop(columns=[helper_target_col])
    exclude_cols = list(DEFAULT_EXCLUDE_FEATURE_COLUMNS)
    exclude_cols.extend(_parse_column_list(params.get("exclude_feature_columns")))
    exclude_cols.extend(_parse_column_list(options.get("exclude_feature_columns")))
    if isinstance(gcfg, dict):
        exclude_cols.extend(_parse_column_list(gcfg.get("exclude_feature_columns")))
    exclude_cols = sorted(set(exclude_cols) - {time_field})
    drop_cols = [c for c in exclude_cols if c in train_features.columns or c in test_features.columns]
    if drop_cols:
        train_features = train_features.drop(columns=[c for c in drop_cols if c in train_features.columns])
        test_features = test_features.drop(columns=[c for c in drop_cols if c in test_features.columns])
        logger.info(f"[{OPERATOR_ID}] 已从特征中剔除元数据列: {drop_cols}")

    logger.info(
        f"[{OPERATOR_ID}] Split {n} rows -> train={len(train_features)}, "
        f"test={len(test_features)}"
    )
    train_finite = int(pd.to_numeric(pd.Series(train_target), errors="coerce").notna().sum())
    test_finite = int(pd.to_numeric(pd.Series(test_target), errors="coerce").notna().sum())
    logger.info(
        f"[{OPERATOR_ID}] 目标列有效值: train_finite={train_finite}/{len(train_target)}, "
        f"test_finite={test_finite}/{len(test_target)}"
    )
    if helper_target_col in test_df.columns:
        helper_test_finite = int(
            pd.to_numeric(test_df[helper_target_col], errors="coerce").notna().sum()
        )
        logger.info(
            f"[{OPERATOR_ID}] 回测真实标签可用数: test_true_finite={helper_test_finite}/{len(test_df)} "
            f"(source={helper_target_col})"
        )

    return {
        "train_features": train_features,
        "train_target": train_target,
        "test_features": test_features,
        "test_target": test_target,
    }
# @AI_GENERATED: end
