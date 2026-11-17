# -*- coding: utf-8 -*-
"""
统一 MLflow 模型包装器（纯 XGBoost）

移除了 N-BEATS 相关逻辑，不再依赖 TensorFlow/Keras
"""
import copy
import numpy as np
import pandas as pd
import mlflow.pyfunc
import xgboost as xgb
from loguru import logger
from datetime import timedelta
from common.holidays import if_workday
from common.constants import ScenarioConfig, SCENARIO_CONFIGS


class LoadForecastWrapper(mlflow.pyfunc.PythonModel):
    """
    统一预测模型包装器（XGBoost）

    通过 scenario 参数区分 DI/D/WI/W/MI/M 场景的预测行为差异
    """

    def __init__(self,
                 train_shift_info,
                 train_delay_info,
                 feat_df,
                 forecast_timestamps,
                 total_model,
                 total_feature_list,
                 total_auto_model_tag,
                 daily_horizon,
                 forecast_horizon,
                 forecast_start_time,
                 time_granularity,
                 scenario=None,
                 time_field="record_time",
                 load_field="load"):
        self.train_shift_info = train_shift_info
        self.train_delay_info = train_delay_info
        self.feat_df = feat_df
        self.forecast_timestamps = forecast_timestamps
        self.total_model = total_model
        self.total_feature_list = total_feature_list
        self.total_auto_model_tag = total_auto_model_tag
        self.daily_horizon = daily_horizon
        self.forecast_horizon = forecast_horizon
        self.forecast_start_time = forecast_start_time
        self.time_granularity = time_granularity
        self.scenario = scenario or SCENARIO_CONFIGS["D"]
        self.time_field = time_field
        self.load_field = load_field

        task_type = self.scenario.task_type
        logger.info(f"'LoadForecastWrapper({task_type})' initialized. ")

    def predict(self, context, inputs):
        task_type = self.scenario.task_type
        logger.info(f"'LoadForecastWrapper({task_type})-predict' start. ")

        # ---------- 场景差异：DI 在顶部计算 forecast_length ----------
        if task_type == "DI":
            forecast_length = int((int(self.daily_horizon) / 24) * int(self.forecast_horizon))

        # 提取预测时间段对应的时间戳
        try:
            timestamps_need_pred = inputs["feat_df"].values[0]['forecast_timestamps']
            real_timestamps_need_pred = inputs["feat_df"].values[0]['real_forecast_timestamps']
            timestamps_need_pred = [pd.to_datetime(t) for t in timestamps_need_pred]
            real_timestamps_need_pred = [pd.to_datetime(t) for t in real_timestamps_need_pred]
        except Exception as e:
            return (f"提取预测时间段对应的时间戳 failed. \n {e}")

        # 提取feat_df部分
        try:
            _feat_df = inputs["feat_df"].values[0]
            first_layer_keys = _feat_df.keys()

            total_feat_df = {}
            feat_df_keys = [k for k in first_layer_keys if k.endswith('feat_df')]
            for tmp_keys in feat_df_keys:
                tmp_df = pd.DataFrame()
                _tmp_keys = _feat_df[tmp_keys].keys()
                for tk in _tmp_keys:
                    tmp_df[tk] = _feat_df[tmp_keys][tk]
                if len(tmp_df):
                    tmp_df.set_index(keys=[self.time_field], drop=True, inplace=True)
                    tmp_df.index = pd.to_datetime(tmp_df.index)
                total_feat_df[tmp_keys] = tmp_df
        except Exception as e:
            return (f"提取feat_df部分 failed. \n {e}")

        real_output_dict = {}
        if real_timestamps_need_pred:
            # 生成需要预测的天
            try:
                days_need_pred = sorted(
                    list(set([pd.to_datetime(t).strftime("%Y-%m-%d") for t in real_timestamps_need_pred])))
                days_need_pred = [pd.to_datetime(d) for d in days_need_pred]
            except Exception as e:
                return (f"生成需要预测的天 failed. \n {e}")

            # 提取other_params部分
            try:
                other_params = inputs["other_params"].values[0]
                separate_modeling = other_params['separate_modeling']
            except Exception as e:
                return (f"提取other_params部分 failed. \n {e}")

            # 生成预测结果
            try:
                model_pred_days = {'all_day': len(days_need_pred),
                                   'workday': len([d for d in days_need_pred if if_workday(pd.to_datetime(d))]),
                                   'holiday': len([d for d in days_need_pred if not if_workday(pd.to_datetime(d))])}
                model_pred_len = {'all_day': model_pred_days['all_day'] * int(self.daily_horizon),
                                  'workday': model_pred_days['workday'] * int(self.daily_horizon),
                                  'holiday': model_pred_days['holiday'] * int(self.daily_horizon)}
                model_specify_days = {'all_day': days_need_pred,
                                      'workday': [d for d in days_need_pred if if_workday(pd.to_datetime(d))],
                                      'holiday': [d for d in days_need_pred if not if_workday(pd.to_datetime(d))]}
            except Exception as e:
                return (f"存储模型预测所需信息 failed. \n {e}")

            # 根据预测需求载入所需模型类型
            model_type_list = []
            if separate_modeling == 'false':
                model_type_list.append('all_day')
            else:
                for tmp_k in ['workday', 'holiday']:
                    if model_pred_days[tmp_k]:
                        model_type_list.append(tmp_k)

            # XGBoost 预测
            final_output = pd.DataFrame(columns=['time', 'pred', 'model'])
            for model_type in model_type_list:
                # 生成目标时间戳
                if task_type == "DI":
                    need_time_index = copy.deepcopy(real_timestamps_need_pred)
                else:
                    tmp_need_pred_ds = model_specify_days[model_type]
                    need_time_index = []
                    for d in tmp_need_pred_ds:
                        tmp_index = pd.date_range(d, pd.to_datetime(d) + timedelta(days=1),
                                                  freq=self.time_granularity, closed='left')
                        need_time_index = need_time_index + list(tmp_index)

                # forecast_length
                if task_type != "DI":
                    forecast_length = model_pred_len[model_type]

                # 获取模型
                xgb_model = self.total_model[f"{model_type}_xgb"]
                feature_list = self.total_feature_list[f"{model_type}_feature_list"]

                # 构建 model input
                use_feat_df = total_feat_df[f"{model_type}_feat_df"]
                feat_df = pd.DataFrame(use_feat_df)
                if self.time_field in feat_df.columns:
                    feat_df[self.time_field] = pd.to_datetime(feat_df[self.time_field])
                    feat_df.set_index(self.time_field, inplace=True)
                feat_df.index = pd.to_datetime(feat_df.index)
                model_input = copy.deepcopy(feat_df)[feature_list]
                for col in list(model_input.columns):
                    model_input[col] = model_input[col].astype(dtype="float32")

                # XGB predict
                try:
                    xgb_input = copy.deepcopy(model_input)
                    xgb_input = xgb_input.loc[need_time_index]
                    input_matrix = xgb.DMatrix(xgb_input)
                    xgb_output = xgb_model.predict(input_matrix).flatten()

                    tmp_output = pd.DataFrame()
                    tmp_output['time'] = need_time_index
                    tmp_output['pred'] = xgb_output
                    tmp_output['model'] = 'xgb'
                    logger.info(f"get xgb pred for {model_type}. ")
                except Exception as e:
                    logger.error(f"xgb prediction error: {e}")
                    return (f"LoadForecastWrapper({task_type}) xgb prediction error. \n {e}")

                final_output = pd.concat([final_output, tmp_output], axis=0)

            try:
                final_output = final_output.sort_values(by='time')
                final_output = final_output.set_index('time')
                final_output.index = pd.to_datetime(final_output.index)
                real_output = final_output.loc[real_timestamps_need_pred]
                real_output = real_output.reset_index()
                real_output_dict["time"] = [pd.to_datetime(t).strftime("%Y-%m-%d %H:%M:%S") for t in
                                            real_output["time"].values]
                real_output_dict["pred"] = real_output["pred"].values.flatten().tolist()
                real_output_dict["model"] = real_output["model"].values.flatten().tolist()

                # 数据超前情况下整体预测值返回
                if len(timestamps_need_pred) > len(real_timestamps_need_pred):
                    tmp_completed_df = total_feat_df["all_day_feat_df"].reset_index()
                    completed_df = tmp_completed_df[[self.time_field, self.load_field]].dropna()
                    completed_df[self.time_field] = pd.to_datetime(completed_df[self.time_field])
                    completed_df.set_index(self.time_field, inplace=True)
                    delta_timestamps = timestamps_need_pred[:timestamps_need_pred.index(real_timestamps_need_pred[0])]
                    add_pred = completed_df.loc[delta_timestamps, self.load_field].values.tolist()
                    add_time = [t.strftime("%Y-%m-%d %H:%M:%S") for t in delta_timestamps]
                    add_model = ["updated_true_values"] * len(add_pred)

                    real_output_dict["time"] = add_time + real_output_dict["time"]
                    real_output_dict["pred"] = add_pred + real_output_dict["pred"]
                    real_output_dict["model"] = add_model + real_output_dict["model"]

                # 数据延迟情况下整体预测值返回
                elif len(timestamps_need_pred) < len(real_timestamps_need_pred):
                    real_output_dict["time"] = real_output_dict["time"][-len(timestamps_need_pred):]
                    real_output_dict["pred"] = real_output_dict["pred"][-len(timestamps_need_pred):]
                    real_output_dict["model"] = real_output_dict["model"][-len(timestamps_need_pred):]

                # 加入delay_info、shift_info返回
                self.train_delay_info.update(self.train_shift_info)
                real_output_dict["delay_info"] = self.train_delay_info
                logger.info(f"Get all model pred. ")
                return real_output_dict

            except Exception as e:
                logger.error(f"LoadForecastWrapper({task_type})-predict failed. \n {e}")
                return (f"LoadForecastWrapper({task_type})-predict failed. \n {e}")

        else:
            logger.info(f"存在数据完全超前，直接返回真实值. ")
            try:
                real_output_dict["time"] = [t.strftime("%Y-%m-%d %H:%M:%S") for t in timestamps_need_pred]
                completed_df = total_feat_df["completed_df"][[self.time_field, self.load_field]].dropna()
                completed_df[self.time_field] = pd.to_datetime(completed_df[self.time_field])
                completed_df.set_index(self.time_field, inplace=True)
                real_output_dict["pred"] = completed_df.loc[timestamps_need_pred, self.load_field].values.tolist()
                real_output_dict["model"] = ['updated_true_values'] * len(real_output_dict["time"])
                self.train_delay_info.update(self.train_shift_info)
                real_output_dict["delay_info"] = self.train_delay_info
                return real_output_dict
            except Exception as e:
                logger.error(f"LoadForecastWrapper({task_type})-predict failed. \n {e}")
                return (f"LoadForecastWrapper({task_type})-predict failed. \n {e}")


# ==================== 向后兼容别名 ====================
ModelWrapperDi = LoadForecastWrapper
ModelWrapperD = LoadForecastWrapper
ModelWrapperWi = LoadForecastWrapper
ModelWrapperW = LoadForecastWrapper
ModelWrapperMi = LoadForecastWrapper
ModelWrapperM = LoadForecastWrapper
