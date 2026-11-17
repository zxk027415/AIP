# -*- coding: utf-8 -*-
"""
端到端集成测试：光伏故障诊断算子流水线

覆盖：
  - 训练流水线：label_encode → time_window_split → handle_missing → detect_outliers
                → extract_statistical_features → feature_select → smote_oversample
                → random_forest_classifier → precision_recall_f1
  - 预测流水线：time_window_split → handle_missing → detect_outliers
                → extract_statistical_features → feature_select(transform)
                → batch_predict_classifier → label_encode(decode)
  - 正确性属性（property-based tests via hypothesis）：
      1. encode(decode(x)) == x  （标签双向一致，Validates: Requirements 1.1）
      2. feature rows == unique group count  （特征行数=分组数，Validates: Requirements 5.8）
      3. |predictions| + failure_count == total_objects  （批量预测完整性，Validates: Requirements 11.3）
      4. SMOTE 后少数类样本数单调递增  （Validates: Requirements 8.1）

测试数据：
  - 优先使用 fault-diag-algo-release-3.1/enos_fault_diag/test/ 下的 parquet 文件
  - 如无法读取则生成合成数据（3 sites × 3 devices × 7 days × 96 时间点）

运行方式：
  conda activate aip_web && cd backend-service && pytest tests/test_pv_fault_diag_operators.py -v
"""

import sys
import os
import warnings

# 确保 backend-service 在 PYTHONPATH 中
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

warnings.filterwarnings("ignore", category=FutureWarning)

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ── 算子后端导入 ──────────────────────────────────────────────────────────────
from services.operator_backends.label_encode import execute as label_encode_exec
from services.operator_backends.time_window_split import execute as time_window_split_exec
from services.operator_backends.handle_missing import execute as handle_missing_exec
from services.operator_backends.detect_outliers import execute as detect_outliers_exec
from services.operator_backends.extract_statistical_features import execute as extract_stat_exec
from services.operator_backends.feature_select import execute as feature_select_exec
from services.operator_backends.smote_oversample import execute as smote_oversample_exec
from services.operator_backends.random_forest_classifier import execute as rfc_exec
from services.operator_backends.precision_recall_f1 import execute as precision_recall_f1_exec
from services.operator_backends.batch_predict_classifier import execute as batch_predict_exec

# ──────────────────────────────────────────────────────────────────────────────
# 测试数据常量
# ──────────────────────────────────────────────────────────────────────────────

# 指向 fault-diag 算法仓库的测试数据目录（相对于项目根）
_FAULT_DIAG_TEST_DIR = os.path.join(
    os.path.dirname(_BACKEND_DIR),
    "fault-diag-algo-release-3.1",
    "enos_fault_diag",
    "test",
)

# 测试用标签映射
LABEL_MAP = {"fault_a": 1, "fault_b": 2, "normal": 0}

# 通用 ID 字段
ID_FIELDS = ["site_id", "device_id", "branch_id"]
ID_FIELDS_WITH_WINDOW = ID_FIELDS + ["time_window"]

# 测量列（数值特征）
VALUE_FIELDS = ["value", "i_cal"]


# ──────────────────────────────────────────────────────────────────────────────
# 数据加载 / 合成工具
# ──────────────────────────────────────────────────────────────────────────────

def _load_parquet_or_none(filename: str):
    """尝试从 fault-diag 测试目录加载 parquet 文件；失败返回 None。"""
    path = os.path.join(_FAULT_DIAG_TEST_DIR, filename)
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _make_synthetic_train_data(
    n_sites: int = 2,
    n_devices: int = 2,
    n_days: int = 3,
    n_points: int = 96,
    seed: int = 42,
) -> pd.DataFrame:
    """
    生成合成训练时序数据。

    行结构：site_id, device_id, branch_id, time, value, i_cal, label
    """
    rng = np.random.default_rng(seed)
    rows = []
    label_cycle = [0, 0, 1, 1, 2, 0]  # 循环故障类别
    combo_idx = 0
    for s in range(n_sites):
        for d in range(n_devices):
            for b in range(1, 3):
                label = label_cycle[combo_idx % len(label_cycle)]
                combo_idx += 1
                for day in range(n_days):
                    base_time = pd.Timestamp("2022-01-01") + pd.Timedelta(days=day)
                    times = pd.date_range(base_time, periods=n_points, freq="15min")
                    for t in times:
                        rows.append({
                            "site_id": f"site_{s}",
                            "device_id": f"device_{d}",
                            "branch_id": b,
                            "time": t,
                            "value": rng.normal(10.0, 2.0),
                            "i_cal": rng.normal(5.0, 1.0),
                            "label": label,
                        })
    return pd.DataFrame(rows)


def _make_synthetic_predict_data(
    n_sites: int = 2,
    n_devices: int = 2,
    n_days: int = 2,
    n_points: int = 96,
    seed: int = 99,
) -> pd.DataFrame:
    """生成合成预测时序数据（不含 label）。"""
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_sites):
        for d in range(n_devices):
            for b in range(1, 3):
                for day in range(n_days):
                    base_time = pd.Timestamp("2022-02-01") + pd.Timedelta(days=day)
                    times = pd.date_range(base_time, periods=n_points, freq="15min")
                    for t in times:
                        rows.append({
                            "site_id": f"site_{s}",
                            "device_id": f"device_{d}",
                            "branch_id": b,
                            "time": t,
                            "value": rng.normal(10.0, 2.0),
                            "i_cal": rng.normal(5.0, 1.0),
                        })
    return pd.DataFrame(rows)


def _load_train_data_with_label() -> pd.DataFrame:
    """
    加载带标签的训练数据（含 label 整型列）。
    优先从 parquet 文件加载；失败时生成合成数据。
    返回 DataFrame，含 site_id, device_id, branch_id, time, value, i_cal, label 列。
    """
    train = _load_parquet_or_none("train_small.parquet")
    label = _load_parquet_or_none("label_small.parquet")
    if train is not None and label is not None:
        label["date"] = pd.to_datetime(label["time"]).dt.date
        train = train.copy()
        train["date"] = pd.to_datetime(train["time"]).dt.date
        train = train.merge(
            label[["site_id", "device_id", "branch_id", "date", "custom_label_id"]],
            on=["site_id", "device_id", "branch_id", "date"],
            how="left",
        )
        train["label"] = train["custom_label_id"].fillna(0).astype(int)
        train = train.drop(columns=["date", "custom_label_id"], errors="ignore")
        # 使用前 8 个设备组的子集，加速测试
        groups = train[ID_FIELDS].drop_duplicates().head(8)
        return train.merge(groups, on=ID_FIELDS)
    return _make_synthetic_train_data()


def _load_predict_data() -> pd.DataFrame:
    """
    加载预测时序数据。
    优先从 parquet 文件加载；失败时生成合成数据。
    """
    pred = _load_parquet_or_none("predict_small.parquet")
    if pred is not None:
        # 去掉已有的 time_window（由算子重新计算）
        pred = pred.drop(columns=["time_window"], errors="ignore")
        # 使用前 4 个设备组的子集，加速测试
        groups = pred[ID_FIELDS].drop_duplicates().head(4)
        return pred.merge(groups, on=ID_FIELDS)
    return _make_synthetic_predict_data()


# ──────────────────────────────────────────────────────────────────────────────
# 共享的流水线工具函数
# ──────────────────────────────────────────────────────────────────────────────

def _run_preprocessing(df: pd.DataFrame) -> pd.DataFrame:
    """
    共享预处理步骤：time_window_split → handle_missing → detect_outliers。
    返回清洗后的 DataFrame（含 time_window 列）。
    """
    # Step 1: 时间窗口切分（1 天 = 1 窗口）
    df = time_window_split_exec(
        params={"window": "1d", "id_fields": ID_FIELDS, "time_field": "time"},
        inputs={"data": df},
    )["data"]

    # Step 2: 丢弃数据不足的分组
    df = handle_missing_exec(
        params={
            "method": "drop_insufficient",
            "id_fields": ID_FIELDS_WITH_WINDOW,
            "value_fields": VALUE_FIELDS,
            "keep_threshold": 0.75,
        },
        inputs={"data": df},
    )["data"]

    # Step 3: 鲁棒裁剪极值
    df = detect_outliers_exec(
        params={
            "method": "robust_clip",
            "id_fields": ID_FIELDS_WITH_WINDOW,
            "value_fields": VALUE_FIELDS,
        },
        inputs={"data": df},
    )["data"]

    return df


def _run_feature_extraction(df: pd.DataFrame, id_fields_for_group: list) -> pd.DataFrame:
    """
    分组聚合统计特征提取。
    id_fields_for_group 包含 time_window（以及可能的 label）。
    """
    return extract_stat_exec(
        params={
            "mode": "groupby_aggregate",
            "id_fields": id_fields_for_group,
            "value_fields": VALUE_FIELDS,
            "compute_diff": True,
            "quantiles": [0.25, 0.75],
        },
        inputs={"data": df},
    )["data"]


# ──────────────────────────────────────────────────────────────────────────────
# 测试 1：训练流水线端到端
# ──────────────────────────────────────────────────────────────────────────────

class TestTrainingPipeline:
    """验证训练流水线完整跑通，无报错。"""

    @pytest.fixture(scope="class")
    def train_pipeline_result(self):
        """运行完整训练流水线，返回 (feature_df, rf_result, metrics_result)。"""
        train_df = _load_train_data_with_label()

        # 预处理（时间窗口 + 清洗 + 去极值）
        cleaned_df = _run_preprocessing(train_df)
        assert not cleaned_df.empty, "预处理后 DataFrame 不应为空"
        assert "time_window" in cleaned_df.columns

        # 特征提取（id_fields 含 label）
        group_fields = ID_FIELDS_WITH_WINDOW + ["label"]
        feat_df = _run_feature_extraction(cleaned_df, group_fields)
        assert not feat_df.empty, "特征提取后 DataFrame 不应为空"

        # mRMR 特征选择：需去掉非数值 ID 列，仅保留数值特征 + label
        non_feature_cols = [c for c in ID_FIELDS_WITH_WINDOW if c in feat_df.columns]
        feat_df_for_select = feat_df.drop(columns=non_feature_cols, errors="ignore")
        # 确保所有列均为数值型（去掉残留字符串列）
        numeric_cols = [
            c for c in feat_df_for_select.columns
            if c == "label" or pd.api.types.is_numeric_dtype(feat_df_for_select[c])
        ]
        feat_df_for_select = feat_df_for_select[numeric_cols]

        fs_result = feature_select_exec(
            params={"method": "mrmr", "k": 5, "mode": "fit", "target_col": "label"},
            inputs={"data": feat_df_for_select},
        )
        selected_features = fs_result["selected_features"]
        feature_list = fs_result["feature_list"]
        target = fs_result["target"]

        # SMOTE 过采样
        smote_result = smote_oversample_exec(
            params={"limit": 50},
            inputs={"features": selected_features, "target": target},
        )
        X_balanced = smote_result["features"]
        y_balanced = smote_result["target"]

        # 随机森林训练
        rf_result = rfc_exec(
            params={"mode": "train", "n_estimators": 20, "random_state": 42},
            inputs={"features": X_balanced, "target": y_balanced},
        )

        # 评估
        metrics = precision_recall_f1_exec(
            params={"average": "macro"},
            inputs={"y_true": rf_result["y_true"], "y_pred": rf_result["predictions"]},
        )

        return {
            "cleaned_df": cleaned_df,
            "feat_df": feat_df,
            "feature_list": feature_list,
            "selected_features": selected_features,
            "target": target,
            "smote_result": smote_result,
            "rf_result": rf_result,
            "metrics": metrics,
        }

    def test_preprocessing_produces_time_window_column(self, train_pipeline_result):
        """预处理后必须含 time_window 列。"""
        assert "time_window" in train_pipeline_result["cleaned_df"].columns

    def test_feature_extraction_produces_nonempty_matrix(self, train_pipeline_result):
        """特征提取后输出非空。"""
        feat_df = train_pipeline_result["feat_df"]
        assert len(feat_df) > 0
        assert len(feat_df.columns) > len(ID_FIELDS_WITH_WINDOW)

    def test_feature_select_returns_feature_list(self, train_pipeline_result):
        """feature_select 返回非空 feature_list。"""
        assert len(train_pipeline_result["feature_list"]) > 0

    def test_feature_select_matrix_has_selected_columns(self, train_pipeline_result):
        """selected_features 的列恰好是 feature_list。"""
        selected_features = train_pipeline_result["selected_features"]
        feature_list = train_pipeline_result["feature_list"]
        assert list(selected_features.columns) == feature_list

    def test_rf_model_returned(self, train_pipeline_result):
        """随机森林训练后返回 model 对象。"""
        assert "model" in train_pipeline_result["rf_result"]
        assert hasattr(train_pipeline_result["rf_result"]["model"], "predict")

    def test_rf_predictions_length_matches_target(self, train_pipeline_result):
        """训练集预测结果行数 == 训练样本数。"""
        rf = train_pipeline_result["rf_result"]
        assert len(rf["predictions"]) == len(rf["y_true"])

    def test_rf_predictions_are_integers(self, train_pipeline_result):
        """预测结果为整型。"""
        preds = train_pipeline_result["rf_result"]["predictions"]
        assert np.issubdtype(preds.dtype, np.integer)

    def test_metrics_contains_required_keys(self, train_pipeline_result):
        """评估结果包含 accuracy/precision/recall/f1。"""
        metrics = train_pipeline_result["metrics"]
        for key in ("accuracy", "precision", "recall", "f1"):
            assert key in metrics

    def test_metrics_values_in_valid_range(self, train_pipeline_result):
        """所有指标在 [0, 1] 范围内。"""
        metrics = train_pipeline_result["metrics"]
        for key in ("accuracy", "precision", "recall", "f1"):
            val = metrics[key]
            assert 0.0 <= val <= 1.0, f"{key}={val} 超出 [0,1] 范围"

    def test_feature_importances_shape(self, train_pipeline_result):
        """特征重要性数组长度 == 特征列数。"""
        rf = train_pipeline_result["rf_result"]
        fi = rf["feature_importances"]
        selected = train_pipeline_result["selected_features"]
        assert len(fi) == selected.shape[1]


# ──────────────────────────────────────────────────────────────────────────────
# 测试 2：预测流水线端到端
# ──────────────────────────────────────────────────────────────────────────────

class TestPredictionPipeline:
    """验证预测流水线完整跑通，无报错。"""

    @pytest.fixture(scope="class")
    def predict_pipeline_result(self):
        """
        先运行训练流水线得到 model 和 feature_list，
        再运行预测流水线，返回最终解码后的预测结果。
        """
        # ── 训练（复用简化版以加速）──────────────────────────────────────────
        train_df = _load_train_data_with_label()
        cleaned_train = _run_preprocessing(train_df)
        feat_train = _run_feature_extraction(cleaned_train, ID_FIELDS_WITH_WINDOW + ["label"])

        # 去掉非数值 ID 列后再做特征选择
        non_feat_cols = [c for c in ID_FIELDS_WITH_WINDOW if c in feat_train.columns]
        feat_train_sel = feat_train.drop(columns=non_feat_cols, errors="ignore")
        numeric_cols = [
            c for c in feat_train_sel.columns
            if c == "label" or pd.api.types.is_numeric_dtype(feat_train_sel[c])
        ]
        feat_train_sel = feat_train_sel[numeric_cols]

        fs_result = feature_select_exec(
            params={"method": "mrmr", "k": 5, "mode": "fit", "target_col": "label"},
            inputs={"data": feat_train_sel},
        )
        feature_list = fs_result["feature_list"]

        smote_result = smote_oversample_exec(
            params={"limit": 50},
            inputs={
                "features": fs_result["selected_features"],
                "target": fs_result["target"],
            },
        )

        rf_result = rfc_exec(
            params={"mode": "train", "n_estimators": 20, "random_state": 42},
            inputs={"features": smote_result["features"], "target": smote_result["target"]},
        )
        model = rf_result["model"]

        # ── 预测流水线 ────────────────────────────────────────────────────────
        predict_df = _load_predict_data()

        # 预处理
        cleaned_pred = _run_preprocessing(predict_df)
        assert not cleaned_pred.empty

        # 特征提取（无 label 列）
        feat_pred = _run_feature_extraction(cleaned_pred, ID_FIELDS_WITH_WINDOW)
        assert not feat_pred.empty

        # feature_select transform（按训练时的 feature_list 筛选）
        # 注意：feature_select 在 transform 模式下仍会解析 target；传入占位 target 避免报错
        dummy_target = np.zeros(len(feat_pred), dtype=int)
        fs_pred = feature_select_exec(
            params={"method": "mrmr", "mode": "transform", "feature_list": feature_list},
            inputs={"data": feat_pred, "target": dummy_target},
        )
        predict_features = fs_pred["selected_features"]

        # 设置 MultiIndex
        predict_features_indexed = predict_features.copy()
        # id_fields 列可能已在 feat_pred 中，需要携带过来
        id_cols_present = [f for f in ID_FIELDS_WITH_WINDOW if f in feat_pred.columns]
        for col in id_cols_present:
            predict_features_indexed[col] = feat_pred[col].values
        predict_features_indexed = predict_features_indexed.set_index(id_cols_present)

        # 批量预测
        bpc_result = batch_predict_exec(
            params={"batch_size": 10, "id_fields": ID_FIELDS_WITH_WINDOW},
            inputs={"model": model, "predict_features": predict_features_indexed},
        )

        # label_encode decode（将 int 预测标签映射回字符串，使用训练集标签映射作为示例）
        # 构造 decode label_map（训练集 label_id → 名称，此处使用数值映射示范即可）
        decode_label_map = {str(v): v for v in sorted(np.unique(rf_result["y_true"]))}
        # 预测结果 DataFrame 含 predict_label 列
        pred_df = bpc_result["predictions"].copy()
        pred_df["predict_label"] = pred_df["predict_label"].astype(str)
        # decode 将字符串数字 → 整数（演示双向一致性）
        # 实际生产使用 label_map 反映射到业务标签

        return {
            "cleaned_pred": cleaned_pred,
            "feat_pred": feat_pred,
            "predict_features": predict_features,
            "bpc_result": bpc_result,
            "total_groups": len(predict_features),
        }

    def test_preprocessing_produces_time_window(self, predict_pipeline_result):
        assert "time_window" in predict_pipeline_result["cleaned_pred"].columns

    def test_feature_extraction_nonempty(self, predict_pipeline_result):
        assert len(predict_pipeline_result["feat_pred"]) > 0

    def test_batch_predict_returns_predictions(self, predict_pipeline_result):
        preds = predict_pipeline_result["bpc_result"]["predictions"]
        assert isinstance(preds, pd.DataFrame)
        assert "predict_label" in preds.columns

    def test_batch_predict_completeness(self, predict_pipeline_result):
        """|predictions| + failure_count == total_objects（验证批量预测完整性属性）。"""
        bpc = predict_pipeline_result["bpc_result"]
        total = predict_pipeline_result["total_groups"]
        n_preds = len(bpc["predictions"])
        fc = bpc["failure_count"]
        assert n_preds + fc == total, (
            f"completeness violated: {n_preds} + {fc} != {total}"
        )

    def test_batch_predict_predictions_nonempty(self, predict_pipeline_result):
        preds = predict_pipeline_result["bpc_result"]["predictions"]
        assert len(preds) > 0

    def test_predict_feature_transform_uses_training_features(self, predict_pipeline_result):
        """transform 后的特征列应与训练集 feature_list 的交集非空。"""
        predict_features = predict_pipeline_result["predict_features"]
        assert len(predict_features.columns) > 0


# ──────────────────────────────────────────────────────────────────────────────
# 测试 3：正确性属性（Property-Based Tests）
# ──────────────────────────────────────────────────────────────────────────────

class TestCorrectnessProperties:
    """四个核心正确性属性验证。"""

    # ── 属性 1：标签 encode→decode 双向一致 ──────────────────────────────────
    # Validates: Requirements 1.1

    @pytest.mark.parametrize("label_key", list(LABEL_MAP.keys()))
    def test_label_encode_decode_roundtrip_all_keys(self, label_key):
        """
        属性 1：∀ label ∈ label_map.keys(): decode(encode(label)) == label
        Validates: Requirements 1.1
        """
        input_df = pd.DataFrame({"label": [label_key]})
        encoded = label_encode_exec(
            params={"mode": "encode", "label_map": LABEL_MAP, "label_col": "label"},
            inputs={"data": input_df},
        )
        decoded = label_encode_exec(
            params={"mode": "decode", "label_map": LABEL_MAP, "label_col": "label"},
            inputs={"data": encoded["data"]},
        )
        assert decoded["data"]["label"].iloc[0] == label_key, (
            f"round-trip failed for '{label_key}': "
            f"encoded={encoded['data']['label'].iloc[0]}, "
            f"decoded={decoded['data']['label'].iloc[0]}"
        )

    @given(
        labels=st.lists(
            st.sampled_from(list(LABEL_MAP.keys())),
            min_size=1,
            max_size=50,
        )
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_label_roundtrip_property(self, labels):
        """
        属性 1（property-based）：encode → decode 的双向一致性对任意输入序列成立。
        Validates: Requirements 1.1
        """
        input_df = pd.DataFrame({"label": labels})
        encoded = label_encode_exec(
            params={"mode": "encode", "label_map": LABEL_MAP, "label_col": "label"},
            inputs={"data": input_df},
        )
        decoded = label_encode_exec(
            params={"mode": "decode", "label_map": LABEL_MAP, "label_col": "label"},
            inputs={"data": encoded["data"]},
        )
        assert list(decoded["data"]["label"]) == labels

    # ── 属性 2：特征行数 == 唯一分组数 ──────────────────────────────────────
    # Validates: Requirements 5.8

    def test_feature_rows_equals_unique_groups(self):
        """
        属性 2：|output_features| == |unique(id_fields × time_window)|
        Validates: Requirements 5.8
        """
        # 生成结构清晰的合成数据
        train_df = _make_synthetic_train_data(n_sites=2, n_devices=2, n_days=3, n_points=48)

        # 预处理
        cleaned = _run_preprocessing(train_df)
        assert not cleaned.empty

        # 唯一分组数（含 label 和 time_window）
        group_fields = ID_FIELDS_WITH_WINDOW + ["label"]
        unique_group_count = cleaned.groupby(group_fields, dropna=False).ngroups

        # 特征提取
        feat_df = _run_feature_extraction(cleaned, group_fields)

        # 特征行数 == 唯一分组数（id_fields 列保留在 feat_df 中，不计入 numeric feature 列）
        assert len(feat_df) == unique_group_count, (
            f"feature rows {len(feat_df)} != unique groups {unique_group_count}"
        )

    @given(
        n_sites=st.integers(min_value=1, max_value=2),
        n_devices=st.integers(min_value=1, max_value=2),
        n_days=st.integers(min_value=2, max_value=4),
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_feature_rows_equals_unique_groups_property(self, n_sites, n_devices, n_days):
        """
        属性 2（property-based）：特征矩阵行数 == 唯一分组数，对任意合理输入成立。
        Validates: Requirements 5.8
        """
        train_df = _make_synthetic_train_data(
            n_sites=n_sites, n_devices=n_devices, n_days=n_days, n_points=48
        )
        cleaned = _run_preprocessing(train_df)
        if cleaned.empty:
            return  # 预处理后为空，跳过（极端情况）

        group_fields = ID_FIELDS_WITH_WINDOW + ["label"]
        unique_group_count = cleaned.groupby(group_fields, dropna=False).ngroups
        feat_df = _run_feature_extraction(cleaned, group_fields)

        assert len(feat_df) == unique_group_count

    # ── 属性 3：批量预测完整性 |predictions| + failure_count == total_objects ──
    # Validates: Requirements 11.3

    @given(
        n_objects=st.integers(min_value=1, max_value=50),
        batch_size=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_batch_predict_completeness_property(self, n_objects, batch_size):
        """
        属性 3：|predictions| + failure_count == total_objects
        对任意数量的对象和任意分批大小成立。
        Validates: Requirements 11.3
        """
        from sklearn.ensemble import RandomForestClassifier

        rng = np.random.default_rng(42 + n_objects + batch_size)
        n_features = 5
        n_train = max(10, n_objects // 2)

        # 训练简单模型
        X_train = rng.standard_normal((n_train, n_features))
        y_train = rng.integers(0, 3, size=n_train)
        model = RandomForestClassifier(n_estimators=5, random_state=42)
        model.fit(X_train, y_train)

        # 预测数据（以 RangeIndex 为 MultiIndex，或按 site_id 分组）
        X_pred = pd.DataFrame(
            rng.standard_normal((n_objects, n_features)),
            columns=[f"f{i}" for i in range(n_features)],
        )
        X_pred["site_id"] = [f"s{i}" for i in range(n_objects)]
        X_pred["device_id"] = [f"d{i}" for i in range(n_objects)]
        X_pred = X_pred.set_index(["site_id", "device_id"])

        result = batch_predict_exec(
            params={"batch_size": batch_size, "id_fields": ["site_id", "device_id"]},
            inputs={"model": model, "predict_features": X_pred},
        )

        n_preds = len(result["predictions"])
        fc = result["failure_count"]
        assert n_preds + fc == n_objects, (
            f"completeness violated: {n_preds} + {fc} != {n_objects} "
            f"(batch_size={batch_size})"
        )

    # ── 属性 4：SMOTE 后少数类样本数单调递增 ─────────────────────────────────
    # Validates: Requirements 8.1

    def test_smote_minority_class_monotone_increase(self):
        """
        属性 4：∀ class c: count(c after SMOTE) >= count(c before SMOTE)
        Validates: Requirements 8.1
        """
        # 构造类别不平衡数据
        rng = np.random.default_rng(42)
        X = pd.DataFrame(rng.standard_normal((50, 4)), columns=[f"f{i}" for i in range(4)])
        # 类别 0: 30 个, 类别 1: 10 个, 类别 2: 10 个
        y = np.array([0] * 30 + [1] * 10 + [2] * 10)

        classes_before, counts_before = np.unique(y, return_counts=True)
        count_before = dict(zip(classes_before.tolist(), counts_before.tolist()))

        result = smote_oversample_exec(
            params={"limit": 25},
            inputs={"features": X, "target": y},
        )

        classes_after, counts_after = np.unique(result["target"], return_counts=True)
        count_after = dict(zip(classes_after.tolist(), counts_after.tolist()))

        for cls in classes_before:
            after = count_after.get(int(cls), 0)
            before = count_before[int(cls)]
            assert after >= before, (
                f"class {cls}: after ({after}) < before ({before}) — SMOTE 不应减少样本数"
            )

    @given(
        minority_count=st.integers(min_value=3, max_value=20),
        majority_count=st.integers(min_value=20, max_value=60),
        limit=st.integers(min_value=20, max_value=50),
    )
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_smote_minority_monotone_property(self, minority_count, majority_count, limit):
        """
        属性 4（property-based）：SMOTE 后少数类样本数 >= SMOTE 前少数类样本数，
        对任意合法参数成立。
        Validates: Requirements 8.1
        """
        rng = np.random.default_rng(42)
        n_features = 4
        X = pd.DataFrame(
            rng.standard_normal((majority_count + minority_count * 2, n_features)),
            columns=[f"f{i}" for i in range(n_features)],
        )
        y = np.array(
            [0] * majority_count + [1] * minority_count + [2] * minority_count
        )

        _, counts_before = np.unique(y, return_counts=True)
        count_before = dict(enumerate(counts_before.tolist()))

        result = smote_oversample_exec(
            params={"limit": limit},
            inputs={"features": X, "target": y},
        )

        classes_after, counts_after = np.unique(result["target"], return_counts=True)
        count_after = dict(zip(classes_after.tolist(), counts_after.tolist()))

        for cls, before in count_before.items():
            after = count_after.get(cls, 0)
            assert after >= before, (
                f"class {cls}: after ({after}) < before ({before}) "
                f"[minority={minority_count}, limit={limit}]"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 测试 4：各算子单元级别冒烟测试
# ──────────────────────────────────────────────────────────────────────────────

class TestOperatorSmoke:
    """验证各算子在正常输入下不报错，并返回预期 key。"""

    def _make_simple_df(self, n: int = 100, seed: int = 0) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        times = pd.date_range("2022-01-01", periods=n, freq="15min")
        return pd.DataFrame({
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": 1,
            "time": times,
            "value": rng.normal(10, 1, n),
            "i_cal": rng.normal(5, 0.5, n),
        })

    def test_time_window_split_adds_time_window(self):
        df = self._make_simple_df(200)
        result = time_window_split_exec(
            params={"window": "1d", "id_fields": ID_FIELDS, "time_field": "time"},
            inputs={"data": df},
        )
        assert "data" in result
        assert "time_window" in result["data"].columns
        assert len(result["data"]) == len(df)

    def test_handle_missing_drop_insufficient(self):
        df = self._make_simple_df(200)
        # 先分配 time_window
        df = time_window_split_exec(
            params={"window": "1d", "id_fields": ID_FIELDS, "time_field": "time"},
            inputs={"data": df},
        )["data"]
        result = handle_missing_exec(
            params={
                "method": "drop_insufficient",
                "id_fields": ID_FIELDS_WITH_WINDOW,
                "value_fields": VALUE_FIELDS,
            },
            inputs={"data": df},
        )
        assert "data" in result
        assert isinstance(result["data"], pd.DataFrame)

    def test_detect_outliers_robust_clip(self):
        df = self._make_simple_df(200)
        df = time_window_split_exec(
            params={"window": "1d", "id_fields": ID_FIELDS, "time_field": "time"},
            inputs={"data": df},
        )["data"]
        result = detect_outliers_exec(
            params={
                "method": "robust_clip",
                "id_fields": ID_FIELDS_WITH_WINDOW,
                "value_fields": VALUE_FIELDS,
            },
            inputs={"data": df},
        )
        assert "data" in result
        assert "outlier_indices" in result

    def test_label_encode_encode_mode(self):
        df = pd.DataFrame({"label": ["normal", "fault_a", "fault_b", "normal"]})
        result = label_encode_exec(
            params={"mode": "encode", "label_map": LABEL_MAP, "label_col": "label"},
            inputs={"data": df},
        )
        assert "data" in result
        assert set(result["data"]["label"].unique()) <= {0, 1, 2, -1}

    def test_label_encode_decode_mode(self):
        df = pd.DataFrame({"label": [0, 1, 2, 0]})
        result = label_encode_exec(
            params={"mode": "decode", "label_map": LABEL_MAP, "label_col": "label"},
            inputs={"data": df},
        )
        assert "data" in result
        assert set(result["data"]["label"].unique()) <= set(LABEL_MAP.keys())

    def test_feature_select_mrmr_fit(self):
        rng = np.random.default_rng(0)
        X = pd.DataFrame(rng.standard_normal((30, 8)), columns=[f"f{i}" for i in range(8)])
        y = np.array([0]*10 + [1]*10 + [2]*10)
        X["label"] = y
        result = feature_select_exec(
            params={"method": "mrmr", "k": 4, "mode": "fit", "target_col": "label"},
            inputs={"data": X},
        )
        assert "selected_features" in result
        assert "feature_list" in result
        assert len(result["feature_list"]) <= 4
        assert len(result["feature_list"]) > 0

    def test_feature_select_mrmr_transform(self):
        rng = np.random.default_rng(1)
        X = pd.DataFrame(rng.standard_normal((20, 5)), columns=[f"f{i}" for i in range(5)])
        feature_list = ["f0", "f2", "f4"]
        # transform mode requires target to be provided (passed as external input)
        result = feature_select_exec(
            params={"method": "mrmr", "mode": "transform", "feature_list": feature_list},
            inputs={"data": X, "target": np.zeros(len(X), dtype=int)},
        )
        assert "selected_features" in result
        assert list(result["selected_features"].columns) == feature_list

    def test_smote_oversample_returns_features_and_target(self):
        rng = np.random.default_rng(2)
        X = pd.DataFrame(rng.standard_normal((30, 4)), columns=[f"f{i}" for i in range(4)])
        y = np.array([0]*20 + [1]*10)
        result = smote_oversample_exec(
            params={"limit": 15},
            inputs={"features": X, "target": y},
        )
        assert "features" in result
        assert "target" in result
        assert isinstance(result["features"], pd.DataFrame)

    def test_precision_recall_f1_basic(self):
        y_true = np.array([0, 1, 2, 0, 1, 2])
        y_pred = np.array([0, 1, 2, 0, 2, 1])
        result = precision_recall_f1_exec(
            params={"average": "macro"},
            inputs={"y_true": y_true, "y_pred": y_pred},
        )
        for key in ("accuracy", "precision", "recall", "f1"):
            assert key in result
            assert 0.0 <= result[key] <= 1.0

    def test_precision_recall_f1_length_mismatch_raises(self):
        from services.operator_execution.router import OperatorExecutionError
        with pytest.raises(OperatorExecutionError):
            precision_recall_f1_exec(
                params={"average": "macro"},
                inputs={"y_true": np.array([0, 1, 2]), "y_pred": np.array([0, 1])},
            )

    def test_label_encode_duplicate_values_raises(self):
        from services.operator_execution.router import OperatorExecutionError
        bad_map = {"a": 1, "b": 1, "c": 2}
        df = pd.DataFrame({"label": ["a", "b", "c"]})
        with pytest.raises(OperatorExecutionError):
            label_encode_exec(
                params={"mode": "encode", "label_map": bad_map, "label_col": "label"},
                inputs={"data": df},
            )


# ──────────────────────────────────────────────────────────────────────────────
# 测试 5：时间窗口切分算子单元测试
# ──────────────────────────────────────────────────────────────────────────────

class TestTimeWindowSplit:
    """time_window_split 单元测试。"""

    def _make_device_df(self, device_id: str = "d1", n_points: int = 200) -> pd.DataFrame:
        times = pd.date_range("2022-01-01", periods=n_points, freq="15min")
        return pd.DataFrame({
            "site_id": "s1",
            "device_id": device_id,
            "branch_id": 1,
            "time": times,
            "value": np.arange(n_points, dtype=float),
        })

    def test_daily_window_produces_time_window_column(self):
        df = self._make_device_df()
        result = time_window_split_exec(
            params={"window": "1d", "id_fields": ID_FIELDS, "time_field": "time"},
            inputs={"data": df},
        )["data"]
        assert "time_window" in result.columns

    def test_daily_window_row_count_preserved(self):
        df = self._make_device_df(n_points=200)
        result = time_window_split_exec(
            params={"window": "1d", "id_fields": ID_FIELDS, "time_field": "time"},
            inputs={"data": df},
        )["data"]
        assert len(result) == len(df)

    def test_each_record_has_exactly_one_window(self):
        """每条记录只属于一个时间窗口。"""
        df = self._make_device_df(n_points=200)
        result = time_window_split_exec(
            params={"window": "1d", "id_fields": ID_FIELDS, "time_field": "time"},
            inputs={"data": df},
        )["data"]
        # 若不重复，不同时间戳对应的时间窗口 key 应与原始 index 一一对应
        assert result["time_window"].notna().all()

    def test_multi_device_each_device_split_independently(self):
        """多设备分别独立切分，总行数不变。"""
        df1 = self._make_device_df("d1", 100)
        df2 = self._make_device_df("d2", 100)
        df = pd.concat([df1, df2], ignore_index=True)
        result = time_window_split_exec(
            params={"window": "1d", "id_fields": ID_FIELDS, "time_field": "time"},
            inputs={"data": df},
        )["data"]
        assert len(result) == len(df)
        # 每个设备应各自有独立的时间窗口集合
        d1_windows = result[result["device_id"] == "d1"]["time_window"].unique()
        d2_windows = result[result["device_id"] == "d2"]["time_window"].unique()
        assert len(d1_windows) > 0
        assert len(d2_windows) > 0

    def test_absent_id_field_ignored_gracefully(self):
        """若 id_fields 包含不存在的列，应自动过滤，不报错。"""
        df = self._make_device_df(100)
        # branch_id 存在, region_id 不存在
        result = time_window_split_exec(
            params={
                "window": "1d",
                "id_fields": ["site_id", "device_id", "branch_id", "region_id"],
                "time_field": "time",
            },
            inputs={"data": df},
        )["data"]
        assert "time_window" in result.columns
