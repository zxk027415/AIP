"""
树模型包装器
实现完整的训练和预测流程
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Any
import xgboost as xgb
from sklearn.linear_model import RidgeCV
from backend.models.model_wrapper import BaseModelWrapper, _ParameterSampler

logger = logging.getLogger(__name__)

class CustomModelEpfWrapper(BaseModelWrapper):
    """
    树模型包装器

    支持: DecisionTree, RandomForest, GradientBoosting

    训练流程：
    1. 数据清洗 (feature_clean)
    2. 构建五折CV索引
    3. 使用一折数据进行超参数搜索
    4. 使用最优参数在五折上分别训练模型
    5. 使用最优参数在全量数据上训练最终模型
    """

    def __init__(self, farm_id: str, capacity: float):
        """
        初始化树模型包装器

        Args:
            farm_id: 场站ID
            capacity: 场站容量
        """
        super().__init__(farm_id, capacity)
        self.nwp_list = None
        self.models = {}


    def _get_model_importance(self, model: Any) -> np.ndarray:
        """获取树模型的特征重要性"""
        return model.feature_importances_

    def _hyperparameter_search(self, X_train: pd.DataFrame, y_train: pd.Series,
                               X_val: pd.DataFrame, y_val: pd.Series,
                               param_grid: Optional[Dict[str, List[Any]]] = None,
                               n_iters: int = 2,
                               **kwargs):
        """
        使用单折数据进行超参数搜索

        Args:
            X_train: 训练特征
            y_train: 训练目标
            X_val: 验证特征
            y_val: 验证目标
            param_grid: 参数网格
            n_iters: 参数采样次数

        Returns:
            score_list: 评分列表
            param_list: 参数列表
        """
        if not param_grid:
            logger.info('没有超参数需要搜索，使用默认参数')
            return [], [{}]

        param_list, score_list, best_ntree_list, importance_by_gain = [], [], [], []

        dtrain = xgb.DMatrix(X_train, y_train, missing=0)
        ddev = xgb.DMatrix(X_val, y_val, missing=0)
        for param in _ParameterSampler(param_grid, n_iters):
            model = xgb.train(param, dtrain, evals=[(dtrain, 'train'), (ddev, 'eval')], verbose_eval=100, **kwargs)
            param_list.append(param)
            score_list.append(model.best_score)
            best_ntree_list.append(model.best_iteration + 1)
            importance_by_gain.append(
                sorted(model.get_score(importance_type='gain').items(), key=lambda k: k[1], reverse=True))
        return score_list, best_ntree_list, param_list, importance_by_gain

    @staticmethod
    def _1st_stacking_feature(nwp):
        input_feature = ['hour', nwp + "_DENSITY", nwp + "_WS",
                         nwp + "_WS_p1", nwp + "_WS_n1",
                         nwp + "_WD", nwp + "_u", nwp + "_v",
                         nwp + "_WS_max", nwp + "_WS_min"]
        if nwp != "IBM":
            input_feature.extend([nwp + "_TMP", nwp + "_PRES"])
        return input_feature, nwp + ".pre_ws"

    @staticmethod
    def _2st_stacking_feature(nwp):
        input_feature_pw = [nwp + ".final_rho3_min", nwp + ".final_rho2_min",
                            nwp + ".final_rho3_median", nwp + ".final_rho3_mean", nwp + ".final_rho3_max",
                            nwp + ".final_rho2_median", nwp + ".final_rho2_mean", nwp + ".final_rho2_max"]
        input_feature_ws = [nwp + '.pre_ws']
        return input_feature_pw, input_feature_ws, nwp + ".final_pw", nwp + '.final_ws'

    def _build_xgb_train(self, x_df, y_df, i_fold, train_name=None):
        if train_name == "power":
            grid_parms = {'seed': [2020], 'eta': [0.01, 0.05, 0.1, 0.3, 0.5], 'max_depth': range(2, 4),
                          'alpha': [0.3, 1, 3, 5, 10], 'min_child_weight': [0.1, 0.3, 3],
                          'subsample': [0.6, 0.7, 0.8], 'lambda': [0.3, 1, 3]}
        else:
            grid_parms = {'seed': [2020], 'eta': [0.00075, 0.05, 0.01, 0.1, 0.3], 'max_depth': range(2, 4),
                          'alpha': [0.3, 1, 3, 5, 10], 'min_child_weight': [0.1, 0.3, 3],
                          'subsample': [0.6, 0.7, 0.8], 'lambda': [0.1, 0.3, 1, 3]}

        X_train, y_train = x_df.loc[i_fold != 0], y_df.loc[i_fold != 0]
        X_val, y_val = x_df.loc[i_fold == 0], y_df.loc[i_fold == 0]
        lscore, lntree, lparam, _ = self._hyperparameter_search(X_train, y_train, X_val, y_val, grid_parms, n_iters=32,
                                                              early_stopping_rounds=8,
                                                              num_boost_round=800)
        idx_min = np.argmin(lscore)
        logging.info("best score: {:.3f}, best_lntree: {},best param:{} feature importance: {}".format(lscore[idx_min],
                                                                                                       lntree[idx_min],
                                                                                                       lparam[idx_min],
                                                                                                       _[idx_min]))
        result, bst = self.cross_prediction(x_df, y_df, i_fold, lparam[idx_min], lntree[idx_min])
        return result, bst, lscore, lntree, lparam

    def _build_xgb_train_copy(self, x_df, y_df, i_fold, lscore, lntree, lparam):
        idx_min = np.argmin(lscore)
        result, bst = self.cross_prediction(x_df, y_df, i_fold, lparam[idx_min], lntree[idx_min])
        return result, bst

    @staticmethod
    def add_feature_rho_crossed(x_df, nwp):
        """添加密度与风速交叉项"""
        logger.debug('Adding density-speed crossed features...')
        tmp_dict = {
            nwp + '.final_rho3_min': 0.5 * x_df[nwp + ".pre_ws_min"] ** 3 * x_df[nwp + '_DENSITY'],
            nwp + '.final_rho3_median': 0.5 * x_df[nwp + ".pre_ws_median"] ** 3 * x_df[nwp + '_DENSITY'],
            nwp + '.final_rho3_mean': 0.5 * x_df[nwp + ".pre_ws_mean"] ** 3 * x_df[nwp + '_DENSITY'],
            nwp + '.final_rho3_max': 0.5 * x_df[nwp + ".pre_ws_max"] ** 3 * x_df[nwp + '_DENSITY'],
            nwp + '.final_rho2_min': 0.5 * x_df[nwp + ".pre_ws_min"] ** 2 * x_df[nwp + '_DENSITY'],
            nwp + '.final_rho2_median': 0.5 * x_df[nwp + ".pre_ws_median"] ** 2 * x_df[nwp + '_DENSITY'],
            nwp + '.final_rho2_mean': 0.5 * x_df[nwp + ".pre_ws_mean"] ** 2 * x_df[nwp + '_DENSITY'],
            nwp + '.final_rho2_max': 0.5 * x_df[nwp + ".pre_ws_max"] ** 2 * x_df[nwp + '_DENSITY']
        }
        return pd.concat([x_df, pd.DataFrame(tmp_dict)], axis=1)

    def _linear_regression_fit_pw(self, x_df, y_df):
        # build a single model
        lr = RidgeCV(alphas=[0.01, 0.1, 1, 10, 100], cv=5)
        lr.fit(x_df, y_df)
        self.models['fusion_pw'] = lr
        result = lr.predict(x_df)
        return result

    def train(self, X: pd.DataFrame, y: pd.DataFrame,
              param_grid: Optional[Dict[str, List[Any]]] = None,
              enable_search: bool = True,
              search_fold: int = 0):
        """
        训练树模型

        流程：
        1. 数据清洗（feature_clean）
        2. 构建五折CV索引
        3. 使用指定fold进行超参数搜索
        4. 使用最优参数在五折上分别训练模型
        5. 使用最优参数在全量数据上训练最终模型

        Args:
            X: 特征矩阵（必须有DatetimeIndex）
            y: 目标变量（DataFrame，包含目标列）
            param_grid: 超参数搜索空间，如果为None则使用默认空间
            enable_search: 是否启用超参数搜索，默认True
            search_fold: 用于超参数搜索的fold编号，默认0

        Returns:
            训练结果字典
        """
        fit_fold = self._create_cv_index(X['i.set'], 5)
        ws_linear = {}
        pw_linear = {}

        self.nwp_list = [x.split('_WS')[0] for x in X.columns if x.endswith('_WS')]
        for nwp in self.nwp_list:
            logging.info(" Training wind speed nwp is : {}".format(nwp))
            input_feature, output_feature = self._1st_stacking_feature(nwp)
            x_clean, y_clean, is_valid = self._feature_clean(X[input_feature], y)
            i_fold, ws_feature = fit_fold[is_valid], {}
            # train wind speed
            res_ws_mean, bst_ws_mean, lscore, lntree, lparam = self._build_xgb_train(x_clean,
                                                                                     np.log1p(y_clean['WS']),
                                                                                     i_fold)
            self.models[output_feature + "_mean"] = bst_ws_mean
            ws_feature[output_feature + "_mean"] = np.expm1(res_ws_mean)

            res_ws_min, bst_ws_min = self._build_xgb_train_copy(x_clean, np.log1p(y_clean['WS_min']),
                                                                i_fold, lscore, lntree, lparam)
            self.models[output_feature + "_min"] = bst_ws_min
            ws_feature[output_feature + "_min"] = np.expm1(res_ws_min)

            res_ws_median, bst_ws_median = self._build_xgb_train_copy(x_clean, np.log1p(y_clean['WS_median']),
                                                                      i_fold,
                                                                      lscore, lntree, lparam)
            self.models[output_feature + "_median"] = bst_ws_median
            ws_feature[output_feature + "_median"] = np.expm1(res_ws_median)

            res_ws_max, bst_ws_max = self._build_xgb_train_copy(x_clean, np.log1p(y_clean['WS_max']), i_fold,
                                                                lscore,
                                                                lntree, lparam)
            self.models[output_feature + "_max"] = bst_ws_max
            ws_feature[output_feature + "_max"] = np.expm1(res_ws_max)

            x_clean = pd.concat([x_clean, pd.DataFrame(ws_feature, index=x_clean.index)], axis=1)

            x_clean = self.add_feature_rho_crossed(x_clean, nwp)

            # power
            logging.info(" Training power ......")
            input_feature_pw, input_feature_ws, output_pw, output_ws = self._2st_stacking_feature(nwp)
            res_pw, bst_pw, _, _, _ = self._build_xgb_train(x_clean[input_feature_pw], y_clean['POWER'] / self.capacity, i_fold,
                                                            "power")
            self.models[output_pw] = bst_pw
            metrics = self._evaluate(y_clean['POWER'], res_pw * self.capacity, self.capacity)
            logging.info("Power metric : {}".format(metrics))

            pw_result = np.nan * np.zeros(len(y))
            pw_result[is_valid] = res_pw
            ws_result = np.nan * np.zeros(len(y))
            ws_result[is_valid] = np.expm1(res_ws_mean)
            pw_linear[output_pw] = pw_result
            ws_linear[output_ws] = ws_result

        pw_train = pd.DataFrame(pw_linear)
        x_train_pw, y_train_pw, is_valid = self._feature_clean(pw_train, y['POWER'])
        res_pw = self._linear_regression_fit_pw(x_train_pw, y_train_pw)
        metrics = self._evaluate(y_train_pw, res_pw * self.capacity, self.capacity)
        logging.info("Power metric : {}".format(metrics))

        self.is_trained = True
        return {"metrics": metrics, "predictions": res_pw}

    def cross_prediction(self, X_clean, y_clean, cv_index, bst_param, num_boost_round, missing=None):
        prediction = np.zeros_like(cv_index, dtype=float) * np.nan
        for idx in np.unique(cv_index):
            dtrain = xgb.DMatrix(X_clean.loc[cv_index != idx], y_clean.loc[cv_index != idx], missing=0)
            dtest = xgb.DMatrix(X_clean.loc[cv_index == idx], y_clean.loc[cv_index == idx], missing=0)
            bst = xgb.train(bst_param, dtrain, num_boost_round)
            prediction[cv_index == idx] = bst.predict(dtest)

        dtrain = xgb.DMatrix(X_clean, y_clean, missing=missing)
        bst = xgb.train(bst_param, dtrain, num_boost_round)
        return prediction, bst

    def _build_xgb_predict(self, model, x_df):
        result = np.nan * np.zeros(len(x_df))
        x_clean, is_valid = self._feature_clean(x_df)
        if x_clean.empty is False:
            result[is_valid] = model.predict(xgb.DMatrix(x_clean))
        return result

    def _linear_regression_predict_pw(self, x_df):
        result = np.zeros(len(x_df)) * np.nan
        try:
            lr = self.models['fusion_pw']
            result = lr.predict(x_df)
        except:
            pass
        return result

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        使用训练好的模型进行预测

        Args:
            X: 特征矩阵

        Returns:
            预测结果数组
        """
        if not self.is_trained:
            raise RuntimeError("模型尚未训练，请先调用train()方法")

        logger.info(f'start predicting farm {self.farm_id} use normal model.')
        assert self.models != {}
        pw_linear = {}
        ws_linear = {}
        for nwp in self.nwp_list:
            input_feature, output_feature = self._1st_stacking_feature(nwp)
            ws_feature = {}
            res_ws_min = self._build_xgb_predict(self.models[output_feature + "_min"], X[input_feature])
            ws_feature[output_feature + "_min"] = np.expm1(res_ws_min)

            res_ws_median = self._build_xgb_predict(self.models[output_feature + "_median"], X[input_feature])
            ws_feature[output_feature + "_median"] = np.expm1(res_ws_median)

            res_ws_mean = self._build_xgb_predict(self.models[output_feature + "_mean"], X[input_feature])
            ws_feature[output_feature + "_mean"] = np.expm1(res_ws_mean)

            res_ws_max = self._build_xgb_predict(self.models[output_feature + "_max"], X[input_feature])
            ws_feature[output_feature + "_max"] = np.expm1(res_ws_max)

            x_df = pd.concat([X, pd.DataFrame(ws_feature, index=X.index)], axis=1)
            x_df = self.add_feature_rho_crossed(x_df, nwp)
            # power
            input_feature_pw, input_feature_ws, output_pw, output_ws = self._2st_stacking_feature(nwp)
            res_pw = self._build_xgb_predict(self.models[output_pw], x_df[input_feature_pw])
            pw_linear[output_pw] = res_pw
            ws_linear[output_ws] = np.expm1(res_ws_mean)

        df_pw = pd.DataFrame(pw_linear)
        final_pw = self._linear_regression_predict_pw(df_pw)
        # 融合层目标是原始POWER值，输出已经是原始功率，不需要再乘capacity
        return final_pw

    def get_feature_importance(self) -> pd.DataFrame:
        """
        获取特征重要性（使用最终模型）

        Returns:
            特征重要性DataFrame
        """
        if not self.is_trained:
            raise RuntimeError("模型尚未训练，请先调用train()方法")

        # 获取最终模型的特征重要性
        importance = self._get_model_importance(self.models)

        # 创建DataFrame
        importance_df = pd.DataFrame({
            'feature': self.feature_names,
            'importance': importance
        })

        # 按重要性降序排序
        importance_df = importance_df.sort_values('importance', ascending=False)
        importance_df = importance_df.reset_index(drop=True)

        return importance_df
