import json
import mlflow
import pandas as pd
import unittest as ut
import os
import sys
import pickle

# 引入外部文件夹的文件
DIR_PATH = os.path.dirname(os.path.abspath(__file__))
ROOT_ABSOLUTE_PATH = os.path.abspath(DIR_PATH + ''.join([os.path.sep+".." for _ in range(1)]))
sys.path.append(ROOT_ABSOLUTE_PATH)

from utils.exception import ParamException
from fault_main import MlflowFaultDiagnosis
from fault_diagnosis import FaultDiagnosis

sys.path.remove(ROOT_ABSOLUTE_PATH)


class TestTrain(ut.TestCase):
    task_id = 'test'
    time_zone = 'Asia/Shanghai'
    diagnosis_window = '1d'
    window_one_label = 1
    label_map = json.dumps({'suite-0': 20, 'suite-1': 21, 'suite-2': 22,
                            'suite-3': 23, 'suite-4': 24, 'suite-5': 25,
                            0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7,
                            8: 8, 9: 9, 10: 10, 11: 11, 12: 12, 13: 13,
                            14: 14, 15: 15, 16: 16, 17: 17})
    train_small = pd.read_parquet('test/train_small.parquet', engine='pyarrow')
    label_small = pd.read_parquet('test/label_small.parquet', engine='pyarrow')
    result_dataset = pd.read_parquet('test/result_dataset.parquet', engine='pyarrow')

    def test_online_data_parsing(self):
        """
        can only run online
        """
        # model training
        mlflow_model = MlflowFaultDiagnosis(task_id=self.task_id,
                                            time_zone=self.time_zone,
                                            diagnosis_window=self.diagnosis_window,
                                            window_one_label=self.window_one_label,
                                            source_dataset='train-small',
                                            label_dataset="fault-label-dataset-0901",
                                            result_table="fault_result_0825",
                                            label_map=self.label_map
                                            )
        mlflow_model.parse_dataset(mlflow_model.source_dataset, 'time')
        mlflow_model.parse_dataset(mlflow_model.label_dataset, 'time')
        mlflow_model.parse_dataset(
            mlflow_model.label_dataset, 'time',
            sql_query=f"select * from {mlflow_model.result_table} where `modified_label_id` IS NOT NULL")

    def test_train_data_initialization(self):
        source_dataset = self.train_small
        label_dataset = self.label_small
        result_dataset = self.result_dataset
        label_dataset['time'] = pd.to_datetime(label_dataset['time'])
        source_dataset['time'] = pd.to_datetime(source_dataset['time'])
        result_dataset['time'] = pd.to_datetime(result_dataset['time'])

        # model training
        mlflow_model = MlflowFaultDiagnosis(task_id=self.task_id,
                                            time_zone=self.time_zone,
                                            diagnosis_window=self.diagnosis_window,
                                            window_one_label=self.window_one_label,
                                            source_dataset='',
                                            label_dataset="",
                                            result_table="",
                                            label_map=json.loads(self.label_map)
                                            )
        mlflow_model.init_train_data(
            source_dataset, label_dataset, result_dataset)

    def test_first_training(self):
        """
        test example 1-(1), all params are correct
        """
        new_dataset = pd.read_parquet('test/train_dataset.parquet', engine='pyarrow')
        new_dataset['time'] = pd.to_datetime(new_dataset['time'])
        new_dataset['time_window'] = pd.to_datetime(new_dataset['time_window'])

        obj_model = FaultDiagnosis(
            time_zone=self.time_zone,
            diagnosis_window='1d',
            window_one_label=1,
            time_field='time',
            label_field='label',
            id_fields=['site_id', 'device_id', 'branch_id', 'time_window'],
            value_fields=['i_cal', 'value'],
            )
        obj_model.train(new_dataset)

    def test_empty_dataset_checking(self):
        """
        test example 1-(2), train dataset is empty or label dataset is empty.
        """
        source_dataset = pd.read_parquet('test/train_empty.parquet', engine='pyarrow')
        label_dataset = pd.read_parquet('test/label_small.parquet', engine='pyarrow')
        result_dataset = pd.read_parquet('test/result_dataset.parquet', engine='pyarrow')
        label_dataset['time'] = pd.to_datetime(label_dataset['time'])
        source_dataset['time'] = pd.to_datetime(source_dataset['time'])
        result_dataset['time'] = pd.to_datetime(result_dataset['time'])

        label_map = json.dumps({'suite-0': 20, 'suite-1': 21, 'suite-2': 22,
                                'suite-3': 23, 'suite-4': 24, 'suite-5': 25,
                                0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7,
                                8: 8, 9: 9, 10: 10, 11: 11, 12: 12, 13: 13,
                                14: 14, 15: 15, 16: 16, 17: 17})

        # model training
        mlflow_model = MlflowFaultDiagnosis(
            task_id='test', time_zone=self.time_zone, diagnosis_window='1d',
            window_one_label=1, source_dataset='', label_dataset="",
            result_table="", label_map=json.loads(label_map))

        with self.assertRaises(ParamException) as cm:
            mlflow_model.init_train_data(
                source_dataset, label_dataset, result_dataset)
        the_exception = cm.exception
        self.assertEqual(the_exception.message,
                         'Training dataset or label dataset is empty')

    def test_label_map_checking(self):
        """
        test example 1-(3), duplicate labels in label_map.
        """
        duplicate_label_map = json.dumps(
            {'suite-0': 20, 'suite-1': 20, 'suite-2': 20,
             'suite-3': 23, 'suite-4': 24, 'suite-5': 25,
             0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7,
             8: 8, 9: 9, 10: 10, 11: 11, 12: 12, 13: 13,
             14: 14, 15: 15, 16: 16, 17: 17})

        # model training
        mlflow_model = MlflowFaultDiagnosis(task_id=self.task_id,
                                            time_zone=self.time_zone,
                                            diagnosis_window=self.diagnosis_window,
                                            window_one_label=self.window_one_label,
                                            source_dataset='train-small',
                                            label_dataset="fault-label-dataset-0901",
                                            result_table="fault_result_0825",
                                            label_map=duplicate_label_map
                                            )
        with self.assertRaises(ParamException) as cm:
            mlflow_model.check_param()
        the_exception = cm.exception
        self.assertEqual(the_exception.message,
                         'Duplicate labels in label_map')

    def test_diag_window_checking(self):
        """
        test example 1-(4), diagnosis window has wrong format.
        """
        wrong_diag_window = 'd'

        # model training
        mlflow_model = MlflowFaultDiagnosis(task_id=self.task_id,
                                            time_zone=self.time_zone,
                                            diagnosis_window=wrong_diag_window,
                                            window_one_label=1,
                                            source_dataset='train-small',
                                            label_dataset="fault-label-dataset-0901",
                                            result_table="fault_result_0825",
                                            label_map=self.label_map
                                            )
        with self.assertRaises(ParamException) as cm:
            mlflow_model.check_param()
        the_exception = cm.exception
        self.assertEqual(the_exception.message,
                         'Diagnosis window format error')

    def test_duplicate_data_parsing(self):
        """
        test example 1-(5), duplicate data in train dataset or label dataset.
        """
        train_duplicate = pd.read_parquet('test/train_duplicate.parquet', engine='pyarrow')
        label_dataset = self.label_small
        result_dataset = self.result_dataset
        label_dataset['time'] = pd.to_datetime(label_dataset['time'])
        train_duplicate['time'] = pd.to_datetime(train_duplicate['time'])
        result_dataset['time'] = pd.to_datetime(result_dataset['time'])

        # model training
        mlflow_model = MlflowFaultDiagnosis(task_id=self.task_id,
                                            time_zone=self.time_zone,
                                            diagnosis_window=self.diagnosis_window,
                                            window_one_label=self.window_one_label,
                                            source_dataset='',
                                            label_dataset="",
                                            result_table="",
                                            label_map=json.loads(self.label_map)
                                            )
        new_dataset = mlflow_model.init_train_data(
            train_duplicate, label_dataset, result_dataset)
        self.assertEqual(new_dataset.duplicated().sum(), 0)

    # def test_first_training_1_6(self):
    #     """
    #     test example 1-(6), train dataset has different timezone with local tz.
    #     """
    #     source_dataset = pd.read_parquet('test/train_utc.parquet', engine='pyarrrow')
    #     label_dataset = pd.read_parquet('test/label_small.parquet', engine='pyarrrow')
    #     result_table = "fault_result_0825"
    #
    #     time_zone = 'UTC'
    #     label_map = json.dumps({'suite-0': 20, 'suite-1': 21, 'suite-2': 22,
    #                             'suite-3': 23, 'suite-4': 24, 'suite-5': 25,
    #                             0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7,
    #                             8: 8, 9: 9, 10: 10, 11: 11, 12: 12, 13: 13,
    #                             14: 14, 15: 15, 16: 16, 17: 17})
    #
    #     # model training
    #     mlflow_model = MlflowFaultDiagnosis(task_id='test',
    #                                         time_zone=time_zone,
    #                                         diagnosis_window='1d',
    #                                         window_one_label=1,
    #                                         source_dataset=source_dataset,
    #                                         label_dataset=label_dataset,
    #                                         result_table=result_table,
    #                                         label_map=label_map
    #                                         )
    #     mlflow_model.train()

    def test_label_dup_checking(self):
        """
        test example 1-(7), label dataset has only one type of label.
        """
        source_dataset = self.train_small
        label_dataset = self.label_small.copy()
        result_dataset = self.result_dataset
        label_dataset['time'] = pd.to_datetime(label_dataset['time'])
        source_dataset['time'] = pd.to_datetime(source_dataset['time'])
        result_dataset['time'] = pd.to_datetime(result_dataset['time'])

        label_dataset.custom_label_id = 1

        # model training
        mlflow_model = MlflowFaultDiagnosis(
            task_id='test', time_zone=self.time_zone, diagnosis_window='1d',
            window_one_label=1, source_dataset='', label_dataset='',
            result_table='', label_map=json.loads(self.label_map))
        with self.assertRaises(ParamException) as cm:
            mlflow_model.init_train_data(source_dataset, label_dataset, result_dataset)
        the_exception = cm.exception
        self.assertEqual(the_exception.message,
                         'Only support data with more than one type of label')

    def test_label_mapping_checking(self):
        """
        test example 1-(8), label dataset cannot map with label_map.
        """
        source_dataset = self.train_small
        label_dataset = self.label_small
        result_dataset = self.result_dataset
        label_dataset['time'] = pd.to_datetime(label_dataset['time'])
        source_dataset['time'] = pd.to_datetime(source_dataset['time'])
        result_dataset['time'] = pd.to_datetime(result_dataset['time'])

        wrong_label_map = json.dumps({'suite-0': 20, 'suite-1': 21,
                                      'suite-2': 22, 'suite-3': 23,
                                      'suite-4': 24, 'suite-5': 25})

        # model training
        mlflow_model = MlflowFaultDiagnosis(task_id=self.task_id,
                                            time_zone=self.time_zone,
                                            diagnosis_window=self.diagnosis_window,
                                            window_one_label=self.window_one_label,
                                            source_dataset="",
                                            label_dataset="",
                                            result_table="",
                                            label_map=json.loads(wrong_label_map)
                                            )
        with self.assertRaises(ParamException) as cm:
            mlflow_model.init_train_data(source_dataset, label_dataset, result_dataset)
        the_exception = cm.exception
        self.assertEqual(the_exception.message,
                         'Label df cannot be mapped with label_map, check if they have same label')


class TestPrediction(ut.TestCase):
    task_id = 'test'
    time_zone = 'Asia/Shanghai'
    diagnosis_window = '1d'
    window_one_label = 1
    label_map = json.dumps({'suite-0': 20, 'suite-1': 21, 'suite-2': 22,
                            'suite-3': 23, 'suite-4': 24, 'suite-5': 25,
                            0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7,
                            8: 8, 9: 9, 10: 10, 11: 11, 12: 12, 13: 13,
                            14: 14, 15: 15, 16: 16, 17: 17})
    predict_small = pd.read_parquet('test/predict_small.parquet', engine='pyarrow')

    def test_first_prediction_2_1(self):
        """
        test example 2-(1), all params are correct
        """
        new_dataset = self.predict_small
        new_dataset['time'] = pd.to_datetime(new_dataset['time'])
        new_dataset['time_window'] = pd.to_datetime(new_dataset['time_window'])
        feature_list = ['value_flat_max', 'i_cal_autocorrelation_1', 'diff_value_i_cal_nanmedian', 'value_diff_nanmax', 'value_diff_flat_max', 'value_i_cal_eu_dist', 'value_autocorrelation_1', 'value_autocorrelation_2', 'value_flat_rate', 'value_diff_max_min', 'value_autocorrelation_3', 'value_i_cal_pearson_', 'value_diff_flat_rate', 'value_diff_benford_correlation', 'value_diff_nanmin', 'diff_value_i_cal_nanmax', 'value_i_cal_spearman', 'value_max_min', 'i_cal_diff_autocorrelation_3', 'value_max_drop', 'value_nanmax', 'value_diff_cid', 'value_diff_max_drop', 'value_benford_correlation', 'value_nanmedian', 'value_flat_count', 'value_diff_autocorrelation_3', 'diff_value_i_cal_nanstd', 'value_diff_autocorrelation_2', 'value_variance_larger_than_standard_deviation', 'value_nanstd', 'value_diff_nanstd', 'value_last_location_of_maximum', 'i_cal_cid', 'value_diff_kurtosis', 'value_quantile_95', 'value_first_location_of_maximum', 'value_nanmin', 'value_above_mean_ratio', 'value_i_cal_dtw', 'i_cal_diff_autocorrelation_2', 'value_quantile_65', 'i_cal_benford_correlation', 'value_diff_first_location_of_minimum', 'value_diff_flat_count', 'value_diff_quantile_85', 'value_quantile_85', 'value_cid', 'value_diff_last_location_of_maximum', 'value_diff_absolute_sum_of_changes']
        model_path = 'test/model_0824.pkl'  # 注意特征顺序！！！
        with open(model_path, 'rb') as f:
            model = pickle.load(f)

        obj_model = FaultDiagnosis(
            time_zone=self.time_zone,
            diagnosis_window=self.diagnosis_window,
            window_one_label=self.window_one_label,
            time_field='time',
            label_field='label',
            id_fields=['site_id', 'device_id', 'branch_id', 'time_window'],
            value_fields=['value', 'i_cal'],
        )
        obj_model.feature_list = feature_list
        obj_model.model = model
        obj_model.predict(model, new_dataset)


if __name__ == '__main__':
    ut.main()
