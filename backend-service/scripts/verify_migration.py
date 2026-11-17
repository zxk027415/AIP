# @AI_GENERATED: Kiro v1.0
"""验证迁移结果：数据库数据与 functions.json 一致性检查"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models.algorithm import AlgorithmCategory, AlgorithmFunction, AlgorithmVersion

def verify():
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "functions.json"
    )
    with open(json_path, "r", encoding="utf-8") as f:
        exported = json.load(f)

    db = SessionLocal()
    try:
        # 数据库计数
        db_cats = db.query(AlgorithmCategory).count()
        db_funcs = db.query(AlgorithmFunction).count()
        db_vers = db.query(AlgorithmVersion).count()

        json_cats = len(exported["categories"])
        json_funcs = len(exported["functions"])

        print(f"数据库: {db_cats} 分类, {db_funcs} 算法, {db_vers} 版本记录")
        print(f"JSON:   {json_cats} 分类, {json_funcs} 算法")

        # 一致性检查
        assert db_cats == json_cats, f"分类数不一致: DB={db_cats}, JSON={json_cats}"
        assert db_funcs == json_funcs, f"算法数不一致: DB={db_funcs}, JSON={json_funcs}"
        assert db_vers == db_funcs, f"版本记录数应等于算法数: {db_vers} != {db_funcs}"

        # 检查每个算法的字段完整性
        for func in exported["functions"]:
            for field in ["id", "name", "category", "parameters", "return_type"]:
                assert field in func, f"算法 {func.get('id', '?')} 缺少字段: {field}"

        # 检查数据库中每个算法都有对应的版本记录
        funcs = db.query(AlgorithmFunction).all()
        for f in funcs:
            ver = db.query(AlgorithmVersion).filter_by(function_id=f.id).first()
            assert ver is not None, f"算法 {f.id} 缺少版本记录"

        print("\n所有验证通过!")
        return True
    finally:
        db.close()

if __name__ == "__main__":
    verify()
# @AI_GENERATED: end
