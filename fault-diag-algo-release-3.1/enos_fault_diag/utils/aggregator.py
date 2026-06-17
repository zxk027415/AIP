#!/usr/bin/env python3
# -*- coding: utf-8 -*
"""
Description : Group data by columns
Author      : Cirun Zhang
Contact     : cirun.zhang@envision-digital.com
Time        : 2020/4/8 
Software    : PyCharm
"""
import pandas as pd


def aggregate_data_list(data, key):
    """
    Aggregates data based on a specific column

    Args:
        :param data: Data frame
        :param key: Name of the column to aggregate

    Return:
        :return: Aggregated data as a list
    """
    data_groupby = data.groupby([key])
    groups = [data_groupby.get_group(x) for x in data_groupby.groups]

    group_aggregate = []
    for group in groups:
        tmp = pd.DataFrame(group, columns=data.columns)
        tmp = tmp.reset_index(drop=True)
        if len(tmp) > 0:
            group_aggregate.append(tmp)

    return group_aggregate


def aggregate_data_dict(data, key):
    """
    Aggregates data based on a specific column

    Args:
        :param data: Data frame
        :param key: Name of the column to aggregate

    Return:
        :return: Aggregated data as a dictionary
    """
    data_groupby = data.groupby([key])
    groups = [data_groupby.get_group(x) for x in data_groupby.groups]

    group_aggregate = {}
    for group in groups:
        tmp = pd.DataFrame(group, columns=data.columns)
        tmp = tmp.reset_index(drop=True)
        if len(tmp) > 0:
            group_aggregate[tmp.loc[0, key]] = tmp

    return group_aggregate
