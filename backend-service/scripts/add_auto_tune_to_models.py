# @AI_GENERATED: Kiro v1.0
"""给6个算法模型函数添加 auto_tune 参数"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

models = {
    "arima_forecast": {
        "auto_tune_desc": "是否自动搜索最优(p,d,q)参数：true/false，默认false",
    },
    "lstm_forecast": {
        "auto_tune_desc": "是否自动搜索最优超参数(hidden_units/learning_rate/dropout)：true/false，默认false",
    },
    "xgboost_forecast": {
        "auto_tune_desc": "是否自动搜索最优超参数(n_estimators/max_depth/learning_rate等)：true/false，默认false",
    },
    "isolation_forest_anomaly": {
        "auto_tune_desc": "是否自动搜索最优contamination参数：true/false，默认false",
    },
    "svm_classifier": {
        "auto_tune_desc": "是否自动搜索最优超参数(C/gamma/kernel)：true/false，默认false",
    },
    "random_forest_classifier": {
        "auto_tune_desc": "是否自动搜索最优超参数(n_estimators/max_depth/max_features等)：true/false，默认false",
    },
}

for func_id, config in models.items():
    # Read current parameters
    row = db.execute(text(
        "SELECT parameters FROM algorithm_functions WHERE id=:id"
    ), {"id": func_id}).fetchone()

    if not row:
        print(f"  {func_id}: NOT FOUND")
        continue

    params = json.loads(row[0])

    # Check if auto_tune already exists
    if any(p["name"] == "auto_tune" for p in params):
        print(f"  {func_id}: auto_tune already exists, skipped")
        continue

    # Add auto_tune parameter
    params.append({
        "name": "auto_tune",
        "type": "STRING",
        "required": False,
        "description": config["auto_tune_desc"],
    })

    db.execute(text(
        "UPDATE algorithm_functions SET parameters=:params WHERE id=:id"
    ), {"params": json.dumps(params), "id": func_id})
    print(f"  {func_id}: added auto_tune param")

db.commit()

# Verify
for func_id in models:
    row = db.execute(text("SELECT parameters FROM algorithm_functions WHERE id=:id"), {"id": func_id}).fetchone()
    params = json.loads(row[0])
    param_names = [p["name"] for p in params]
    print(f"  {func_id}: {param_names}")

db.close()
print("Done!")
# @AI_GENERATED: end
