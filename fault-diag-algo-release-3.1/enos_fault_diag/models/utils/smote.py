#!/usr/bin/env python3
# -*- coding: utf-8 -*
"""
Description :

Author      : Cirun Zhang
Contact     : cirun.zhang@envision-digital.com
Time        : 2020/5/20 
Software    : PyCharm
"""

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

import utils.aggregator as aggregator


def make_sample(X, Y, num_to_add):
    """
    Make new vectors

    Args:
        :param X: The features
        :param Y: The prediction values
        :param num_to_add: Number of vectors to add

    Return:
        :return: New X and new Y
    """
    nns = NearestNeighbors(n_neighbors=2).fit(X).kneighbors(X, return_distance=False)[:, 1:]
    rnd_indices = np.random.randint(low=0, high=len(X), size=num_to_add)
    dist = np.random.uniform(-1, 1, num_to_add)  # random distance
    label = Y.iloc[0]

    for i, d in zip(rnd_indices, dist):
        v = X.iloc[i] + d * (X.iloc[i] - X.iloc[nns[i]])
        X = X.append(v)
        Y = Y.append(label)

    return X.reset_index(drop=True), Y.reset_index(drop=True)


def smote(X, Y, limit):
    """
    SMOTE algorithm

    Args:
        :param X: The features
        :param Y: Prediction values
        :param limit: Number of features to generate

    Returns:
        :return: New X and new Y
    """
    x_cols = X.columns
    y_col = Y.columns

    df = pd.concat((X, Y), axis=1)
    df_groups = aggregator.aggregate_data_list(df, key=y_col[0])

    X_new = pd.DataFrame()
    Y_new = pd.DataFrame()

    for gp in df_groups:
        l = len(gp)
        x_tmp = gp[x_cols]
        y_tmp = gp[y_col]

        if l < limit:
            smote_x, smote_y = make_sample(x_tmp, y_tmp, num_to_add=limit - l)
            X_new = X_new.append(smote_x)
            Y_new = Y_new.append(smote_y)

        else:
            X_new = X_new.append(x_tmp)
            Y_new = Y_new.append(y_tmp)

    return X_new, Y_new
