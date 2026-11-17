# @AI_GENERATED
"""
注册负荷预测流水线模板到数据库

将三个新的通用算子流水线模板（训练、推理、回测）插入 workflow_templates 表，
使其在模板库页面中可见。
"""
import sys
import os

# Add backend dir to path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from datetime import datetime
from database import SessionLocal
from models.algo_template import WorkflowTemplate

TEMPLATES = [
    {
        "id": "tpl-load-forecast-training",
        "name": "负荷预测训练流水线",
        "description": "基于通用算子的完整负荷预测训练流程：CSV数据加载 → 行过滤 → 时序重采样 → 异常值检测 → 缺失值处理 → 时间特征 → 节假日特征 → 工作日特征 → 滚动统计 → 滞后特征 → 滑动窗口 → 数据切分 → 多步预测配置 → XGBoost预测 → SMAPE评估 + MSE/RMSE/MAE评估",
        "scenario_id": "load_forecast",
        "scenario_name": "负荷预测",
        "category": "时序预测",
        "status": "published",
        "version": "v1.0.0",
        "author": "system",
        "node_count": 16,
        "edge_count": 15,
        "tags": ["负荷预测", "XGBoost", "时序预测", "通用算子"],
    },
    {
        "id": "tpl-load-forecast-prediction",
        "name": "负荷预测推理流水线",
        "description": "使用已训练模型执行负荷预测推理：CSV数据加载 → 行过滤 → 时序重采样 → 缺失值处理 → 时间特征 → 节假日特征 → 工作日特征 → 滚动统计 → 滞后特征 → 多步预测配置 → XGBoost预测（预测模式）",
        "scenario_id": "load_forecast",
        "scenario_name": "负荷预测",
        "category": "时序预测",
        "status": "published",
        "version": "v1.0.0",
        "author": "system",
        "node_count": 11,
        "edge_count": 10,
        "tags": ["负荷预测", "推理", "XGBoost", "通用算子"],
    },
    {
        "id": "tpl-load-forecast-backtest",
        "name": "负荷预测回测流水线",
        "description": "按日期范围逐日执行训练+推理，评估模型回测表现。包含完整的训练流水线算子，支持配置回测开始/结束日期。",
        "scenario_id": "load_forecast",
        "scenario_name": "负荷预测",
        "category": "时序预测",
        "status": "published",
        "version": "v1.0.0",
        "author": "system",
        "node_count": 16,
        "edge_count": 15,
        "tags": ["负荷预测", "回测", "XGBoost", "通用算子"],
    },
]


def register_templates():
    db = SessionLocal()
    try:
        for tpl_data in TEMPLATES:
            existing = db.query(WorkflowTemplate).filter(
                WorkflowTemplate.id == tpl_data["id"]
            ).first()

            if existing:
                # Update existing
                for key, value in tpl_data.items():
                    if key != "id":
                        setattr(existing, key, value)
                existing.updated_at = datetime.now()
                print(f"  Updated: {tpl_data['name']}")
            else:
                # Create new
                now = datetime.now()
                new_tpl = WorkflowTemplate(
                    id=tpl_data["id"],
                    name=tpl_data["name"],
                    description=tpl_data["description"],
                    scenario_id=tpl_data["scenario_id"],
                    scenario_name=tpl_data["scenario_name"],
                    category=tpl_data["category"],
                    status=tpl_data["status"],
                    version=tpl_data["version"],
                    author=tpl_data["author"],
                    node_count=tpl_data["node_count"],
                    edge_count=tpl_data["edge_count"],
                    tags=tpl_data["tags"],
                    created_at=now,
                    updated_at=now,
                    published_at=now,
                )
                db.add(new_tpl)
                print(f"  Created: {tpl_data['name']}")

        db.commit()
        print(f"\nDone! Registered {len(TEMPLATES)} pipeline templates.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Registering load forecast pipeline templates...")
    register_templates()
# @AI_GENERATED: end
