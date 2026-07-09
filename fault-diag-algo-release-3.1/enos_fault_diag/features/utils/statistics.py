from tsfresh.feature_extraction.feature_calculators import count_above_mean, \
    cid_ce
import numpy as np


def above_mean_ratio(I):
    return count_above_mean(I) / len(I)


def max_min(I):
    return np.nanmax(I) - np.nanmin(I)


def cid(I):
    return cid_ce(I, True)
