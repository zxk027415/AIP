import numpy as np


def variation_coefficient(I):
    return np.nanstd(I) / np.nanmean(I) if np.nanmean(I) != 0 else 0

