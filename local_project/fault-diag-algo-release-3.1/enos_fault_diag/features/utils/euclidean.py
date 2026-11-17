#!/usr/bin/env python3
# -*- coding: utf-8 -*
"""
Description : Calculates the euclidean distance
Author      : Cirun Zhang
Contact     : cirun.zhang@envision-digital.com
Time        : 2020/3/31 
Software    : PyCharm
"""
import numpy as np
import features.utils.normalizer as norm


def euclidean_distance(list1, list2):
    """
    Calculates the euclidean distance between two vectors

    Args:
        :param list1: Series 1
        :param list2: Series 2
    Returns:
        :return: Averaged Euclidean distance
    """
    norm1 = norm.normalize(list1)  # normalization
    norm2 = norm.normalize(list2)
    dist = np.sqrt(np.sum(np.square(norm1 - norm2)) / len(norm1))
    return np.round(dist, 6)
