# @AI_GENERATED: Kiro v1.0
"""合并 load_timeseries 到 load_csv，同步数据库"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# 1. Delete load_timeseries
db.execute(text("DELETE FROM algorithm_versions WHERE function_id='load_timeseries'"))
db.execute(text("DELETE FROM algorithm_functions WHERE id='load_timeseries'"))
print("Deleted load_timeseries")

# 2. Update load_csv
new_params = json.dumps([
    {"name": "file_path", "type": "STRING", "required": True, "description": "文件路径或上传文件ID"},
    {"name": "delimiter", "type": "STRING", "required": False, "description": "分隔符，默认逗号"},
    {"name": "encoding", "type": "STRING", "required": False, "description": "文件编码：utf-8/gbk/gb2312，默认自动检测"},
    {"name": "header_row", "type": "NUMBER", "required": False, "description": "表头行号，默认0（第一行）"},
    {"name": "timestamp_column", "type": "STRING", "required": False, "description": "时间戳列名（时序数据场景使用，自动解析为时间索引）"},
    {"name": "value_columns", "type": "ARRAY", "required": False, "description": "数值列名列表（时序数据场景使用，仅加载指定列）"},
])
new_desc = "从CSV/Excel文件加载数据，支持自动类型推断、编码检测和大文件分块读取。可指定时间戳列和数值列用于时序数据场景。"
new_name = "CSV/Excel文件加载"
new_examples = json.dumps([
    "data = load_csv('sensor_data.csv')",
    "# 加载时序数据：指定时间列和数值列",
    "data = load_csv('load_data.csv', timestamp_column='timestamp', value_columns=['power', 'temperature'])",
])

db.execute(text(
    "UPDATE algorithm_functions SET name=:name, description=:desc, parameters=:params, examples=:examples WHERE id='load_csv'"
), {"name": new_name, "desc": new_desc, "params": new_params, "examples": new_examples})
print("Updated load_csv")

db.commit()

# Verify
funcs = db.execute(text("SELECT id, name FROM algorithm_functions WHERE category_id='data_source' ORDER BY name")).fetchall()
print(f"\n数据源分类: {len(funcs)} 个函数")
for f in funcs:
    print(f"  - {f[0]}: {f[1]}")

db.close()
print("Done!")
# @AI_GENERATED: end
