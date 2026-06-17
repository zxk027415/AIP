# @AI_GENERATED: Kiro v1.0
"""
更新算法分类：新增数据预处理分类，迁移预处理函数，新增数据接入模块
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import SessionLocal, engine
from sqlalchemy import text
import json

db = SessionLocal()

# 1. Update data_source description
db.execute(text("UPDATE algorithm_categories SET description='数据接入、采集和加载' WHERE id='data_source'"))
print("Updated data_source description")

# 2. Add new data_preprocessing category
try:
    db.execute(text(
        "INSERT INTO algorithm_categories (id, name, description, display_order, created_at, updated_at) "
        "VALUES ('data_preprocessing', '数据预处理', '数据清洗、异常检测、缺失值处理和重采样', 2, datetime('now'), datetime('now'))"
    ))
    print("Added data_preprocessing category")
except Exception as e:
    print(f"Category may already exist: {e}")

# 3. Update display_order
orders = [
    ("data_source", 1),
    ("data_preprocessing", 2),
    ("feature_engineering", 3),
    ("algorithm_model", 4),
    ("evaluation_metrics", 5),
]
for cat_id, order in orders:
    db.execute(text(f"UPDATE algorithm_categories SET display_order={order} WHERE id='{cat_id}'"))
print("Updated display_order")

# 4. Move 3 preprocessing functions
for fid in ["detect_outliers", "resample_timeseries", "handle_missing"]:
    db.execute(text(f"UPDATE algorithm_functions SET category_id='data_preprocessing' WHERE id='{fid}'"))
print("Moved 3 functions to data_preprocessing")

# 5. Add new data source functions
new_functions = [
    {
        "id": "load_csv",
        "name": "CSV文件加载",
        "category_id": "data_source",
        "description": "从CSV/Excel文件加载数据，支持自动类型推断、编码检测和大文件分块读取。",
        "parameters": json.dumps([
            {"name": "file_path", "type": "STRING", "required": True, "description": "文件路径或上传文件ID"},
            {"name": "delimiter", "type": "STRING", "required": False, "description": "分隔符，默认逗号"},
            {"name": "encoding", "type": "STRING", "required": False, "description": "文件编码：utf-8/gbk/gb2312"},
            {"name": "header_row", "type": "NUMBER", "required": False, "description": "表头行号，默认0"}
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["data = load_csv('sensor_data.csv', ',', 'utf-8')"]),
        "status": "published",
    },
    {
        "id": "load_database",
        "name": "数据库连接",
        "category_id": "data_source",
        "description": "连接关系型数据库执行SQL查询，支持MySQL、PostgreSQL、SQLite等。",
        "parameters": json.dumps([
            {"name": "db_type", "type": "STRING", "required": True, "description": "数据库类型：mysql/postgresql/sqlite"},
            {"name": "connection_string", "type": "STRING", "required": True, "description": "数据库连接字符串"},
            {"name": "query", "type": "STRING", "required": True, "description": "SQL查询语句"}
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["data = load_database('mysql', 'mysql://user:pass@host/db', 'SELECT * FROM sensor_data')"]),
        "status": "published",
    },
    {
        "id": "load_api",
        "name": "REST API数据接入",
        "category_id": "data_source",
        "description": "通过REST API接口获取外部系统数据，支持GET/POST请求和多种认证方式。",
        "parameters": json.dumps([
            {"name": "url", "type": "STRING", "required": True, "description": "API请求地址"},
            {"name": "method", "type": "STRING", "required": False, "description": "请求方法：GET/POST"},
            {"name": "headers", "type": "STRING", "required": False, "description": "请求头JSON字符串"},
            {"name": "params", "type": "STRING", "required": False, "description": "请求参数JSON字符串"}
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["data = load_api('https://scada.example.com/api/data', 'GET')"]),
        "status": "published",
    },
    {
        "id": "load_timeseries_db",
        "name": "时序数据库接入",
        "category_id": "data_source",
        "description": "连接时序数据库查询历史数据，支持InfluxDB、TDengine、TimescaleDB等。",
        "parameters": json.dumps([
            {"name": "db_type", "type": "STRING", "required": True, "description": "时序数据库类型：influxdb/tdengine/timescaledb"},
            {"name": "connection_string", "type": "STRING", "required": True, "description": "数据库连接字符串"},
            {"name": "query", "type": "STRING", "required": True, "description": "查询语句"},
            {"name": "start_time", "type": "STRING", "required": False, "description": "查询起始时间"},
            {"name": "end_time", "type": "STRING", "required": False, "description": "查询结束时间"}
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["data = load_timeseries_db('influxdb', 'http://localhost:8086', 'SELECT * FROM temperature')"]),
        "status": "published",
    },
    {
        "id": "load_mqtt",
        "name": "MQTT实时数据订阅",
        "category_id": "data_source",
        "description": "订阅MQTT主题获取IoT传感器实时数据流，适用于工业物联网场景。",
        "parameters": json.dumps([
            {"name": "broker", "type": "STRING", "required": True, "description": "MQTT Broker地址"},
            {"name": "topic", "type": "STRING", "required": True, "description": "订阅主题"},
            {"name": "duration_seconds", "type": "NUMBER", "required": False, "description": "采集持续时间（秒）"},
            {"name": "username", "type": "STRING", "required": False, "description": "认证用户名"},
            {"name": "password", "type": "STRING", "required": False, "description": "认证密码"}
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["data = load_mqtt('mqtt://broker:1883', 'factory/sensor/#', 60)"]),
        "status": "published",
    },
    {
        "id": "load_opcua",
        "name": "OPC UA数据读取",
        "category_id": "data_source",
        "description": "通过OPC UA协议读取工业设备数据，适用于PLC、DCS等工控系统。",
        "parameters": json.dumps([
            {"name": "server_url", "type": "STRING", "required": True, "description": "OPC UA服务器地址"},
            {"name": "node_ids", "type": "ARRAY", "required": True, "description": "节点ID列表"},
            {"name": "mode", "type": "STRING", "required": False, "description": "读取模式：realtime/history"},
            {"name": "start_time", "type": "STRING", "required": False, "description": "历史模式起始时间"},
            {"name": "end_time", "type": "STRING", "required": False, "description": "历史模式结束时间"}
        ]),
        "return_type": "MATRIX",
        "examples": json.dumps(["data = load_opcua('opc.tcp://plc:4840', ['ns=2;s=Temperature'])"]),
        "status": "published",
    },
    {
        "id": "load_modbus",
        "name": "Modbus设备数据读取",
        "category_id": "data_source",
        "description": "通过Modbus TCP/RTU协议读取工业设备寄存器数据，适用于传感器、仪表、变频器等。",
        "parameters": json.dumps([
            {"name": "host", "type": "STRING", "required": True, "description": "设备地址"},
            {"name": "protocol", "type": "STRING", "required": True, "description": "协议类型：tcp/rtu"},
            {"name": "slave_id", "type": "NUMBER", "required": True, "description": "从站地址"},
            {"name": "register_address", "type": "NUMBER", "required": True, "description": "起始寄存器地址"},
            {"name": "register_count", "type": "NUMBER", "required": True, "description": "读取寄存器数量"},
            {"name": "register_type", "type": "STRING", "required": False, "description": "寄存器类型：holding/input/coil/discrete"}
        ]),
        "return_type": "ARRAY",
        "examples": json.dumps(["data = load_modbus('192.168.1.100', 'tcp', 1, 0, 10)"]),
        "status": "published",
    },
]

for func in new_functions:
    # Check if already exists
    exists = db.execute(text(f"SELECT COUNT(*) FROM algorithm_functions WHERE id='{func['id']}'")).scalar()
    if exists > 0:
        print(f"  Skipped {func['id']} (already exists)")
        continue

    db.execute(text(
        "INSERT INTO algorithm_functions (id, name, category_id, description, parameters, return_type, examples, status, version, created_at, updated_at) "
        "VALUES (:id, :name, :category_id, :description, :parameters, :return_type, :examples, :status, 1, datetime('now'), datetime('now'))"
    ), {
        "id": func["id"],
        "name": func["name"],
        "category_id": func["category_id"],
        "description": func["description"],
        "parameters": func["parameters"],
        "return_type": func["return_type"],
        "examples": func["examples"],
        "status": func["status"],
    })

    # Add version record
    db.execute(text(
        "INSERT INTO algorithm_versions (function_id, version, data_snapshot, change_description, created_at) "
        "VALUES (:fid, 1, :snapshot, '初始版本', datetime('now'))"
    ), {"fid": func["id"], "snapshot": json.dumps(func)})

    print(f"  Added {func['id']}: {func['name']}")

db.commit()

# Final verification
print("\n=== 最终结果 ===")
cats = db.execute(text("SELECT id, name, display_order FROM algorithm_categories ORDER BY display_order")).fetchall()
for c in cats:
    count = db.execute(text(f"SELECT COUNT(*) FROM algorithm_functions WHERE category_id='{c[0]}'")).scalar()
    funcs = db.execute(text(f"SELECT id, name FROM algorithm_functions WHERE category_id='{c[0]}' ORDER BY name")).fetchall()
    print(f"\n{c[2]}. {c[1]} ({c[0]}): {count} 个函数")
    for f in funcs:
        print(f"   - {f[0]}: {f[1]}")

db.close()
print("\nDone!")
# @AI_GENERATED: end
