# @AI_GENERATED: Kiro v1.0
"""
同步 functions.json 中的参数默认值到数据库
将所有函数的 parameters JSON 字段更新为包含 default 的版本
"""
import os
import sys
import json

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_PATH = "data/users.db"
JSON_PATH = "data/functions.json"

def main():
    # 加载 functions.json
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    functions = data["functions"]
    print(f"从 functions.json 加载了 {len(functions)} 个函数")

    # 连接数据库
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Session = sessionmaker(bind=engine)
    session = Session()

    updated = 0
    skipped = 0

    for func in functions:
        func_id = func["id"]
        new_params = func["parameters"]

        # 查询数据库中的函数
        result = session.execute(
            text("SELECT id, parameters FROM algorithm_functions WHERE id = :fid"),
            {"fid": func_id}
        ).fetchone()

        if result is None:
            print(f"  [跳过] {func_id} - 数据库中不存在")
            skipped += 1
            continue

        # 更新 parameters 字段
        session.execute(
            text("UPDATE algorithm_functions SET parameters = :params, updated_at = CURRENT_TIMESTAMP WHERE id = :fid"),
            {"params": json.dumps(new_params, ensure_ascii=False), "fid": func_id}
        )
        updated += 1
        print(f"  [更新] {func_id} - parameters 已同步")

    session.commit()
    session.close()

    print(f"\n同步完成: 更新 {updated} 个, 跳过 {skipped} 个")

if __name__ == "__main__":
    main()
# @AI_GENERATED: end
