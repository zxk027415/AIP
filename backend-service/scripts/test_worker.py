"""快速测试 Worker 逻辑（同步跑 2 天验证）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.precision_ops.daily_prediction_worker import DailyPredictionWorker

worker = DailyPredictionWorker(
    slot="default",
    start_date="2026-04-01",
    observation_days=3,  # 只跑 3 天验证
    train_days=60,
    interval_seconds=1,  # 1 秒间隔
)
worker._load_data()
worker._init_state()

# 手动执行 3 天
for _ in range(3):
    worker._execute_one_day()
    status = worker.get_status()
    print(f"Day {status['current_day']}: prod={worker.daily_results[-1]['production_mape']}% "
          f"pre={worker.daily_results[-1]['prelaunch_mape']}% "
          f"winner={worker.daily_results[-1]['winner']}")

print(f"\nDone! Status: {worker.get_status()['completed']}")
