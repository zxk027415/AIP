# @AI_GENERATED: Kiro v1.0
"""
算法库管理系统 - 测试 API
提供数据库表结构验证、数据查询、一致性检查等测试端点
"""
from fastapi import APIRouter
from database import SessionLocal, engine
from sqlalchemy import inspect, text
import json
import os
import time
import traceback

router = APIRouter(prefix="/api/algorithm-test", tags=["algorithm-test"])


def _run_test(test_fn):
    """通用测试执行包装器"""
    start = time.time()
    try:
        result = test_fn()
        return {
            "success": True,
            "duration": round(time.time() - start, 4),
            **result
        }
    except Exception as e:
        return {
            "success": False,
            "duration": round(time.time() - start, 4),
            "error": str(e),
            "detail": traceback.format_exc()
        }


@router.get("/tables", summary="场景1: 数据库表结构验证")
async def test_tables():
    """检查4个算法库相关表是否存在，并验证字段结构"""
    def run():
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        required = [
            "algorithm_categories",
            "algorithm_functions",
            "algorithm_versions",
            "algorithm_audit_logs"
        ]
        results = []
        for table in required:
            exists = table in existing_tables
            columns = []
            if exists:
                columns = [
                    {"name": c["name"], "type": str(c["type"])}
                    for c in inspector.get_columns(table)
                ]
            results.append({
                "table": table,
                "exists": exists,
                "column_count": len(columns),
                "columns": columns
            })
        all_exist = all(r["exists"] for r in results)
        return {
            "message": "所有表均存在" if all_exist else "部分表缺失",
            "data": results,
            "all_passed": all_exist
        }
    return _run_test(run)


@router.get("/categories", summary="场景2: 分类数据查询")
async def test_categories():
    """查询 algorithm_categories 表，验证分类数据完整性"""
    def run():
        db = SessionLocal()
        try:
            rows = db.execute(text("SELECT * FROM algorithm_categories ORDER BY display_order")).fetchall()
            categories = [dict(r._mapping) for r in rows]
            return {
                "message": f"共查询到 {len(categories)} 个分类",
                "data": categories,
                "all_passed": len(categories) > 0
            }
        finally:
            db.close()
    return _run_test(run)


@router.get("/functions", summary="场景3: 算法数据查询")
async def test_functions():
    """查询 algorithm_functions 表，验证算法数据完整性"""
    def run():
        db = SessionLocal()
        try:
            rows = db.execute(text(
                "SELECT f.id, f.name, f.category_id, f.description, f.status, f.version, "
                "c.name as category_name "
                "FROM algorithm_functions f "
                "LEFT JOIN algorithm_categories c ON f.category_id = c.id "
                "ORDER BY f.category_id, f.name"
            )).fetchall()
            functions = [dict(r._mapping) for r in rows]
            # 按分类分组统计
            category_stats = {}
            for f in functions:
                cat = f.get("category_name", "未知")
                category_stats[cat] = category_stats.get(cat, 0) + 1
            return {
                "message": f"共查询到 {len(functions)} 个算法函数",
                "data": functions,
                "category_stats": category_stats,
                "all_passed": len(functions) > 0
            }
        finally:
            db.close()
    return _run_test(run)


@router.get("/versions", summary="场景4: 版本记录验证")
async def test_versions():
    """查询 algorithm_versions 表，验证版本记录"""
    def run():
        db = SessionLocal()
        try:
            rows = db.execute(text(
                "SELECT v.id, v.function_id, v.version, v.change_description, v.created_at, "
                "f.name as function_name "
                "FROM algorithm_versions v "
                "LEFT JOIN algorithm_functions f ON v.function_id = f.id "
                "ORDER BY v.function_id, v.version"
            )).fetchall()
            versions = [dict(r._mapping) for r in rows]
            # 统计每个函数的版本数
            func_version_count = {}
            for v in versions:
                fid = v.get("function_id", "")
                func_version_count[fid] = func_version_count.get(fid, 0) + 1
            return {
                "message": f"共查询到 {len(versions)} 条版本记录",
                "data": versions,
                "function_version_stats": func_version_count,
                "all_passed": len(versions) > 0
            }
        finally:
            db.close()
    return _run_test(run)


@router.get("/consistency", summary="场景5: 数据一致性检查")
async def test_consistency():
    """对比数据库数据与 functions.json 文件的一致性"""
    def run():
        # 读取 JSON 文件
        json_path = os.path.join(os.path.dirname(__file__), "..", "data", "functions.json")
        json_path = os.path.abspath(json_path)
        if not os.path.exists(json_path):
            return {
                "message": "functions.json 文件不存在",
                "all_passed": False,
                "data": {"json_path": json_path}
            }
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        json_categories = json_data.get("categories", [])
        json_functions = json_data.get("functions", [])
        json_cat_ids = {c["id"] for c in json_categories}
        json_func_ids = {fn["id"] for fn in json_functions}

        # 查询数据库
        db = SessionLocal()
        try:
            db_cats = db.execute(text("SELECT id FROM algorithm_categories")).fetchall()
            db_funcs = db.execute(text("SELECT id FROM algorithm_functions")).fetchall()
            db_cat_ids = {r[0] for r in db_cats}
            db_func_ids = {r[0] for r in db_funcs}

            missing_cats = json_cat_ids - db_cat_ids
            extra_cats = db_cat_ids - json_cat_ids
            missing_funcs = json_func_ids - db_func_ids
            extra_funcs = db_func_ids - json_func_ids
            all_passed = not missing_cats and not missing_funcs

            return {
                "message": "数据完全一致" if all_passed else "存在数据差异",
                "all_passed": all_passed,
                "data": {
                    "json_categories": len(json_cat_ids),
                    "db_categories": len(db_cat_ids),
                    "json_functions": len(json_func_ids),
                    "db_functions": len(db_func_ids),
                    "missing_categories_in_db": list(missing_cats),
                    "extra_categories_in_db": list(extra_cats),
                    "missing_functions_in_db": list(missing_funcs),
                    "extra_functions_in_db": list(extra_funcs),
                }
            }
        finally:
            db.close()
    return _run_test(run)


@router.get("/audit-logs", summary="场景6: 审计日志表验证")
async def test_audit_logs():
    """检查 algorithm_audit_logs 表结构和数据"""
    def run():
        db = SessionLocal()
        try:
            # 检查表是否存在并查询数据
            rows = db.execute(text(
                "SELECT id, action, object_type, object_id, created_at "
                "FROM algorithm_audit_logs ORDER BY created_at DESC LIMIT 50"
            )).fetchall()
            logs = [dict(r._mapping) for r in rows]
            # 按 action 统计
            action_stats = {}
            for log in logs:
                a = log.get("action", "unknown")
                action_stats[a] = action_stats.get(a, 0) + 1
            return {
                "message": f"审计日志表正常，共 {len(logs)} 条记录",
                "data": logs,
                "action_stats": action_stats,
                "all_passed": True  # 表存在即通过，日志可以为空
            }
        finally:
            db.close()
    return _run_test(run)


@router.get("/run-all", summary="一键运行所有测试")
async def run_all_tests():
    """依次运行所有6个测试场景"""
    results = {
        "tables": await test_tables(),
        "categories": await test_categories(),
        "functions": await test_functions(),
        "versions": await test_versions(),
        "consistency": await test_consistency(),
        "audit_logs": await test_audit_logs(),
    }
    total = len(results)
    passed = sum(1 for r in results.values() if r.get("success") and r.get("all_passed"))
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "all_passed": passed == total,
        "results": results
    }
# @AI_GENERATED: end
