# -*- coding: utf-8 -*-
"""
统一离线回测入口

用法:
    python run.py --config configs/aesc.yaml
    python run.py --config configs/mengxi.yaml

替代原有的 aesc_d1_dataset.py 和 mengxi_d1_dataset.py 两个独立的回测脚本
"""
import os
import sys
import copy
import json
import time
import pickle
import argparse
import warnings
import numpy as np
import pandas as pd
import pytz
from datetime import timedelta
from loguru import logger
import yaml

from common.constants import SCENARIO_CONFIGS
from configs.schema import CustomerConfig, DataSourceConfig, ForecastConfig, BacktestConfig

# 使用原有的功能模块（兼容过渡期）
from data_process import (get_completed_timestamp, chebyshev_detector, get_completed_df,
                          get_train_status, get_timestamp_freq, get_daily_horizon)
from db_data_fetch import offline_load_data
from features.engine import (add_more_features_di, add_more_features_d, add_more_features_wi,
                             add_more_features_w, add_more_features_mi, add_more_features_m)
from models_pkg.trainer import (model_prefer_trainer_di, model_prefer_trainer_d, model_prefer_trainer_wi,
                                model_prefer_trainer_w, model_prefer_trainer_mi, model_prefer_trainer_m)
from models_pkg.wrapper import LoadForecastWrapper
from utils import (predict_format_transform, capture_df_delay_info, delay_info_insert_offline_db,
                   insert_beta, get_delay_info_from_offline_db, df_recovery_from_db, df_recovery_by_self_defined)

warnings.filterwarnings(action="ignore")

# 任务类型 -> 功能函数映射
TASK_TYPE_MAP = {
    'DI': {'features': add_more_features_di, 'trainer': model_prefer_trainer_di},
    'D':  {'features': add_more_features_d,  'trainer': model_prefer_trainer_d},
    'WI': {'features': add_more_features_wi, 'trainer': model_prefer_trainer_wi},
    'W':  {'features': add_more_features_w,  'trainer': model_prefer_trainer_w},
    'MI': {'features': add_more_features_mi, 'trainer': model_prefer_trainer_mi},
    'M':  {'features': add_more_features_m,  'trainer': model_prefer_trainer_m},
}


def load_config(config_path: str) -> CustomerConfig:
    """从 YAML 文件加载客户配置"""
    with open(config_path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)

    cfg = CustomerConfig(
        name=raw['customer']['name'],
        task_id=raw['customer']['task_id'],
        output_dir=raw['customer'].get('output_dir', './output'),
        data_source=DataSourceConfig(**raw.get('data_source', {})),
        forecast=ForecastConfig(**raw.get('forecast', {})),
        backtest=BacktestConfig(**raw.get('backtest', {})),
        id_lists=raw.get('id_lists', {}),
        weather_cols=raw.get('weather_cols', {}),
    )
    return cfg


def build_delay_info(str_d, forecast_horizon, load_field, weather_cols):
    """
    动态生成 that_time_latest 延迟信息字典

    替代原先每个气象列手动硬编码的方式
    """
    base_time = (pd.to_datetime(str_d) + timedelta(days=1) - timedelta(minutes=15))
    end_time = (pd.to_datetime(str_d) + timedelta(days=forecast_horizon + 1) - timedelta(minutes=15))

    info = {load_field: base_time.strftime("%Y-%m-%d %H:%M:%S")}
    for col in weather_cols:
        info[col] = end_time.strftime("%Y-%m-%d %H:%M:%S")
    return info


def run_backtest(config_path: str):
    """
    执行离线回测主流程

    从 YAML 配置文件读取参数，执行训练-预测-后处理流水线
    """
    cfg = load_config(config_path)
    scenario = cfg.forecast.scenario
    task_funcs = TASK_TYPE_MAP.get(cfg.forecast.task_type, TASK_TYPE_MAP['D'])

    add_more_features = task_funcs['features']
    model_prefer_trainer = task_funcs['trainer']

    ds = cfg.data_source
    fc = cfg.forecast
    time_zone = ds.time_zone
    tz = pytz.timezone(time_zone)

    logger.info(f"==================== 开始回测: {cfg.name} ====================")
    logger.info(f"task_type={fc.task_type}, forecast_horizon={fc.forecast_horizon}, "
                f"specify_model={fc.specify_model}")
    if getattr(ds, "offline_csv_path", ""):
        logger.info(f"offline_csv_path(from yaml)={ds.offline_csv_path}")
    else:
        logger.info("offline_csv_path(from yaml) is empty; will fall back to OFFLINE_CSV_PATH env or default.")

    for parent_id, all_child_id in cfg.id_lists.items():
        for child_id in all_child_id:
            for start_d in pd.date_range(cfg.backtest.start_date, cfg.backtest.end_date,
                                         freq='D', closed='left'):
                str_d = start_d.strftime('%Y-%m-%d')
                train_trigger_time = str_d + ' 00:00:00'
                pred_trigger_time = str_d + ' 00:00:00'

                # ==================== 训练模块 ====================
                train_start_time = time.time()
                is_training = 'true'

                load_df, his_min_max = offline_load_data(
                    fc.task_type, ds.table_name, ds.parent_field, ds.child_field,
                    ds.time_field, ds.load_field, parent_id, child_id,
                    ds.time_granularity, is_training, time_zone,
                    nowtime=train_trigger_time, other_cols=cfg.train_other_cols,
                    csv_path=(ds.offline_csv_path or None))

                logger.info(f"'offline_load_data' run successful.\nload_df: \n {load_df} \n his_min_max: \n {his_min_max}")

                # 构建延迟信息
                tmp_load_df = pd.DataFrame()
                if not len(tmp_load_df):
                    that_time_latest = build_delay_info(
                        str_d, fc.forecast_horizon, ds.load_field, cfg.train_other_cols)
                    load_df, his_min_max = df_recovery_by_self_defined(
                        load_df, that_time_latest, ds.time_granularity,
                        time_field=ds.time_field, load_field=ds.load_field)
                else:
                    load_df, his_min_max = pd.DataFrame(), pd.DataFrame()

                load_df.rename(columns=dict(zip(cfg.train_other_cols, cfg.pred_other_cols)), inplace=True)

                train_status = get_train_status(load_df, fc.task_type, fc.forecast_horizon,
                                                time_field=ds.time_field, load_field=ds.load_field)
                logger.info(f"'get_train_status' run successful.\ntrain_status: \n {train_status}")

                if train_status == 'true':
                    logger.info(f"Start to train model.")

                    original_time_freq, daily_horizon = get_timestamp_freq(load_df, time_field=ds.time_field)
                    logger.info(f"original_time_freq: {original_time_freq}, daily_horizon: {daily_horizon}")

                    timestamp_completed_df = get_completed_timestamp(
                        load_df, original_time_freq, daily_horizon, is_training, time_field=ds.time_field)

                    train_delay_info = capture_df_delay_info(
                        timestamp_completed_df, is_training, train_trigger_time, time_field=ds.time_field)

                    anomaly_detected_df = chebyshev_detector(
                        timestamp_completed_df, load_field=ds.load_field)

                    completed_df = get_completed_df(
                        anomaly_detected_df, delay_info=train_delay_info,
                        time_field=ds.time_field, load_field=ds.load_field)

                    forecast_timestamps, feat_df, train_shift_info = add_more_features(
                        cfg.task_id, parent_id, child_id, fc.operate_status,
                        completed_df, original_time_freq, daily_horizon,
                        fc.forecast_horizon, fc.forecast_start_time, is_training,
                        time_zone, nowtime=train_trigger_time,
                        separate_modeling=fc.separate_modeling, gaps_defined=None,
                        time_field=ds.time_field, load_field=ds.load_field)

                    total_model, total_feature_list, total_auto_model_tag, _daily_horizon = model_prefer_trainer(
                            feat_df, daily_horizon, fc.forecast_horizon,
                            scenario=scenario, separate_modeling=fc.separate_modeling,
                            time_field=ds.time_field, load_field=ds.load_field)

                    train_end_time = time.time()
                    print(f"\n ************************** train cost "
                          f"{np.round((train_end_time - train_start_time) / 60, 2)}min ************************** \n ")

                    # model wrapper
                    custom_model = LoadForecastWrapper(
                        train_shift_info, train_delay_info, feat_df, forecast_timestamps,
                        total_model, total_feature_list, total_auto_model_tag, daily_horizon,
                        fc.forecast_horizon, fc.forecast_start_time, ds.time_granularity,
                        scenario=scenario, time_field=ds.time_field, load_field=ds.load_field)

                    # pickle保存
                    model_filename = (f"custom_model_{train_trigger_time.replace(':', '_').replace(' ', '_')}_"
                                      f"{parent_id}_{child_id}_{fc.task_type}_{cfg.task_id}.pkl")
                    s = pickle.dumps(custom_model)
                    with open(model_filename, 'wb+') as f:
                        f.write(s)
                        f.close()
                    logger.info(f"saved {model_filename}")

                else:
                    logger.warning(f"train_status is: {train_status}")
                    logger.warning(f"It is unable to meet {fc.task_type} training conditions!")
                    assert train_status == 'true'

                # ==================== 预测模块 ====================
                pred_start_time = time.time()
                is_training = 'false'

                # 加载 pickle 模型
                model_filename = (f"custom_model_{train_trigger_time.replace(':', '_').replace(' ', '_')}_"
                                  f"{parent_id}_{child_id}_{fc.task_type}_{cfg.task_id}.pkl")
                s = open(model_filename, 'rb').read()
                custom_model = pickle.loads(s)

                load_df, his_min_max = offline_load_data(
                    fc.task_type, ds.table_name, ds.parent_field, ds.child_field,
                    ds.time_field, ds.load_field, parent_id, child_id,
                    ds.time_granularity, is_training, time_zone,
                    nowtime=pred_trigger_time, other_cols=cfg.pred_other_cols,
                    csv_path=(ds.offline_csv_path or None))

                tmp_load_df = pd.DataFrame()
                if not len(tmp_load_df):
                    that_time_latest = build_delay_info(
                        str_d, fc.forecast_horizon, ds.load_field, cfg.pred_other_cols)
                    load_df, his_min_max = df_recovery_by_self_defined(
                        load_df, that_time_latest, ds.time_granularity,
                        time_field=ds.time_field, load_field=ds.load_field)
                else:
                    load_df, his_min_max = pd.DataFrame(), pd.DataFrame()

                original_time_freq, daily_horizon = get_timestamp_freq(load_df, time_field=ds.time_field)

                timestamp_completed_df = get_completed_timestamp(
                    load_df, original_time_freq, daily_horizon, is_training, time_field=ds.time_field)

                pred_delay_info = capture_df_delay_info(
                    timestamp_completed_df, is_training, pred_trigger_time, time_field=ds.time_field)

                anomaly_detected_df = chebyshev_detector(timestamp_completed_df, load_field=ds.load_field)

                completed_df = get_completed_df(
                    anomaly_detected_df, pred_delay_info, time_field=ds.time_field, load_field=ds.load_field)

                forecast_timestamps, feat_df, pred_shift_info = add_more_features(
                    cfg.task_id, parent_id, child_id, fc.operate_status,
                    completed_df, original_time_freq, daily_horizon,
                    fc.forecast_horizon, fc.forecast_start_time, is_training,
                    time_zone, nowtime=pred_trigger_time,
                    separate_modeling=fc.separate_modeling, gaps_defined=None,
                    time_field=ds.time_field, load_field=ds.load_field)

                # 构造 MLflow predict 输入
                first_layer_keys = list(feat_df.keys())
                feat_df_dict = {}
                for tmp_key in first_layer_keys:
                    if isinstance(feat_df[tmp_key], pd.DataFrame):
                        tmp_dict = {}
                        for c in feat_df[tmp_key].columns:
                            tmp_dict[c] = feat_df[tmp_key][c].values
                        feat_df_dict[tmp_key] = tmp_dict
                    else:
                        feat_df_dict[tmp_key] = feat_df[tmp_key]

                inputs = pd.DataFrame()
                inputs["feat_df"] = [feat_df_dict]
                inputs["other_params"] = [{"pred_start_time": pred_trigger_time,
                                           "specify_model": fc.specify_model,
                                           "separate_modeling": fc.separate_modeling}]

                predict_output = custom_model.predict(None, inputs)
                print(f"train_trigger_time: {train_trigger_time} \n"
                      f"pred_trigger_time: {pred_trigger_time} \n"
                      f"predict_output: {predict_output}\n")

                # 预测结果 DataFrame
                tmp_re = pd.DataFrame()
                tmp_re["record_time"] = forecast_timestamps
                tmp_re["task_id"] = cfg.task_id
                tmp_re["parent_id"] = parent_id
                tmp_re["child_id"] = child_id
                tmp_re["fcst_load"] = predict_output['pred']
                tmp_re["separate_modeling"] = fc.separate_modeling
                tmp_re["specify_model"] = 'xgb'
                tmp_re["auto_bst_model"] = 'xgb'
                tmp_re["pred_start_time"] = forecast_timestamps[0]
                tmp_re["pred_end_time"] = forecast_timestamps[-1]
                tmp_re["operate_status"] = fc.operate_status

                # 数据delay捕获
                delay_info = predict_output["delay_info"]
                delay_info.update(pred_shift_info)
                delay_info.update(pred_delay_info)

                # predict_format_transform
                pred_re = tmp_re["fcst_load"].values.flatten().tolist()
                json_list = predict_format_transform(
                    pred_re, forecast_timestamps, his_min_max,
                    time_field=ds.time_field, load_field=ds.load_field)

                # 构建输出 DataFrame（修复 df.append 弃用问题）
                data_df_pred = pd.DataFrame(columns=["task_id", ds.time_field, "parent_id",
                                                      "child_id", "fcst_" + ds.load_field])
                rows = []
                for data in json_list:
                    ts = data['time']
                    tz_obj = pytz.timezone(time_zone)
                    dt = pytz.datetime.datetime.fromtimestamp(ts, tz_obj)
                    dt = dt.strftime('%Y-%m-%d %H:%M:%S')
                    rows.append({"task_id": cfg.task_id, ds.time_field: dt,
                                 "parent_id": parent_id, "child_id": child_id,
                                 "fcst_" + ds.load_field: data[ds.load_field]})
                data_df_pred = pd.DataFrame(rows)

                tmp_re.rename(columns={'fcst_load': 'fcst_load_before'}, inplace=True)
                tmp_re["fcst_load"] = data_df_pred["fcst_" + ds.load_field].values.flatten()

                tmp_re = tmp_re[["task_id", "record_time", "parent_id", "child_id", "fcst_load",
                                 "separate_modeling", "specify_model", "auto_bst_model",
                                 "fcst_load_before", "pred_start_time",
                                 "pred_end_time", "operate_status"]]
                tmp_re = tmp_re.replace(np.nan, 'null')

                print(tmp_re.head())

                # 确保输出目录存在
                output_dir = cfg.output_dir
                os.makedirs(output_dir, exist_ok=True)

                tmp_re.to_csv(
                    f"{output_dir}/tmp_re_{pred_trigger_time.replace(':', '_').replace(' ', '_')}_"
                    f"{parent_id}_{child_id}_{fc.task_type}.csv")

                pred_end_time = time.time()
                print(f"\n ************************** "
                      f"pred cost {np.round((pred_end_time - pred_start_time) / 60, 2)}min "
                      f"**************************\n ")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='离线负荷预测回测')
    parser.add_argument('--config', type=str, required=True, help='配置文件路径 (YAML)')
    args = parser.parse_args()
    run_backtest(args.config)
