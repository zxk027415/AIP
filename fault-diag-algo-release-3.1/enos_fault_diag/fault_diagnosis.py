#!/usr/bin/env python3
# -*- coding: utf-8 -*
import json
import logging
import time

import pandas as pd
import numpy as np
from data_cleaning.data_cleaner import DataCleaner
from features.feature_engineer import FeatureEngineer
from models.rnd_fst import RandomForest
from utils.time import set_time_window, set_time_zone, local_timezone

np.set_printoptions(suppress=True)

logger = logging.getLogger(__name__)


class FaultDiagnosis:
    def __init__(self, time_zone, window_one_label=1, diagnosis_window='1d',
                 time_field='time', label_field='label',
                 value_fields=None, id_fields=None):
        if id_fields is None:
            id_fields = ['site_id', 'device_id', 'branch_id']
        if not isinstance(id_fields, list):
            id_fields = list(id_fields)
        self.time_zone = time_zone
        self.diagnosis_window = diagnosis_window
        self.window_one_label = window_one_label
        self.time_field = time_field
        self.label_field = label_field
        self.id_fields = id_fields
        self.value_fields = value_fields
        self.time_window_field = 'time_window'
        self.feature_list = []
        self.model = None

    def init_data(self, data_set):
        data = data_set.copy()

        # set time zone  todo
        # data = set_time_zone(data, time_col=self.time_field,
        #                      init_time_zone=None,
        #                      target_time_zone=self.time_zone)

        # clean data
        data_cleaner = DataCleaner(self.value_fields, self.id_fields,
                                   self.time_field)
        print('before clean', data.shape)
        data = data_cleaner.transform(data)
        print('after clean', data.shape)

        try:
            data.loc[:, self.value_fields] = \
                data.loc[:, self.value_fields].astype(float)
        except Exception as e:
            logging.error('Value fields of data cannot be changed to float.')
            logging.error(e)
            raise ValueError('Value fields of data cannot be changed to float.')

        return data

    def train(self, source_dataset):
        logging.info('training start')
        data = source_dataset.copy()

        # data initialization
        logging.info('data initialization')

        data = self.init_data(data)
        label_df = data.groupby(self.id_fields)[self.label_field].max()

        # feature engineering
        logging.info('feature engineering')

        if self.window_one_label == 1:
            fe_engineerer = FeatureEngineer(self.id_fields, self.value_fields)
            fe_df = fe_engineerer.transform(data)
        else:
            fe_engineerer = None
            fe_df = pd.DataFrame()

        # merge label
        fe_df = pd.concat([fe_df, label_df], axis=1)
        fe_df = fe_df.dropna(how='any')  # todo
        X_train = fe_df.drop(self.label_field, axis=1)
        Y_train = fe_df[[self.label_field]]

        # feature selection
        logging.info('feature selection')

        self.feature_list = fe_engineerer.select_features(X_train, Y_train)
        if not self.feature_list:
            logging.error('Feature selection error, feature list is empty')
            logging.error(f'Unique label for debug: {fe_df[self.label_field].unique()}')
            raise ValueError('Feature selection error, feature list is empty')

        X_train = X_train[self.feature_list]

        # model training  # todo params opt
        logging.info('model training')
        clf_model = RandomForest()
        clf_model.train(X_train, Y_train)

        self.model = clf_model.model

    def predict(self, model, predict_dataset):
        logging.info('prediction start')

        # data cleaning
        data = predict_dataset.copy()

        # data initialization
        logging.info('data initialization')
        data = self.init_data(data)

        if self.window_one_label == 1:
            # feature engineering
            logging.info('feature engineering')
            fe_engineerer = FeatureEngineer(self.id_fields, self.value_fields)
            t1 = time.time()
            fe_df = fe_engineerer.transform(data)
            t2 = time.time()
            print('feature engineer', t2-t1)
            fe_df = fe_df[self.feature_list]

            # model prediction
            logging.info('model prediction')
            pred_y = model.predict(fe_df)
            fe_df['predict_label'] = pred_y
            label_df = fe_df[['predict_label']].reset_index()
            label_df.columns = self.id_fields + ['predict_label']
        else:
            label_df = pd.DataFrame(columns=self.id_fields + ['predict_label'])

        rtn_df = label_df.copy()
        rtn_df[self.time_field] = rtn_df[self.time_window_field]
        logging.info('prediction done')
        return rtn_df

    def get_feature_importance(self):
        return self.model.feature_importances_
