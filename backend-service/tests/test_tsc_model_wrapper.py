# @AI_GENERATED
"""
单元测试：TSCModelWrapper + model_registry + 自定义模型

验证：
- Tier 1 模型（MiniRocket/MultiRocket/ROCKET）fit/predict 正常
- ROCKET+RF 两阶段模型 fit/predict 正常
- save/load 后预测结果一致
- metadata 含完整窗口配置
- 注册表工厂函数正确实例化
- list_models 过滤逻辑正确
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.iterative_labeling.tsc.model_wrapper import TSCModelWrapper
from services.iterative_labeling.tsc.model_registry import (
    MODEL_REGISTRY,
    get_model,
    list_models,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_data():
    """合成数据：100 样本，64 时间步，2 通道，3 类。"""
    rng = np.random.default_rng(42)
    n_samples = 100
    seq_len = 64
    n_channels = 2
    X = rng.random((n_samples, seq_len, n_channels)).astype(np.float32)
    y = rng.choice([0, 1, 2], size=n_samples)
    return X, y


# ---------------------------------------------------------------------------
# Tests: Registry
# ---------------------------------------------------------------------------


class TestModelRegistry:
    """模型注册表测试。"""

    def test_all_entries_have_required_keys(self):
        """所有注册条目含必要字段。"""
        required = {"class_path", "tier", "gpu_required", "is_aeon", "default_params", "description"}
        for name, entry in MODEL_REGISTRY.items():
            missing = required - set(entry.keys())
            assert not missing, f"模型 {name} 缺少字段: {missing}"

    def test_list_models_all(self):
        """list_models() 无过滤返回所有模型。"""
        models = list_models()
        assert len(models) == len(MODEL_REGISTRY)

    def test_list_models_tier_filter(self):
        """tier_filter 正确过滤。"""
        tier1 = list_models(tier_filter=1)
        for m in tier1:
            assert m["tier"] == 1
        assert len(tier1) >= 3  # minirocket, multirocket, rocket, rocket_rf

    def test_list_models_gpu_filter(self):
        """gpu_available=False 排除需要 GPU 的模型。"""
        no_gpu = list_models(gpu_available=False)
        for m in no_gpu:
            assert m["gpu_required"] is False

    def test_get_model_unknown_raises(self):
        """获取不存在的模型应报错。"""
        with pytest.raises(ValueError, match="未知模型"):
            get_model("nonexistent_model")


# ---------------------------------------------------------------------------
# Tests: Tier 1 Models (aeon convolution-based)
# ---------------------------------------------------------------------------


class TestTier1Models:
    """Tier 1 模型 fit/predict 测试。"""

    @pytest.mark.parametrize("model_name", ["minirocket", "multirocket", "rocket"])
    def test_fit_predict(self, model_name, synthetic_data):
        """Tier 1 模型能正常 fit 和 predict。"""
        X, y = synthetic_data
        wrapper = get_model(model_name)
        wrapper.fit(X, y)

        preds = wrapper.predict(X)
        assert preds.shape == (len(y),)
        assert set(preds).issubset(set(y))  # 预测标签在训练标签范围内

    @pytest.mark.parametrize("model_name", ["minirocket", "multirocket"])
    def test_train_time_recorded(self, model_name, synthetic_data):
        """训练时间被记录。"""
        X, y = synthetic_data
        wrapper = get_model(model_name)
        wrapper.fit(X, y)
        assert wrapper.train_time_sec > 0


class TestRocketRF:
    """ROCKET + RF 两阶段模型测试。"""

    def test_fit_predict(self, synthetic_data):
        """rocket_rf 能正常 fit 和 predict。"""
        X, y = synthetic_data
        wrapper = get_model("rocket_rf")
        wrapper.fit(X, y)

        preds = wrapper.predict(X)
        assert preds.shape == (len(y),)

    def test_predict_proba(self, synthetic_data):
        """rocket_rf 支持 predict_proba。"""
        X, y = synthetic_data
        wrapper = get_model("rocket_rf")
        wrapper.fit(X, y)

        proba = wrapper.predict_proba(X)
        assert proba is not None
        assert proba.shape == (len(y), 3)
        # 概率和为 1
        assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-5)


# ---------------------------------------------------------------------------
# Tests: Save / Load
# ---------------------------------------------------------------------------


class TestSaveLoad:
    """模型持久化测试。"""

    def test_save_load_roundtrip(self, synthetic_data):
        """save → load 后 predict 结果一致。"""
        X, y = synthetic_data
        wrapper = get_model("minirocket")
        wrapper.set_window_config({"window_length": 288, "stride": 72, "channels": ["value", "i_cal"]})
        wrapper.fit(X, y)

        preds_before = wrapper.predict(X)

        with tempfile.TemporaryDirectory() as tmp:
            wrapper.save(tmp)

            # 验证文件存在
            assert (Path(tmp) / "model.pkl").exists()
            assert (Path(tmp) / "metadata.json").exists()

            # 加载
            loaded = TSCModelWrapper.load(tmp)
            preds_after = loaded.predict(X)

        np.testing.assert_array_equal(preds_before, preds_after)

    def test_metadata_contains_window_config(self, synthetic_data):
        """元数据包含完整窗口配置。"""
        X, y = synthetic_data
        wrapper = get_model("multirocket")
        window_cfg = {"window_length": 288, "stride": 72, "channels": ["value", "i_cal"]}
        wrapper.set_window_config(window_cfg)
        wrapper.fit(X, y)

        meta = wrapper.get_metadata()
        assert meta["model_name"] == "multirocket"
        assert meta["window_config"] == window_cfg
        assert meta["is_fitted"] is True
        assert meta["train_time_sec"] > 0


# ---------------------------------------------------------------------------
# Tests: Tier 3 (only if torch available)
# ---------------------------------------------------------------------------


class TestTier3Models:
    """Tier 3 自定义模型冒烟测试（仅在 torch 可用时执行）。"""

    @pytest.fixture(autouse=True)
    def check_torch(self):
        try:
            import torch  # noqa: F401
        except ImportError:
            pytest.skip("torch 未安装，跳过 Tier 3 测试")

    def test_cnn_lstm_smoke(self, synthetic_data):
        """CNN-LSTM 1 epoch 冒烟测试。"""
        X, y = synthetic_data
        wrapper = get_model("cnn_lstm", n_epochs=2, patience=2)
        wrapper.fit(X, y)
        preds = wrapper.predict(X)
        assert preds.shape == (len(y),)

    def test_cnn_bilstm_attention_smoke(self, synthetic_data):
        """CNN-BiLSTM-Attention 1 epoch 冒烟测试。"""
        X, y = synthetic_data
        wrapper = get_model("cnn_bilstm_attention", n_epochs=2, patience=2)
        wrapper.fit(X, y)
        preds = wrapper.predict(X)
        assert preds.shape == (len(y),)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
# @AI_GENERATED: end
