# @AI_GENERATED: Kiro v1.0
"""新增模型训练分类和相关函数到数据库"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# 1. Add model_training category
try:
    db.execute(text(
        "INSERT INTO algorithm_categories (id, name, description, display_order, created_at, updated_at) "
        "VALUES ('model_training', '模型训练', '数据切分、自动调参和训练流水线', 5, datetime('now'), datetime('now'))"
    ))
    print("Added model_training category")
except Exception as e:
    print(f"Category may exist: {e}")

# 2. Update display_order
orders = [
    ("data_source", 1), ("data_preprocessing", 2), ("feature_engineering", 3),
    ("algorithm_model", 4), ("model_training", 5), ("evaluation_metrics", 6),
]
for cat_id, order in orders:
    db.execute(text(f"UPDATE algorithm_categories SET display_order={order} WHERE id='{cat_id}'"))
print("Updated display_order")

# 3. Add new functions
new_functions = [
    {
        "id": "train_test_split_ts", "name": "时序数据切分", "category_id": "model_training",
        "description": "按时间顺序切分时序数据为训练集、验证集和测试集，保持时间顺序不打乱。",
        "parameters": json.dumps([
            {"name": "data", "type": "MATRIX", "required": True, "description": "输入时序数据"},
            {"name": "train_ratio", "type": "NUMBER", "required": False, "description": "训练集比例，默认0.7"},
            {"name": "val_ratio", "type": "NUMBER", "required": False, "description": "验证集比例，默认0.15"},
            {"name": "split_date", "type": "STRING", "required": False, "description": "按日期切分（YYYY-MM-DD）"},
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["train, val, test = train_test_split_ts(data, 0.7, 0.15)"]),
    },
    {
        "id": "train_test_split_stratified", "name": "分层数据切分", "category_id": "model_training",
        "description": "对分类数据进行分层抽样切分，保持各类别比例一致。",
        "parameters": json.dumps([
            {"name": "features", "type": "MATRIX", "required": True, "description": "特征数据"},
            {"name": "labels", "type": "ARRAY", "required": True, "description": "标签数据"},
            {"name": "test_ratio", "type": "NUMBER", "required": False, "description": "测试集比例，默认0.2"},
            {"name": "random_seed", "type": "NUMBER", "required": False, "description": "随机种子，默认42"},
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["X_train, X_test, y_train, y_test = train_test_split_stratified(features, labels, 0.2)"]),
    },
    {
        "id": "cross_validate_ts", "name": "时序交叉验证", "category_id": "model_training",
        "description": "使用TimeSeriesSplit进行时序交叉验证，避免数据泄露。",
        "parameters": json.dumps([
            {"name": "data", "type": "MATRIX", "required": True, "description": "输入时序数据"},
            {"name": "n_splits", "type": "NUMBER", "required": False, "description": "折数，默认5"},
            {"name": "model_type", "type": "STRING", "required": True, "description": "模型类型：xgboost/random_forest/svm"},
            {"name": "model_params", "type": "STRING", "required": False, "description": "模型参数JSON字符串"},
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["scores = cross_validate_ts(data, 5, 'xgboost')"]),
    },
    {
        "id": "auto_tune_xgboost", "name": "XGBoost自动调参", "category_id": "model_training",
        "description": "使用贝叶斯优化自动搜索XGBoost最优超参数。",
        "parameters": json.dumps([
            {"name": "train_features", "type": "MATRIX", "required": True, "description": "训练特征"},
            {"name": "train_target", "type": "ARRAY", "required": True, "description": "训练目标"},
            {"name": "n_trials", "type": "NUMBER", "required": False, "description": "搜索次数，默认50"},
            {"name": "metric", "type": "STRING", "required": False, "description": "优化指标：rmse/mae/mape"},
            {"name": "cv_folds", "type": "NUMBER", "required": False, "description": "交叉验证折数，默认5"},
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["best_params = auto_tune_xgboost(X_train, y_train, 100, 'rmse')"]),
    },
    {
        "id": "auto_tune_lstm", "name": "LSTM自动调参", "category_id": "model_training",
        "description": "自动搜索LSTM最优超参数，使用EarlyStopping防止过拟合。",
        "parameters": json.dumps([
            {"name": "train_data", "type": "MATRIX", "required": True, "description": "训练数据"},
            {"name": "sequence_length", "type": "NUMBER", "required": True, "description": "输入序列长度"},
            {"name": "n_trials", "type": "NUMBER", "required": False, "description": "搜索次数，默认30"},
            {"name": "metric", "type": "STRING", "required": False, "description": "优化指标：rmse/mae"},
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["best_params = auto_tune_lstm(train_data, 168, 30, 'rmse')"]),
    },
    {
        "id": "auto_tune_svm", "name": "SVM自动调参", "category_id": "model_training",
        "description": "使用网格搜索自动搜索SVM最优超参数（C、gamma、kernel）。",
        "parameters": json.dumps([
            {"name": "train_features", "type": "MATRIX", "required": True, "description": "训练特征"},
            {"name": "train_labels", "type": "ARRAY", "required": True, "description": "训练标签"},
            {"name": "cv_folds", "type": "NUMBER", "required": False, "description": "交叉验证折数，默认5"},
            {"name": "scoring", "type": "STRING", "required": False, "description": "评分指标：accuracy/f1_weighted"},
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["best_params = auto_tune_svm(X_train, y_train, 5, 'f1_weighted')"]),
    },
    {
        "id": "auto_tune_random_forest", "name": "随机森林自动调参", "category_id": "model_training",
        "description": "使用随机搜索自动优化随机森林超参数。",
        "parameters": json.dumps([
            {"name": "train_features", "type": "MATRIX", "required": True, "description": "训练特征"},
            {"name": "train_labels", "type": "ARRAY", "required": True, "description": "训练标签"},
            {"name": "n_iter", "type": "NUMBER", "required": False, "description": "随机搜索迭代次数，默认50"},
            {"name": "cv_folds", "type": "NUMBER", "required": False, "description": "交叉验证折数，默认5"},
            {"name": "scoring", "type": "STRING", "required": False, "description": "评分指标：accuracy/f1_weighted"},
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["best_params = auto_tune_random_forest(X_train, y_train, 50, 5)"]),
    },
    {
        "id": "train_pipeline", "name": "训练流水线", "category_id": "model_training",
        "description": "一键执行完整训练流水线：数据切分→模型训练→预测→评估。自动输出训练报告。",
        "parameters": json.dumps([
            {"name": "data", "type": "MATRIX", "required": True, "description": "输入数据"},
            {"name": "target_column", "type": "STRING", "required": True, "description": "目标列名"},
            {"name": "model_type", "type": "STRING", "required": True, "description": "模型类型：arima/lstm/xgboost/svm/random_forest/isolation_forest"},
            {"name": "task_type", "type": "STRING", "required": False, "description": "任务类型：regression/classification/anomaly_detection"},
            {"name": "auto_tune", "type": "STRING", "required": False, "description": "是否自动调参：true/false"},
            {"name": "split_ratio", "type": "STRING", "required": False, "description": "切分比例JSON"},
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["report = train_pipeline(data, 'power', 'xgboost', 'regression', 'true')"]),
    },
]

for func in new_functions:
    exists = db.execute(text(f"SELECT COUNT(*) FROM algorithm_functions WHERE id='{func['id']}'")).scalar()
    if exists > 0:
        print(f"  Skipped {func['id']} (exists)")
        continue
    db.execute(text(
        "INSERT INTO algorithm_functions (id, name, category_id, description, parameters, return_type, examples, status, version, created_at, updated_at) "
        "VALUES (:id, :name, :category_id, :description, :parameters, :return_type, :examples, 'published', 1, datetime('now'), datetime('now'))"
    ), func)
    db.execute(text(
        "INSERT INTO algorithm_versions (function_id, version, data_snapshot, change_description, created_at) "
        "VALUES (:fid, 1, :snapshot, '初始版本', datetime('now'))"
    ), {"fid": func["id"], "snapshot": json.dumps(func)})
    print(f"  Added {func['id']}: {func['name']}")

db.commit()

# Verify
print("\n=== 最终结果 ===")
cats = db.execute(text("SELECT id, name, display_order FROM algorithm_categories ORDER BY display_order")).fetchall()
for c in cats:
    count = db.execute(text(f"SELECT COUNT(*) FROM algorithm_functions WHERE category_id='{c[0]}'")).scalar()
    print(f"{c[2]}. {c[1]} ({c[0]}): {count} 个函数")

total = db.execute(text("SELECT COUNT(*) FROM algorithm_functions")).scalar()
print(f"\n总计: {total} 个算法函数")
db.close()
# @AI_GENERATED: end
