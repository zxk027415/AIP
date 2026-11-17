# @AI_GENERATED
"""
load_mongodb operator backend — MongoDB 文档集合读取。

依赖 pymongo 包。返回集合内文档为 DataFrame（自动展平顶层字段）。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "load_mongodb"


def execute(params: dict, inputs: dict) -> dict:
    """
    从 MongoDB 读取集合。

    params:
        - connection_string (str, 必填): mongodb:// URI
        - database (str, 必填): 数据库名
        - collection (str, 必填): 集合名
        - query (dict | None): 查询过滤条件，默认全部
        - projection (dict | None): 字段投影
        - limit (int, default 0): 结果数上限，0=不限
    inputs: 无
    returns: {"data": pd.DataFrame}
    """
    try:
        from pymongo import MongoClient
    except ImportError:
        raise OperatorExecutionError(
            OPERATOR_ID, "DependencyError",
            "pymongo package not installed. Install: pip install pymongo"
        )

    conn_str = params.get("connection_string")
    database = params.get("database")
    collection = params.get("collection")

    if not conn_str:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "'connection_string' is required")
    if not database:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "'database' is required")
    if not collection:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "'collection' is required")

    query = params.get("query") or {}
    projection = params.get("projection")
    try:
        limit = int(params.get("limit") or 0)
    except (TypeError, ValueError):
        limit = 0

    try:
        client = MongoClient(conn_str, serverSelectionTimeoutMS=5000)
        col = client[database][collection]
        cursor = col.find(query, projection)
        if limit > 0:
            cursor = cursor.limit(limit)
        docs = list(cursor)
    except Exception as e:
        raise OperatorExecutionError(OPERATOR_ID, "ConnectionError", f"MongoDB read failed: {e}")
    finally:
        try:
            client.close()
        except Exception:
            pass

    if not docs:
        logger.info(f"[{OPERATOR_ID}] Empty result from {database}.{collection}")
        return {"data": pd.DataFrame()}

    df = pd.json_normalize(docs)
    # ObjectId 转 string 避免下游序列化问题
    if "_id" in df.columns:
        df["_id"] = df["_id"].astype(str)

    logger.info(f"[{OPERATOR_ID}] Loaded {len(df)} docs from {database}.{collection}")
    return {"data": df}
# @AI_GENERATED: end
