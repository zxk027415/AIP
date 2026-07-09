#!/usr/bin/env python3
# -*- coding: utf-8 -*
"""
Description : Computes fluctuation features
Author      : Cirun Zhang, Danni Li
Contact     : danni.li@envision-digital.com
Time        : 2021/12/3
Software    : PyCharm
"""
import numpy as np
import pandas as pd


def gradient(data):
    """
    Compute the gradient array

    Args:
        :param data: time series data

    Returns:
        :return: flat_rate: the rate of zero point in gradient array
        :return: flat_max: maximum size of flat zone
        :return: flat_count: count of how many flat zone
    """

    if len(data) < 2:
        return data

    tmp = np.copy(data)
    tmp = np.delete(tmp, 0)
    return np.round(tmp - data[:-1], 3)


def get_features(data, tag):
    """
    Computes fluctuation features
    """
    grad = gradient(data)
    flat_count = sum(grad == 0)
    flat_rate = round(flat_count / len(data), 6)  # 无波动率
    max_drop = np.max(np.abs(grad))

    count = 0
    flat_area = []
    for i in range(0, len(grad)):
        if grad[i] == 0:
            count += 1

        if (grad[i] != 0 or i == len(grad) - 1) and count > 0:
            flat_area.append(count)
            count = 0

    if len(flat_area) == 0:
        flat_max = 0
    else:
        flat_max = max(flat_area)

    rtn_dict = {f'{tag}_flat_rate': flat_rate,
                f'{tag}_flat_max': flat_max,
                f'{tag}_flat_count': len(flat_area),
                f'{tag}_max_drop': max_drop}

    return rtn_dict


# @get_run_time
def get_rolling_features(I_real, I_cal, window=8):
    """
    get rolling flat features
    Args:
        data: np.darray
        tag: str, tag of feature

    Returns:

    """
    rolling_matrix = [I_real[i: i+window] for i in range(len(I_real)-window+1)]
    rolling_sort = [np.sort(array[~np.isnan(array)])[1:-1]
                    for array in rolling_matrix]
    rolling_grad = [np.max(array) - np.min(array) for array in rolling_sort
                    if len(array) > 1]
    if rolling_grad:
        max_rolling_grad = np.max(rolling_grad)
        # I_real = np.sort(I_real)[1: -1]  # todo 没有波动 全为零
        I_cal_range = np.nanmax(I_cal) - np.nanmin(I_cal)
        max_rolling_grad_ratio = max_rolling_grad / I_cal_range if I_cal_range else 0
        return {'max_rolling_grad': round(max_rolling_grad, 6),
                'max_rolling_grad_ratio': round(max_rolling_grad_ratio, 6)}
    else:
        return {'max_rolling_grad': np.nan,
                'max_rolling_grad_ratio': np.nan}


if __name__ == '__main__':
    data = [1, -2, 3, 4, 6]
    print(gradient(data))