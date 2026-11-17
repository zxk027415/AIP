#!/usr/bin/env python3
# -*- coding: utf-8 -*
"""
Description : Random forest training module
Author      : Cirun Zhang
Contact     : cirun.zhang@envision-digital.com
Time        : 2020/4/10 
Software    : PyCharm
"""
import logging
import pickle
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from models.utils.smote import smote

logger = logging.getLogger(__name__)

np.set_printoptions(suppress=True)


class RandomForest:
    def __init__(self):
        self.model = None
        self.description = None

    def train(self, X_train, Y_train, n_estimators=80, is_smote=True, smote_num=500):
        if is_smote:
            print('smote...')
            try:
                X, Y = smote(X_train, Y_train, limit=smote_num)
            except Exception as e:
                logging.error('smote error')
                logging.error(e)
                X, Y = X_train, Y_train
        else:
            X, Y = X_train, Y_train

        Y = Y.to_numpy().ravel()
        print('train...')

        self.model = RandomForestClassifier(n_estimators=n_estimators, random_state=90, n_jobs=-1)
        self.model.fit(X, Y)

        print('done.')

    def predict(self, X_test):
        print('predict...')

        Y_pred = self.model.predict(X_test)

        print('done.')
        return Y_pred

    def save_model(self, path, model_tag):
        if not path.endswith('/'):
            path += '/'
        with open(path + '%s.pkl' % model_tag, 'wb') as file:
            pickle.dump(self.model, file)

    def get_feature_importance(self):
        return self.model.feature_importances_

