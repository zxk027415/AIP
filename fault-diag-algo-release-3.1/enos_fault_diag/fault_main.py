import json
import traceback

import cloudpickle
import mrmr
import numpy
import numpy as np
import pandas as pd
import mlflow.pyfunc
import sys
import argparse
import pandas
import pip
import scipy
import sklearn
import warnings
import os
import logging
import tsfresh
import tslearn
from eapdataset import Dataset

# 引入外部文件夹的文件

DIR_PATH = os.path.dirname(os.path.abspath(__file__))
ROOT_ABSOLUTE_PATH = os.path.abspath(DIR_PATH)
sys.path.append(ROOT_ABSOLUTE_PATH)
print(DIR_PATH, ROOT_ABSOLUTE_PATH)

from utils.exception import ParamException, AlgoException
from utils.log import setup_logging

# 指定日志存储位置，并开启日志监控
setup_logging(log_path=os.path.join(DIR_PATH, 'logs'))

sys.path.remove(ROOT_ABSOLUTE_PATH)

logger = logging.getLogger(__name__)

from fault_diagnosis import FaultDiagnosis
from utils.time import timedelta_f_freqstr, set_time_window, local_now, \
    convert_timezone, format_timestr

warnings.filterwarnings("ignore")

TIME_COL = 'time'
MOD_LABEL = 'modified_label_id'
CUSTOM_LABEL = 'custom_label_id'
PREDICT_LABEL = 'predict_label_id'
SITE_COL = 'site_id'
DEVICE_COL = 'device_id'
BRANCH_COL = 'branch_id'


# define the mlflow model class
class MlflowFaultDiagnosis(mlflow.pyfunc.PythonModel):
    def __init__(self, task_id, time_zone, source_dataset, label_dataset,
                 result_table, label_map, diagnosis_window='1d',
                 window_one_label="1"):
        self.task_id = task_id
        self.time_zone = time_zone
        self.diagnosis_window = diagnosis_window
        self.window_one_label = int(window_one_label)
        self.obj_model = None
        self.source_dataset = source_dataset  # todo
        self.label_dataset = label_dataset
        self.result_table = result_table
        self.predict_dataset = None
        self.label_map = label_map

    def parse_dataset(self, dataset_name, time_col, sql_query=None, query_params=None):
        """
        parse dataset from name to dataframe through eap api
        """
        try:
            dataset = Dataset.get_by_name(dataset_name)
            data = dataset.to_pandas_dataframe(use_cached_result=False,
                                               query=sql_query,
                                               query_parameters=query_params)
            data[time_col] = pd.to_datetime(data[time_col])
        except Exception as e:
            logging.error(f'{dataset_name} dataset parsing error')
            logging.error(f'sql_query: {sql_query}')
            logging.error(f'query_params: {query_params}')
            logging.error(e)
            raise ParamException(f'{dataset_name} dataset parsing error')
        return data

    def __get_structure(self, source_dataset):
        cols = source_dataset.columns
        structure = [SITE_COL]
        if DEVICE_COL in cols:
            structure.append(DEVICE_COL)
        if BRANCH_COL in cols:
            structure.append(BRANCH_COL)
        self.structure = structure

    def parse_label(self, label_df, label_col):
        """
        do label cleaning and mapping
        """
        label_df = label_df[(label_df[label_col].notnull()) & (label_df[label_col])]
        # map label, int keys will become str after serialization
        try:
            label_df[label_col] = label_df[label_col].apply(
                lambda x: int(self.label_map[str(x)])
                if str(x) in self.label_map.keys() else -1)  # -1 todo
        except Exception as e:
            logging.error('Label mapping failed')
            logging.error(e)
            raise ParamException('Label mapping failed')

        if len(label_df[label_col].unique()) == 1 and \
                label_df[label_col].unique() == -1:
            logging.error(
                'Label df cannot be mapped with label_map, check if they have same label')
            raise ParamException(
                'Label df cannot be mapped with label_map, check if they have same label')

        label_df.drop_duplicates(inplace=True)
        return label_df

    def init_train_data(self, source_dataset, label_dataset, result_dataset):

        """
        initialize train data from source_dataset, 
        label_dataset and result_dataset     
        """
        if source_dataset.empty or label_dataset.empty:
            logging.error('Training dataset or label dataset is empty')
            raise ParamException('Training dataset or label dataset is empty')

        self.__get_structure(source_dataset)
        id_cols = self.structure + [TIME_COL]

        source_dataset.loc[:, self.structure] = \
            source_dataset.loc[:, self.structure].astype(str)
        label_dataset.loc[:, self.structure] = \
            label_dataset.loc[:, self.structure].astype(str)
        result_dataset.loc[:, self.structure] = \
            result_dataset.loc[:, self.structure].astype(str)

        # parse label
        label_dataset = self.parse_label(label_dataset, CUSTOM_LABEL)
        result_dataset = self.parse_label(result_dataset, MOD_LABEL)
        result_dataset = result_dataset[id_cols + [MOD_LABEL]]
        if result_dataset.empty:
            label_all = label_dataset.copy()
            label_all[MOD_LABEL] = pd.Series()
        else:
            label_all = pd.merge_asof(label_dataset.sort_values(by=TIME_COL),
                                      result_dataset.sort_values(by=TIME_COL),
                                      by=self.structure, on=TIME_COL)
        # there may be new devices in result which cannot be merged by merge_asof
        label_all = pd.merge(
            label_all, result_dataset, on=id_cols + [MOD_LABEL], how='outer')
        label_all['label'] = label_all.apply(
            lambda x: x[MOD_LABEL]
            if x[MOD_LABEL] is not None and not np.isnan(x[MOD_LABEL])
            else x[CUSTOM_LABEL], axis=1)
        label_all.drop([MOD_LABEL, CUSTOM_LABEL], axis=1, inplace=True)

        if len(label_all.label.unique()) == 1:
            logging.error('Only support data with more than one type of label')
            raise ParamException(
                'Only support data with more than one type of label')

        # merge training dataset with label df
        new_dataset = source_dataset.sort_values(by=TIME_COL)
        label_all = label_all.sort_values(by=TIME_COL)
        new_dataset = pd.merge_asof(
            new_dataset, label_all, by=self.structure, on=TIME_COL)
        new_dataset = new_dataset[new_dataset.label.notnull()]

        if new_dataset.empty:
            logging.error('Training data is empty after merging with label \
            data, check if they have same group of site, device, branch and time')
            raise ParamException('Training data is empty after merging with \
            label data, check if they have same group of site, device, branch \
            and time')

        new_dataset.drop_duplicates(subset=id_cols, inplace=True)

        # set time window
        new_dataset = set_time_window(
            new_dataset, self.structure, TIME_COL, self.diagnosis_window)

        return new_dataset

    def init_pred_data(self, start_time, end_time):
        """
        initialize prediction data
        """
        # parse timestamp
        if pd.isnull(start_time) and pd.isnull(end_time):
            time_now = local_now()
            time_custom = convert_timezone(time_now, self.time_zone)
            time_before = time_custom - timedelta_f_freqstr(self.diagnosis_window)
            start_time = time_before.replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
            end_time = start_time + timedelta_f_freqstr(self.diagnosis_window)

        logging.info(f'pred start_time:{start_time}, end_time:{end_time}')

        new_dataset = self.parse_dataset(
            self.predict_dataset, TIME_COL,
            query_params=[str(start_time), str(end_time)])

        if new_dataset.empty:
            logging.error('Predict data is empty, check if start_time and end_time are valid.')
            raise ParamException('Predict data is empty, check if start_time and end_time are valid.')

        # set time window
        new_dataset = set_time_window(
            new_dataset, self.structure, TIME_COL, self.diagnosis_window)

        return new_dataset

    def check_param(self):
        """
        parse and validate params
        """
        try:
            if isinstance(self.label_map, str):
                self.label_map = json.loads(self.label_map)
        except Exception as e:
            logging.error('Param parse error, label_map parsing failed')
            logging.error(e)
            raise ParamException('Label_map parsing failed')

        if not len(self.label_map) == len(set(self.label_map.values())):
            logging.error('Param error, duplicate labels in label_map')
            raise ParamException('Duplicate labels in label_map')

        if self.window_one_label not in [0, 1]:
            logging.error('Param error, window one label must be 0 or 1')
            raise ParamException('Window one label must be 0 or 1')
        # todo tmp
        if self.window_one_label == 0:
            logging.warning('This version do not support window one label as 0')
            raise ParamException('This version do not support window one label as 0')

        try:
            num, time_unit = self.diagnosis_window[:-1], self.diagnosis_window[-1]
            num = int(num)
        except Exception as e:
            logging.error(e)
            logging.error('Param error, diagnosis window format error')
            raise ParamException('Diagnosis window format error')
        if time_unit not in ['t', 'm', 'h', 'd', 'w']:
            logging.error('Param error, diagnosis window format error')
            raise ParamException('Diagnosis window format error')

    def train(self):
        """
        main training process
        """
        logging.info('Check parameters')
        self.check_param()

        logging.info('Parse dataset')
        source_dataset = self.parse_dataset(self.source_dataset, TIME_COL)
        label_dataset = self.parse_dataset(self.label_dataset, TIME_COL)
        result_dataset = self.parse_dataset(
            self.label_dataset, TIME_COL,
            sql_query=f"select * from {self.result_table} where `{MOD_LABEL}` is not NULL")

        new_dataset = self.init_train_data(
            source_dataset, label_dataset, result_dataset)

        value_fields = [col for col in new_dataset.columns if col not in
                        [SITE_COL, DEVICE_COL, BRANCH_COL, TIME_COL, 
                         'label', 'time_window']]

        obj_model = FaultDiagnosis(
            time_zone=self.time_zone,
            diagnosis_window=self.diagnosis_window,
            window_one_label=self.window_one_label,
            time_field=TIME_COL,
            label_field='label',
            id_fields=self.structure + ['time_window'],
            value_fields=value_fields,
            )
        # train the model
        try:
            obj_model.train(new_dataset)
            logging.info('Training done.')
        except AlgoException:
            logging.error('Training failed')
            logging.error(traceback.format_exc())
            raise AlgoException('Training failed')

        # save model
        self.obj_model = obj_model

    def predict(self, context, model_input):
        try:
            self.predict_dataset = model_input['predict_dataset'].iloc[0]
            start_time = model_input['start_time'].iloc[0]
            end_time = model_input['end_time'].iloc[0]
            logging.info(
                f'pred param: predict_dataset:{self.predict_dataset}, start_time:{start_time}, end_time:{end_time}')
        except Exception as e:
            logging.error('Prediction params parsing error')
            logging.error(e)
            raise ParamException('Prediction params parsing error')

        # parse dataset
        new_dataset = self.init_pred_data(start_time=start_time,
                                          end_time=end_time)
        unique_fields = self.structure + ['time_window']
        data_groupby = new_dataset.groupby(unique_fields)
        tmp_df = data_groupby.count()
        len_objs = len(tmp_df)

        # split data every 10k objects
        step = 10000
        merge_list = []
        repred_list = []
        for start in range(0, len_objs, step):
            split_ids = tmp_df.iloc[start: start+step, :].reset_index()[unique_fields]
            print('split_ids shape', split_ids.shape)
            split_df = split_ids.merge(new_dataset, on=unique_fields)
            try:
                split_result = self.obj_model.predict(model=self.obj_model.model,
                                                      predict_dataset=split_df)
                merge_list.append(split_result)
                print('split_result shape', split_result.shape)
            except Exception as e:
                logging.error(f'Prediction failed from No.{start} to No.{start+step}.')
                logging.error(e)
                repred_list.append(split_ids)

        # re-prediction for failed data
        fail_num = 0
        if repred_list:
            for split_ids in repred_list:
                for split_id in split_ids.values:
                    split_df = data_groupby.get_group(tuple(split_id))
                    try:
                        split_result = self.obj_model.predict(
                            model=self.obj_model.model,
                            predict_dataset=split_df)
                        merge_list.append(split_result)
                        print('split_result shape', split_result.shape)
                    except AlgoException:
                        fail_num += 1
                        logging.error(f'Re-prediction failed for {split_id}.')
                        logging.error(traceback.format_exc())
        logging.info('Prediction done.')
        logging.info(f'Prediction failure number: {fail_num}')

        try:
            result_df = pd.concat(merge_list)
            result_df = result_df[self.structure + [TIME_COL, 'predict_label']]
            label_map_df = pd.DataFrame(
                self.label_map, index=['predict_label']).T.reset_index()
            label_map_df.rename(columns={'index': PREDICT_LABEL}, inplace=True)
            result_df = result_df.merge(label_map_df, on='predict_label', how='left')
            result_df.drop('predict_label', axis=1, inplace=True)
            result_df['time'] = result_df['time'].apply(
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S"))
            print(result_df.shape)
            logging.info('Prediction done.')
            return np.array(result_df.to_json())

        except Exception:
            logging.error('Result parsing error.')
            logging.error(traceback.format_exc())
            raise ValueError('Result parsing error.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='fault_diagnosis')
    parser.add_argument('--task_id', type=str, required=True)
    parser.add_argument('--scene', type=str, required=False)
    parser.add_argument('--device_type', type=str, required=False)
    parser.add_argument('--time_zone', type=str, required=True)
    parser.add_argument('--diagnosis_window', type=str, required=True)
    parser.add_argument('--label_dataset', type=str, required=True)
    parser.add_argument('--train_dataset', type=str, required=True)
    parser.add_argument('--result_table', type=str, required=True)
    parser.add_argument('--window_one_label', type=str, required=True)
    parser.add_argument('--label_map', type=str, required=True)

    args = parser.parse_args(sys.argv[1:])
    task_id = args.task_id
    device_type = args.device_type
    scene = args.scene
    time_zone = args.time_zone
    diagnosis_window = args.diagnosis_window
    source_dataset = args.train_dataset
    label_dataset = args.label_dataset
    result_table = args.result_table
    window_one_label = args.window_one_label
    label_map = args.label_map

    # environment settings
    python_v = sys.version.split('|')[0].strip()

    # 模型上传
    conda_env = {
        'name': 'mlflow-env',
        'channels': ['default', 'conda-forge'],
        'dependencies': [
            'python=%s' % python_v,
            'pip={}'.format(pip.__version__),
            {'pip': [
                'matrixprofile==1.1.10.1',
                'scikit-learn=={}'.format(sklearn.__version__),
                'mlflow=={}'.format(mlflow.__version__),
                'pandas=={}'.format(pandas.__version__),
                'numpy=={}'.format(numpy.__version__),
                'mrmr-selection'.format(mrmr.__version__),
                'scipy=={}'.format(scipy.__version__),
                'cloudpickle=={}'.format(cloudpickle.__version__),
                'tsfresh=={}'.format(tsfresh.__version__),
                'tslearn=={}'.format(tslearn.__version__),
                'tzlocal==4.2',
                'eapdataset',
                'pytz==2021.3'
            ]}
        ]
    }

    # model training
    mlflow_model = MlflowFaultDiagnosis(task_id=task_id,
                                        time_zone=time_zone,
                                        diagnosis_window=diagnosis_window,
                                        window_one_label=window_one_label,
                                        source_dataset=source_dataset,
                                        label_dataset=label_dataset,
                                        result_table=result_table,
                                        label_map=label_map
                                        )
    mlflow_model.train()

    # mlflow模型训练与保存
    with mlflow.start_run(run_name=f'V1-{task_id}'):
        artifact_path = "fault-diag"

        # cache the mlflow model
        mlflow.log_artifact(f'{ROOT_ABSOLUTE_PATH}/utils/', artifact_path)
        mlflow.log_artifact(f'{ROOT_ABSOLUTE_PATH}/features/', artifact_path)
        mlflow.log_artifact(f'{ROOT_ABSOLUTE_PATH}/data_cleaning/',
                            artifact_path)
        mlflow.log_artifact(f'{ROOT_ABSOLUTE_PATH}/models/', artifact_path)
        mlflow.log_artifact(f'{ROOT_ABSOLUTE_PATH}/fault_diagnosis.py',
                            artifact_path)
        mlflow.pyfunc.log_model(artifact_path=artifact_path,
                                python_model=mlflow_model,
                                conda_env=conda_env)
