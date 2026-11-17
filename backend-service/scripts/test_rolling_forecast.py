"""运行真实 XGBoost 滚动预测实验"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.precision_ops.rolling_forecast_experiment import run_rolling_forecast_experiment

result = run_rolling_forecast_experiment(
    csv_path="datasets/load_true_weihai_260415.csv",
    start_date="2026-04-01",
    observation_days=7,
    train_days=60,
    production_n_estimators=200,
    prelaunch_n_estimators=500,
)

print(json.dumps(result, indent=2, ensure_ascii=False))
