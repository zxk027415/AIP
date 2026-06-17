# -*- coding: utf-8 -*-
"""
统一模型训练模块（纯 XGBoost）

移除了 N-BEATS 深度学习模型，原因：
- 原项目中两个入口均硬编码 specify_model='xgb'，N-BEATS 从未被实际使用
- N-BEATS 是单变量模型，无法利用气象特征（温度、风速、辐照等）
- TensorFlow/Keras 是项目中最重的依赖，仅为此一个模型服务
"""
import gc
import copy
import numpy as np
import pandas as pd
import xgboost as xgb
from forecast_utils import smape
from loguru import logger
from common.holidays import if_workday
from common.constants import ScenarioConfig, SCENARIO_CONFIGS
from sklearn.model_selection import KFold
from bayes_opt import BayesianOptimization
from sklearn.metrics import mean_squared_error as mse
from bayes_opt import UtilityFunction


def xgb_model_trainer(x_train, y_train, forecast_length, nfolds=5, set_weight_ac=0.99):
    '''
    XGBoost model trainer with Bayesian Optimization
    '''
    logger.info(f"'xgb_model_trainer' input param:\n"
                f"x_train:\n{x_train}\n"
                f"y_train:\n{y_train}\n"
                f"forecast_length:\n{forecast_length}\n")

    # 特征列排序确保特征一致
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]

    feature_list = list(feat_columns)
    logger.info(f"get sorted feature_list for xgb. \nfeature_list: \n{feature_list}")

    def sample_weigths(train_label, ac=set_weight_ac):
        """样本权重(近、中、远)"""
        train_len = len(train_label)
        sample_weight = []
        for i in range(train_len):
            sample_weight.append(pow(ac, i // forecast_length))
        sample_weight = np.array(list(reversed(sample_weight)))
        return sample_weight

    def xgb_crossval(eta, max_depth, min_child_weight, subsample, lambdas, x_train, y_train):
        folds = KFold(n_splits=nfolds, shuffle=True, random_state=10)
        oof = np.zeros(x_train.shape[0])
        for fold_, (trn_idx, val_idx) in enumerate(folds.split(x_train, y_train)):
            trn_data = xgb.DMatrix(x_train.iloc[trn_idx], label=y_train.iloc[trn_idx], missing=0)
            val_data = xgb.DMatrix(x_train.iloc[val_idx], label=y_train.iloc[val_idx], missing=0)
            param = {
                'objective': 'reg:linear', 'booster': 'gbtree', 'eval_metric': 'rmse', 'silent': 1,
                'max_depth': int(max_depth), 'min_child_weight': float(min_child_weight),
                'subsample': float(subsample), 'eta': float(eta), 'lambda': float(lambdas),
                'seed': 100, 'nthread': 13, 'verbosity': 0
            }
            clf = xgb.train(param, trn_data, 100, evals=[(trn_data, 'train'), (val_data, 'valid')],
                            verbose_eval=0, early_stopping_rounds=5, xgb_model=None)
            oof[val_idx] = clf.predict(val_data)
            del clf, trn_idx, val_idx
            gc.collect()
        return -mse(y_train, oof) ** 0.5

    def optimize_xgb(train_x, train_y):
        def xgb_cv(eta, max_depth, min_child_weight, subsample, lambdas):
            return xgb_crossval(eta, max_depth, min_child_weight, subsample, lambdas, train_x, train_y)

        crossval_params = {
            'eta': (0.01, 0.1),
            'max_depth': (2, 7),
            'min_child_weight': (0.3, 8),
            'subsample': (0.3, 1),
            'lambdas': (0.1, 100)
        }
        xgb_op = BayesianOptimization(xgb_cv, crossval_params)
        xgb_op.set_gp_params(
            alpha=1e-6, n_restarts_optimizer=10, normalize_y=True
        )
        utility = UtilityFunction(kind="ei", kappa=2.5, xi=0.0)
        xgb_op.maximize(init_points=5, n_iter=25, acquisition_function=utility)

        print("Final result:", xgb_op.max)
        bst_params = xgb_op.max['params']
        bst_params['max_depth'] = int(bst_params['max_depth'])

        dtrain = xgb.DMatrix(x_train, y_train, missing=0, weight=sample_weigths(y_train))
        dtest = xgb.DMatrix(x_train, y_train, missing=0, weight=sample_weigths(y_train))

        bst_model = xgb.train(bst_params, xgb.DMatrix(x_train, label=y_train), 200,
                              evals=[(dtrain, 'train'), (dtest, 'eval')], early_stopping_rounds=6, verbose_eval=50)
        importance_by_gain = sorted(bst_model.get_score(importance_type='gain').items(), key=lambda k: k[1],
                                    reverse=True)
        logger.info(f"features importance: \n{importance_by_gain}")
        return bst_model

    logger.info(f"训练xgb采用{nfolds}折交叉验证. ")
    trained_model = optimize_xgb(x_train, y_train)
    logger.info(f"'xgb_model_trainer' output param:\n"
                f"trained_model\n"
                f"feature_list:\n{feature_list}\n")
    return trained_model, feature_list


def model_prefer_trainer(feat_df,
                         daily_horizon,
                         forecast_horizon,
                         scenario,
                         separate_modeling='true',
                         retrain=None,
                         time_field="record_time",
                         load_field="load"):
    """
    统一 XGBoost 模型训练

    Parameters
    ----------
    feat_df: 特征工程后输入
    daily_horizon: 数据日长度
    forecast_horizon: 预测长度
    scenario: ScenarioConfig 场景配置
    separate_modeling: 是否分开建模 ('true'/'false')
    retrain: 训练后是否用全量数据重新训练（None 时使用场景默认值）
    time_field: 时间字段
    load_field: 负荷字段
    """
    task_type = scenario.task_type
    if retrain is None:
        retrain = scenario.default_retrain

    logger.info(f"******************** model_prefer_trainer_{task_type.lower()} ********************")
    logger.info(f"'model_prefer_trainer_{task_type.lower()}' input params:\n"
                f"feat_df:\n{feat_df}\n"
                f"daily_horizon:\n{daily_horizon}\n"
                f"forecast_horizon:\n{forecast_horizon}\n"
                f"separate_modeling:\n{separate_modeling}\n"
                f"retrain:\n{retrain}\n")

    # 结果以字典形式保存
    total_xgb_model = {}
    total_feature_list = {}
    total_auto_model_tag = {}

    daily_horizon = int(daily_horizon)
    forecast_horizon = int(forecast_horizon)
    feat_df_copy = copy.deepcopy(feat_df)

    # ---------- 场景差异：forecast_length 和 prefer_unit_len 的计算 ----------
    if task_type == "DI":
        forecast_length = len(feat_df_copy['real_forecast_timestamps'])
        prefer_unit_len = scenario.prefer_unit_len
        prefer_length = prefer_unit_len * forecast_length
    else:
        pred_include_days = feat_df_copy['pred_include_days']
        all_day_pred_len = len(pred_include_days) * daily_horizon
        workday_pred_len = len([d for d in pred_include_days if if_workday(pd.to_datetime(d))]) * daily_horizon
        holiday_pred_len = len([d for d in pred_include_days if not if_workday(pd.to_datetime(d))]) * daily_horizon

        prefer_unit_len = scenario.prefer_unit_len
        total_forecast_length = {"all_day_pred_len": all_day_pred_len,
                                 "workday_pred_len": workday_pred_len,
                                 "holiday_pred_len": holiday_pred_len}
        logger.info(f"The total_forecast_length is: \n {total_forecast_length}. ")

    pred_col = load_field

    # loop select
    use_feat_types = [key for key in feat_df_copy.keys() if key.endswith("feat_df")]
    use_feat_types = [n for n in use_feat_types if n.startswith("workday") or n.startswith("holiday")
                      ] if separate_modeling == 'true' else ["all_day_feat_df"]
    logger.info(f"separate_modeling：{separate_modeling}，所需feat_type：{use_feat_types}. ")

    for feat_type in use_feat_types:
        public_field = feat_type[:-8]
        logger.info(f"Start to train xgb for {public_field} days. ")

        if task_type != "DI":
            forecast_length = total_forecast_length[f"{public_field}_pred_len"]
            if not forecast_length:
                logger.warning(f"forecast_length is: {forecast_length}, skip {public_field}.")
                continue

        prefer_length = prefer_unit_len * forecast_length

        tmp_feat_df = feat_df_copy[feat_type]
        tmp_feat_df.set_index(keys=[time_field], drop=True, inplace=True)
        tmp_feat_df.index = pd.to_datetime(tmp_feat_df.index)
        tmp_feat_df = tmp_feat_df[tmp_feat_df.index <= tmp_feat_df[[pred_col]].dropna().index[-1]]

        # 全部真值
        train_data = tmp_feat_df[pred_col].values.flatten()
        # 优选验证目标数据
        prefer_valid_data = train_data[-prefer_length:]
        xgb_train_df = tmp_feat_df.iloc[:-prefer_length]

        # ---- XGBoost 训练 ----
        if retrain:
            logger.info(f"训练xgb模型，训练数据不包含选优集. ")
            y_train = xgb_train_df[pred_col]
            x_train = copy.deepcopy(xgb_train_df)
            x_train.drop(pred_col, axis=1, inplace=True)
            prefer_xgb_model, feature_list = xgb_model_trainer(x_train, y_train, forecast_length)
        else:
            logger.info(f"训练xgb模型，训练数据包含选优集. ")
            y_train = tmp_feat_df[pred_col]
            x_train = copy.deepcopy(tmp_feat_df)
            x_train.drop(pred_col, axis=1, inplace=True)
            prefer_xgb_model, feature_list = xgb_model_trainer(x_train, y_train, forecast_length)

        logger.info(f"complete training xgb for {public_field}. ")

        # 选优验证
        prefer_xgb_inputs = tmp_feat_df.iloc[-prefer_length:]
        prefer_xgb_inputs = prefer_xgb_inputs[feature_list]
        prefer_matrix = xgb.DMatrix(prefer_xgb_inputs)
        xgb_prefer_output = prefer_xgb_model.predict(prefer_matrix).flatten()
        xgb_prefer_metric = 1 - smape(prefer_valid_data, xgb_prefer_output) / 100
        logger.info(f"xgb_prefer_metric for {public_field}: {xgb_prefer_metric}")

        if retrain:
            logger.info(f"重新训练xgb模型. ")
            y_train = tmp_feat_df[pred_col]
            x_train = copy.deepcopy(tmp_feat_df)
            x_train.drop(pred_col, axis=1, inplace=True)
            prefer_xgb_model, feature_list = xgb_model_trainer(x_train, y_train, forecast_length)
            logger.info(f"xgb模型重新训练完毕. ")

        # save
        total_xgb_model[public_field + "_xgb"] = prefer_xgb_model
        total_feature_list[public_field + "_feature_list"] = feature_list
        total_auto_model_tag[public_field + "_auto_model"] = "xgb"

    logger.info(f"'model_prefer_trainer_{task_type.lower()}' output params:\n"
                f"total_xgb_model:{type(total_xgb_model)}\n"
                f"total_feature_list:\n{total_feature_list}\n"
                f"total_auto_model_tag:\n{total_auto_model_tag}\n"
                f"daily_horizon:\n{daily_horizon}\n")
    return total_xgb_model, total_feature_list, total_auto_model_tag, daily_horizon


# ==================== 向后兼容包装器 ====================
def model_prefer_trainer_di(feat_df, daily_horizon, forecast_horizon, specify_model='xgb',
                            separate_modeling='false', retrain=False, time_field="record_time", load_field="load"):
    return model_prefer_trainer(feat_df, daily_horizon, forecast_horizon,
                                scenario=SCENARIO_CONFIGS["DI"],
                                separate_modeling=separate_modeling,
                                retrain=retrain, time_field=time_field, load_field=load_field)


def model_prefer_trainer_d(feat_df, daily_horizon, forecast_horizon, specify_model='xgb',
                           separate_modeling='true', retrain=True, time_field="record_time", load_field="load"):
    return model_prefer_trainer(feat_df, daily_horizon, forecast_horizon,
                                scenario=SCENARIO_CONFIGS["D"],
                                separate_modeling=separate_modeling,
                                retrain=retrain, time_field=time_field, load_field=load_field)


def model_prefer_trainer_wi(feat_df, daily_horizon, forecast_horizon, specify_model='xgb',
                            separate_modeling='true', retrain=True, time_field="record_time", load_field="load"):
    return model_prefer_trainer(feat_df, daily_horizon, forecast_horizon,
                                scenario=SCENARIO_CONFIGS["WI"],
                                separate_modeling=separate_modeling,
                                retrain=retrain, time_field=time_field, load_field=load_field)


def model_prefer_trainer_w(feat_df, daily_horizon, forecast_horizon, specify_model='xgb',
                           separate_modeling='true', retrain=True, time_field="record_time", load_field="load"):
    return model_prefer_trainer(feat_df, daily_horizon, forecast_horizon,
                                scenario=SCENARIO_CONFIGS["W"],
                                separate_modeling=separate_modeling,
                                retrain=retrain, time_field=time_field, load_field=load_field)


def model_prefer_trainer_mi(feat_df, daily_horizon, forecast_horizon, specify_model='xgb',
                            separate_modeling='true', retrain=False, time_field="record_time", load_field="load"):
    return model_prefer_trainer(feat_df, daily_horizon, forecast_horizon,
                                scenario=SCENARIO_CONFIGS["MI"],
                                separate_modeling=separate_modeling,
                                retrain=retrain, time_field=time_field, load_field=load_field)


def model_prefer_trainer_m(feat_df, daily_horizon, forecast_horizon, specify_model='xgb',
                           separate_modeling='true', retrain=False, time_field="record_time", load_field="load"):
    return model_prefer_trainer(feat_df, daily_horizon, forecast_horizon,
                                scenario=SCENARIO_CONFIGS["M"],
                                separate_modeling=separate_modeling,
                                retrain=retrain, time_field=time_field, load_field=load_field)
