# LSTM日前功率预测方法论

基于光伏电站功率预测的迭代优化实践总结

## 1. 问题定义

**目标**: 在D日预测D+1日的96个时间点（15分钟间隔，24小时）的光伏发电功率

**输入数据**:
- D日历史功率数据
- D+1日气象预报数据（辐照度、温度等）
- 时间特征

**评估指标**: MAE (Mean Absolute Error), RMSE

## 2. 迭代优化历程

### 2.1 基线模型演进

| 版本 | 方法 | MAE (kW) | 关键改进 |
|------|------|----------|----------|
| V6 | 22逆变器分别建模 | 15,777 | 基线 |
| V8 | Seq2Seq + Huber Loss | 15,404 | +2.4% |
| V10 | Seq2Seq + 数据增强 | **14,953** | **最佳** |
| V16 | V10 + D+1气象(5特征) | 14,992 | 无改善 |
| V18 | V10 + D/D+1气象(8特征) | 17,625 | 过拟合 |
| V19-V26 | 各种气象特征组合 | 15,000-18,000 | 不稳定 |

### 2.2 关键发现

1. **数据增强有效**: 噪声注入+缩放增强使MAE从15,777降至14,953
2. **气象数据引入需谨慎**: 简单添加气象特征反而可能降低精度
3. **训练/测试集天气分布差异**: 训练集77.8%晴天，测试集57%多云，导致预测偏高

## 3. 最佳实践方法论

### 3.1 数据预处理

```python
# 1. 时间对齐：确保每天96个点
POINTS_PER_DAY = 96

# 2. 缺失值处理：跳过不完整的天
if len(day_df) != POINTS_PER_DAY:
    continue

# 3. 特征工程：时间编码
hour_sin = np.sin(2 * np.pi * hours / 24)
hour_cos = np.cos(2 * np.pi * hours / 24)
```

### 3.2 数据增强策略

```python
def augment_data(X, y, n_augment=2):
    X_aug, y_aug = [X], [y]
    for _ in range(n_augment):
        # 噪声注入 (2%)
        noise_scale = 0.02
        X_noisy = X * (1 + np.random.randn(*X.shape) * noise_scale)
        y_noisy = y * (1 + np.random.randn(*y.shape) * noise_scale)
        X_aug.append(X_noisy)
        y_aug.append(y_noisy)
        
        # 缩放增强 (90%-110%)
        scale = np.random.uniform(0.9, 1.1, size=(X.shape[0], 1))
        X_scaled = X * scale
        y_scaled = y * scale
        X_aug.append(X_scaled)
        y_aug.append(y_scaled)
    return np.concatenate(X_aug), np.concatenate(y_aug)
```

### 3.3 模型架构 (Seq2Seq LSTM)

```python
def build_seq2seq_model(input_shape, output_len):
    # Encoder
    encoder_input = Input(shape=input_shape)
    encoder = LSTM(128, return_state=True)
    _, state_h, state_c = encoder(encoder_input)
    
    # Decoder
    decoder_input = RepeatVector(output_len)(state_h)
    decoder_lstm = LSTM(128, return_sequences=True)
    decoder_output = decoder_lstm(decoder_input, initial_state=[state_h, state_c])
    
    # Output
    output = TimeDistributed(Dense(64, activation='relu'))(decoder_output)
    output = TimeDistributed(Dense(1))(output)
    
    model = Model(encoder_input, output)
    model.compile(optimizer='adam', loss='huber')  # Huber Loss更鲁棒
    return model
```

### 3.4 训练策略

```python
callbacks = [
    EarlyStopping(patience=10, restore_best_weights=True),
    ReduceLROnPlateau(patience=5, factor=0.5)
]

model.fit(X_train, y_train, 
          epochs=80, 
          batch_size=32,
          validation_split=0.1,
          callbacks=callbacks,
          verbose=0)
```

## 4. 气象数据使用指南

### 4.1 何时使用气象数据

| 场景 | 建议 |
|------|------|
| 训练集天气分布均匀 | 可以使用 |
| 训练集以晴天为主 | 谨慎使用 |
| 数据量小(<50天) | 不建议使用 |
| 需要极端天气预测 | 必须使用 |

### 4.2 气象特征选择优先级

1. **辐照度 (IRRADIATION)** - 最重要，与功率直接相关
2. **环境温度 (AMBIENT_TEMPERATURE)** - 影响光伏效率
3. **组件温度 (MODULE_TEMPERATURE)** - 可由环境温度推算

### 4.3 天气分类策略

```python
def classify_weather(irr_sum, avg_irr):
    ratio = irr_sum / avg_irr
    if ratio < 0.6:
        return 'cloudy'      # 阴天
    elif ratio < 0.85:
        return 'partly_cloudy'  # 多云
    else:
        return 'sunny'       # 晴天
```

## 5. 常见问题与解决方案

### 5.1 早上时段预测偏高

**原因分析**:
- 早上效率与中午效率比值约0.99
- 模型学习了全天平均的功率-辐照度关系
- 早上辐照度变化快，模型难以捕捉

**解决方案**:
1. 添加时段特征（效果有限）
2. 后处理修正（需要验证集调参）
3. 分时段建模（增加复杂度）

### 5.2 多云天预测偏高

**原因分析**:
- 训练集晴天占比高（77.8%）
- 测试集多云天占比高（57%）
- 模型学习了晴天模式

**解决方案**:
1. 确保训练集天气分布均衡
2. 使用天气分类后的分层模型
3. 基于辐照度预报的动态修正

### 5.3 特征过多导致过拟合

**现象**: V18使用8个特征，MAE反而升至17,625

**解决方案**:
1. 特征选择：只保留最相关的特征
2. 正则化：L1/L2正则化
3. Dropout：在LSTM层后添加Dropout

## 6. 模型验证清单

### 6.1 数据验证
- [ ] 检查时间连续性
- [ ] 检查缺失值比例
- [ ] 分析训练/测试集天气分布
- [ ] 验证特征与目标的相关性

### 6.2 模型验证
- [ ] 使用时间序列交叉验证
- [ ] 检查训练/验证损失曲线
- [ ] 分析各时段预测误差
- [ ] 在不同电站上验证泛化能力

### 6.3 结果验证
- [ ] 对比基线模型
- [ ] 分析极端天气表现
- [ ] 检查预测值物理合理性（非负、上限）

## 7. 跨电站验证结果

| 电站 | 逆变器数 | 样本数 | MAE | RMSE |
|------|----------|--------|-----|------|
| Plant 1 | 22 | 299 | 14,953 | ~28,000 |
| Plant 2 | 22 | 490 | 1,529 | 2,904 |

Plant 2的MAE显著低于Plant 1，可能原因：
1. 电站规模不同
2. 数据质量差异
3. 天气条件更稳定

## 8. 推荐的模型配置

```python
# 最佳配置 (V10)
config = {
    'features': ['power_d0', 'irr_d1', 'hour_sin', 'hour_cos'],
    'lstm_units': 128,
    'dense_units': 64,
    'loss': 'huber',
    'optimizer': 'adam',
    'batch_size': 32,
    'epochs': 80,
    'augment_times': 2,
    'noise_scale': 0.02,
    'scale_range': (0.9, 1.1)
}
```

## 9. 未来优化方向

1. **Attention机制**: 让模型关注关键时间点
2. **多任务学习**: 同时预测功率和辐照度
3. **迁移学习**: 从大电站迁移到小电站
4. **概率预测**: 输出预测区间而非点估计
5. **在线学习**: 根据最新数据持续更新模型

## 10. 参考脚本

| 脚本 | 用途 |
|------|------|
| `predict_next_day.py` | V19模型（带气象） |
| `predict_plant2.py` | Plant 2验证 |
| `analyze_test_weather.py` | 天气分析 |
| `analyze_morning_error.py` | 早上误差分析 |

---

**文档版本**: 1.0  
**创建日期**: 2026-03-22  
**基于数据**: Kaggle Solar Power Generation Data
