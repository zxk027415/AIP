"""
线性模型包装器
实现完整的训练和预测流程
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Any
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from backend.models.model_wrapper import BaseModelWrapper, _ParameterSampler

logger = logging.getLogger(__name__)


class LinearModelWrapper(BaseModelWrapper):
    """
    线性模型包装器
    
    支持: LinearRegression, Ridge, Lasso
    
    训练流程：
    1. 数据清洗 (feature_clean)
    2. 构建五折CV索引
    3. 使用一折数据进行超参数搜索
    4. 使用最优参数在五折上分别训练模型
    5. 使用最优参数在全量数据上训练最终模型
    """
    
    def __init__(self, farm_id: str, capacity: float, model_type: str = 'linear'):
        """
        初始化线性模型包装器
        
        Args:
            farm_id: 场站ID
            capacity: 场站容量
            model_type: 模型类型，可选 'linear', 'ridge', 'lasso'
        """
        super().__init__(farm_id, capacity)
        self.model_type = model_type
        
        if model_type not in ['linear', 'ridge', 'lasso']:
            raise ValueError(f"不支持的线性模型类型: {model_type}")

    def _create_model(self, params: Dict[str, Any]) -> Any:
        """创建线性模型实例"""
        if self.model_type == 'linear':
            return LinearRegression()
        elif self.model_type == 'ridge':
            return Ridge(**params)
        elif self.model_type == 'lasso':
            return Lasso(**params)
    
    def _get_default_param_grid(self) -> Dict[str, List[Any]]:
        """获取默认的超参数搜索空间"""
        if self.model_type == 'linear':
            # 线性回归没有超参数
            return {}
        elif self.model_type == 'ridge':
            return {
                'alpha': [0.01, 0.1, 0.5, 1.0, 5.0, 10.0]
            }
        elif self.model_type == 'lasso':
            return {
                'alpha': [0.01, 0.1, 0.5, 1.0, 5.0, 10.0]
            }
        else:
            return {}
    
    def _get_model_importance(self, model: Any) -> np.ndarray:
        """获取线性模型的特征重要性（系数绝对值）"""
        return np.abs(model.coef_)
    
    def _hyperparameter_search(self, X_train: pd.DataFrame, y_train: pd.Series,
                              X_val: pd.DataFrame, y_val: pd.Series,
                              param_grid: Optional[Dict[str, List[Any]]] = None,
                               n_iters: int=32,
                              **kwargs):
        """
        使用单折数据进行超参数搜索
        
        Args:
            X_train: 训练特征
            y_train: 训练目标
            X_val: 验证特征
            y_val: 验证目标
            param_grid: 参数网格
        
        Returns:
            最优参数字典
        """
        # 获取参数网格
        if param_grid is None:
            param_grid = self._get_default_param_grid()
        
        if not param_grid:
            logger.info('没有超参数需要搜索，使用默认参数')
            return [], []

        param_list, score_list = [], []

        for param in _ParameterSampler(param_grid, n_iters):
            model = self._create_model(param)
            model.fit(X_train, y_train)
            y_pred = model.predict(X_val)
            rmse = np.sqrt(((y_val - y_pred) ** 2).mean())

            param_list.append(param)
            score_list.append(rmse)

        return score_list, param_list
    
    def train(self, X: pd.DataFrame, y: pd.DataFrame,
             param_grid: Optional[Dict[str, List[Any]]] = None,
             enable_search: bool = True,
             search_fold: int = 0):
        """
        训练线性模型
        
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
        n_folds = 5  # 固定为五折
        
        # 步骤1: 数据清洗
        logger.info('步骤1: 数据清洗 (feature_clean)')

        cv_index = self._create_cv_index(X['i.set'], n_folds, shuffle=True, seed=2026)

        y_series = y['POWER']
        X_clean, y_clean, is_valid = self._feature_clean(X, y_series, cleaning_x=True)
        i_fold = cv_index[is_valid]

        # 保存特征名称（排除 i.set）
        self.feature_names = [x for x in X_clean.columns if x not in ['i.set']]
        
        # 移除 i.set 列用于训练
        X_clean_train = X_clean[self.feature_names]

        X_train, y_train = X_clean_train[i_fold != 0], y_clean[i_fold != 0]
        X_val, y_val = X_clean_train[i_fold == 0], y_clean[i_fold == 0]

        param_list, score_list = self._hyperparameter_search(X_train, y_train, X_val, y_val, param_grid)
        if len(param_list) > 0:
            idx_min = np.argmin(score_list)
            bst_params = param_list[idx_min]
            bst_socre = score_list[idx_min]
            logger.info(f"Linear model - {self.model_type}: best score: {bst_socre}, best params: {bst_params}")
            prediction, bst_model = self.cross_prediction(X_clean_train, y_clean, i_fold, bst_params)
        else:
            prediction, bst_model = self.cross_prediction(X_clean_train, y_clean, i_fold, None)
        self.models = bst_model

        metrics = self._evaluate(y_clean.values, prediction, capacity=self.capacity)
        logger.info(f"Linear model - {self.model_type}: {metrics}")
        
        self.is_trained = True
        return {"metrics": metrics, "predictions": prediction}


    def cross_prediction(self, X_clean, y_clean, cv_index, bst_param):
        prediction = np.zeros_like(cv_index, dtype=float) * np.nan
        model = self._create_model(bst_param)
        for idx in np.unique(cv_index):
            X_train, y_train = X_clean[cv_index == idx], y_clean[cv_index == idx]
            X_val = X_clean[cv_index == idx]
            model.fit(X_train, y_train)
            prediction[cv_index == idx] = model.predict(X_val)
        bst = model.fit(X_clean, y_clean)
        return prediction, bst

    
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

        # 只使用训练时的特征列
        X_pred = X[self.feature_names] if isinstance(X, pd.DataFrame) else X
        predictions = self.models.predict(X_pred)
        return predictions
    
    def get_feature_importance(self) -> pd.DataFrame:
        """
        获取特征重要性（使用最终模型）
        
        Returns:
            特征重要性DataFrame
        """
        if not self.is_trained:
            raise RuntimeError("模型尚未训练，请先调用train()方法")
        
        if self.models is None:
            raise RuntimeError("最终模型不存在")
        
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
