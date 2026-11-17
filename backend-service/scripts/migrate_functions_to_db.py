# @AI_GENERATED: Kiro v1.0
"""
算法库数据迁移脚本
从 functions.json 导入数据到数据库

用法:
    cd backend
    python scripts/migrate_functions_to_db.py
"""
import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, init_db
from models.algorithm import (
    AlgorithmCategory, AlgorithmFunction, AlgorithmVersion
)


def migrate():
    """从 functions.json 迁移数据到数据库"""

    # 1. 初始化数据库（创建新表）
    print("正在初始化数据库表...")
    init_db()

    # 2. 读取 functions.json
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "functions.json"
    )
    if not os.path.exists(json_path):
        print(f"错误: 文件不存在 {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    db = SessionLocal()
    try:
        categories = data.get("categories", [])
        functions = data.get("functions", [])

        # 3. 迁移分类
        cat_count = 0
        for idx, cat in enumerate(categories):
            existing = db.query(AlgorithmCategory).filter_by(id=cat["id"]).first()
            if existing:
                print(f"  跳过已存在的分类: {cat['id']}")
                continue

            db_cat = AlgorithmCategory(
                id=cat["id"],
                name=cat["name"],
                description=cat.get("description", ""),
                parent_id=None,
                icon=None,
                display_order=idx + 1,
            )
            db.add(db_cat)
            cat_count += 1

        db.flush()
        print(f"迁移分类: {cat_count} 个新增, {len(categories) - cat_count} 个已存在")

        # 4. 迁移算法函数
        func_count = 0
        for func in functions:
            existing = db.query(AlgorithmFunction).filter_by(id=func["id"]).first()
            if existing:
                print(f"  跳过已存在的算法: {func['id']}")
                continue

            db_func = AlgorithmFunction(
                id=func["id"],
                name=func["name"],
                category_id=func["category"],
                description=func["description"],
                parameters=func["parameters"],
                return_type=func["return_type"],
                examples=func.get("examples", []),
                tags=[],
                status="published",
                version=1,
            )
            db.add(db_func)
            db.flush()

            # 5. 创建初始版本记录
            snapshot = {
                "id": func["id"],
                "name": func["name"],
                "category": func["category"],
                "description": func["description"],
                "parameters": func["parameters"],
                "return_type": func["return_type"],
                "examples": func.get("examples", []),
            }
            db_version = AlgorithmVersion(
                function_id=func["id"],
                version=1,
                data_snapshot=snapshot,
                change_description="初始版本（从 functions.json 迁移）",
            )
            db.add(db_version)
            func_count += 1

        db.commit()
        print(f"迁移算法: {func_count} 个新增, {len(functions) - func_count} 个已存在")
        print(f"\n迁移完成! 共 {cat_count} 个分类, {func_count} 个算法")

    except Exception as e:
        db.rollback()
        print(f"迁移失败: {e}")
        raise
    finally:
        db.close()


def verify():
    """验证迁移结果"""
    db = SessionLocal()
    try:
        cat_count = db.query(AlgorithmCategory).count()
        func_count = db.query(AlgorithmFunction).count()
        ver_count = db.query(AlgorithmVersion).count()

        print(f"\n验证结果:")
        print(f"  分类数: {cat_count}")
        print(f"  算法数: {func_count}")
        print(f"  版本记录数: {ver_count}")

        # 检查每个分类下的算法数
        categories = db.query(AlgorithmCategory).order_by(AlgorithmCategory.display_order).all()
        for cat in categories:
            count = db.query(AlgorithmFunction).filter_by(category_id=cat.id).count()
            print(f"  - {cat.name} ({cat.id}): {count} 个算法")

    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("算法库数据迁移: functions.json → 数据库")
    print("=" * 50)
    migrate()
    verify()
# @AI_GENERATED: end
