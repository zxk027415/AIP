"""
手动创建数据库
"""
from database import init_db

if __name__ == "__main__":
    print("正在创建数据库...")
    init_db()
    print("数据库创建完成！")
    print("位置：backend/data/users.db")
