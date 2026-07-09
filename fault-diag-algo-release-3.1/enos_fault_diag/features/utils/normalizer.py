#!/usr/bin/env python3
# -*- coding: utf-8 -*
"""
Description : Normalize the data
Author      : Cirun Zhang
Contact     : cirun.zhang@envision-digital.com
Time        : 2020/3/31 
Software    : PyCharm
"""

import numpy as np


def normalize(data):
    """
    Normalize the data

    Args:
        :param data: Input vector

    Returns:
        :return: Normalized data
    """
    max_ = np.max(data)
    min_ = np.min(data)
    data = (data - min_) / (max_ - min_ + 1e-10)
    return data
