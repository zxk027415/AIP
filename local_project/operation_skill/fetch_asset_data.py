"""
数据读取脚本（面向使用方）

直接从数据库 agent_grid_db 读取已入库的数据
  1. fetch_load    : 按 region(+可选 asset_name) + 时间拉取负荷 P/Q 等指标
  2. fetch_weather : 按 asset_name(站点) + 时间拉取气象 WS/TMP（北京时间小时序列）
  3. 辅助：list_load_regions / list_weather_stations / list_assets_in_region

依赖：
  - pip install pymysql pandas
  - 数据库账号：在本文件顶部 DB_CONFIG 填写 user/password，
    或设置环境变量 DB_USER / DB_PASSWORD（推荐，避免密码写进代码）。
  （不需要 kong_sdk / fc-console 账号 / 代理，气象数据已预先入库）

DB说明：
  - 负荷数据按 region 分表存储（load_data_15min_<region>），故拉负荷必须指定 region。
  - 时间参数支持 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS'。
  - 负荷区间为左闭右开 [start, end)；气象区间为按日左闭右闭（含 end 当天 23:00）。
  - 气象 ts 已是北京时间。

直接运行本文件即可看到示例输出（见文件底部 __main__）。
同事使用时：改 __main__ 里的 region / asset / 时间，或在自己脚本里 import 下列函数：
    from DATA.fetch_asset_data import (
        fetch_load, fetch_weather,
        list_load_regions, list_weather_stations, list_assets_in_region,
    )
"""
# %%
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd

try:
    import pymysql
except ImportError as exc:  # pragma: no cover
    raise ImportError("缺少依赖 pymysql，请先执行: pip install pymysql") from exc

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ========== 数据库连接配置（同事改这里）==========
# host / port / 库名是固定的，已写死。只需填入你自己的数据库账号；
# 也可通过环境变量 DB_USER / DB_PASSWORD 覆盖，避免把密码写进脚本。
DB_HOST = "10.230.66.32"
DB_PORT = 3306
DB_NAME = "agent_grid_db"

DB_CONFIG = {
    "host": DB_HOST,
    "port": DB_PORT,
    "db_name": DB_NAME,
    "user": os.environ.get("DB_USER", "admin"),          # <-- 填你的用户名
    "password": os.environ.get("DB_PASSWORD", "admin@123"),  # <-- 填你的密码
}

# ========== 常量 ==========
LOAD_TABLE_PREFIX = "load_data_15min_"
WEATHER_TABLE = "subload_weather_xiongzhou"
LOAD_METRICS = ("p", "q", "volt", "asset_volt", "asset_type", "asset_sub", "asset_sub_volt")
DEFAULT_LOAD_METRICS = ("p", "q")


# ========== DB 连接 ==========
def get_db_conn(user=None, password=None, **overrides):
    """新建数据库连接（DictCursor）。用完请 conn.close()，或用 with 复用"""
    cfg = {**DB_CONFIG, **overrides}
    if user is not None:
        cfg["user"] = user
    if password is not None:
        cfg["password"] = password
    if not cfg["user"] or not cfg["password"]:
        raise ValueError(
            "数据库用户名/密码未设置。请在脚本顶部 DB_CONFIG 填写，"
            "或设置环境变量 DB_USER / DB_PASSWORD，"
            "或调用 get_db_conn(user=..., password=...)。"
        )
    return pymysql.connect(
        host=cfg["host"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["db_name"],
        port=int(cfg.get("port", 3306)),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _quote_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def _norm_start(t: str) -> str:
    """起始时间：纯日期补 00:00:00。"""
    return f"{t} 00:00:00" if len(t.strip()) == 10 else t


def _norm_end_load(t: str) -> str:
    """负荷区间右开：纯日期当天即 [start, end) 不含 end 当天，
    若想含 end 当天请显式传到次日。这里保持与时间字符串一致。"""
    return f"{t} 00:00:00" if len(t.strip()) == 10 else t


def _norm_end_weather_exclusive(t: str) -> str:
    """气象按日左闭右闭：纯日期则取到 end 次日 00:00（即含 end 当天 23:00）。"""
    s = t.strip()
    if len(s) == 10:
        d = datetime.strptime(s, "%Y-%m-%d") + timedelta(days=1)
        return d.strftime("%Y-%m-%d %H:%M:%S")
    return s


# ========== 辅助：枚举 ==========
def list_load_regions(connection=None) -> list[str]:
    """列出所有负荷 region（来自分表名）。"""
    own = connection is None
    conn = connection or get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name AS tn FROM information_schema.tables "
                "WHERE table_schema=%s AND table_name LIKE %s",
                (DB_CONFIG["db_name"], f"{LOAD_TABLE_PREFIX}%"),
            )
            rows = cur.fetchall()
        return sorted(r["tn"][len(LOAD_TABLE_PREFIX):] for r in rows)
    finally:
        if own:
            conn.close()


def list_assets_in_region(region, asset_group="load", connection=None) -> pd.DataFrame:
    """列出某 region 下的 asset_name / asset_id。"""
    table = f"{LOAD_TABLE_PREFIX}{region}"
    own = connection is None
    conn = connection or get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT asset_name, asset_id FROM {_quote_ident(table)} "
                "WHERE asset_group=%s ORDER BY asset_name",
                (asset_group,),
            )
            rows = cur.fetchall()
        return pd.DataFrame(rows, columns=["asset_name", "asset_id"]) if rows \
            else pd.DataFrame(columns=["asset_name", "asset_id"])
    finally:
        if own:
            conn.close()


def list_weather_stations(connection=None) -> list[str]:
    """列出气象表里有数据的站点名。"""
    own = connection is None
    conn = connection or get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT station_name FROM {_quote_ident(WEATHER_TABLE)} "
                "ORDER BY station_name"
            )
            rows = cur.fetchall()
        return [r["station_name"] for r in rows]
    finally:
        if own:
            conn.close()


# ========== 1. 负荷 ==========
def fetch_load(
    region,
    start_time,
    end_time,
    *,
    asset_name=None,
    asset_group="load",
    metrics=None,
    connection=None,
) -> pd.DataFrame:
    """按 region + 时间拉取负荷数据（必须指定 region）。

    region     : 区域名，对应表 load_data_15min_<region>（必填）
    start_time : 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS'，含
    end_time   : 同上，不含（左闭右开）。要含某天请传到次日。
    asset_name : 可选，精确过滤单个资产；不传则返回该 region 全部 asset
    asset_group: 默认 'load'
    metrics    : 可选，默认 ['p','q']；可选 p/q/volt/...，传 'all' 取全部
    返回 DataFrame: record_time, asset_id, asset_name, asset_group, <metrics...>
    """
    if not region:
        raise ValueError("拉取负荷必须指定 region（对应 load_data_15min_<region> 分表）")

    if metrics is None:
        sel_metrics = list(DEFAULT_LOAD_METRICS)
    elif metrics == "all":
        sel_metrics = list(LOAD_METRICS)
    elif isinstance(metrics, str):
        sel_metrics = [metrics]
    else:
        sel_metrics = list(metrics)
    bad = [m for m in sel_metrics if m not in LOAD_METRICS]
    if bad:
        raise ValueError(f"非法指标 {bad}，可选: {list(LOAD_METRICS)}")

    table = f"{LOAD_TABLE_PREFIX}{region}"
    base_cols = ["record_time", "asset_id", "asset_name", "asset_group"]
    sel_sql = ", ".join(_quote_ident(c) for c in base_cols + sel_metrics)

    where = [
        f"{_quote_ident('record_time')} >= %s",
        f"{_quote_ident('record_time')} < %s",
        f"{_quote_ident('asset_group')} = %s",
    ]
    params = [_norm_start(str(start_time)), _norm_end_load(str(end_time)), asset_group]
    if asset_name:
        where.append(f"{_quote_ident('asset_name')} = %s")
        params.append(asset_name)

    sql = (
        f"SELECT {sel_sql} FROM {_quote_ident(table)} "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY {_quote_ident('record_time')}, {_quote_ident('asset_id')}"
    )

    own = connection is None
    conn = connection or get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        cols = base_cols + sel_metrics
        return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
    finally:
        if own:
            conn.close()


# ========== 2. 气象 ==========
def fetch_weather(
    asset_name,
    start_time,
    end_time,
    *,
    nwp=None,
    connection=None,
) -> pd.DataFrame:
    """按站点名 + 时间从 DB 拉取气象 WS/TMP（北京时间小时序列）。

    asset_name : 站点名（= 负荷 asset_name），气象表 station_name
    start_time : 'YYYY-MM-DD' 或带时分秒，含
    end_time   : 'YYYY-MM-DD' 按日含 end 当天(到 23:00)；带时分秒则右开
    nwp        : 可选，气象源过滤（如 'ENS_AVG'）；不传则返回全部源
    返回 DataFrame: station_name, lon, lat, nwp, ts(北京时间), ws, tmp
    """
    where = [
        f"{_quote_ident('station_name')} = %s",
        f"{_quote_ident('ts')} >= %s",
        f"{_quote_ident('ts')} < %s",
    ]
    params = [
        asset_name,
        _norm_start(str(start_time)),
        _norm_end_weather_exclusive(str(end_time)),
    ]
    if nwp:
        where.append(f"{_quote_ident('nwp')} = %s")
        params.append(nwp)

    cols = ["station_name", "lon", "lat", "nwp", "ts", "ws", "tmp"]
    sql = (
        f"SELECT {', '.join(_quote_ident(c) for c in cols)} "
        f"FROM {_quote_ident(WEATHER_TABLE)} "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY {_quote_ident('nwp')}, {_quote_ident('ts')}"
    )

    own = connection is None
    conn = connection or get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
    finally:
        if own:
            conn.close()


# %%========== 直接运行示例 ==========
# 按需修改下面的参数，然后 `python DATA/fetch_asset_data.py` 即可。
if __name__ == "__main__":
    # ---- 0) 先看有哪些可用的 region 和气象站点 ----
    print("可用负荷 region:")
    print("  " + ", ".join(list_load_regions()))
    print("\n气象站点:")
    print("  " + ", ".join(list_weather_stations()))

    # ---- 1) 拉负荷（必须指定 region） ----
    REGION = "雄州"
    ASSET = "南华变.10kV叶家线085"
    START = "2026-02-01"
    END = "2026-05-28"

    df_load = fetch_load(
        REGION, START, END,
        asset_name=ASSET,      # 不传则返回该 region 下全部资产
        metrics=["p", "q"],    # 或 "all" 取全部指标
    )
    print(f"\n[负荷] region={REGION} asset={ASSET} -> {len(df_load)} 行")
    print(df_load.head(10).to_string(index=False))

    # ---- 2) 拉气象（按站点名，时间为北京时间） ----
    df_wx = fetch_weather(ASSET, START, END, nwp="ENS_AVG")
    print(f"\n[气象] 站点={ASSET} -> {len(df_wx)} 行")
    if not df_wx.empty:
        print(f"区间: {df_wx['ts'].min()} ~ {df_wx['ts'].max()}")
    print(df_wx.head(10).to_string(index=False))

    # ---- 3) 其他可用辅助 ----
    # df_assets = list_assets_in_region("雄州")    # 列出某 region 下全部 asset
    # df_load_all = fetch_load("雄州", START, END)  # 不指定 asset，拉该 region 全部
