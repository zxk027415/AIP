# -*- coding: utf-8 -*-
"""
统一的节假日/工作日判断工具模块

消除 data_process.py / feature_eng.py / model_prefer.py / post_process.py 中的重复定义
"""
import pandas as pd
from chinese_calendar import is_workday


def if_workday(date):
    """
    判断给定日期是否为中国工作日

    :type date: datetime.date | datetime.datetime | str
    :rtype: bool
    """
    date = pd.to_datetime(date)
    try:
        flag = is_workday(date)
    except Exception as e:
        print(e)
        weekday = date.weekday()
        flag = weekday <= 4
    return flag
