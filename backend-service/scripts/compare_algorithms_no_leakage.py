# @AI_GENERATED: Kiro v1.0
"""
算法对比测试脚本 - 无数据泄露版本

修复了以下数据泄露问题：
1. 归一化仅使用训练集统计量
2. 使用时序划分而非随机划分
3. 测试集严格在训练集之后
"""
import os
import csv
import math

# ============================================================
# 数据加载
# ============================================================

def load_pv_data(use_full_year=True):
    """加载光伏数据
    
    Args:
        use_full_year: True使用1年数据(35040条), False使用1天样本(96条)
    """
    if use_full_year:
        filename = 'pv_power_data.csv'  # 1年数据
    else:
        filename = 'pv_power_sample.csv'  # 1天样本
    
    data_path = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'demo', filename
    )
    
    data = []
    columns = []
    
    with open(data_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        columns = next(reader)
        for row in reader:
            parsed = [row[0]]  # timestamp
            for val in row[1:]:
                try:
                    parsed.append(float(val))
                except:
                    parsed.append(0.0)
            data.append(parsed)
    
    return columns, data


def time_series_split(data, test_ratio=0.2, filter_valid=True):
    """
    时序划分 - 无数据泄露版本
    
    关键点：
    1. 不打乱数据，保持时序顺序
    2. 测试集严格在训练集之后
    3. 先过滤有效数据，再划分（保证测试集有数据）
    """
    power_col_idx = 6  # power_actual 列
    
    # 先过滤有效数据（白天有发电的时段）
    if filter_valid:
        valid_data = [row for row in data if row[power_col_idx] > 0]
    else:
        valid_data = data
    
    # 再按时序划分（不打乱！）
    split_idx = int(len(valid_data) * (1 - test_ratio))
    train_data = valid_data[:split_idx]
    test_data = valid_data[split_idx:]
    
    return train_data, test_data


def normalize_with_train_stats(train_data, test_data, columns):
    """
    归一化 - 仅使用训练集统计量
    
    关键点：
    1. min/max 仅从训练集计算
    2. 测试集使用训练集的统计量归一化
    3. 测试集可能超出 [0,1] 范围（这是正常的）
    """
    # 仅用训练集计算 min/max
    min_vals = {}
    max_vals = {}
    
    for col_idx in range(1, len(columns)):
        train_col_values = [row[col_idx] for row in train_data]
        min_vals[col_idx] = min(train_col_values)
        max_vals[col_idx] = max(train_col_values)
    
    def normalize_rows(data):
        normalized = []
        for row in data:
            new_row = [row[0]]
            for col_idx in range(1, len(row)):
                min_v = min_vals[col_idx]
                max_v = max_vals[col_idx]
                if max_v > min_v:
                    # 注意：测试集可能超出 [0,1]
                    scaled = (row[col_idx] - min_v) / (max_v - min_v)
                else:
                    scaled = 0
                new_row.append(scaled)
            normalized.append(new_row)
        return normalized
    
    train_normalized = normalize_rows(train_data)
    test_normalized = normalize_rows(test_data)
    
    return train_normalized, test_normalized, min_vals, max_vals


def extract_features_targets(data, power_col_idx=6):
    """提取特征和目标"""
    X = []
    y = []
    
    for row in data:
        features = [row[i] for i in range(1, power_col_idx)]
        target = row[power_col_idx]
        X.append(features)
        y.append(target)
    
    return X, y


# ============================================================
# 本项目改进算法 (正规方程 + Ridge正则化)
# ============================================================

def ridge_regression(X_train, y_train, X_test, lambda_reg=0.01):
    """Ridge 回归"""
    n = len(X_train)
    if n == 0:
        return {'weights': [0.0], 'y_pred_train': [], 'y_pred_test': []}
    
    n_features = len(X_train[0])
    
    # 添加偏置列
    X_with_bias = [[1.0] + row for row in X_train]
    m = n_features + 1
    
    # 计算 X^T X
    XtX = [[0.0] * m for _ in range(m)]
    for i in range(m):
        for j in range(m):
            XtX[i][j] = sum(X_with_bias[k][i] * X_with_bias[k][j] for k in range(n))
    
    # 添加 L2 正则化
    for i in range(1, m):
        XtX[i][i] += lambda_reg * n
    
    # 计算 X^T y
    Xty = [sum(X_with_bias[k][i] * y_train[k] for k in range(n)) for i in range(m)]
    
    # 高斯消元法求解
    weights = solve_linear_system(XtX, Xty)
    
    # 计算训练集目标范围
    target_min = min(y_train)
    target_max = max(y_train)
    
    # 预测函数
    def predict(X, constrain=True):
        preds = []
        for row in X:
            pred = weights[0]
            for k, f in enumerate(row):
                pred += weights[k + 1] * f
            
            if constrain:
                pred = max(target_min, min(target_max, pred))
                pred = max(0, pred)
            preds.append(pred)
        return preds
    
    y_pred_train = predict(X_train)
    y_pred_test = predict(X_test) if X_test else []
    
    return {
        'weights': weights,
        'y_pred_train': y_pred_train,
        'y_pred_test': y_pred_test,
        'target_range': (target_min, target_max)
    }


def solve_linear_system(A, b):
    """高斯消元法"""
    n = len(A)
    aug = [A[i][:] + [b[i]] for i in range(n)]
    
    for col in range(n):
        max_row = col
        for row in range(col + 1, n):
            if abs(aug[row][col]) > abs(aug[max_row][col]):
                max_row = row
        aug[col], aug[max_row] = aug[max_row], aug[col]
        
        if abs(aug[col][col]) < 1e-10:
            continue
        
        for row in range(col + 1, n):
            factor = aug[row][col] / aug[col][col]
            for j in range(col, n + 1):
                aug[row][j] -= factor * aug[col][j]
    
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        if abs(aug[i][i]) < 1e-10:
            x[i] = 0.0
        else:
            x[i] = aug[i][n]
            for j in range(i + 1, n):
                x[i] -= aug[i][j] * x[j]
            x[i] /= aug[i][i]
    
    return x


# ============================================================
# 评估指标
# ============================================================

def calc_metrics(y_true, y_pred):
    """计算评估指标"""
    n = len(y_true)
    if n == 0:
        return {'rmse': 0, 'mae': 0, 'r2': 0, 'mape': 0}
    
    # RMSE
    mse = sum((y_true[i] - y_pred[i])**2 for i in range(n)) / n
    rmse = math.sqrt(mse)
    
    # MAE
    mae = sum(abs(y_true[i] - y_pred[i]) for i in range(n)) / n
    
    # R²
    y_mean = sum(y_true) / n
    ss_tot = sum((y_true[i] - y_mean)**2 for i in range(n))
    ss_res = sum((y_true[i] - y_pred[i])**2 for i in range(n))
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    
    # MAPE (过滤掉太小的值，避免除以接近零的数)
    mape_vals = []
    threshold = 0.05  # 只计算大于5%最大值的样本
    max_val = max(y_true) if y_true else 1
    for i in range(n):
        if y_true[i] > threshold * max_val:
            mape_vals.append(abs((y_true[i] - y_pred[i]) / y_true[i]))
    mape = (sum(mape_vals) / len(mape_vals) * 100) if mape_vals else 0
    
    return {
        'rmse': round(rmse, 4),
        'mae': round(mae, 4),
        'r2': round(r2, 4),
        'mape': round(mape, 2),
        'mape_samples': len(mape_vals)
    }


# ============================================================
# 主测试函数
# ============================================================

def main():
    print("=" * 70)
    print("算法测试 - 无数据泄露版本（1年数据）")
    print("=" * 70)
    
    # 1. 加载数据
    print("\n1. 加载数据...")
    columns, raw_data = load_pv_data(use_full_year=True)
    print(f"   原始数据: {len(raw_data)} 行, {len(columns)} 列")
    print(f"   数据时间范围: {raw_data[0][0]} ~ {raw_data[-1][0]}")
    
    # 2. 时序划分（不打乱！）
    print("\n2. 时序划分（测试集在训练集之后）...")
    train_raw, test_raw = time_series_split(raw_data, test_ratio=0.2, filter_valid=True)
    print(f"   训练集: {len(train_raw)} 个有效样本")
    print(f"   测试集: {len(test_raw)} 个有效样本")
    
    # 显示时间范围
    if train_raw and test_raw:
        print(f"   训练集时间: {train_raw[0][0]} ~ {train_raw[-1][0]}")
        print(f"   测试集时间: {test_raw[0][0]} ~ {test_raw[-1][0]}")
    
    # 3. 归一化（仅用训练集统计量）
    print("\n3. 归一化（仅用训练集统计量）...")
    train_norm, test_norm, min_vals, max_vals = normalize_with_train_stats(
        train_raw, test_raw, columns
    )
    
    # 检查测试集是否超出 [0,1] 范围
    test_out_of_range = 0
    for row in test_norm:
        for val in row[1:]:
            if val < 0 or val > 1:
                test_out_of_range += 1
    print(f"   测试集超出 [0,1] 范围的值: {test_out_of_range} 个")
    
    # 4. 提取特征和目标
    X_train, y_train = extract_features_targets(train_norm)
    X_test, y_test = extract_features_targets(test_norm)
    
    print(f"   特征数: {len(X_train[0]) if X_train else 0}")
    print(f"   训练集目标范围: [{min(y_train):.4f}, {max(y_train):.4f}]" if y_train else "")
    print(f"   测试集目标范围: [{min(y_test):.4f}, {max(y_test):.4f}]" if y_test else "")
    
    # 5. 训练模型
    print("\n" + "=" * 70)
    print("Ridge 回归（无数据泄露）")
    print("=" * 70)
    
    result = ridge_regression(X_train, y_train, X_test, lambda_reg=0.01)
    
    print("\n权重:")
    feature_names = ['irradiance', 'temperature', 'humidity', 'wind_speed', 'cloud_cover']
    print(f"   bias: {result['weights'][0]:.4f}")
    for i, name in enumerate(feature_names):
        if i + 1 < len(result['weights']):
            print(f"   {name}: {result['weights'][i+1]:.4f}")
    
    # 6. 评估
    train_metrics = calc_metrics(y_train, result['y_pred_train'])
    test_metrics = calc_metrics(y_test, result['y_pred_test'])
    
    print("\n训练集指标:")
    print(f"   R²: {train_metrics['r2']}")
    print(f"   RMSE: {train_metrics['rmse']}")
    print(f"   MAPE: {train_metrics['mape']}%")
    
    print("\n测试集指标:")
    print(f"   R²: {test_metrics['r2']}")
    print(f"   RMSE: {test_metrics['rmse']}")
    print(f"   MAPE: {test_metrics['mape']}%")
    
    # 7. 对比
    print("\n" + "=" * 70)
    print("与有泄露版本对比")
    print("=" * 70)
    
    print("\n| 指标 | 有泄露版本 | 无泄露版本 | 变化 |")
    print("|------|-----------|-----------|------|")
    print(f"| 测试R² | 0.9926 | {test_metrics['r2']} | {test_metrics['r2'] - 0.9926:+.4f} |")
    print(f"| 测试RMSE | 0.0279 | {test_metrics['rmse']} | {test_metrics['rmse'] - 0.0279:+.4f} |")
    print(f"| 测试MAPE | 10.76% | {test_metrics['mape']}% | {test_metrics['mape'] - 10.76:+.2f}% |")
    
    # 8. 预测对比
    print("\n" + "=" * 70)
    print("预测对比（测试集前20个样本）")
    print("=" * 70)
    
    print("\n| 样本 | 时间 | 实际值 | 预测值 | 误差 |")
    print("|------|------|--------|--------|------|")
    
    for i in range(min(20, len(y_test), len(result['y_pred_test']))):
        actual = y_test[i]
        pred = result['y_pred_test'][i]
        err = abs(actual - pred) / actual * 100 if actual > 0 else 0
        time_str = test_raw[i][0] if i < len(test_raw) else "N/A"
        print(f"| {i+1} | {time_str} | {actual:.4f} | {pred:.4f} | {err:.1f}% |")
    
    # 9. 结论
    print("\n" + "=" * 70)
    print("结论")
    print("=" * 70)
    
    if test_metrics['r2'] < 0.9:
        print("\n⚠️ 修复数据泄露后，模型精度显著下降")
        print("   这说明之前的高精度是由数据泄露造成的虚假结果")
    else:
        print("\n✅ 即使修复数据泄露，模型仍有较好的精度")
    
    print("\n关键修复点:")
    print("   1. 时序划分：测试集严格在训练集之后")
    print("   2. 归一化：仅使用训练集统计量")
    print("   3. 无随机打乱：保持时序结构")
    
    return test_metrics


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
