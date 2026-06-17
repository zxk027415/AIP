# @AI_GENERATED
"""
load_database operator backend — Connects to a database and executes a SQL query.

Supports mysql, postgresql, and sqlite via sqlalchemy or sqlite3.
Closes connection on error. Sorts by timestamp column if detected.
"""
import sqlite3

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "load_database"


def _detect_timestamp_column(df: pd.DataFrame) -> str | None:
    """Try to detect a timestamp column by name or dtype."""
    common_names = [
        "record_time", "timestamp", "time", "datetime", "date",
        "created_at", "updated_at",
    ]
    for col in df.columns:
        if col.lower() in common_names:
            return col
    # Check for datetime dtypes
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
    return None


def execute(params: dict, inputs: dict) -> dict:
    """
    Connect to a database, execute a SQL query, and return a DataFrame.

    Args:
        params: Operator parameters including:
            - db_type (str, required): "mysql", "postgresql", or "sqlite"
            - connection_string (str, required): Database connection string
              For sqlite, this is the file path.
              For mysql/postgresql, a SQLAlchemy connection URL.
            - query (str, required): SQL query to execute
        inputs: Not used for data source operators.

    Returns:
        {"data": DataFrame}
    """
    db_type = params.get("db_type", "").lower()
    connection_string = params.get("connection_string", "")
    query = params.get("query", "")

    if not db_type:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "db_type parameter is required"
        )
    if not connection_string:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "connection_string parameter is required"
        )
    if not query:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "query parameter is required"
        )
    if db_type not in ("mysql", "postgresql", "sqlite"):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Unsupported db_type: {db_type}. Must be mysql, postgresql, or sqlite",
        )

    conn = None
    try:
        if db_type == "sqlite":
            conn = sqlite3.connect(connection_string)
            df = pd.read_sql_query(query, conn)
        else:
            # mysql / postgresql via sqlalchemy
            import sqlalchemy

            engine = sqlalchemy.create_engine(connection_string)
            with engine.connect() as sa_conn:
                df = pd.read_sql_query(query, sa_conn)
    except Exception as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "DatabaseError", f"Database query failed: {e}"
        )
    finally:
        if conn is not None:
            conn.close()

    # Sort by timestamp column if detected
    ts_col = _detect_timestamp_column(df)
    if ts_col:
        try:
            df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
            df = df.sort_values(by=ts_col).reset_index(drop=True)
        except Exception:
            pass  # best-effort sorting

    logger.info(
        f"[load_database] Queried {len(df)} rows, {len(df.columns)} columns "
        f"from {db_type} database"
    )
    return {"data": df}
# @AI_GENERATED: end
