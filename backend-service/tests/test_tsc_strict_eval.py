# @AI_GENERATED
"""
单元测试：tsc_strict_eval —— 严格口径多次划分评估。

重点验证：
 - 三种口径的隔离性质（strict 必须设备+日期双隔离）
 - 返回 mean ± std 结构而非单个数字
 - macro 指标固定在完整标签空间（不因稀有类缺席而虚高）
 - n_repeats < 10 时给出 warning
 - 配对差计算正确
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.iterative_labeling.tsc.tsc_strict_eval import (
    SPLIT_MODES,
    StrictEvalConfig,
    compare_models_multi_split,
    evaluate_model_multi_split,
    format_metric,
)


def _make_dataset(n_devices=40, n_days=6, window_length=64, n_channels=2, seed=0):
    """
    合成已切窗数据：每设备每天 2 个窗口，标签由设备决定（保证可学）。

    返回 (X, y, meta)，meta 含 device_id / series_id / t_start —— 与切分器输出一致。
    """
    rng = np.random.default_rng(seed)
    Xs, ys, rows = [], [], []
    base = pd.Timestamp("2021-01-01")
    for d in range(n_devices):
        label = d % 4  # 4 类
        for day in range(n_days):
            for k in range(2):
                # 不同类给不同形态，保证模型能学到东西
                t = np.linspace(0, 4 * np.pi, window_length)
                sig = np.sin(t * (label + 1)) * (label + 1) + rng.normal(0, 0.15, window_length)
                x = np.stack([sig, sig * 1.05], axis=-1)[:, :n_channels]
                Xs.append(x.astype(np.float32))
                ys.append(label)
                rows.append({
                    "sample_id": f"s-{d}-{day}-{k}",
                    "device_id": f"dev{d:03d}",
                    "series_id": f"siteA|dev{d:03d}|1",
                    "t_start": base + pd.Timedelta(days=day, hours=k * 6),
                    "t_end": base + pd.Timedelta(days=day, hours=k * 6 + 5),
                    "purity": 1.0,
                })
    return np.stack(Xs), np.array(ys), pd.DataFrame(rows)


@pytest.fixture(scope="module")
def data():
    return _make_dataset()


class TestSplitIsolation:
    """各口径的隔离性质。"""

    def test_strict_isolates_device_and_date(self, data):
        X, y, meta = data
        r = evaluate_model_multi_split(
            "minirocket", X, y, meta,
            StrictEvalConfig(split_mode="strict", n_repeats=3, n_test_days=2),
        )
        assert r["status"] == "ok"
        assert r["n_splits_completed"] >= 1
        for s in r["per_split"]:
            assert s["isolation"]["device_overlap"] == 0, "strict 口径必须设备隔离"
            assert s["isolation"]["date_overlap"] == 0, "strict 口径必须日期隔离"

    def test_time_isolates_date_only(self, data):
        X, y, meta = data
        r = evaluate_model_multi_split(
            "minirocket", X, y, meta,
            StrictEvalConfig(split_mode="time", n_repeats=1, n_test_days=2,
                             require_isolation=False),
        )
        assert r["status"] == "ok"
        for s in r["per_split"]:
            assert s["isolation"]["date_overlap"] == 0, "time 口径必须日期隔离"

    def test_device_mode_isolates_device_only(self, data):
        X, y, meta = data
        r = evaluate_model_multi_split(
            "minirocket", X, y, meta,
            StrictEvalConfig(split_mode="device", n_repeats=2, require_isolation=False),
        )
        assert r["status"] == "ok"
        for s in r["per_split"]:
            assert s["isolation"]["device_overlap"] == 0

    def test_unknown_split_mode_raises(self, data):
        X, y, meta = data
        with pytest.raises(ValueError, match="未知 split_mode"):
            evaluate_model_multi_split(
                "minirocket", X, y, meta, StrictEvalConfig(split_mode="nonsense"))

    def test_all_split_modes_registered(self):
        assert set(SPLIT_MODES) == {"strict", "time", "device"}


class TestMeanStdOutput:
    """必须输出 mean ± std 结构。"""

    def test_metrics_are_aggregates_not_scalars(self, data):
        X, y, meta = data
        r = evaluate_model_multi_split(
            "minirocket", X, y, meta,
            StrictEvalConfig(split_mode="strict", n_repeats=3, n_test_days=2),
        )
        for k in ("macro_f1", "balanced_accuracy", "accuracy",
                  "macro_precision", "macro_recall", "weighted_f1"):
            assert isinstance(r[k], dict), f"{k} 应是聚合字典而非标量"
            assert set(r[k]) >= {"mean", "std", "min", "max", "n"}
            assert 0.0 <= r[k]["mean"] <= 1.0
            assert r[k]["std"] >= 0.0
            assert r[k]["min"] <= r[k]["mean"] <= r[k]["max"]

    def test_n_matches_completed_splits(self, data):
        X, y, meta = data
        r = evaluate_model_multi_split(
            "minirocket", X, y, meta,
            StrictEvalConfig(split_mode="strict", n_repeats=4, n_test_days=2),
        )
        assert r["macro_f1"]["n"] == r["n_splits_completed"]
        assert len(r["per_split"]) == r["n_splits_completed"]

    def test_warns_when_fewer_than_10_splits(self, data):
        X, y, meta = data
        r = evaluate_model_multi_split(
            "minirocket", X, y, meta,
            StrictEvalConfig(split_mode="strict", n_repeats=3, n_test_days=2),
        )
        assert "warning" in r
        assert "10" in r["warning"]

    def test_no_warning_at_10_splits(self, data):
        X, y, meta = data
        r = evaluate_model_multi_split(
            "minirocket", X, y, meta,
            StrictEvalConfig(split_mode="strict", n_repeats=10, n_test_days=2),
        )
        if r["n_splits_completed"] >= 10:
            assert "warning" not in r


class TestFullLabelSpaceMetric:
    """macro 指标必须在完整标签空间上算。"""

    def test_labels_recorded(self, data):
        X, y, meta = data
        r = evaluate_model_multi_split(
            "minirocket", X, y, meta,
            StrictEvalConfig(split_mode="strict", n_repeats=2, n_test_days=2),
        )
        assert r["n_labels_full"] == len(np.unique(y))
        assert r["labels"] == sorted(int(v) for v in np.unique(y))

    def test_rare_class_absent_from_test_still_counted(self):
        """
        构造一个稀有类只出现在 train 的情形：
        全类口径下该类 F1=0 会拉低 macro，不应被静默排除。
        """
        X, y, meta = _make_dataset(n_devices=40, n_days=6)
        # 把某个只在早期日期出现的设备改成第 5 类（稀有类）
        rare_mask = (meta["device_id"] == "dev000").values
        y = y.copy()
        y[rare_mask] = 99
        r = evaluate_model_multi_split(
            "minirocket", X, y, meta,
            StrictEvalConfig(split_mode="strict", n_repeats=3, n_test_days=2),
        )
        assert 99 in r["labels"]
        assert r["n_labels_full"] == 5


class TestPairwiseComparison:
    """多模型对比与配对差。"""

    def test_compare_produces_ranking_and_pairwise(self, data):
        X, y, meta = data
        out = compare_models_multi_split(
            ["minirocket", "multirocket"], X, y, meta,
            StrictEvalConfig(split_mode="strict", n_repeats=3, n_test_days=2),
            baseline_model="minirocket",
        )
        assert out["best_model"] in ("minirocket", "multirocket")
        assert len(out["ranking_by_macro_f1"]) == 2
        assert "pairwise_vs_baseline" in out
        pw = out["pairwise_vs_baseline"]["multirocket"]
        assert pw["vs"] == "minirocket"
        assert set(pw) >= {"macro_f1_diff_mean", "macro_f1_diff_std", "wins", "n_paired"}
        assert 0 <= pw["wins"] <= pw["n_paired"]

    def test_failed_model_does_not_break_comparison(self, data):
        X, y, meta = data
        out = compare_models_multi_split(
            ["minirocket", "no_such_model_xyz"], X, y, meta,
            StrictEvalConfig(split_mode="strict", n_repeats=2, n_test_days=2),
        )
        assert out["results"]["no_such_model_xyz"]["status"] == "failed"
        assert out["best_model"] == "minirocket"


class TestGuards:
    """边界与守卫。"""

    def test_insufficient_days_reports_skip(self):
        """可切窗日期不足时不应崩，而是报告跳过原因。"""
        X, y, meta = _make_dataset(n_devices=10, n_days=2)
        r = evaluate_model_multi_split(
            "minirocket", X, y, meta,
            StrictEvalConfig(split_mode="strict", n_repeats=3, n_test_days=3),
        )
        assert r["status"] == "failed"
        assert "skipped_splits" in r
        assert "日期" in r["skipped_splits"][0]["reason"]

    def test_format_metric(self):
        assert format_metric({"mean": 0.6315, "std": 0.0750}) == "0.6315 ± 0.0750"
        assert format_metric(None) == "—"
        assert format_metric({"mean": None, "std": None}) == "—"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
# @AI_GENERATED: end
