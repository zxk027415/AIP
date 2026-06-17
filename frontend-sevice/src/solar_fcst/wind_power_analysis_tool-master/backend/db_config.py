"""
数据库配置模块
"""

# 数据库连接配置
DB_CONFIG = {
    'host': '10.230.66.32',
    'user': 'admin',
    'password': 'admin@123',
    'database': 'agent_power_db',
    'charset': 'utf8mb4',
    'port': 3306
}

# 表名配置
TABLE_NAMES = {
    'farm_info': 'farm_info',  # 场站信息表
    'actual_data': 'actual_data'  # 真实数据表
}
