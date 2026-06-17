# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
生成训练集曲线对比图 + 预测日曲线对比图
"""
import os
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import timedelta

warnings.filterwarnings(action="ignore")
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

OUTPUT_DIR = os.path.join("output", "predict_first_day")
PRED_DAY = "2026-04-01"
TRAIN_DAYS = 30
DAILY_HORIZON = 96


def load_weihai_data():
    xlsx_path = os.path.join("datasets", "load_true_weihai_260407.xlsx")
    df = pd.read_excel(xlsx_path)
    df["record_time"] = pd.to_datetime(df["record_time"])
    load_df = df[df["feature_name"] == "load"][["record_time", "value"]].copy()
    load_df.rename(columns={"value": "load"}, inplace=True)
    load_df = load_df.sort_values("record_time").reset_index(drop=True)
    load_df = load_df.drop_duplicates(subset="record_time", keep="first")
    load_df = load_df.set_index("record_time")
    load_df = load_df.resample("15min").mean()
    load_df = load_df.interpolate().fillna(method="bfill").fillna(method="ffill")
    load_df.reset_index(inplace=True)
    return load_df


def smape(y_true, y_pred):
    d = np.abs(y_true) + np.abs(y_pred)
    m = d > 1e-8
    return 2.0 * np.mean(np.abs(y_pred[m] - y_true[m]) / d[m]) * 100


def main():
    # 加载原始数据和预测结果
    full_df = load_weihai_data()
    pred_df = pd.read_csv(os.path.join(OUTPUT_DIR, f"predict_{PRED_DAY}.csv"))
    pred_df["record_time"] = pd.to_datetime(pred_df["record_time"])

    pred_day = pd.to_datetime(PRED_DAY)
    train_end = pred_day - timedelta(minutes=15)
    train_start = pred_day - timedelta(days=1) - timedelta(days=TRAIN_DAYS)

    # 训练集数据
    train_df = full_df[
        (full_df["record_time"] >= train_start) &
        (full_df["record_time"] <= train_end)
    ].copy()

    # ================================================================
    # 图1: 训练集负荷曲线 (30天)
    # ================================================================
    fig, axes = plt.subplots(2, 1, figsize=(20, 10), gridspec_kw={'height_ratios': [3, 1]})

    ax = axes[0]
    ax.plot(train_df["record_time"], train_df["load"], color="black", lw=0.8, alpha=0.9)
    ax.axvline(pred_day, color="red", ls="--", lw=1.5, label=f"预测日 {PRED_DAY}")

    # 标注每天的日期
    for d in pd.date_range(train_start, train_end, freq="7D"):
        ax.axvline(d, color="gray", ls=":", lw=0.3, alpha=0.5)

    ax.set_ylabel("Load (kW)", fontsize=12)
    ax.set_title(f"训练集负荷曲线 ({train_start.strftime('%Y-%m-%d')} ~ {train_end.strftime('%Y-%m-%d')}, {TRAIN_DAYS}天)",
                 fontsize=14)
    ax.legend(fontsize=11, loc="upper right")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))

    # 下方: 每日均值/峰谷
    train_df["date"] = train_df["record_time"].dt.date
    daily = train_df.groupby("date")["load"].agg(["mean", "max", "min"]).reset_index()
    daily["date"] = pd.to_datetime(daily["date"])

    ax2 = axes[1]
    ax2.fill_between(daily["date"], daily["min"], daily["max"], alpha=0.3, color="#3498db", label="峰谷范围")
    ax2.plot(daily["date"], daily["mean"], "o-", color="#2c3e50", ms=3, lw=1, label="日均值")
    ax2.set_ylabel("Load (kW)", fontsize=11)
    ax2.set_xlabel("日期", fontsize=11)
    ax2.set_title("每日负荷统计（均值 + 峰谷范围）", fontsize=12)
    ax2.legend(fontsize=9, loc="upper right")
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax2.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    plt.xticks(rotation=30)

    plt.tight_layout()
    path1 = os.path.join(OUTPUT_DIR, "train_curve.png")
    fig.savefig(path1, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"已保存: {path1}")

    # ================================================================
    # 图2: 预测日曲线对比 (详细版)
    # ================================================================
    fig, axes = plt.subplots(3, 1, figsize=(16, 12),
                              gridspec_kw={'height_ratios': [3, 1.5, 1.5]})

    x = range(len(pred_df))
    times = pred_df["record_time"]
    y_true = pred_df["true"].values
    y_ens = pred_df["pred_ensemble"].values

    # 上图: 真实 vs 各模型预测
    ax = axes[0]
    ax.plot(x, y_true, "k-o", ms=2.5, lw=1.8, label="真实值", zorder=5)
    ax.plot(x, y_ens, color="#2ecc71", lw=1.5, label="Ensemble", zorder=4)
    ax.plot(x, pred_df["pred_xgb"], color="#3498db", lw=0.8, alpha=0.5, label="XGBoost")
    ax.plot(x, pred_df["pred_lgb"], color="#e67e22", lw=0.8, alpha=0.5, label="LightGBM")
    ax.plot(x, pred_df["pred_catb"], color="#9b59b6", lw=0.8, alpha=0.5, label="CatBoost")
    ax.plot(x, pred_df["pred_ridge"], color="#e74c3c", lw=0.8, alpha=0.5, label="Ridge")

    # 标注误差最大的点
    err = np.abs(y_ens - y_true)
    worst_idx = np.argmax(err)
    ax.annotate(f"最大误差\n{err[worst_idx]:.0f} kW",
                xy=(worst_idx, y_ens[worst_idx]),
                xytext=(worst_idx + 8, y_ens[worst_idx] + 800),
                arrowprops=dict(arrowstyle="->", color="red", lw=1.5),
                fontsize=9, color="red", fontweight="bold")

    s = smape(y_true, y_ens)
    weekday = times.iloc[0].strftime('%A')
    weekdays_cn = ['一','二','三','四','五','六','日']
    wd_cn = weekdays_cn[times.iloc[0].weekday()]
    ax.set_title(f"{PRED_DAY} (星期{wd_cn}) — 数据截取方式预测  Ensemble SMAPE={s:.2f}%", fontsize=14)
    ax.set_ylabel("Load (kW)", fontsize=12)
    ax.legend(loc="upper right", ncol=3, fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xticks([0, 12, 24, 36, 48, 60, 72, 84, 95])
    ax.set_xticklabels(["00:00","03:00","06:00","09:00","12:00","15:00","18:00","21:00","23:45"], fontsize=8)

    # 中图: 误差曲线
    ax = axes[1]
    err_signed = y_ens - y_true
    colors = ['#2ecc71' if e >= 0 else '#e74c3c' for e in err_signed]
    ax.bar(x, err_signed, color=colors, alpha=0.7, width=1.0)
    ax.axhline(0, color="k", lw=0.5)
    ax.axhline(np.mean(err_signed), color="blue", ls="--", lw=1,
               label=f"Bias={np.mean(err_signed):+.0f} kW")
    ax.set_ylabel("误差 (kW)", fontsize=11)
    ax.set_title("预测误差 (正=高估, 负=低估)", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xticks([0, 12, 24, 36, 48, 60, 72, 84, 95])
    ax.set_xticklabels(["00:00","03:00","06:00","09:00","12:00","15:00","18:00","21:00","23:45"], fontsize=8)

    # 下图: 各模型误差百分比
    ax = axes[2]
    for col, name, color in [
        ("pred_xgb", "XGB", "#3498db"),
        ("pred_lgb", "LGB", "#e67e22"),
        ("pred_catb", "CatB", "#9b59b6"),
        ("pred_ridge", "Ridge", "#e74c3c"),
        ("pred_ensemble", "Ensemble", "#2ecc71"),
    ]:
        pct_err = (pred_df[col].values - y_true) / y_true * 100
        lw = 1.5 if col == "pred_ensemble" else 0.7
        alpha = 1.0 if col == "pred_ensemble" else 0.5
        ax.plot(x, pct_err, color=color, lw=lw, alpha=alpha, label=name)
    ax.axhline(0, color="k", lw=0.5)
    ax.set_ylabel("误差率 (%)", fontsize=11)
    ax.set_xlabel("时刻", fontsize=11)
    ax.set_title("各模型误差率对比", fontsize=12)
    ax.legend(loc="upper right", ncol=5, fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xticks([0, 12, 24, 36, 48, 60, 72, 84, 95])
    ax.set_xticklabels(["00:00","03:00","06:00","09:00","12:00","15:00","18:00","21:00","23:45"], fontsize=8)

    plt.tight_layout()
    path2 = os.path.join(OUTPUT_DIR, "pred_day_detail.png")
    fig.savefig(path2, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"已保存: {path2}")


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
