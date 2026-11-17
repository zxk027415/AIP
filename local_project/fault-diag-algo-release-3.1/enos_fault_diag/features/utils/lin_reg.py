#!/usr/bin/env python3
# -*- coding: utf-8 -*

from numpy import polyfit
from sklearn.linear_model import LinearRegression


def get_slope(list1, list2):
    """
    Performs linear regression on two vectors

    Args:
        :param list1: Vector 1
        :param list2: Vector 2

    Returns:
        :return: The slope of regression line
    """
    lin_reg = LinearRegression()
    lin_reg.fit(list1.reshape(-1, 1), list2.reshape(-1, 1))
    slope = round(lin_reg.coef_[0][0], 6)
    return slope