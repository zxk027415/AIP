#!/usr/bin/env python3
# -*- coding: utf-8 -*
"""
Description :

Author      : Danni Li
Time        : 2021-10-10
Software    : PyCharm
"""
import numpy as np
import pandas as pd


def outlier_detect_mean_std(data, col, threshold=3):
    """
    outlier detection by Mean and Standard Deviation Method.
    If a value is a certain number(called threshold) of standard deviations away
    from the mean, that data point is identified as an outlier.
    Default threshold is 3.
    This method can fail to detect outliers because the outliers increase the standard deviation.
    The more extreme the outlier, the more the standard deviation is affected.
    """
    upper_fence = data[col].mean() + threshold * data[col].std()
    lower_fence = data[col].mean() - threshold * data[col].std()
    tmp = pd.concat([data[col] > upper_fence, data[col] < lower_fence], axis=1)
    outlier_index = tmp.any(axis=1)
    return outlier_index


def outlier_detect_arbitrary(data, col, upper_fence=10e3, lower_fence=-10e3):
    """
    identify outliers based on arbitrary boundaries passed to the function.
    """
    tmp = pd.concat([data[col] > upper_fence, data[col] < lower_fence], axis=1)
    outlier_index = tmp.any(axis=1)
    return outlier_index
