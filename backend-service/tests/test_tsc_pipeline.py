# @AI_GENERATED
"""
单元测试：TSCPipeline + run_model_comparison

验证：
- Pipeline 跑通：切分→训练→评估→输出指标
- 输出统一分类评测字段
- 多模型对比输出 ranking 正确
- 按设备划分不泄漏
- 异步 job 启动与状态查询
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.iterative_labeling.tsc.sliding_window_sampler import SamplerConfig
from services.iterative_labeling.tsc.tsc_pipeline import TSCPipeline
from services.iterative_labeling.tsc.tsc_model_compare import run_model_comparison
from services.iterative_labeling.tsc.tsc_compare_job import (
    start_tsc_compare_job,
    load_tsc_compare_status,
    load_tsc_compare_result,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REAL_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "iterative_labeling" / "modeling_path_compare" / "pv_fault" / "datasets" / "pathcmp-20260803021250-ea9c92ab-by_day.parquet"


@pytest.fixture
def synthetic_parquet(tmp_path) -> str:
    """生成合成 parquet 数据集，返回路径。"""
    rows = []
    rng = np.random.default_rng(42)
    # 10 设备，每设备 1200 点（~4天@5min），多类别
    for i in range(10):
        dev_id = f"synth_dev_{i:03d}"
        times = pd.date_range("2021-01-01", periods=1200, freq="5min")
        values = np.sin(np.linspace(0, 8 * np.pi, 1200)) * 5 + 10 + rng.normal(0, 0.5, 1200)
        i_cal = values * 1.05
        # 标签：大段正常，大段故障（保证纯度够高能通过过滤）
        labels = np.zeros(1200, dtype=int)
        if i % 3 == 0:
            labels[0:400] = 1  # 前 400 点故障类型 1（纯度=1.0）
        elif i % 3 == 1:
            labels[0:400] = 2  # 前 400 点故障类型 2（纯度=1.0）
        # i%3==2 全正常

        for t, v, ic, lbl in zip(times, values, i_cal, labels):
            rows.append({"time": t, "device_id": dev_id, "value": v, "i_cal": ic, "label": lbl})

    df = pd.DataFrame(rows)
    path = tmp_path / "synth_tsc_data.parquet"
    df.to_parquet(path, index=False)
    return str(path)


@pytest.fixture
def small_real_parquet(tmp_path) -> str:
    """从真实数据取前 20 设备做小集。若无真实数据则 skip。"""
    if not REAL_DATA_PATH.exists():
        pytest.skip("真实数据文件不存在")
    df = pd.read_parquet(REAL_DATA_PATH, columns=["time", "device_id", "value", "i_cal", "label"])
    devices = df["device_id"].unique()[:20]
    subset = df[df["device_id"].isin(devices)].copy()
    path = tmp_path / "real_small.parquet"
    subset.to_parquet(path, index=False)
    return str(path)


# ---------------------------------------------------------------------------
# Tests: TSCPipeline
# ---------------------------------------------------------------------------


class TestTSCPipeline:
    """Pipeline 完整流程测试。"""

    def test_pipeline_runs_synthetic(self, synthetic_parquet):
        """合成数据 Pipeline 跑通并输出正确格式。"""
        cfg = SamplerConfig(window_length=288, stride=144)
        pipeline = TSCPipeline(
            sampler_config=cfg,
            model_name="minirocket",
            n_repeats=2,
            n_splits=3,
            test_ratio=0.2,
            random_state=90,
        )
        result = pipeline.run(synthetic_parquet)

        assert result["status"] == "ok"
        assert result["model_name"] == "minirocket"
        assert result["n_samples"] > 0
        assert result["n_classes"] >= 2
        # 统一分类评测字段
        assert "macro_f1_mean" in result
        assert "macro_f1_std" in result
        assert "accuracy_mean" in result
        assert "accuracy_std" in result
        assert "macro_precision_mean" in result
        assert "macro_recall_mean" in result
        assert result["macro_f1_mean"] is not None
        assert 0 <= result["macro_f1_mean"] <= 1
        assert result["error"] is None

    def test_pipeline_extra_fields(self, synthetic_parquet):
        """时序路线额外输出字段存在。"""
        cfg = SamplerConfig(window_length=288, stride=144)
        pipeline = TSCPipeline(
            sampler_config=cfg,
            model_name="minirocket",
            n_repeats=1,
            n_splits=2,
        )
        result = pipeline.run(synthetic_parquet)

        assert "per_class_f1" in result
        assert "confusion_matrix" in result
        assert "train_time_sec" in result
        assert "window_length" in result
        assert result["window_length"] == 288

    def test_pipeline_empty_data(self, tmp_path):
        """无有效数据时返回 failed。"""
        # 生成一个只有 10 点的数据集（太短切不出窗口）
        df = pd.DataFrame({
            "time": pd.date_range("2021-01-01", periods=10, freq="5min"),
            "device_id": "tiny_dev",
            "value": range(10),
            "i_cal": range(10),
            "label": [0] * 10,
        })
        path = tmp_path / "tiny.parquet"
        df.to_parquet(path, index=False)

        pipeline = TSCPipeline(model_name="minirocket")
        result = pipeline.run(str(path))
        assert result["status"] == "failed"
        assert result["error"] is not None

    def test_pipeline_real_data(self, small_real_parquet):
        """真实数据小集 Pipeline 跑通。"""
        cfg = SamplerConfig(window_length=288, stride=72)
        pipeline = TSCPipeline(
            sampler_config=cfg,
            model_name="minirocket",
            n_repeats=2,
            n_splits=3,
        )
        result = pipeline.run(small_real_parquet)

        assert result["status"] == "ok"
        assert result["macro_f1_mean"] > 0
        assert result["n_samples"] > 10


# ---------------------------------------------------------------------------
# Tests: run_model_comparison
# ---------------------------------------------------------------------------


class TestModelComparison:
    """多模型对比测试。"""

    def test_comparison_produces_ranking(self, synthetic_parquet):
        """对比运行产出 ranking。"""
        result = run_model_comparison(
            dataset_path=synthetic_parquet,
            model_names=["minirocket", "multirocket"],
            window_configs=[{"window_length": 288, "stride": 144}],
            n_repeats=1,
        )

        assert "experiment_id" in result
        assert "results" in result
        assert "ranking" in result
        assert len(result["results"]) == 2
        assert "by_f1" in result["ranking"]
        assert len(result["ranking"]["by_f1"]) >= 1
        assert result["best_model"] is not None

    def test_comparison_with_failed_model(self, synthetic_parquet):
        """包含不存在的模型时，该模型标 failed，不影响其他。"""
        result = run_model_comparison(
            dataset_path=synthetic_parquet,
            model_names=["minirocket", "nonexistent_model_xyz"],
            window_configs=[{"window_length": 288, "stride": 144}],
            n_repeats=1,
        )

        statuses = [r["status"] for r in result["results"]]
        assert "ok" in statuses
        assert "failed" in statuses
        # best_model 应该是成功的那个
        assert result["best_model"] is not None
        assert "minirocket" in result["best_model"]


# ---------------------------------------------------------------------------
# Tests: Async Job
# ---------------------------------------------------------------------------


class TestAsyncJob:
    """异步任务入口测试。"""

    def test_start_and_wait(self, synthetic_parquet):
        """
        启动异步任务并等待完成（legacy 口径）。

        本用例验证的是异步任务机制本身（启动/轮询/取结果），故显式用 legacy 口径：
        合成数据只有 ~4 天，不满足 strict 口径 n_test_days=3 的时间切分要求。
        strict 口径另有 test_strict_mode_job 覆盖。
        """
        import time as _time

        job_id = start_tsc_compare_job(
            slot="test_async",
            dataset_path=synthetic_parquet,
            model_names=["minirocket"],
            window_configs=[{"window_length": 288, "stride": 144}],
            n_repeats=1,
            evaluation="legacy",
        )
        assert job_id.startswith("tsc-job-")

        # 等待完成（最多 120s）
        for _ in range(120):
            status = load_tsc_compare_status("test_async")
            if status and status.get("status") in ("completed", "failed"):
                break
            _time.sleep(1)

        status = load_tsc_compare_status("test_async")
        assert status is not None
        assert status["status"] == "completed"

        result = load_tsc_compare_result("test_async")
        assert result is not None
        assert "results" in result
        assert len(result["results"]) > 0

    def test_strict_mode_job(self, tmp_path):
        """
        strict 口径异步任务：需要足够的连续日期，结果应带 mean ± std 结构。

        回归意义：strict 是 start_tsc_compare_job 的默认口径，若它在异步链路上
        跑不通，前端拿到的就永远是 legacy 数字。
        """
        import time as _time

        # 数据规模需同时满足两个约束（否则 strict 划分会被跳过）：
        #   1. 可切窗日期 > n_test_days(3)  -> 用 8 天
        #   2. test 窗口数 >= min_test_samples(30)
        #      strict 只留 30% 设备 × 末 3 天，故设备数不能太少：
        #      40 设备 × 30% = 12 设备，× 末3天约 2 窗口/天 ≈ 72 个 test 窗口
        n_devices, n_days = 40, 8
        rows = []
        rng = np.random.default_rng(7)
        times = pd.date_range("2021-03-01", periods=288 * n_days, freq="5min")
        for i in range(n_devices):
            dev = f"strict_dev_{i:02d}"
            label = i % 3
            base = np.sin(np.linspace(0, 8 * n_days * np.pi, len(times))) * (label + 1) + 10
            vals = base + rng.normal(0, 0.3, len(times))
            for t, v in zip(times, vals):
                rows.append({
                    "time": t, "site_id": "S1", "device_id": dev, "branch_id": "1",
                    "value": v, "i_cal": v * 1.05, "label": label,
                })
        path = tmp_path / "strict_job.parquet"
        pd.DataFrame(rows).to_parquet(path, index=False)

        job_id = start_tsc_compare_job(
            slot="test_strict_job",
            dataset_path=str(path),
            model_names=["minirocket"],
            window_configs=[{"window_length": 288, "stride": 144}],
            n_repeats=3,
            evaluation="strict",
            split_mode="strict",
            n_test_days=3,
            baseline_model=None,
        )
        assert job_id.startswith("tsc-job-")

        for _ in range(180):
            st = load_tsc_compare_status("test_strict_job")
            if st and st.get("status") in ("completed", "failed"):
                break
            _time.sleep(1)

        st = load_tsc_compare_status("test_strict_job")
        assert st is not None, "状态文件未生成"
        assert st["status"] == "completed", f"任务未完成: {st}"

        res = load_tsc_compare_result("test_strict_job")
        assert res is not None
        assert res.get("evaluation") == "strict_multi_split"
        r = res["results"]["minirocket"]
        assert r["status"] == "ok", f"评估未成功: {r.get('error')}"
        # 关键：strict 口径必须返回聚合结构，而不是单个数字
        assert isinstance(r["macro_f1"], dict)
        assert {"mean", "std", "n"} <= set(r["macro_f1"])
        assert r["n_splits_completed"] >= 1
        # 每次划分都应通过设备+日期隔离
        for s in r["per_split"]:
            assert s["isolation"]["device_overlap"] == 0
            assert s["isolation"]["date_overlap"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
# @AI_GENERATED: end
