# @AI_GENERATED: Kiro v1.0
"""
光伏发电功率预测 - 日前预测训练脚本（Agent 可编辑）

场景：每天07:00预测未来48小时（次日00:00 ~ 后天23:45）
输入：历史实测数据 + 气象预报数据
输出：48小时功率预测（192个点）

Usage: python train.py
"""

import os
import gc
import time
import numpy as np
from typing import Tuple, Dict, Any

from prepare import (
    TIME_BUDGET,
    FORECAST_HORIZON,
    HISTORY_LENGTH,
    load_pv_data,
    prepare_features,
    create_day_ahead_sequences,
    train_test_split_temporal,
    evaluate_day_ahead,
    MinMaxScaler,
)

# ---------------------------------------------------------------------------
# 超参数（可修改）
# ---------------------------------------------------------------------------

MODEL_TYPE = "linear"       # 可选: "linear", "mlp", "ridge"
HIDDEN_SIZE = 128           # MLP 隐藏层大小
NUM_LAYERS = 2              # MLP 层数
LEARNING_RATE = 0.001       # 学习率
BATCH_SIZE = 16             # 批次大小
NUM_EPOCHS = 100            # 最大训练轮数
RIDGE_ALPHA = 1.0           # Ridge 正则化系数

# 特征融合方式
FUSION_METHOD = "concat"    # 可选: "concat", "attention"

# ---------------------------------------------------------------------------
# 模型定义
# ---------------------------------------------------------------------------

class LinearDayAheadModel:
    """
    线性日前预测模型
    
    将历史特征和气象预报特征展平后拼接，用线性回归预测
    """
    
    def __init__(self, history_dim: int, forecast_dim: int, output_dim: int):
        self.history_dim = history_dim
        self.forecast_dim = forecast_dim
        self.output_dim = output_dim
        self.weights = None
        self.bias = None
    
    def fit(self, X_history: np.ndarray, X_forecast: np.ndarray, y: np.ndarray) -> 'LinearDayAheadModel':
        """最小二乘法拟合"""
        # 展平并拼接特征
        X_hist_flat = X_history.reshape(X_history.shape[0], -1)
        X_fcst_flat = X_forecast.reshape(X_forecast.shape[0], -1)
        X_combined = np.hstack([X_hist_flat, X_fcst_flat])
        
        # 添加偏置项
        X_bias = np.hstack([X_combined, np.ones((X_combined.shape[0], 1))])
        
        # 最小二乘解
        solution = np.linalg.lstsq(X_bias, y, rcond=None)[0]
        
        self.weights = solution[:-1]
        self.bias = solution[-1]
        
        return self
    
    def predict(self, X_history: np.ndarray, X_forecast: np.ndarray) -> np.ndarray:
        """预测"""
        X_hist_flat = X_history.reshape(X_history.shape[0], -1)
        X_fcst_flat = X_forecast.reshape(X_forecast.shape[0], -1)
        X_combined = np.hstack([X_hist_flat, X_fcst_flat])
        
        return X_combined @ self.weights + self.bias
    
    def num_params(self) -> int:
        if self.weights is None:
            return 0
        return self.weights.size + self.bias.size


class RidgeDayAheadModel:
    """
    Ridge 回归日前预测模型（带 L2 正则化）
    """
    
    def __init__(self, history_dim: int, forecast_dim: int, output_dim: int, alpha: float = RIDGE_ALPHA):
        self.history_dim = history_dim
        self.forecast_dim = forecast_dim
        self.output_dim = output_dim
        self.alpha = alpha
        self.weights = None
        self.bias = None
    
    def fit(self, X_history: np.ndarray, X_forecast: np.ndarray, y: np.ndarray) -> 'RidgeDayAheadModel':
        """Ridge 回归拟合"""
        X_hist_flat = X_history.reshape(X_history.shape[0], -1)
        X_fcst_flat = X_forecast.reshape(X_forecast.shape[0], -1)
        X = np.hstack([X_hist_flat, X_fcst_flat])
        
        n_features = X.shape[1]
        
        # Ridge 回归闭式解: (X'X + αI)^(-1) X'y
        XtX = X.T @ X
        Xty = X.T @ y
        
        # 添加正则化项
        reg_matrix = self.alpha * np.eye(n_features)
        
        self.weights = np.linalg.solve(XtX + reg_matrix, Xty)
        
        # 计算偏置
        y_pred = X @ self.weights
        self.bias = np.mean(y - y_pred, axis=0)
        
        return self
    
    def predict(self, X_history: np.ndarray, X_forecast: np.ndarray) -> np.ndarray:
        X_hist_flat = X_history.reshape(X_history.shape[0], -1)
        X_fcst_flat = X_forecast.reshape(X_forecast.shape[0], -1)
        X = np.hstack([X_hist_flat, X_fcst_flat])
        
        return X @ self.weights + self.bias
    
    def num_params(self) -> int:
        if self.weights is None:
            return 0
        return self.weights.size + self.bias.size


class MLPDayAheadModel:
    """
    MLP 日前预测模型
    """
    
    def __init__(
        self,
        history_dim: int,
        forecast_dim: int,
        output_dim: int,
        hidden_size: int = HIDDEN_SIZE,
        num_layers: int = NUM_LAYERS,
        learning_rate: float = LEARNING_RATE,
    ):
        self.history_dim = history_dim
        self.forecast_dim = forecast_dim
        self.output_dim = output_dim
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lr = learning_rate
        
        # 计算输入维度
        self.input_dim = history_dim + forecast_dim
        
        # 初始化权重
        self.weights = []
        self.biases = []
        
        # 输入层 -> 第一个隐藏层
        self.weights.append(np.random.randn(self.input_dim, hidden_size) * 0.01)
        self.biases.append(np.zeros(hidden_size))
        
        # 隐藏层
        for _ in range(num_layers - 1):
            self.weights.append(np.random.randn(hidden_size, hidden_size) * 0.01)
            self.biases.append(np.zeros(hidden_size))
        
        # 输出层
        self.weights.append(np.random.randn(hidden_size, output_dim) * 0.01)
        self.biases.append(np.zeros(output_dim))
    
    def relu(self, x: np.ndarray) -> np.ndarray:
        return np.maximum(0, x)
    
    def relu_grad(self, x: np.ndarray) -> np.ndarray:
        return (x > 0).astype(float)
    
    def forward(self, X: np.ndarray) -> Tuple[np.ndarray, list]:
        activations = [X]
        h = X
        
        for i in range(len(self.weights) - 1):
            h = h @ self.weights[i] + self.biases[i]
            h = self.relu(h)
            activations.append(h)
        
        output = h @ self.weights[-1] + self.biases[-1]
        activations.append(output)
        
        return output, activations
    
    def backward(self, activations: list, y: np.ndarray) -> Tuple[list, list]:
        m = y.shape[0]
        grad_weights = []
        grad_biases = []
        
        delta = (activations[-1] - y) / m
        
        for i in range(len(self.weights) - 1, -1, -1):
            grad_weights.insert(0, activations[i].T @ delta)
            grad_biases.insert(0, np.sum(delta, axis=0))
            
            if i > 0:
                delta = (delta @ self.weights[i].T) * self.relu_grad(activations[i])
        
        return grad_weights, grad_biases
    
    def fit(
        self,
        X_history: np.ndarray,
        X_forecast: np.ndarray,
        y: np.ndarray,
        epochs: int = NUM_EPOCHS,
        batch_size: int = BATCH_SIZE,
        verbose: bool = True,
    ) -> 'MLPDayAheadModel':
        # 展平并拼接
        X_hist_flat = X_history.reshape(X_history.shape[0], -1)
        X_fcst_flat = X_forecast.reshape(X_forecast.shape[0], -1)
        X = np.hstack([X_hist_flat, X_fcst_flat])
        
        n_samples = X.shape[0]
        
        for epoch in range(epochs):
            indices = np.random.permutation(n_samples)
            X_shuffled = X[indices]
            y_shuffled = y[indices]
            
            epoch_loss = 0
            n_batches = 0
            
            for i in range(0, n_samples, batch_size):
                X_batch = X_shuffled[i:i + batch_size]
                y_batch = y_shuffled[i:i + batch_size]
                
                output, activations = self.forward(X_batch)
                loss = np.mean((output - y_batch) ** 2)
                epoch_loss += loss
                n_batches += 1
                
                grad_weights, grad_biases = self.backward(activations, y_batch)
                
                for j in range(len(self.weights)):
                    self.weights[j] -= self.lr * grad_weights[j]
                    self.biases[j] -= self.lr * grad_biases[j]
            
            if verbose and (epoch + 1) % 20 == 0:
                print(f"Epoch {epoch + 1}/{epochs}, Loss: {epoch_loss / n_batches:.6f}")
        
        return self
    
    def predict(self, X_history: np.ndarray, X_forecast: np.ndarray) -> np.ndarray:
        X_hist_flat = X_history.reshape(X_history.shape[0], -1)
        X_fcst_flat = X_forecast.reshape(X_forecast.shape[0], -1)
        X = np.hstack([X_hist_flat, X_fcst_flat])
        
        output, _ = self.forward(X)
        return output
    
    def num_params(self) -> int:
        total = 0
        for w, b in zip(self.weights, self.biases):
            total += w.size + b.size
        return total


# ---------------------------------------------------------------------------
# 训练流程
# ---------------------------------------------------------------------------

def get_model(history_dim: int, forecast_dim: int, output_dim: int) -> Any:
    """根据配置获取模型"""
    if MODEL_TYPE == "linear":
        return LinearDayAheadModel(history_dim, forecast_dim, output_dim)
    elif MODEL_TYPE == "ridge":
        return RidgeDayAheadModel(history_dim, forecast_dim, output_dim, alpha=RIDGE_ALPHA)
    elif MODEL_TYPE == "mlp":
        return MLPDayAheadModel(
            history_dim, forecast_dim, output_dim,
            hidden_size=HIDDEN_SIZE,
            num_layers=NUM_LAYERS,
            learning_rate=LEARNING_RATE,
        )
    else:
        raise ValueError(f"未知模型类型: {MODEL_TYPE}")


def train_and_evaluate() -> Dict[str, Any]:
    """主训练和评估流程"""
    t_start = time.time()
    
    # 1. 加载数据
    print("加载数据...")
    df = load_pv_data()
    df = prepare_features(df)
    
    # 2. 创建日前预测序列
    print("\n创建日前预测序列...")
    X_history, X_forecast, y, dates = create_day_ahead_sequences(df)
    
    print(f"历史输入形状: {X_history.shape}")
    print(f"预报输入形状: {X_forecast.shape}")
    print(f"目标形状: {y.shape}")
    
    # 3. 标准化
    print("\n标准化数据...")
    # 历史特征标准化
    n_samples = X_history.shape[0]
    X_hist_flat = X_history.reshape(n_samples, -1)
    hist_scaler = MinMaxScaler()
    X_hist_scaled = hist_scaler.fit_transform(X_hist_flat).reshape(X_history.shape)
    
    # 预报特征标准化
    X_fcst_flat = X_forecast.reshape(n_samples, -1)
    fcst_scaler = MinMaxScaler()
    X_fcst_scaled = fcst_scaler.fit_transform(X_fcst_flat).reshape(X_forecast.shape)
    
    # 目标标准化
    target_scaler = MinMaxScaler()
    y_scaled = target_scaler.fit_transform(y)
    
    # 4. 划分数据集
    print("\n划分数据集...")
    (X_hist_train, X_hist_test, 
     X_fcst_train, X_fcst_test, 
     y_train, y_test) = train_test_split_temporal(X_hist_scaled, X_fcst_scaled, y_scaled)
    
    # 5. 训练模型
    print(f"\n训练 {MODEL_TYPE} 模型...")
    t_train_start = time.time()
    
    history_dim = X_hist_train.shape[1] * X_hist_train.shape[2]
    forecast_dim = X_fcst_train.shape[1] * X_fcst_train.shape[2]
    output_dim = y_train.shape[1]
    
    model = get_model(history_dim, forecast_dim, output_dim)
    
    if MODEL_TYPE in ["linear", "ridge"]:
        model.fit(X_hist_train, X_fcst_train, y_train)
    else:
        remaining_budget = max(10, TIME_BUDGET - (time.time() - t_start) - 30)
        test_epochs = 2
        t_test = time.time()
        model.fit(X_hist_train[:5], X_fcst_train[:5], y_train[:5], epochs=test_epochs, verbose=False)
        time_per_epoch = (time.time() - t_test) / test_epochs * (len(X_hist_train) / 5)
        max_epochs = min(NUM_EPOCHS, int(remaining_budget / max(time_per_epoch, 0.1)))
        print(f"时间预算: {remaining_budget:.0f}s, 最大epochs: {max_epochs}")
        
        model = get_model(history_dim, forecast_dim, output_dim)
        model.fit(X_hist_train, X_fcst_train, y_train, epochs=max_epochs)
    
    training_time = time.time() - t_train_start
    
    # 6. 预测
    print("\n评估模型...")
    y_pred_scaled = model.predict(X_hist_test, X_fcst_test)
    
    # 反标准化
    y_pred = target_scaler.inverse_transform(y_pred_scaled)
    y_true = target_scaler.inverse_transform(y_test)
    
    # 7. 评估
    metrics = evaluate_day_ahead(y_true, y_pred)
    
    # 8. 统计信息
    total_time = time.time() - t_start
    num_params = model.num_params()
    
    import sys
    peak_memory_mb = sys.getsizeof(X_hist_train) / 1024 / 1024 * 3
    
    results = {
        'mape': metrics['overall_mape'],
        'rmse': metrics['overall_rmse'],
        'r2': metrics['overall_r2'],
        'day1_mape': metrics.get('day1_mape', 0),
        'day2_mape': metrics.get('day2_mape', 0),
        'daytime_mape': metrics.get('daytime_mape', 0),
        'training_seconds': training_time,
        'total_seconds': total_time,
        'peak_vram_mb': peak_memory_mb,
        'num_epochs': NUM_EPOCHS if MODEL_TYPE == "mlp" else 1,
        'model_params': num_params,
        'model_type': MODEL_TYPE,
        'train_samples': len(X_hist_train),
        'test_samples': len(X_hist_test),
    }
    
    return results


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("光伏发电功率预测 - 日前预测训练脚本")
    print("场景: 每天07:00预测未来48小时")
    print("=" * 60)
    
    np.random.seed(42)
    
    results = train_and_evaluate()
    
    print("\n" + "=" * 60)
    print("训练结果")
    print("=" * 60)
    print(f"模型类型:       {results['model_type']}")
    print(f"训练样本:       {results['train_samples']}")
    print(f"测试样本:       {results['test_samples']}")
    print("-" * 40)
    print(f"整体 MAPE:      {results['mape']:.2f}%")
    print(f"第1天 MAPE:     {results['day1_mape']:.2f}%")
    print(f"第2天 MAPE:     {results['day2_mape']:.2f}%")
    print(f"白天 MAPE:      {results['daytime_mape']:.2f}%")
    print(f"RMSE:           {results['rmse']:.2f}")
    print(f"R²:             {results['r2']:.4f}")
    print("-" * 40)
    print(f"训练时间:       {results['training_seconds']:.1f}s")
    print(f"模型参数:       {results['model_params']}")
    
    gc.collect()
# @AI_GENERATED: end
