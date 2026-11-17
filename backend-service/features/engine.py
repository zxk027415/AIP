# -*- coding: utf-8 -*-
# @Time : 2022/3/27 13:28
# @Author : mingyang.zong
# @File : engine.py
"""
Unified feature engineering module.

Replaces the six near-duplicate functions from feature_eng.py with a single
parameterized ``add_more_features`` that branches on ScenarioConfig.
Backward-compatible wrappers are provided so that existing callers are
unaffected.
"""
import copy
import json
import warnings

import numpy as np
import pandas as pd
import pytz
from loguru import logger
from datetime import datetime, timedelta

from data_process import get_all_filled_data
from forecast_utils import get_delay_info_from_offline_db, shift_len_mapping
from common.constants import ScenarioConfig, SCENARIO_CONFIGS
from common.holidays import if_workday
from add_features import (
    get_stat_features, get_rolling_features, get_hist_period_statis,
    get_same_moment_window_statis, get_period_load_rate,
    get_diff_features, get_pct_rate_feature,
)

warnings.filterwarnings(action="ignore")

'''
config information:
{
      "task_id": "666"                                   # str, 预测任务id
      "task_type": "D",                                  # str, 预测任务类型
      "datasource_name": "ai-suite-load-4-beta",         # mysql_source, 数据源名
      "dataset_name": "ai-suite-load-4-beta",     # str, 数据集名
      "table_name": "sgms_hbuilding_load_quarter3",      # str, 历史真值数据所在表
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


# ---------------------------------------------------------------------------
# Core unified implementation
# ---------------------------------------------------------------------------

def add_more_features(scenario,
                      task_id,
                      parent_id,
                      child_id,
                      operate_status,
                      completed_df,
                      original_time_freq,
                      daily_horizon,
                      forecast_horizon,
                      forecast_start_time,
                      is_training,
                      time_zone,
                      nowtime=None,
                      separate_modeling='true',
                      gaps_defined=None,
                      time_field="record_time",
                      load_field="load"):
    """
    Unified feature engineering for all six forecast scenarios (DI / D / WI / W / MI / M).

    The behavioral differences between scenarios are captured by *scenario*
    (a ``ScenarioConfig`` instance) and an internal branch on
    ``scenario.rounding_unit``:

    * ``"hour"``  -- intra-day (DI): hour-boundary rounding, hour-based
      extend_delta, gaps_defined shift logic.
    * ``"day"``   -- all others: day-boundary rounding, day-based
      extend_delta, simple shift_length logic.

    Parameters
    ----------
    scenario : ScenarioConfig
        Scenario configuration (rounding_unit, task_type, etc.).
    task_id : str
        预测任务id
    parent_id : str
        父节点
    child_id : str
        子节点
    operate_status : str
        运行状态标识（线上/线下标识）
    completed_df : DataFrame
        预测变量补全后的数据
    original_time_freq : str
        原始数据频率
    daily_horizon : str or int
        日数据长度
    forecast_horizon : str or int
        预测长度（日内为小时，其余为天）
    forecast_start_time : str
        预测起始时间
    is_training : str
        是否训练, 'true'/'false'
    time_zone : str
        时区
    nowtime : str, optional
        回测时间设置, 默认None
    separate_modeling : str
        是否分开建模, 'true'/'false', 默认'true'
    gaps_defined : dict, optional
        自定义的列的延迟时间, 默认None
    time_field : str
        时间戳字段, 默认'record_time'
    load_field : str
        预测变量（负荷）字段, 默认'load'

    Returns
    -------
    tuple
        (forecast_timestamps, feat_df, final_shift_info)
    """
    task_type = scenario.task_type
    is_hour_rounding = (scenario.rounding_unit == "hour")

    logger.info(f"******************** add_more_features_{task_type.lower()} ********************")
    logger.info(f"'add_more_features_{task_type.lower()}' input params:\n"
                f"task_id:\n{task_id}\n"
                f"parent_id:\n{parent_id}\n child_id:\n{child_id}\n"
                f"operate_status:\n{operate_status}\n"
                f"completed_df:\n{completed_df.head()}\n...{completed_df.tail()}\n{completed_df.shape}\n"
                f"original_time_freq:\n{original_time_freq}\n"
                f"daily_horizon:\n{daily_horizon}\n"
                f"forecast_horizon:\n{forecast_horizon}\n"
                f"forecast_start_time:\n{forecast_start_time}\n"
                f"is_training:\n{is_training}\n"
                f"time_zone:\n{time_zone}\n"
                f"nowtime:\n{nowtime}\n"
                f"separate_modeling:\n{separate_modeling}\n"
                f"gaps_defined:\n{gaps_defined}\n"
                f"time_field:\n{time_field}\n"
                f"load_field:\n{load_field}\n")

    daily_horizon = int(daily_horizon)
    forecast_horizon = int(forecast_horizon)
    tz = pytz.timezone(time_zone)

    # 生成now_time, shift_cols
    now_time = pd.to_datetime(nowtime) if nowtime and nowtime != 'false' else datetime.now(tz)
    shift_cols = [c for c in completed_df.columns if c != time_field]

    # ------ Branch: time rounding (hour vs day) ------
    if is_hour_rounding:
        # DI: 数据最新小时取整（向下取整）
        round_start = now_time.strftime("%Y-%m-%d %H:00:00")
        round_end = (now_time + timedelta(hours=1)).strftime("%Y-%m-%d %H:00:00")
        standard_ts = pd.date_range(round_start, round_end, freq=original_time_freq, closed='left')
        ends_str = pd.to_datetime(standard_ts[-1]).strftime("%M:%S")

        whole_df = pd.DataFrame(columns=[time_field])
        for ac in shift_cols:
            tmp_whole = completed_df[[time_field, ac]].dropna()
            tmp_end_h = pd.to_datetime(tmp_whole.iloc[-1][time_field]).strftime("%Y-%m-%d %H:00:00")
            tmp_end_time = pd.to_datetime(tmp_whole.iloc[-1][time_field]).strftime("%M:%S")
            tmp_merge = tmp_whole if tmp_end_time == ends_str else tmp_whole[tmp_whole[time_field] < tmp_end_h]
            whole_df = whole_df.merge(tmp_merge, how='outer', on=time_field)
        logger.info(f"完成数据最新小时取整. ")
    else:
        # D/WI/W/MI/M: 数据最新日取整（向下取整）
        round_start = now_time.strftime("%Y-%m-%d")
        round_end = (now_time + timedelta(days=1)).strftime("%Y-%m-%d")
        standard_ts = pd.date_range(round_start, round_end, freq=original_time_freq, closed='left')
        ends_str = pd.to_datetime(standard_ts[-1]).strftime("%H:%M:%S")

        whole_df = pd.DataFrame(columns=[time_field])
        for ac in shift_cols:
            tmp_whole = completed_df[[time_field, ac]].dropna()
            tmp_end_d = pd.to_datetime(tmp_whole.iloc[-1][time_field]).strftime("%Y-%m-%d")
            tmp_end_time = pd.to_datetime(tmp_whole.iloc[-1][time_field]).strftime("%H:%M:%S")
            tmp_merge = tmp_whole if tmp_end_time == ends_str else tmp_whole[tmp_whole[time_field] < tmp_end_d]
            whole_df = whole_df.merge(tmp_merge, how='outer', on=time_field)
        logger.info(f"完成数据最新日取整. ")

    # ------ Branch: DI gaps_defined / shift info vs others ------
    if is_hour_rounding:
        # DI: 日内预测阶段考虑外源shift信息（gaps_defined）输入
        if is_training == "false":
            if operate_status == "online":
                delay_info = {}
                pass
            else:
                delay_info = get_delay_info_from_offline_db(task_id, parent_id, child_id, operate_status)
            shift_info = json.loads(delay_info["raw_data_delay_info"].values[-1])["train_shift_info"] if len(
                delay_info) else {}

            # gaps_defined优先使用
            get_shift = copy.deepcopy(shift_info)
            get_shift.update(gaps_defined) if gaps_defined else get_shift
        else:
            # 日内训练阶段不考虑外源shift信息输入，只针对数据本身
            get_shift = {}
            pass

    # 生成原始forecast_timestamps
    if is_hour_rounding:
        # DI: extend by hours
        extend_start = copy.deepcopy(round_end)
        extend_end = pd.to_datetime(extend_start) + timedelta(hours=forecast_horizon)
    else:
        # D/WI/W/MI/M: extend by days
        extend_start = round_end + f" {forecast_start_time}:00"
        extend_end = pd.to_datetime(extend_start) + timedelta(days=forecast_horizon)

    forecast_timestamps = pd.date_range(extend_start, extend_end,
                                        freq=original_time_freq, closed='left').tolist()

    # 生成实际real_forecast_timestamps
    load_single = whole_df[[time_field, load_field]].dropna()
    load_end_t = pd.to_datetime(load_single.iloc[-1][time_field])

    # 存在全部数据超前时
    if forecast_timestamps[-1] <= load_end_t:
        real_forecast_timestamps = []
    # 存在部分数据超前时
    elif (forecast_timestamps[0] <= load_end_t) & (forecast_timestamps[-1] > load_end_t):
        real_forecast_timestamps = forecast_timestamps[forecast_timestamps.index(load_end_t) + 1:]
    # 存在数据延迟时(需要再模拟一些延迟数据来进行验证)
    else:
        delta_timestamps = list(
            pd.date_range(load_end_t, forecast_timestamps[0], freq=original_time_freq, closed='left'))
        real_forecast_timestamps = delta_timestamps[1:] + forecast_timestamps
    logger.info(f"生成实际的real_forecast_timestamps. ")

    if real_forecast_timestamps:
        if is_hour_rounding:
            # DI: 补全预测变量预测需求时间戳，以满足整小时预测
            cut_boundary = (real_forecast_timestamps[-1] + timedelta(hours=1)).strftime("%Y-%m-%d %H:00:00")
            add_timestamps = list(
                pd.date_range(real_forecast_timestamps[-1], cut_boundary, freq=original_time_freq, closed='left'))[1:]
            tmp_add_df = pd.DataFrame(real_forecast_timestamps + add_timestamps, columns=[time_field])
            whole_df_add = whole_df.merge(tmp_add_df, how='outer', on=time_field)
            whole_df_add = whole_df_add[whole_df_add[time_field] < cut_boundary]  # 超额辅助变量按小时截断
            final_end_boundary = pd.to_datetime(whole_df_add.iloc[-1][time_field]).strftime("%Y-%m-%d %H:00:00")
        else:
            # D/WI/W/MI/M: 补全预测变量预测需求时间戳
            cut_boundary = (real_forecast_timestamps[-1] + timedelta(days=1)).strftime("%Y-%m-%d")
            add_timestamps = list(
                pd.date_range(real_forecast_timestamps[-1], cut_boundary, freq=original_time_freq, closed='left'))[1:]
            tmp_add_df = pd.DataFrame(real_forecast_timestamps + add_timestamps, columns=[time_field])
            whole_df_add = whole_df.merge(tmp_add_df, how='outer', on=time_field)
            whole_df_add = whole_df_add[whole_df_add[time_field] < cut_boundary]  # 超额辅助变量按天截断
            final_end_boundary = pd.to_datetime(whole_df_add.iloc[-1][time_field]).strftime("%Y-%m-%d")

        # ------ Branch: shift/delay handling (DI vs others) ------
        if is_hour_rounding:
            # DI: 结合get_shift进行数据统一shift对齐，并记录最终shift信息
            get_shift_keys = list(get_shift.keys())
            final_shift_info = copy.deepcopy(get_shift)
            final_shift_length = {}
            for c in shift_cols:
                tmp_single = whole_df[[time_field, c]].dropna()
                tmp_end_h = pd.to_datetime(tmp_single.iloc[-1][time_field]).strftime("%Y-%m-%d %H:00:00")
                delta_d = int(str(pd.to_datetime(final_end_boundary) - pd.to_datetime(tmp_end_h)).split(' ')[0])
                delta_h = int(str(pd.to_datetime(final_end_boundary) - pd.to_datetime(tmp_end_h)).split(' ')[-1][:2])
                tmp_shift_h = int(delta_d * 24 + delta_h) if int(delta_d * 24 + delta_h) >= 0 else 0
                tmp_shift_info = {c: f"{tmp_shift_h}H"}  # 拒绝反向shift记录
                final_shift_info.update(tmp_shift_info) if c not in get_shift_keys else final_shift_info
                final_shift_length[c] = shift_len_mapping(final_shift_info[c], daily_horizon)
            whole_df_add[f"{load_field}_shift"] = whole_df_add[load_field].shift(
                final_shift_length[load_field])  # 生成预测变量本身的shift特征
            shift_cols_copy = copy.deepcopy(shift_cols)
            shift_cols_copy.remove(load_field)
            for sc in shift_cols_copy:
                whole_df_add[sc] = whole_df_add[sc].shift(final_shift_length[sc])  # 辅助变量shift对齐
        else:
            # D/WI/W/MI/M: 数据统一shift对齐
            shift_length = {}
            for c in shift_cols:
                tmp_single = whole_df[[time_field, c]].dropna()
                tmp_end_d = pd.to_datetime(tmp_single.iloc[-1][time_field]).strftime("%Y-%m-%d")
                delta_d = int(str(pd.to_datetime(final_end_boundary) - pd.to_datetime(tmp_end_d)).split(' ')[0])
                shift_length[c] = delta_d * daily_horizon if delta_d >= 0 else 0
            whole_df_add[f"{load_field}_shift"] = whole_df_add[load_field].shift(
                shift_length[load_field])  # 生成预测变量本身的shift特征
            shift_cols_copy = copy.deepcopy(shift_cols)
            shift_cols_copy.remove(load_field)
            for sc in shift_cols_copy:
                whole_df_add[sc] = whole_df_add[sc].shift(shift_length[sc])  # 辅助变量shift对齐

        # # 预测阶段尤其当存在gaps_defined时，需要考虑对f"{load_field}_shift"} + shift_cols_copy进行数据周期性填补
        # # 预测阶段为节省时间开销，仅取最后5个预测长度的数据进行填补操作，完成后进行拼接
        fill_len = 5 * len(real_forecast_timestamps)
        cyc_filled_cols = [f"{load_field}_shift"] + shift_cols_copy
        if is_training == "false":
            tmp_fill_df = whole_df_add.iloc[-fill_len:]
            other_fill_df = whole_df_add.iloc[:-fill_len]
            tmp_fill_df.set_index(time_field, inplace=True)
            tmp_fill_df = get_all_filled_data(tmp_fill_df, [load_field] + cyc_filled_cols)
            tmp_fill_df.reset_index(inplace=True)
            whole_df_add = pd.concat([other_fill_df, tmp_fill_df], axis=0)
        # # 训练阶段需要对所有数据进行填补操作
        else:
            tmp_fill_df = copy.deepcopy(whole_df_add)
            tmp_fill_df_train = copy.deepcopy(whole_df_add)
            tmp_fill_df_train.dropna(subset=[load_field] + [f"{load_field}_shift"], inplace=True)
            last_complete_time = pd.to_datetime(tmp_fill_df_train[time_field].values[-1])
            tmp_fill_df_train_add = tmp_fill_df[tmp_fill_df[time_field] > last_complete_time]
            # 基于已更新的load_field已完成填补的操作
            tmp_fill_df_train.set_index(time_field, inplace=True)
            tmp_fill_df_train = get_all_filled_data(tmp_fill_df_train, [load_field] + cyc_filled_cols)
            tmp_fill_df_train.reset_index(inplace=True)
            tmp_fill_df = pd.concat([tmp_fill_df_train, tmp_fill_df_train_add], axis=0)
            whole_df_add = copy.deepcopy(tmp_fill_df)

        '''
        生成额外特征
        '''
        feat_df = copy.deepcopy(whole_df_add)
        # ******************************* 加入时间属性特征 *******************************
        # 节假日特征
        feat_df["is_holiday"] = feat_df[time_field].apply(lambda x: 0 if if_workday(x) else 1)
        # 时间标识特征
        feat_df['day'] = feat_df[time_field].dt.day
        feat_df['yday'] = feat_df[time_field].dt.dayofyear
        feat_df['month'] = feat_df[time_field].dt.month
        feat_df['dayofweek'] = feat_df[time_field].dt.dayofweek
        feat_df['hour'] = feat_df[time_field].dt.hour
        feat_df['minute'] = feat_df[time_field].dt.minute
        nums_1 = len(feat_df) // daily_horizon  # 此前的操作已保证原始数据时间戳从00:00:00开始
        nums_2 = len(feat_df) - nums_1 * daily_horizon
        feat_df["period"] = list(range(daily_horizon)) * nums_1 + list(range(nums_2))  # 天内的数据序号
        # 获取时间周期编码特征
        feat_df['hour_sin'] = np.sin(2 * np.pi * feat_df['hour'] / 24)
        feat_df['hour_cos'] = np.cos(2 * np.pi * feat_df['hour'] / 24)
        feat_df['wday_sin'] = np.sin(2 * np.pi * feat_df['dayofweek'] / 6)
        feat_df['wday_cos'] = np.cos(2 * np.pi * feat_df['dayofweek'] / 6)
        logger.info(f"时间属性特征已生成. ")

        feat_df[time_field] = feat_df[time_field].apply(lambda x: pd.to_datetime(x).strftime("%Y-%m-%d %H:%M:%S"))

        # 获取预测时间段所包含的天，确定workday和holiday的历史数据shift长度，分开建模时训练&预测须在同一天调度
        pred_include_days = list(
            sorted(set([pd.to_datetime(t).strftime("%Y-%m-%d") for t in real_forecast_timestamps])))
        workday_shift_len = len([d for d in pred_include_days if if_workday(pd.to_datetime(d))]) * daily_horizon
        holiday_shift_len = len([d for d in pred_include_days if not if_workday(pd.to_datetime(d))]) * daily_horizon
        logger.info(
            f"workday_shift_len is: {workday_shift_len // daily_horizon}*{daily_horizon}={workday_shift_len}. \n "
            f"holiday_shift_len is: {holiday_shift_len // daily_horizon}*{daily_horizon}={holiday_shift_len}. ")

        # 特征列排序确保特征一致
        feat_columns = sorted(feat_df.columns)
        feat_df = feat_df[feat_columns]

        all_day_feat_df = copy.deepcopy(feat_df)
        logger.info(f"all_day_feat_df已生成. ")

        if separate_modeling == 'true':
            workday_feat_df = feat_df[feat_df['is_holiday'] == 0].drop('is_holiday', axis=1)
            if workday_shift_len:
                # workday_feat_df[f"workday_load_shift_1d"] = workday_feat_df[load_field].shift(daily_horizon)
                workday_feat_df[f"workday_load_shift_{workday_shift_len // daily_horizon}d"] = workday_feat_df[
                    load_field].shift(workday_shift_len)  # 可优化
            logger.info(f"workday_feat_df已生成. ")
            holiday_feat_df = feat_df[feat_df['is_holiday'] == 1].drop('is_holiday', axis=1)
            if holiday_shift_len:
                # holiday_feat_df[f"workday_load_shift_1d"] = holiday_feat_df[load_field].shift(daily_horizon)
                holiday_feat_df[f"holiday_load_shift_{holiday_shift_len // daily_horizon}d"] = holiday_feat_df[
                    load_field].shift(holiday_shift_len)  # 可优化
            logger.info(f"holiday_feat_df已生成. ")
            workday_feat_df.index = [_ for _ in range(len(workday_feat_df))]
            holiday_feat_df.index = [_ for _ in range(len(holiday_feat_df))]

            # 预测时防止后面请求body中有nan字符
            workday_feat_df = workday_feat_df.fillna(0)
            holiday_feat_df = holiday_feat_df.fillna(0)

        else:
            workday_feat_df = pd.DataFrame()
            holiday_feat_df = pd.DataFrame()
            logger.info(f"separate_modeling is not 'true', workday_feat_df is empty, holiday_feat_df is empty. ")

        all_day_feat_df.index = [_ for _ in range(len(all_day_feat_df))]
        # 预测时防止后面请求body中有nan字符
        all_day_feat_df = all_day_feat_df if is_training == "true" else all_day_feat_df.fillna(0)

        # 将预测时间戳转化为字符串方便数据导出(forecast_timestamps为空不影响)
        forecast_timestamps = [elem.strftime("%Y-%m-%d %H:%M:%S") for elem in forecast_timestamps]
        real_forecast_timestamps = [elem.strftime("%Y-%m-%d %H:%M:%S") for elem in real_forecast_timestamps]

        feat_df = {'all_day_feat_df': all_day_feat_df,
                   'workday_feat_df': workday_feat_df,
                   'holiday_feat_df': holiday_feat_df,
                   'pred_include_days': pred_include_days,
                   'forecast_timestamps': forecast_timestamps,
                   'real_forecast_timestamps': real_forecast_timestamps}
    else:
        feat_df = {'all_day_feat_df': [],
                   'workday_feat_df': [],
                   'holiday_feat_df': [],
                   'pred_include_days': [],
                   'forecast_timestamps': [],
                   'real_forecast_timestamps': [],
                   'completed_df': completed_df}
        logger.info(f"存在全部数据超前的情况，不需要做预测. ")

    # ------ final_shift_info ------
    if is_hour_rounding:
        # DI: final_shift_info comes from the shift logic above (already set in the if-branch)
        # If real_forecast_timestamps was empty, initialize to empty dict
        if real_forecast_timestamps:
            pass  # final_shift_info already set above
        else:
            final_shift_info = {}
    else:
        # D/WI/W/MI/M: 保持所有场景参数传递一致，该场景下该参数尚未考虑
        final_shift_info = {}

    logger.info(f"特征数据已生成. ")
    logger.info(f"'add_more_features_{task_type.lower()}' output params:\n"
                f"forecast_timestamps:\n{forecast_timestamps}"
                f"feat_df:\n{feat_df}")

    final_shift_info = {"pred_shift_info": final_shift_info} if is_training == "false" else {
        "train_shift_info": final_shift_info}
    return forecast_timestamps, feat_df, final_shift_info


# ---------------------------------------------------------------------------
# Backward-compatible wrappers
# ---------------------------------------------------------------------------

def add_more_features_di(task_id,
                         parent_id,
                         child_id,
                         operate_status,
                         completed_df,
                         original_time_freq,
                         daily_horizon,
                         forecast_horizon,
                         forecast_start_time,
                         is_training,
                         time_zone,
                         nowtime=None,
                         separate_modeling='true',
                         gaps_defined=None,
                         time_field="record_time",
                         load_field="load"):
    """日内特征工程 (DI) -- backward-compatible wrapper."""
    return add_more_features(
        SCENARIO_CONFIGS["DI"],
        task_id=task_id,
        parent_id=parent_id,
        child_id=child_id,
        operate_status=operate_status,
        completed_df=completed_df,
        original_time_freq=original_time_freq,
        daily_horizon=daily_horizon,
        forecast_horizon=forecast_horizon,
        forecast_start_time=forecast_start_time,
        is_training=is_training,
        time_zone=time_zone,
        nowtime=nowtime,
        separate_modeling=separate_modeling,
        gaps_defined=gaps_defined,
        time_field=time_field,
        load_field=load_field,
    )


def add_more_features_d(task_id,
                        parent_id,
                        child_id,
                        operate_status,
                        completed_df,
                        original_time_freq,
                        daily_horizon,
                        forecast_horizon,
                        forecast_start_time,
                        is_training,
                        time_zone,
                        nowtime=None,
                        separate_modeling='true',
                        gaps_defined=None,
                        time_field="record_time",
                        load_field="load"):
    """日前特征工程 (D) -- backward-compatible wrapper."""
    return add_more_features(
        SCENARIO_CONFIGS["D"],
        task_id=task_id,
        parent_id=parent_id,
        child_id=child_id,
        operate_status=operate_status,
        completed_df=completed_df,
        original_time_freq=original_time_freq,
        daily_horizon=daily_horizon,
        forecast_horizon=forecast_horizon,
        forecast_start_time=forecast_start_time,
        is_training=is_training,
        time_zone=time_zone,
        nowtime=nowtime,
        separate_modeling=separate_modeling,
        gaps_defined=gaps_defined,
        time_field=time_field,
        load_field=load_field,
    )


def add_more_features_wi(task_id,
                         parent_id,
                         child_id,
                         operate_status,
                         completed_df,
                         original_time_freq,
                         daily_horizon,
                         forecast_horizon,
                         forecast_start_time,
                         is_training,
                         time_zone,
                         nowtime=None,
                         separate_modeling='true',
                         gaps_defined=None,
                         time_field="record_time",
                         load_field="load"):
    """周内特征工程 (WI) -- backward-compatible wrapper."""
    return add_more_features(
        SCENARIO_CONFIGS["WI"],
        task_id=task_id,
        parent_id=parent_id,
        child_id=child_id,
        operate_status=operate_status,
        completed_df=completed_df,
        original_time_freq=original_time_freq,
        daily_horizon=daily_horizon,
        forecast_horizon=forecast_horizon,
        forecast_start_time=forecast_start_time,
        is_training=is_training,
        time_zone=time_zone,
        nowtime=nowtime,
        separate_modeling=separate_modeling,
        gaps_defined=gaps_defined,
        time_field=time_field,
        load_field=load_field,
    )


def add_more_features_w(task_id,
                        parent_id,
                        child_id,
                        operate_status,
                        completed_df,
                        original_time_freq,
                        daily_horizon,
                        forecast_horizon,
                        forecast_start_time,
                        is_training,
                        time_zone,
                        nowtime=None,
                        separate_modeling='true',
                        gaps_defined=None,
                        time_field="record_time",
                        load_field="load"):
    """周前特征工程 (W) -- backward-compatible wrapper."""
    return add_more_features(
        SCENARIO_CONFIGS["W"],
        task_id=task_id,
        parent_id=parent_id,
        child_id=child_id,
        operate_status=operate_status,
        completed_df=completed_df,
        original_time_freq=original_time_freq,
        daily_horizon=daily_horizon,
        forecast_horizon=forecast_horizon,
        forecast_start_time=forecast_start_time,
        is_training=is_training,
        time_zone=time_zone,
        nowtime=nowtime,
        separate_modeling=separate_modeling,
        gaps_defined=gaps_defined,
        time_field=time_field,
        load_field=load_field,
    )


def add_more_features_mi(task_id,
                         parent_id,
                         child_id,
                         operate_status,
                         completed_df,
                         original_time_freq,
                         daily_horizon,
                         forecast_horizon,
                         forecast_start_time,
                         is_training,
                         time_zone,
                         nowtime=None,
                         separate_modeling='true',
                         gaps_defined=None,
                         time_field="record_time",
                         load_field="load"):
    """月内特征工程 (MI) -- backward-compatible wrapper."""
    return add_more_features(
        SCENARIO_CONFIGS["MI"],
        task_id=task_id,
        parent_id=parent_id,
        child_id=child_id,
        operate_status=operate_status,
        completed_df=completed_df,
        original_time_freq=original_time_freq,
        daily_horizon=daily_horizon,
        forecast_horizon=forecast_horizon,
        forecast_start_time=forecast_start_time,
        is_training=is_training,
        time_zone=time_zone,
        nowtime=nowtime,
        separate_modeling=separate_modeling,
        gaps_defined=gaps_defined,
        time_field=time_field,
        load_field=load_field,
    )


def add_more_features_m(task_id,
                        parent_id,
                        child_id,
                        operate_status,
                        completed_df,
                        original_time_freq,
                        daily_horizon,
                        forecast_horizon,
                        forecast_start_time,
                        is_training,
                        time_zone,
                        nowtime=None,
                        separate_modeling='true',
                        gaps_defined=None,
                        time_field="record_time",
                        load_field="load"):
    """月前特征工程 (M) -- backward-compatible wrapper."""
    return add_more_features(
        SCENARIO_CONFIGS["M"],
        task_id=task_id,
        parent_id=parent_id,
        child_id=child_id,
        operate_status=operate_status,
        completed_df=completed_df,
        original_time_freq=original_time_freq,
        daily_horizon=daily_horizon,
        forecast_horizon=forecast_horizon,
        forecast_start_time=forecast_start_time,
        is_training=is_training,
        time_zone=time_zone,
        nowtime=nowtime,
        separate_modeling=separate_modeling,
        gaps_defined=gaps_defined,
        time_field=time_field,
        load_field=load_field,
    )
