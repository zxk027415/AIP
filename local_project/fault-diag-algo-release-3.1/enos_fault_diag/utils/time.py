# -*- coding: utf-8 -*-
"""
time utilites
@author: qi.cheng, danni.li
"""
import json
import logging

import pandas as pd
import tzlocal
from pytz import timezone
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def local_timezone():
    return timezone(tzlocal.get_localzone_name())


def local_now():
    return datetime.now(tz=local_timezone())


def convert_timezone(date_time, target_timezone):
    return date_time.astimezone(timezone(target_timezone))


def format_time(time, tz=False):
    if tz:
        return time.strftime('%Y-%m-%d %H:%M:%S %z')
    else:
        return time.strftime('%Y-%m-%d %H:%M:%S')


def format_date(time):
    return time.strftime('%Y-%m-%d')


def format_timestr(timestr):
    try:
        ts = datetime.strptime(timestr, "%Y-%m-%d %H:%M:%S")
    except Exception:
        ts = datetime.strptime(timestr, '%Y-%m-%d')
    return ts


def detect_time_freq(data, time_col):
    """
    detect frequency of time series by using diff method
    :param data: df
    :param time_col: str
    :return: freq: timedelta
    """
    df = data.copy()
    df[time_col] = pd.to_datetime(df[time_col])
    freq = df[time_col].diff().mode()[0]
    return freq


def set_time_window(data, id_cols, time_col, freq, solar_mode=None, **solar_kwargs):
    """
    set time window for data.

    solar_mode=None 时：走原有 resample 逻辑。
    solar_mode 非空时：委托给 segment_solar_window()。
    """
    if solar_mode:
        from utils.solar_window import segment_solar_window
        segmented, _warnings = segment_solar_window(
            data,
            id_cols=id_cols,
            time_col=time_col,
            value_cols=solar_kwargs.get("value_cols", []),
            solar_mode=solar_mode,
            irr_threshold=solar_kwargs.get("irr_threshold", 0.05),
            peak_ratio=solar_kwargs.get("peak_ratio", 0.30),
            sub_window=solar_kwargs.get("sub_window", "4h"),
            power_col=solar_kwargs.get("power_col"),
        )
        return segmented

    new_freq = get_standard_freq(freq)

    merge_list = []
    groups = data.groupby(id_cols)

    for key, group in groups:
        tmp_df = group.copy()
        tmp_df.drop_duplicates(subset=id_cols + [time_col], inplace=True)
        tmp_df[time_col] = pd.to_datetime(tmp_df[time_col])
        tmp_df.set_index(time_col, inplace=True)
        tmp_df.sort_index(inplace=True)
        df_resample = tmp_df.resample(new_freq, label='left').asfreq()
        df_resample['time_window'] = df_resample.index
        tmp_df = pd.merge_asof(tmp_df, df_resample[['time_window']],
                               left_index=True,
                               right_index=True)
        tmp_df.reset_index(inplace=True)
        merge_list.append(tmp_df)

    df = pd.concat(merge_list)

    return df


def set_time_zone(data, time_col, target_time_zone, init_time_zone=None):
    """
    set time zone for data
    """
    df = data.copy()
    df[time_col] = pd.to_datetime(df[time_col])
    if df[time_col].iloc[0].tzinfo is None and init_time_zone is None:
        df[time_col] = df[time_col].dt.tz_localize(target_time_zone)
    elif df[time_col].iloc[0].tzinfo is None and init_time_zone:
        df[time_col] = df[time_col].dt.tz_localize(
            init_time_zone).dt.tz_convert(target_time_zone)
    elif df[time_col].iloc[0].tzinfo:
        df[time_col] = df[time_col].dt.tz_convert(target_time_zone)

    return df


def get_standard_freq(time_freq_str):
    num, time_unit = time_freq_str[:-1], time_freq_str[-1]
    time_unit_mapping = {
        'm': 't',
        'w': 'w-mon',  # set monday as start day
    }
    if time_unit in time_unit_mapping.keys():
        time_unit = time_unit_mapping[time_unit]

    return num + time_unit


def timedelta_f_freqstr(time_freq_str):
    """
    parse time_freq_str to timedelta
    :param time_freq_str: for example, '5t'
    :return:
    """
    num, time_unit = time_freq_str[:-1], time_freq_str[-1]
    num = int(num)
    time_unit_mapping = {
        'm': timedelta(minutes=num),
        't': timedelta(minutes=num),
        'h': timedelta(hours=num),
        'd': timedelta(days=num),
        'w': timedelta(weeks=num)
    }
    if time_unit not in time_unit_mapping.keys():
        logging.error('time unit error')
    return time_unit_mapping[time_unit]
