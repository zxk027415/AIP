import itertools
import pandas as pd
from scipy.stats import kurtosis, skew
import numpy as np
from mrmr import mrmr_classif

from tsfresh.feature_extraction.feature_calculators import \
    abs_energy, first_location_of_maximum, first_location_of_minimum, \
    last_location_of_maximum, last_location_of_minimum, \
    absolute_sum_of_changes, benford_correlation, sum_values, \
    variance_larger_than_standard_deviation
from tslearn.metrics import dtw

from features.utils.correlation import autocorrelation_1, \
    autocorrelation_2, autocorrelation_3, spearman_corr, pearson_corr
from features.utils.fluctuation import get_features
from features.utils.statistics import above_mean_ratio, \
    max_min, cid
from features.utils.euclidean import euclidean_distance
from features.utils.lin_reg import get_slope
from features.utils.variation_coefficient import \
    variation_coefficient


class FeatureEngineer:
    def __init__(self, id_cols, value_cols):

        self.id_cols = id_cols
        self.value_cols = value_cols
        self.diff_cols = None
        self.is_diff = True
        self.is_split = False
        self.is_compare = False
        self.is_quantile = True
        self.avg_count = None

    def init_data(self, data):
        self.avg_count = \
            data.groupby(self.id_cols)[self.value_cols].count().mean().mean()
        if self.avg_count < 48:
            self.is_quantile = False

        if self.is_diff:
            self.diff_cols = [f'{value}_diff' for value in self.value_cols]
            if set(self.diff_cols) - set(data.columns):
                data = self.get_diff_data(data, self.id_cols, self.value_cols)

        if len(self.value_cols) > 1:  # todo
            self.is_compare = True

        return data

    def transform(self, df):
        # data initialization
        data = df.copy()
        data = self.init_data(data)

        merge_list = []
        # basic features
        basic_fe = self.get_basic_features(data, self.id_cols, self.value_cols)
        merge_list.append(basic_fe)

        # basic features for diff data
        if self.is_diff:
            diff_basic_fe = self.get_basic_features(
                data, self.id_cols, self.diff_cols)
            merge_list.append(diff_basic_fe)

        # compare features
        if self.is_compare:
            cmp_fe = self.get_compare_features(data, self.id_cols,
                                               self.value_cols)
            merge_list.append(cmp_fe)

        fe_df = pd.concat(merge_list, axis=1)
        fe_df.fillna(0, inplace=True)  # todo
        # fe_df.dropna(axis=1, inplace=True)

        return fe_df

    def get_basic_features(self, df, id_cols, value_cols):
        data = df.copy()
        data = data.dropna(subset=value_cols, how='any')
        data_gps = data.groupby(id_cols)
        merge_list = []

        # stat_fe
        stat_fe = self.get_groupby_features(
            data_gps=data_gps, value_cols=value_cols, fe_funcs=
            [np.nanmax, np.nanmin, np.nanmean, np.nanmedian, np.nanstd,
             kurtosis, skew, max_min])
        merge_list.append(stat_fe)

        # above mean ratio
        above_mean_ratio_fe = self.get_groupby_features(
            data_gps=data_gps, value_cols=value_cols, fe_funcs=above_mean_ratio)
        merge_list.append(above_mean_ratio_fe)

        # variation_coefficient
        variation_coef = self.get_groupby_features(
            data_gps=data_gps, value_cols=value_cols,
            fe_funcs=variation_coefficient)
        merge_list.append(variation_coef)

        # quantile_fe
        if self.is_quantile:
            quantile_fe = self.get_quantile_features(data, id_cols, value_cols)
            merge_list.append(quantile_fe)

        # auto_correlation
        auto_corr_fe = self.get_groupby_features(
            data_gps=data_gps, value_cols=value_cols,
            fe_funcs=[autocorrelation_1, autocorrelation_2, autocorrelation_3])
        merge_list.append(auto_corr_fe)

        # benford_correlation
        benford_fe = self.get_groupby_features(
            data_gps=data_gps, value_cols=value_cols,
            fe_funcs=benford_correlation)
        merge_list.append(benford_fe)

        # sum_fe
        sum_fe = self.get_groupby_features(
            data_gps=data_gps, value_cols=value_cols,
            fe_funcs=[abs_energy, sum_values])
        merge_list.append(sum_fe)

        # absolute_sum_of_changes
        absolute_sum_of_changes_fe = self.get_groupby_features(
            data_gps=data_gps, value_cols=value_cols,
            fe_funcs=absolute_sum_of_changes)
        merge_list.append(absolute_sum_of_changes_fe)

        # loc_fe
        loc_fe = self.get_groupby_features(
            data_gps=data_gps, value_cols=value_cols,
            fe_funcs=[first_location_of_minimum, first_location_of_maximum,
                      last_location_of_minimum, last_location_of_maximum])
        merge_list.append(loc_fe)

        # cid_ce
        cid_fe = self.get_groupby_features(
            data_gps=data_gps, value_cols=value_cols, fe_funcs=cid)
        merge_list.append(cid_fe)

        # variance_larger_than_standard_deviation
        var_vs_dev_fe = self.get_groupby_features(
            data_gps=data_gps, value_cols=value_cols,
            fe_funcs=variance_larger_than_standard_deviation,
            round_n=None)
        var_vs_dev_fe = var_vs_dev_fe.astype(int)
        merge_list.append(var_vs_dev_fe)

        # flat fe
        flat_fe = self.get_flat_features(data, id_cols, value_cols)
        merge_list.append(flat_fe)

        basic_fe = pd.concat(merge_list, axis=1)
        return basic_fe

    def get_compare_features(self, df, id_cols, value_cols):
        data = df.copy()
        data.dropna(subset=value_cols, how='any', inplace=True)
        groups = data.groupby(id_cols)
        merge_list = []

        combinations = list(itertools.combinations(value_cols, 2))
        for col1, col2 in combinations:
            diff_col = f'diff_{col1}_{col2}'
            data[diff_col] = data[col1] - data[col2]

            # stat fe
            stat_fe = self.get_groupby_features(
                data_gps=groups, value_cols=diff_col,
                fe_funcs=[np.nanmax, np.nanstd, np.nanmedian])
            merge_list.append(stat_fe)

            # sum fe
            sum_fe = self.get_groupby_features(
                data_gps=groups, value_cols=diff_col,
                fe_funcs=[absolute_sum_of_changes, sum_values])
            merge_list.append(sum_fe)

            merge_dict = {}
            for key, group in groups:
                merge_dict[key] = {}
                # corr
                spearman = spearman_corr(group[col1], group[col2])
                merge_dict[key][f'{col1}_{col2}_spearman'] = spearman

                pearson = pearson_corr(group[col1], group[col2])
                merge_dict[key][f'{col1}_{col2}_pearson_'] = pearson

                # dist
                eu_dist = euclidean_distance(group[col1], group[col2])
                merge_dict[key][f'{col1}_{col2}_eu_dist'] = eu_dist

                dtw_dist = dtw(group[col1].ravel(), group[col2].ravel())
                merge_dict[key][f'{col1}_{col2}_dtw'] = dtw_dist

                # linear reg
                scope = get_slope(group[col1].ravel(), group[col2].ravel())
                merge_dict[key][f'{col1}_{col2}_scope'] = scope

            tmp_fe_df = pd.DataFrame(merge_dict).T
            merge_list.append(tmp_fe_df)

        cmp_df = pd.concat(merge_list, axis=1)
        return cmp_df

    def get_diff_data(self, data, id_cols, value_cols):
        groups = data.groupby(id_cols)
        diff_cols = [f'{value}_diff' for value in value_cols]

        merge_list = []
        for key, group in groups:
            tmp = group[value_cols].diff()
            tmp.columns = diff_cols
            tmp = group.merge(tmp, left_index=True, right_index=True)
            merge_list.append(tmp)

        new_df = pd.concat(merge_list)
        return new_df

    def get_quantile_features(self, data, id_cols, value_cols):
        quantile_fe = data.groupby(id_cols)[value_cols].agg(
            [lambda x: np.nanquantile(x, 0.15),
             lambda x: np.nanquantile(x, 0.25),
             lambda x: np.nanquantile(x, 0.35),
             lambda x: np.nanquantile(x, 0.65),
             lambda x: np.nanquantile(x, 0.75),
             lambda x: np.nanquantile(x, 0.85),
             lambda x: np.nanquantile(x, 0.95)])
        new_cols = [f'{col}_quantile_{x}' for col in value_cols for x in [15, 25, 35, 65, 75, 85, 95]]
        quantile_fe.columns = new_cols
        quantile_fe = quantile_fe.round(6)
        return quantile_fe

    def get_flat_features(self, data, id_cols, value_cols):
        groups = data.groupby(id_cols)
        merge_dict = {}
        for key, group in groups:
            merge_dict[key] = {}
            for col in value_cols:
                tmp = get_features(group[col].ravel(), tag=col)
                merge_dict[key].update(tmp)
        flat_fe = pd.DataFrame(merge_dict).T
        return flat_fe

    def get_groupby_features(self, value_cols, fe_funcs, data=None,
                             data_gps=None, id_cols=None, round_n=6,
                             *args, **kwargs):
        """
        group data by groupby_cols,
        then extract features on value_cols by fe_funcs.
        """
        if not isinstance(fe_funcs, list):
            fe_funcs = [fe_funcs]
        if not isinstance(value_cols, list):
            value_cols = [value_cols]
        if not data_gps:
            data_gps = data.groupby(id_cols)
        fe_df = data_gps[value_cols].aggregate(
            fe_funcs, *args, **kwargs)  # todo 传参有问题
        fe_df.columns = [f'{col}_{fe}' for col, fe in fe_df.columns]

        if isinstance(round_n, int):
            fe_df = fe_df.round(round_n)
        return pd.DataFrame(fe_df)

    def select_features(self, X, Y, K=50):
        selected_fe = mrmr_classif(X=X, y=Y, K=K)
        return selected_fe


