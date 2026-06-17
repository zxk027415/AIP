# @AI_GENERATED
"""
电力负荷预测 - 训练脚本（Agent 可编辑）

使用 XGBoost 和贝叶斯超参优化训练负荷预测模型。
Agent 可以修改模型架构、超参数、特征选择和训练策略来优化预测效果。

Usage: python train.py [--data DATA_PATH] [--scenario D]
"""

import os
import gc
import time
import argparse
import numpy as np
import pandas as pd
from typing import Dict, Any

from prepare import (
    TIME_BUDGET,
    DEFAULT_TIME_FIELD,
    DEFAULT_LOAD_FIELD,
    load_data,
    preprocess_data,
    add_features,
    train_test_split_temporal,
    evaluate_all,
)

# ---------------------------------------------------------------------------
# 超参数（可修改）
# ---------------------------------------------------------------------------

SCENARIO = "D"              # 预测场景: DI/D/WI/W/MI/M
MODEL_TYPE = "xgboost"      # 可选: "xgboost", "lightgbm", "random_forest"
N_TRIALS = 50               # 贝叶斯优化试验次数
RANDOM_SEED = 42

# XGBoost 默认超参数（贝叶斯优化会覆盖这些值）
XGB_PARAMS = {
    "max_depth": 6,
    "learning_rate": 0.1,
    "n_estimators": 200,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 3,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
}

# 特征选择（可修改）
FEATURE_COLS = None  # None 表示使用所有特征；也可指定列表如 ["hour_sin", "lag_24h", ...]


# ---------------------------------------------------------------------------
# 模型训练
# ---------------------------------------------------------------------------

def train_xgboost(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    n_trials: int = N_TRIALS,
) -> Any:
    """
    使用贝叶斯超参优化训练 XGBoost 模型。

    可修改搜索空间和优化策略。
    """
    try:
        import xgboost as xgb
    except ImportError:
        raise ImportError("请安装 xgboost: pip install xgboost")

    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        # 如果没有 optuna，使用默认参数
        print("optuna 未安装，使用默认超参数")
        model = xgb.XGBRegressor(
            **XGB_PARAMS,
            random_state=RANDOM_SEED,
            n_jobs=-1,
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        return model

    def objective(trial):
        params = {
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 500),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }

        model = xgb.XGBRegressor(
            **params,
            random_state=RANDOM_SEED,
            n_jobs=-1,
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        y_pred = model.predict(X_val)
        # 使用 SMAPE 作为优化目标
        denom = np.maximum(1e-8, (np.abs(y_val) + np.abs(y_pred)) / 2.0)
        smape = float(np.mean(np.abs(y_pred - y_val) / denom) * 100.0)
        return smape

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    print(f"最优 SMAPE: {study.best_value:.4f}%")
    print(f"最优参数: {study.best_params}")

    # 用最优参数重新训练
    best_model = xgb.XGBRegressor(
        **study.best_params,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    best_model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    return best_model


def train_and_evaluate(
    data_path: str = None,
    scenario: str = SCENARIO,
) -> Dict[str, Any]:
    """主训练和评估流程"""
    t_start = time.time()

    # 1. 加载数据
    print("加载数据...")
    df = load_data(data_path)

    # 2. 预处理
    print("预处理数据...")
    df = preprocess_data(df)

    # 3. 特征工程
    print("特征工程...")
    df = add_features(df)

    # 4. 准备训练数据
    target_col = DEFAULT_LOAD_FIELD
    feature_cols = FEATURE_COLS
    if feature_cols is None:
        feature_cols = [c for c in df.columns
                        if c not in [DEFAULT_TIME_FIELD, target_col, "date"]]

    X = df[feature_cols].values
    y = df[target_col].values

    # 5. 划分数据集
    print("划分数据集...")
    split_idx = int(len(X) * 0.8)
    val_split = int(len(X) * 0.9)

    X_train, y_train = X[:split_idx], y[:split_idx]
    X_val, y_val = X[split_idx:val_split], y[split_idx:val_split]
    X_test, y_test = X[val_split:], y[val_split:]

    print(f"训练集: {len(X_train)}, 验证集: {len(X_val)}, 测试集: {len(X_test)}")

    # 6. 训练模型
    print(f"\n训练 {MODEL_TYPE} 模型 (场景: {scenario})...")
    t_train_start = time.time()

    if MODEL_TYPE == "xgboost":
        model = train_xgboost(X_train, y_train, X_val, y_val, n_trials=N_TRIALS)
    else:
        raise ValueError(f"未支持的模型类型: {MODEL_TYPE}")

    training_time = time.time() - t_train_start

    # 7. 预测和评估
    print("\n评估模型...")
    y_pred = model.predict(X_test)
    metrics = evaluate_all(y_test, y_pred)

    total_time = time.time() - t_start

    results = {
        "smape": metrics["smape"],
        "mae": metrics["mae"],
        "rmse": metrics["rmse"],
        "training_seconds": training_time,
        "total_seconds": total_time,
        "scenario": scenario,
        "forecast_horizon": 1,
        "model_type": MODEL_TYPE,
        "n_trials": N_TRIALS,
        "train_samples": len(X_train),
        "val_samples": len(X_val),
        "test_samples": len(X_test),
        "n_features": len(feature_cols),
    }

    return results


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="电力负荷预测 - 训练脚本")
    parser.add_argument("--data", type=str, default=None, help="数据文件路径")
    parser.add_argument("--scenario", type=str, default=SCENARIO, help="预测场景")
    args = parser.parse_args()

    print("=" * 60)
    print("电力负荷预测 - 训练脚本")
    print(f"场景: {args.scenario}")
    print(f"模型: {MODEL_TYPE}")
    print(f"优化试验次数: {N_TRIALS}")
    print("=" * 60)

    np.random.seed(RANDOM_SEED)

    results = train_and_evaluate(data_path=args.data, scenario=args.scenario)

    print("\n" + "=" * 60)
    print("训练结果")
    print("=" * 60)

    # 标准输出格式（供 program.md 解析）
    print("---")
    print(f"smape:            {results['smape']:.4f}")
    print(f"mae:              {results['mae']:.4f}")
    print(f"rmse:             {results['rmse']:.4f}")
    print(f"training_seconds: {results['training_seconds']:.1f}")
    print(f"total_seconds:    {results['total_seconds']:.1f}")
    print(f"scenario:         {results['scenario']}")
    print(f"forecast_horizon: {results['forecast_horizon']}")
    print(f"model_type:       {results['model_type']}")
    print(f"n_trials:         {results['n_trials']}")

    gc.collect()
# @AI_GENERATED: end
