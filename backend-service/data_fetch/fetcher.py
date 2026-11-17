# -*- coding: utf-8 -*-
# @Time : 2022/3/27 13:38
# @Author : mingyang.zong
# @File : fetcher.py (refactored from db_data_fetch.py)
import copy
import os
import traceback

import pytz
import pymysql
import warnings
import pandas as pd
import chinese_calendar
# from workalendar.usa import core
from loguru import logger
from datetime import datetime

# from eapdataset import Dataset

warnings.filterwarnings(action="ignore")

'''
config information:
{
      "task_id": "666"                                   # str, 预测任务id
      "task_type": "D",                                  # str, 预测任务类型
      "datasource_name": "ai-suite-load-4-beta",         # mysql_source, 数据源名
      "dataset_name": "ai-suite-load-4-beta",     # str, 数据集名
      "table_name": "sgmm_hbuilding_load_quarter3",      # str, 历史真值数据所在表
      "parent_field": "parent_id",                       # str, 父节点字段标识
      "child_field": "child_id",                         # str, 子节点字段标识
      "time_field": "record_time",                       # str, 时间戳字段标识
      "load_field": "load",                              # str, 负荷（预测目标）字段标识
      "forecast_horizon": 2,                             # number, 日内单位为小时，其它为天
      "forecast_start_time": "00:15",                    # str, 预测时间戳开始时刻
      "time_granularity": "15min",                       # str, 5min/15min/30min/1H/1D, 不低于原始颗粒度
      "id_lists": []                                     # list, 所有的parent_id、child_id对
      "is_training": "true"                              # str, "true"/"false"
      "time_zone": "Asia/Shanghai"                       # str, 时区信息
      "nowtime": "false"                                 # str, "false"/"2022-04-01 00:00:00"
      "specify_model": "auto"                            # str, "auto"/"xgb"/"nbeats"/...
      "separate_modeling": "true"                        # str, "true"/"false"
      "operate_status": "offline"                        # str, "online"/"offline"/"trigger"
      "other_cols": []                                   # list, 其它列输入

}
'''


def remove_special_data(data, time_field="record_time"):
    """
    data: dataframe格式,时间列名为timestamp,负荷列名load
    """
    import chinese_calendar
    logger.info(f"get chinese calendar...")
    copy_df = data.set_index(time_field)
    copy_df.index = pd.to_datetime(copy_df.index)
    # 获得数据中所有天（按先后顺序完成排序）
    all_ds = list(sorted(set([pd.to_datetime(t).strftime('%Y-%m-%d') for t in copy_df.index])))
    tmp_df = pd.DataFrame()
    for d in all_ds:  # 根据剔除规则逐天进行判断
        use_d = pd.to_datetime(d)
        on_holiday, holiday_name = chinese_calendar.get_holiday_detail(use_d)
        if on_holiday and holiday_name in ['Spring Festival']:  # 剔除春节假期数据
            continue
        else:
            tmp_df = pd.concat([tmp_df, copy_df.loc[d]], axis=0)
    return_df = tmp_df.reset_index()
    # return_df = return_df[[load_field, time_field]]
    logger.info(f"已剔除春节假期数据...")
    return return_df


def festival_judge(tmp_t):
    import chinese_calendar
    on_holiday, holiday_name = chinese_calendar.get_holiday_detail(pd.to_datetime(tmp_t))
    if on_holiday and holiday_name in ['Spring Festival']:  # 判断春节假期
        return True
    else:
        return False


# ---------------------------------------------------------------------------
# Shared helper functions
# ---------------------------------------------------------------------------

def _pivot_and_extract(raw_df, time_field, load_field, other_cols):
    """
    Pivot a long-format DataFrame (with feature_name / value columns) into
    wide format, extracting the load_field column and any additional columns
    listed in other_cols.

    Parameters
    ----------
    raw_df : pd.DataFrame
        Raw data containing at least the columns [time_field, 'feature_name', 'value'].
    time_field : str
        Name of the timestamp column.
    load_field : str
        Name of the load (target) feature inside the 'feature_name' column.
    other_cols : list[str] | None
        Additional feature_name values to extract as separate columns.

    Returns
    -------
    pd.DataFrame
        Wide-format DataFrame with columns [time_field, load_field, ...other_cols].
    """
    raw_df[time_field] = pd.to_datetime(raw_df[time_field])

    # Extract the load column
    init_df = raw_df[raw_df["feature_name"] == load_field][[time_field, 'value']]
    init_df = init_df.rename(columns={'value': load_field})
    init_df.drop_duplicates(subset=time_field, keep='first', inplace=True)
    init_df = init_df.sort_values(by=time_field, ascending=True)
    logger.info(f"已提取{load_field}列")

    # Extract additional columns
    add_cols = [] if not other_cols else other_cols
    if add_cols:
        for ac in add_cols:
            logger.info(f"提取{ac}列")
            tmp_df = raw_df[raw_df["feature_name"] == ac][[time_field, 'value']]
            tmp_df = tmp_df.rename(columns={'value': ac})
            tmp_df.drop_duplicates(subset=time_field, keep='first', inplace=True)
            tmp_df.sort_values(by=time_field, ascending=True)
            init_df = init_df.merge(tmp_df, how='outer', on=time_field)
    else:
        logger.info(f"仅提取{load_field}列")

    # Select and order columns
    init_df = init_df[[time_field, load_field] + add_cols]
    return init_df


def _resample_and_clean(df, time_granularity, task_type, time_field, load_field,
                        now_time, apply_time_filter=False):
    """
    Apply shared post-processing: deduplication, sorting, resampling,
    Spring-Festival handling, and min/max computation.

    Parameters
    ----------
    df : pd.DataFrame
        Wide-format DataFrame produced by ``_pivot_and_extract``.
    time_granularity : str
        Target granularity, e.g. '15min', '1H', '1D'.
    task_type : str
        Prediction task type, e.g. 'DI', 'D', 'M'.
    time_field : str
        Name of the timestamp column.
    load_field : str
        Name of the load column.
    now_time : datetime
        Reference timestamp used for holiday checks (and optional row filtering).
    apply_time_filter : bool, optional
        If True, keep only rows where time_field < now_time before resampling.
        This matches the behaviour of ``offline_load_data``.  Default False.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        (processed_df, his_min_max)
    """
    import chinese_calendar

    if apply_time_filter:
        df = df.loc[df[time_field] < now_time]

    # Deduplicate and sort
    df = df.sort_values(by=time_field)
    df = df.drop_duplicates(subset=[time_field], keep='first', inplace=False)

    # Resample to the requested granularity
    df = df.set_index(time_field, drop=True, inplace=False)
    df = df.resample(rule=time_granularity).mean()
    df[time_field] = df.index
    df.index = [_ for _ in range(len(df))]

    # Conditionally remove Spring Festival data
    _, holiday_name = chinese_calendar.get_holiday_detail(now_time)

    logger.info(f"task_type：{task_type}\n"
                f"time_granularity：{time_granularity}\n"
                f"holiday_name：{holiday_name}")

    if task_type != 'M' and time_granularity != '1D' and holiday_name != 'Spring Festival':
        logger.info(f"数据中包含春节假期数据且需要剔除...")
        df = remove_special_data(df)
    else:
        logger.info(f"数据中不包含春节假期数据或者春节假期数据不需要剔除...")

    # Compute historical min / max
    his_min_max = pd.DataFrame()
    his_min_max["min"] = [df[load_field].min()]
    his_min_max["max"] = [df[load_field].max()]

    return df, his_min_max


def _resolve_now_time(nowtime, time_zone):
    """
    Resolve the *nowtime* parameter to a timezone-aware datetime.

    Parameters
    ----------
    nowtime : str | None
        Either None, 'false', or a parseable datetime string.
    time_zone : str
        IANA timezone name, e.g. 'Asia/Shanghai'.

    Returns
    -------
    datetime
    """
    tz = pytz.timezone(time_zone)
    if nowtime and nowtime != 'false':
        return pd.to_datetime(nowtime)
    return datetime.now(tz)


# ---------------------------------------------------------------------------
# Database credential helper (reads from environment variables)
# ---------------------------------------------------------------------------

def _get_db_config(parent_id):
    """
    Build a database configuration dict for the given *parent_id*.

    Credentials are read from environment variables.  The expected env-var
    naming convention is::

        DB_<PARENT_ID>_HOST
        DB_<PARENT_ID>_PORT          (defaults to 3306)
        DB_<PARENT_ID>_DATABASE
        DB_<PARENT_ID>_USER
        DB_<PARENT_ID>_PASSWORD

    If any required variable is missing the function falls back to a
    hardcoded default (kept for backward compatibility during migration).

    Parameters
    ----------
    parent_id : str
        Identifier used both as the env-var prefix and as the lookup key
        into the fallback defaults dict.

    Returns
    -------
    dict
        Keys: host, port, database, user, password.
    """
    # Hardcoded defaults (kept for backward compatibility)
    _defaults = {
        "mengxi": {
            "host": "10.65.101.249",
            "port": 3306,
            "database": "enos_suite_load_mengxi_new",
            "user": "enos_suite_mengxi_user",
            "password": "Enos_suite_1234",
        },
        "shandong": {
            "host": "10.65.101.249",
            "port": 3306,
            "database": "enos_suite_load_shandong_new",
            "user": "enos_suite_shandong_user",
            "password": "Enos_suite_1234",
        },
        "gansu": {
            "host": "10.65.101.249",
            "port": 3306,
            "database": "enos_suite_load_gansu_new",
            "user": "enos_suite_gansu_user",
            "password": "Enos_suite_1234",
        },
        "shanxi": {
            "host": "10.65.101.249",
            "port": 3306,
            "database": "enos_suite_load_shanxi_new",
            "user": "enos_suite_shanxi_user",
            "password": "Enos_suite_1234",
        },
    }

    prefix = f"DB_{parent_id.upper()}_"
    host = os.environ.get(f"{prefix}HOST")
    port = os.environ.get(f"{prefix}PORT")
    database = os.environ.get(f"{prefix}DATABASE")
    user = os.environ.get(f"{prefix}USER")
    password = os.environ.get(f"{prefix}PASSWORD")

    # If all env vars are provided, use them; otherwise fall back to defaults
    if host and database and user and password:
        return {
            "host": host,
            "port": int(port) if port else 3306,
            "database": database,
            "user": user,
            "password": password,
        }

    # Fallback to hardcoded defaults
    return _defaults.get(parent_id, {})


# ---------------------------------------------------------------------------
# Public data-source functions
# ---------------------------------------------------------------------------

# dataset_operator
def extract_load_data(task_type,
                      dataset_name,
                      table_name,
                      parent_field,
                      child_field,
                      time_field,
                      load_field,
                      parent_id,
                      child_id,
                      time_granularity,
                      is_training,
                      time_zone,
                      nowtime=None,
                      other_cols=None):
    """
    全部为全局参数，其中is_training和time_zone为默认参数，其他为传入参数
    """
    logger.info(f"'extract_load_data' input params:\n"
                f"task_type: {task_type}\n"
                f"dataset_name: {dataset_name}\n"
                f"table_name: {table_name}\n"
                f"parent_field: {parent_field}\n"
                f"child_field: {child_field}\n"
                f"time_field: {time_field}\n"
                f"load_field: {load_field}\n"
                f"parent_id: {parent_id}\n"
                f"child_id: {child_id}\n"
                f"time_granularity: {time_granularity}\n"
                f"is_training: {is_training}\n"
                f"time_zone: {time_zone}\n"
                f"nowtime:\n{nowtime}\n"
                f"other_cols:\n{other_cols}\n")

    import chinese_calendar
    logger.info(f"get chinese calendar...")

    dataset = Dataset.get_by_name(dataset_name)

    # select
    try:
        sql_query = "select * from %s where %s='%s' and %s='%s'" % (
            table_name, parent_field, parent_id, child_field, child_id)
        tmp_load_df = dataset.to_pandas_dataframe(use_cached_result=False, query=sql_query)

        # Pivot and extract columns
        init_df = _pivot_and_extract(tmp_load_df, time_field, load_field, other_cols)

        logger.info(f"获得data.")
        data = copy.deepcopy(init_df)

        if not data.empty:
            logger.info(f"The type of is_training: {type(is_training)}")
            now_time = _resolve_now_time(nowtime, time_zone)

            data, his_min_max = _resample_and_clean(
                data, time_granularity, task_type, time_field, load_field,
                now_time, apply_time_filter=False)

            logger.info(f"The raw data of {parent_id}-{child_id} is got. ")
            logger.info(f"'extract_load_data' output params:\n data: {data}\n his_min_max: {his_min_max}\n")
            return data, his_min_max

    except Exception as e:
        logger.error(f"extract_load_data failed.")
        logger.info(f"{e}.")
        pass


# beta环境测试数据
def beta_load_data(task_type,
                   table_name,
                   parent_field,
                   child_field,
                   time_field,
                   load_field,
                   parent_id,
                   child_id,
                   time_granularity,
                   is_training,
                   time_zone,
                   nowtime=None,
                   other_cols=None):
    logger.info(f"******************** beta_load_data ********************")
    logger.info(f"'beta_load_data' input params:\n"
                f"task_type:\n{task_type}\n"
                f"table_name:\n{table_name}\n"
                f"parent_field:\n{parent_field}\n"
                f"child_field:\n{child_field}\n"
                f"time_field:\n{time_field}\n"
                f"load_field:\n{load_field}\n"
                f"parent_id:\n{parent_id}\n"
                f"child_id:\n{child_id}\n"
                f"time_granularity:\n{time_granularity}\n"
                f"is_training:\n{is_training}\n"
                f"time_zone:\n{time_zone}\n"
                f"nowtime:\n{nowtime}\n"
                f"other_cols:\n{other_cols}\n")

    DB_conf = _get_db_config(parent_id)

    db = pymysql.connect(host=DB_conf["host"],
                         port=DB_conf["port"],
                         user=DB_conf["user"],
                         password=DB_conf["password"],
                         database=DB_conf["database"],
                         charset="utf8")
    cursor = db.cursor()
    logger.info(f"beta db connected.")

    try:
        sql_query = "select * from %s where %s='%s' and %s='%s';" % (
            table_name, parent_field, parent_id, child_field, child_id)

        cursor.execute(sql_query)
        field = cursor.fetchall()
        tmp_load_df = pd.DataFrame(field)

        header = cursor.description
        header = [elem[0] for elem in header]

        tmp_load_df.columns = header

        # Pivot and extract columns
        init_df = _pivot_and_extract(tmp_load_df, time_field, load_field, other_cols)

        logger.info(f"获得load_df.")
        now_time = _resolve_now_time(nowtime, time_zone)

        load_df, his_min_max = _resample_and_clean(
            init_df, time_granularity, task_type, time_field, load_field,
            now_time, apply_time_filter=False)

        return load_df, his_min_max
    except Exception as e:
        logger.error(f"beta_load_data failed.")
        logger.info(f"{e}.")
        pass


# ppe offline数据
def offline_load_data(task_type,
                      table_name,
                      parent_field,
                      child_field,
                      time_field,
                      load_field,
                      parent_id,
                      child_id,
                      time_granularity,
                      is_training,
                      time_zone,
                      nowtime=None,
                      other_cols=None,
                      csv_path=None):
    logger.info(f"******************** offline_load_data ********************")
    logger.info(f"'offline_load_data' input params:\n"
                f"task_type:\n{task_type}\n"
                f"table_name:\n{table_name}\n"
                f"parent_field:\n{parent_field}\n"
                f"child_field:\n{child_field}\n"
                f"time_field:\n{time_field}\n"
                f"load_field:\n{load_field}\n"
                f"parent_id:\n{parent_id}\n"
                f"child_id:\n{child_id}\n"
                f"time_granularity:\n{time_granularity}\n"
                f"is_training:\n{is_training}\n"
                f"time_zone:\n{time_zone}\n"
                f"nowtime:\n{nowtime}\n"
                f"other_cols:\n{other_cols}\n")

    try:
        # Resolve CSV path: explicit parameter > env var > hardcoded default
        resolved_csv_path = (
            csv_path
            or os.environ.get("OFFLINE_CSV_PATH")
            or f"data/load_true_{parent_id}_sum_20250101_250518.csv"
        )
        tmp_load_df = pd.read_csv(resolved_csv_path)
        tmp_load_df = tmp_load_df[(tmp_load_df[parent_field] == parent_id) & (tmp_load_df[child_field] == child_id)]

        # Pivot and extract columns
        init_df = _pivot_and_extract(tmp_load_df, time_field, load_field, other_cols)

        logger.info(f"获得load_df.")
        now_time = _resolve_now_time(nowtime, time_zone)

        # offline_load_data applies a time filter (< now_time) before resampling
        load_df, his_min_max = _resample_and_clean(
            init_df, time_granularity, task_type, time_field, load_field,
            now_time, apply_time_filter=True)

        logger.info(f"'offline_load_data' output params:\nload_df:\n{load_df}\nhis_min_max:\n{his_min_max}")
        return load_df, his_min_max
    except Exception as e:
        print(traceback.format_exc())
        logger.error(f"offline_load_data failed.")
        logger.info(f"{e}.")
        pass
