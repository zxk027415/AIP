# @AI_GENERATED: Kiro v1.0
"""
使用真实 Kaggle 太阳能数据集进行无泄漏测试

数据集: https://www.kaggle.com/anikannal/solar-power-generation-data
- Plant_1_Generation_Data.csv: 发电数据 (68,778 条)
- Plant_1_Weather_Sensor_Data.csv: 气象数据 (3,182 条)
- 时间范围: 2020-05-15 ~ 2020-06-17 (34天)
"""
import os
import csv
import math
from datetime import datetime
from collections import defaultdict


# ============================================================
# 数据加载
# ============================================================

def load_generation_data(plant_id=1):
    """加载发电数据"""
    filename = f'Plant_{plant_id}_Generation_Data.csv'
    data_path = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'demo', filename
    )
    
    data = []
    with open(data_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 尝试多种时间格式
            dt = None
            for fmt in ['%d-%m-%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']:
                try:
                    dt = datetime.strptime(row['DATE_TIME'], fmt)
                    break
                except:
                    continue
            
            if dt is None:
                continue
            
            data.append({
                'datetime': dt,
                'plant_id': row['PLANT_ID'],
                'source_key': row['SOURCE_KEY'],
                'dc_power': float(row['DC_POWER'] or 0),
                'ac_power': float(row['AC_POWER'] or 0),
                'daily_yield': float(row['DAILY_YIELD'] or 0),
                'total_yield': float(row['TOTAL_YIELD'] or 0),
            })
    
    return data


def load_weather_data(plant_id=1):
    """加载气象数据"""
    filename = f'Plant_{plant_id}_Weather_Sensor_Data.csv'
    data_path = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'demo', filename
    )
    
    data = []
    with open(data_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 尝试多种时间格式
            dt = None
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d-%m-%Y %H:%M']:
                try:
                    dt = datetime.strptime(row['DATE_TIME'], fmt)
                    break
                except:
                    continue
            
            if dt is None:
                continue
            
            data.append({
                'datetime': dt,
                'plant_id': row['PLANT_ID'],
                'source_key': row['SOURCE_KEY'],
                'ambient_temp': float(row['AMBIENT_TEMPERATURE'] or 0),
                'module_temp': float(row['MODULE_TEMPERATURE'] or 0),
                'irradiation': float(row['IRRADIATION'] or 0),
            })
    
    return data


def merge_and_aggregate(gen_data, weather_data):
    """
    合并发电和气象数据，按时间聚合
    
    发电数据有多个逆变器，需要聚合
    气象数据只有一个传感器
    """
    # 按时间聚合发电数据
    gen_by_time = defaultdict(list)
    for row in gen_data:
        key = row['datetime'].strftime('%Y-%m-%d %H:%M')
        gen_by_time[key].append(row)
    
    # 气象数据按时间索引
    weather_by_time = {}
    for row in weather_data:
        key = row['datetime'].strftime('%Y-%m-%d %H:%M')
        weather_by_time[key] = row
    
    # 合并
    merged = []
    for time_key, gen_rows in sorted(gen_by_time.items()):
        # 聚合发电数据
        total_dc_power = sum(r['dc_power'] for r in gen_rows)
        total_ac_power = sum(r['ac_power'] for r in gen_rows)
        
        # 获取气象数据
        weather = weather_by_time.get(time_key)
        if weather is None:
            continue
        
        merged.append({
            'datetime': gen_rows[0]['datetime'],
            'dc_power': total_dc_power,
            'ac_power': total_ac_power,
            'ambient_temp': weather['ambient_temp'],
            'module_temp': weather['module_temp'],
            'irradiation': weather['irradiation'],
        })
    
    return merged


# ============================================================
# 时序划分和归一化
# ============================================================

def time_series_split(data, test_days=7):
    """
    时序划分：最后 N 天作为测试集
    """
    # 按日期分组
    days = defaultdict(list)
    for row in data:
        day_key = row['datetime'].strftime('%Y-%m-%d')
        days[day_key].append(row)
    
    sorted_days = sorted(days.keys())
    print(f"   总天数: {len(sorted_days)}")
    print(f"   日期范围: {sorted_days[0]} ~ {sorted_days[-1]}")
    
    train_days = sorted_days[:-test_days]
    test_days_list = sorted_days[-test_days:]
    
    train_data = []
    for day in train_days:
        train_data.extend(days[day])
    
    test_data = []
    for day in test_days_list:
        test_data.extend(days[day])
    
    return train_data, test_data


def normalize_with_train_stats(train_data, test_data, feature_keys):
    """
    归一化：仅使用训练集统计量
    """
    stats = {}
    for key in feature_keys:
        train_values = [row[key] for row in train_data]
        stats[key] = {
            'min': min(train_values),
            'max': max(train_values),
        }
    
    def normalize_rows(data):
        normalized = []
        for row in data:
            new_row = {'datetime': row['datetime']}
            for key in feature_keys:
                min_v = stats[key]['min']
                max_v = stats[key]['max']
                if max_v > min_v:
                    new_row[key] = (row[key] - min_v) / (max_v - min_v)
                else:
                    new_row[key] = 0
            normalized.append(new_row)
        return normalized
    
    return normalize_rows(train_data), normalize_rows(test_data), stats


def extract_features_targets(data, feature_keys, target_key='dc_power'):
    """提取特征和目标"""
    X = []
    y = []
    times = []
    
    for row in data:
        features = [row[k] for k in feature_keys if k != target_key]
        X.append(features)
        y.append(row[target_key])
        times.append(row['datetime'])
    
    return X, y, times


# ============================================================
# Ridge 回归
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
    
    # 预测
    def predict(X):
        preds = []
        for row in X:
            pred = weights[0]
            for k, f in enumerate(row):
                pred += weights[k + 1] * f
            pred = max(0, pred)  # 功率不能为负
            preds.append(pred)
        return preds
    
    y_pred_train = predict(X_train)
    y_pred_test = predict(X_test) if X_test else []
    
    return {
        'weights': weights,
        'y_pred_train': y_pred_train,
        'y_pred_test': y_pred_test,
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
    
    # MAPE (过滤小值)
    mape_vals = []
    threshold = 0.05 * max(y_true) if y_true else 1
    for i in range(n):
        if y_true[i] > threshold:
            mape_vals.append(abs((y_true[i] - y_pred[i]) / y_true[i]))
    mape = (sum(mape_vals) / len(mape_vals) * 100) if mape_vals else 0
    
    return {
        'rmse': round(rmse, 4),
        'mae': round(mae, 4),
        'r2': round(r2, 4),
        'mape': round(mape, 2),
    }


# ============================================================
# 主函数
# ============================================================

def test_plant(plant_id=1):
    """测试指定电站"""
    print("=" * 70)
    print(f"Kaggle 真实数据测试 - Plant {plant_id} - 无数据泄露版本")
    print("=" * 70)
    
    # 1. 加载数据
    print("\n1. 加载 Kaggle 原始数据...")
    gen_data = load_generation_data(plant_id=plant_id)
    weather_data = load_weather_data(plant_id=plant_id)
    print(f"   发电数据: {len(gen_data)} 条")
    print(f"   气象数据: {len(weather_data)} 条")
    
    # 2. 合并和聚合
    print("\n2. 合并发电和气象数据...")
    merged_data = merge_and_aggregate(gen_data, weather_data)
    print(f"   合并后: {len(merged_data)} 条")
    
    # 过滤有效数据（白天有发电）
    valid_data = [row for row in merged_data if row['dc_power'] > 0]
    print(f"   有效数据（dc_power > 0）: {len(valid_data)} 条")
    
    # 3. 时序划分
    print("\n3. 时序划分（最后7天作为测试集）...")
    train_raw, test_raw = time_series_split(valid_data, test_days=7)
    print(f"   训练集: {len(train_raw)} 条")
    print(f"   测试集: {len(test_raw)} 条")
    
    if train_raw and test_raw:
        print(f"   训练集时间: {train_raw[0]['datetime']} ~ {train_raw[-1]['datetime']}")
        print(f"   测试集时间: {test_raw[0]['datetime']} ~ {test_raw[-1]['datetime']}")
    
    # 4. 归一化
    print("\n4. 归一化（仅用训练集统计量）...")
    feature_keys = ['dc_power', 'ambient_temp', 'module_temp', 'irradiation']
    train_norm, test_norm, stats = normalize_with_train_stats(
        train_raw, test_raw, feature_keys
    )
    
    # 5. 提取特征和目标
    input_features = ['ambient_temp', 'module_temp', 'irradiation']
    X_train, y_train, train_times = extract_features_targets(train_norm, feature_keys)
    X_test, y_test, test_times = extract_features_targets(test_norm, feature_keys)
    
    print(f"   特征: {input_features}")
    print(f"   目标: dc_power")
    
    # 6. 训练模型
    print("\n" + "=" * 70)
    print("Ridge 回归（无数据泄露）")
    print("=" * 70)
    
    result = ridge_regression(X_train, y_train, X_test, lambda_reg=0.01)
    
    print("\n权重:")
    print(f"   bias: {result['weights'][0]:.4f}")
    for i, name in enumerate(input_features):
        if i + 1 < len(result['weights']):
            print(f"   {name}: {result['weights'][i+1]:.4f}")
    
    # 7. 评估
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
    
    # 8. 预测对比
    print("\n" + "=" * 70)
    print("预测对比（测试集前20个样本）")
    print("=" * 70)
    
    # 反归一化用于显示
    dc_min = stats['dc_power']['min']
    dc_max = stats['dc_power']['max']
    
    print("\n| 时间 | 实际功率(kW) | 预测功率(kW) | 误差 |")
    print("|------|-------------|-------------|------|")
    
    for i in range(min(20, len(y_test))):
        actual_norm = y_test[i]
        pred_norm = result['y_pred_test'][i]
        
        # 反归一化
        actual_kw = actual_norm * (dc_max - dc_min) + dc_min
        pred_kw = pred_norm * (dc_max - dc_min) + dc_min
        
        err = abs(actual_norm - pred_norm) / actual_norm * 100 if actual_norm > 0.05 else 0
        time_str = test_times[i].strftime('%m-%d %H:%M')
        print(f"| {time_str} | {actual_kw:.1f} | {pred_kw:.1f} | {err:.1f}% |")
    
    # 9. 总结
    print("\n" + "=" * 70)
    print("总结")
    print("=" * 70)
    
    print(f"""
数据集信息:
- 来源: Kaggle Solar Power Generation Data (Plant {plant_id})
- 时间范围: 34天 (2020-05-15 ~ 2020-06-17)
- 有效样本: {len(valid_data)} 条

无泄漏测试结果:
- 训练集: {len(train_raw)} 条 (前27天)
- 测试集: {len(test_raw)} 条 (后7天)
- 测试 R²: {test_metrics['r2']}
- 测试 MAPE: {test_metrics['mape']}%

结论:
- 使用真实 Kaggle 数据，严格时序划分
- R² = {test_metrics['r2']} 表示模型解释了 {test_metrics['r2']*100:.1f}% 的方差
- MAPE = {test_metrics['mape']}% 是真实的预测误差
""")
    
    return test_metrics


def main():
    """测试两个电站"""
    results = {}
    
    # 测试 Plant 1
    results['plant_1'] = test_plant(plant_id=1)
    
    print("\n" + "=" * 70)
    print("\n")
    
    # 测试 Plant 2
    results['plant_2'] = test_plant(plant_id=2)
    
    # 对比总结
    print("\n" + "=" * 70)
    print("两个电站对比")
    print("=" * 70)
    
    print("\n| 电站 | 测试 R² | 测试 MAPE |")
    print("|------|---------|----------|")
    print(f"| Plant 1 | {results['plant_1']['r2']} | {results['plant_1']['mape']}% |")
    print(f"| Plant 2 | {results['plant_2']['r2']} | {results['plant_2']['mape']}% |")
    
    return results


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
