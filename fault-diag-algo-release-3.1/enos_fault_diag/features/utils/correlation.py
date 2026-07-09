#!/usr/bin/env python3
# -*- coding: utf-8 -*
import numpy as np
from scipy.stats import stats
from tsfresh.feature_extraction.feature_calculators import autocorrelation


def autocorrelation_1(I):
    return autocorrelation(I, 1)


def autocorrelation_2(I):
    return autocorrelation(I, 2)


def autocorrelation_3(I):
    return autocorrelation(I, 3)


def spearman_corr(series1, series2):
    if round(np.std(series1), 6) == 0 or round(np.std(series2), 6) == 0:
        return 0
    else:
        return stats.spearmanr(series1, series2)[0]


def pearson_corr(series1, series2):
    if round(np.std(series1), 6) == 0 or round(np.std(series2), 6) == 0:
        return 0
    else:
        return stats.pearsonr(series1, series2)[0]
