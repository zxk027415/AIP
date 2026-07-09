#!/usr/bin/env python3
# -*- coding: utf-8 -*
import numpy as np
import pandas as pd


class DataCleaner:
    def __init__(self, value_fields, id_fields, time_field='data_date'):
        self.id_fields = id_fields
        self.value_fields = value_fields
        self.time_field = time_field

    def transform(self, data):
        df = data.copy()
        # check missing
        df = self.check_missing(df)

        # check outliers
        for col in self.value_fields:
            if df.groupby(self.id_fields).count().median()[col] > 24:
                df = df.groupby(self.id_fields).apply(self.get_robust_data, col)

        # already sort in get_robust_data
        # # sort data
        # df = self.sort_data(df, self.id_fields, self.time_field)
        return df

    def check_missing(self, data, keep_threshold=0.75):
        """
        Drop data slices if not-null counts of any features less than its
        minimum keep length.
        The median of not-null counts of every feature is used as its reference
        data length.
        """
        df = data.copy()
        groupby_series = [df[col] for col in self.id_fields]
        not_null_count = df[self.value_fields].notnull().groupby(
            groupby_series).sum()
        not_null_count_median = not_null_count.median()
        min_keep_len = not_null_count_median * keep_threshold
        print('min_keep_len', min_keep_len)
        check_df = (not_null_count < min_keep_len).any(axis=1)
        keep_df = check_df[~check_df].reset_index()
        keep_index = keep_df[self.id_fields]
        df = df.merge(keep_index, on=self.id_fields, how='right')
        return df

    def get_robust_data(self, data, value_col):
        """
        drop a maximum value and a minimum value to avoid extreme outliers
        """
        robust_data = data.copy()
        robust_data[f'{value_col}_diff'] = robust_data[value_col].diff()
        robust_data = robust_data.sort_values(by=f'{value_col}_diff')
        # the last one is np.nan bc of diff
        new_val = [np.nan] + robust_data[value_col][1:-2].tolist() + [np.nan, np.nan]
        robust_data[value_col] = new_val
        robust_data.sort_index(inplace=True)
        return robust_data

    def sort_data(self, data, id_cols, sort_col):
        """
        sort every group of data by sort_col
        """
        merge_list = []
        for key, group in data.groupby(id_cols):
            tmp = group.sort_values(by=sort_col)
            merge_list.append(tmp)

        new_data = pd.concat(merge_list)
        return new_data
