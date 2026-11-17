"""
模型包装器模块
为不同类型的模型提供统一的训练和预测接口
支持五折交叉验证、超参数寻优和模型持久化
"""
from functools import reduce
import operator
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

logger = logging.getLogger(__name__)


class BaseModelWrapper(ABC):
    """
    模型包装器基类
    
    提供统一的训练和预测接口，支持五折交叉验证和超参数寻优
    所有模型都应该继承此类并实现抽象方法
    """
    
    def __init__(self, farm_id, capacity):
        """
        初始化模型包装器
        
        子类可以在自己的__init__中添加特定参数，但应该调用super().__init__()
        """
        self.farm_id = farm_id
        self.capacity = capacity
        # 存储训练好的模型（五个fold）
        self.models = None
        
        # 存储特征列名
        self.feature_names = None
        
        # 训练状态
        self.is_trained = False
        
        # 超参数寻优相关
        self.best_params = None
        self.param_search_results = []

    def _get_default_param_grid(self) -> Dict[str, List[Any]]:
        """
        获取默认的超参数搜索空间（子类必须实现）
        
        Returns:
            参数网格字典，例如：
            {
                'n_estimators': [50, 100, 200],
                'max_depth': [10, 20, None]
            }
        """
        return {}
    

    def _get_model_importance(self, model: Any) -> np.ndarray:
        """
        获取模型的特征重要性（子类必须实现）
        
        Args:
            model: 模型实例
        
        Returns:
            特征重要性数组，长度应与特征数量一致
        """
        pass

    def _feature_clean(self, x_df, y_df=None, cleaning_x=True):
        """清除含有空值的样本。可选择是否保留X中的空值。"""
        if cleaning_x:
            if isinstance(x_df, pd.DataFrame):
                is_valid = x_df.notnull().all(axis=1)
            else:
                is_valid = x_df.notnull()
        else:
            is_valid = pd.Series(np.ones(len(x_df), dtype=bool), index=x_df.index)
        if y_df is not None:
            if isinstance(y_df, pd.DataFrame):
                is_valid = is_valid & y_df.notnull().all(axis=1)
            else:
                is_valid = is_valid & y_df.notnull()
        x_clean = x_df.loc[is_valid]
        if y_df is not None:
            y_clean = y_df.loc[is_valid]
            return x_clean, y_clean, is_valid
        else:
            return x_clean, is_valid
    
    def _create_cv_index(self, i_set: np.ndarray, n_folds: int = 5, shuffle: bool = False, seed=123) -> np.ndarray:
        """
        创建五折交叉验证索引
        
        Args:
            i_set: 数据集标识数组，同一天的数据具有相同的i_set值
            n_folds: 折数，固定为5
        
        Returns:
            cv_index: 交叉验证索引数组
        """
        i_set_unique = np.unique(i_set)
        if shuffle:
            if seed is not None:
                np.random.seed(seed)
            np.random.shuffle(i_set_unique)
        cv_index = np.ones_like(i_set, dtype=int) * -1
        for k in range(n_folds):
            for m in i_set_unique[k::n_folds]:
                cv_index[i_set == m] = k
        return cv_index

    @abstractmethod
    def _hyperparameter_search(self, X_train: pd.DataFrame, y_train: pd.Series,
                               X_val: pd.DataFrame, y_val: pd.Series,
                               param_grid: Optional[Dict[str, List[Any]]] = None,
                               n_iters: int = 32, **kwargs):
        """
        超参数搜索
        
        Args:
            X: 特征矩阵
            y: 目标变量
            cv_index: 交叉验证索引
            param_grid: 参数网格，如果为None则使用默认网格
            n_folds: 折数，固定为5
        
        Returns:
            最优参数字典
        """
        pass

    @abstractmethod
    def train(self, X: pd.DataFrame, y: pd.DataFrame):
        """
        训练模型, 不同的模型训练方法不一致，需要重写
        
        流程：
        1. 准备数据（去除NaN，创建i_set）
        2. 创建五折交叉验证索引
        3. 超参数搜索（如果启用）
        4. 使用最优参数训练五个fold的模型
        5. 计算OOF预测和评估指标
        
        Args:
            X: 特征矩阵（必须有DatetimeIndex）
            y: 目标变量
        
        Returns:
            训练结果字典
        """
        pass

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        使用训练好的模型进行预测
        
        Args:
            X: 特征矩阵
            use_average: 是否使用所有fold模型的平均预测，默认True
        
        Returns:
            预测结果数组
        """
        pass
    
    def _evaluate(self, y_true: np.ndarray, y_pred: np.ndarray, capacity: float = None) -> Dict[str, float]:
        """
        评估模型性能
        
        Args:
            y_true: 真实值
            y_pred: 预测值
            capacity: 场站容量，如果为风速则传入None
        
        Returns:
            评估指标字典
        """
        if capacity is None:
            rmse = np.sqrt(mean_squared_error(y_true, y_pred))
            mae = mean_absolute_error(y_true, y_pred)
        else:
            rmse = np.sqrt(mean_squared_error(y_true, y_pred)) / capacity
            mae = mean_absolute_error(y_true, y_pred) / capacity

        spearman_corr = np.corrcoef(y_true, y_pred)[0, 1]
        
        return {
            'rmse': float(rmse),
            'mae': float(mae),
            'spearman_corr': float(spearman_corr)
        }

class _ParameterSampler(object):
    def __init__(self, param_distribution, n_iter):
        self.param_distr = param_distribution
        self.n_iter = n_iter
        self.p = None
        if isinstance(self.param_distr, list):
            n_sets = []
            for param_dict in self.param_distr:
                n_sets.append(reduce(operator.mul, [len(x) for x in param_dict.values()]))
            self.p = np.array(n_sets) / sum(n_sets)

    def __iter__(self):
        for kk in range(self.n_iter):
            if isinstance(self.param_distr, list):
                i_grid = np.random.choice(range(len(self.param_distr)), p=self.p)
                yield self.random_sample(self.param_distr[i_grid])
            else:
                yield self.random_sample(self.param_distr)

    @staticmethod
    def random_sample(params_grid):
        result = {}
        for k, v in params_grid.items():
            result[k] = np.random.choice(v)
        return result