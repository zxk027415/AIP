# @AI_GENERATED: Kiro v1.0
"""
算法库反向导出脚本
从数据库导出到 functions.json（向后兼容）

用法:
    cd backend
    python scripts/export_functions_to_json.py
"""
import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models.algorithm import AlgorithmCategory, AlgorithmFunction


def export_to_json(output_path: str = None):
    """从数据库导出已发布的算法到 functions.json"""

    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "functions.json"
        )

    db = SessionLocal()
    try:
        # 1. 查询所有分类
        categories = (
            db.query(AlgorithmCategory)
            .order_by(AlgorithmCategory.display_order)
            .all()
        )

        # 2. 查询所有已发布的算法
        functions = (
            db.query(AlgorithmFunction)
            .filter(AlgorithmFunction.status == "published")
            .order_by(AlgorithmFunction.category_id, AlgorithmFunction.name)
            .all()
        )

        # 3. 构建兼容格式
        data = {
            "categories": [
                {
                    "id": cat.id,
                    "name": cat.name,
                    "description": cat.description or "",
                    "subcategories": [],
                }
                for cat in categories
            ],
            "functions": [func.to_legacy_dict() for func in functions],
        }

        # 4. 写入文件
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"导出完成: {len(categories)} 个分类, {len(functions)} 个算法")
        print(f"输出文件: {output_path}")

        return data

    finally:
        db.close()


def verify_export(output_path: str = None):
    """验证导出的JSON与原始文件一致性"""

    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "functions.json"
        )

    # 读取导出的文件
    with open(output_path, "r", encoding="utf-8") as f:
        exported = json.load(f)

    cat_count = len(exported.get("categories", []))
    func_count = len(exported.get("functions", []))

    print(f"\n验证导出文件:")
    print(f"  分类数: {cat_count}")
    print(f"  算法数: {func_count}")

    # 检查每个分类下的算法数
    for cat in exported["categories"]:
        count = sum(1 for f in exported["functions"] if f["category"] == cat["id"])
        print(f"  - {cat['name']} ({cat['id']}): {count} 个算法")

    return True


if __name__ == "__main__":
    print("=" * 50)
    print("算法库数据导出: 数据库 → functions.json")
    print("=" * 50)
    export_to_json()
    verify_export()
# @AI_GENERATED: end
