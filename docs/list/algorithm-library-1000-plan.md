# 工业AI算法库 1000+ 函数规划

> 行业聚焦：新能源发电、工业制造（钢铁/光伏/动力电池）、源网荷储充、碳管理、微网/新电网、楼宇园区、港口运输
> 效率维度：能源效率 × 设备效率 × 运营效率
> 当前状态：6 分类 / 36 函数
> 目标状态：20 分类 / 1012 函数
> 标记说明：✅ 已有 | 🆕 新增

---

## 目录

| # | 分类 | 分类ID | 数量 | 已有 | 新增 | 定位 |
|---|------|--------|------|------|------|------|
| 1 | 数据源 | data_source | 40 | 7 | 33 | 数据接入层 |
| 2 | 数据预处理 | data_preprocessing | 66 | 3 | 63 | 数据处理层 |
| 3 | 特征工程 | feature_engineering | 82 | 6 | 76 | 数据处理层 |
| 4 | 时序预测 | ts_forecast | 60 | 4 | 56 | 算法模型层 |
| 5 | 异常检测 | anomaly_detection | 55 | 1 | 54 | 算法模型层 |
| 6 | 分类识别 | classification | 52 | 2 | 50 | 算法模型层 |
| 7 | 回归分析 | regression | 35 | 0 | 35 | 算法模型层 |
| 8 | 聚类分析 | clustering | 35 | 0 | 35 | 算法模型层 |
| 9 | 深度学习 | deep_learning | 72 | 0 | 72 | 算法模型层 |
| 10 | 工业视觉 | industrial_vision | 45 | 0 | 45 | 算法模型层 |
| 11 | 信号处理 | signal_processing | 56 | 0 | 56 | 算法模型层 |
| 12 | 优化算法 | optimization | 51 | 0 | 51 | 算法模型层 |
| 13 | 数学与统计 | math_statistics | 45 | 5 | 40 | 基础计算层 |
| 14 | 模型训练 | model_training | 40 | 8 | 32 | MLOps层 |
| 15 | 模型部署 | model_deployment | 32 | 0 | 32 | MLOps层 |
| 16 | 评估指标 | evaluation_metrics | 40 | 7 | 33 | MLOps层 |
| 17 | 可视化 | visualization | 49 | 0 | 49 | 输出展示层 |
| 18 | 数据输出 | data_output | 37 | 0 | 37 | 输出展示层 |
| 19 | 能源管理 | energy_management | 60 | 0 | 60 | 行业场景层 |
| 20 | 工业专用 | industrial | 60 | 0 | 60 | 行业场景层 |
| | **合计** | | **1012** | **43** | **969** | |

---

## 1. 数据源 (data_source) — 40 个

### 1.1 文件类数据源（12 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 1 | ✅ load_csv | CSV/Excel文件加载 | 支持CSV/Excel，自动编码检测 |
| 2 | 🆕 load_json | JSON文件加载 | JSON/JSONL格式 |
| 3 | 🆕 load_parquet | Parquet文件加载 | 列式存储高效读取 |
| 4 | 🆕 load_hdf5 | HDF5文件加载 | 科学计算大数据文件 |
| 5 | 🆕 load_xml | XML文件加载 | 工业配置/CIM模型解析 |
| 6 | 🆕 load_mat | MATLAB文件加载 | .mat仿真数据导入 |
| 7 | 🆕 load_tdms | TDMS文件加载 | NI LabVIEW测试数据 |
| 8 | 🆕 load_wav | WAV音频文件加载 | 设备振动/声学信号 |
| 9 | 🆕 load_image | 图像文件加载 | PNG/JPG/BMP/TIFF |
| 10 | 🆕 load_video | 视频文件加载 | 产线视频帧提取 |
| 11 | 🆕 load_comtrade | COMTRADE文件加载 | 电力故障录波数据 |
| 12 | 🆕 load_cim | CIM模型文件加载 | 电网拓扑模型 |

### 1.2 数据库数据源（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 13 | ✅ load_database | 数据库连接 | MySQL/PostgreSQL/SQLite |
| 14 | ✅ load_timeseries_db | 时序数据库接入 | InfluxDB/TDengine/TimescaleDB |
| 15 | 🆕 load_mongodb | MongoDB数据读取 | 文档型数据库 |
| 16 | 🆕 load_redis | Redis数据读取 | 缓存/实时数据 |
| 17 | 🆕 load_elasticsearch | Elasticsearch查询 | 日志/告警检索 |
| 18 | 🆕 load_clickhouse | ClickHouse查询 | OLAP分析型数据库 |
| 19 | 🆕 load_neo4j | Neo4j图数据库查询 | 电网拓扑/设备关系 |
| 20 | 🆕 load_hive | Hive数据查询 | 大数据仓库 |

### 1.3 工业协议数据源（14 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 21 | ✅ load_mqtt | MQTT实时数据订阅 | IoT传感器数据流 |
| 22 | ✅ load_opcua | OPC UA数据读取 | PLC/DCS工控系统 |
| 23 | ✅ load_modbus | Modbus设备数据读取 | 传感器/仪表/变频器 |
| 24 | 🆕 load_opcda | OPC DA数据读取 | 经典OPC协议 |
| 25 | 🆕 load_s7 | S7协议数据读取 | 西门子PLC专用 |
| 26 | 🆕 load_fins | FINS协议数据读取 | 欧姆龙PLC专用 |
| 27 | 🆕 load_melsec | MELSEC协议数据读取 | 三菱PLC专用 |
| 28 | 🆕 load_ethernetip | EtherNet/IP数据读取 | 罗克韦尔PLC |
| 29 | 🆕 load_profinet | PROFINET数据读取 | 西门子工业以太网 |
| 30 | 🆕 load_canbus | CAN总线数据读取 | 港口车辆/工程机械 |
| 31 | 🆕 load_bacnet | BACnet数据读取 | 楼宇自动化 |
| 32 | 🆕 load_dnp3 | DNP3协议数据读取 | 电力SCADA |
| 33 | 🆕 load_iec61850 | IEC 61850数据读取 | 变电站自动化 |
| 34 | 🆕 load_iec104 | IEC 104数据读取 | 电力远动协议 |

### 1.4 网络/流式数据源（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 35 | ✅ load_api | REST API数据接入 | GET/POST请求 |
| 36 | 🆕 load_graphql | GraphQL数据接入 | GraphQL查询 |
| 37 | 🆕 load_websocket | WebSocket实时数据 | 双向实时通信 |
| 38 | 🆕 load_kafka | Kafka消息消费 | 大数据流处理 |
| 39 | 🆕 load_rabbitmq | RabbitMQ消息消费 | 消息队列 |
| 40 | 🆕 load_ftp | FTP/SFTP文件下载 | 远程文件获取 |

---

## 2. 数据预处理 (data_preprocessing) — 66 个

### 2.1 数据清洗（15 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 41 | ✅ detect_outliers | 异常值检测 | zscore/iqr/isolation_forest |
| 42 | ✅ handle_missing | 缺失值处理 | 插值/前向/后向填充 |
| 43 | ✅ resample_timeseries | 时序重采样 | 上采样/下采样 |
| 44 | 🆕 remove_duplicates | 重复数据删除 | 精确/模糊去重 |
| 45 | 🆕 replace_outliers | 异常值替换 | 截断/中位数/插值替换 |
| 46 | 🆕 data_type_convert | 数据类型转换 | 数值/字符串/日期互转 |
| 47 | 🆕 column_rename | 列名重命名 | 批量/映射重命名 |
| 48 | 🆕 column_select | 列选择/删除 | 按名称/类型筛选列 |
| 49 | 🆕 row_filter | 行过滤 | 条件表达式过滤 |
| 50 | 🆕 data_merge | 数据合并 | 多表JOIN/UNION |
| 51 | 🆕 data_pivot | 数据透视 | 行列转换/交叉表 |
| 52 | 🆕 data_melt | 数据融合 | 宽表转长表 |
| 53 | 🆕 string_clean | 字符串清洗 | 去空格/特殊字符/统一格式 |
| 54 | 🆕 timestamp_parse | 时间戳解析 | 多格式时间解析统一 |
| 55 | 🆕 timezone_convert | 时区转换 | UTC/本地时间互转 |

### 2.2 去噪与平滑（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 56 | 🆕 moving_average | 移动平均平滑 | 简单/加权/指数移动平均 |
| 57 | 🆕 savgol_filter | Savitzky-Golay滤波 | 多项式平滑 |
| 58 | 🆕 median_filter | 中值滤波 | 脉冲噪声去除 |
| 59 | 🆕 gaussian_filter | 高斯滤波 | 高斯核平滑 |
| 60 | 🆕 kalman_filter | 卡尔曼滤波 | 状态估计去噪 |
| 61 | 🆕 wavelet_denoise | 小波去噪 | 多尺度去噪 |
| 62 | 🆕 lowpass_filter | 低通滤波 | 去除高频噪声 |
| 63 | 🆕 highpass_filter | 高通滤波 | 去除低频漂移 |
| 64 | 🆕 bandpass_filter | 带通滤波 | 保留特定频段 |
| 65 | 🆕 notch_filter | 陷波滤波 | 去除工频干扰(50Hz) |

### 2.3 数据变换（12 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 66 | 🆕 log_transform | 对数变换 | 压缩数据范围 |
| 67 | 🆕 box_cox_transform | Box-Cox变换 | 正态化变换 |
| 68 | 🆕 yeo_johnson_transform | Yeo-Johnson变换 | 支持负值的正态化 |
| 69 | 🆕 diff_transform | 差分变换 | 去趋势/平稳化 |
| 70 | 🆕 power_transform | 幂变换 | 非线性变换 |
| 71 | 🆕 quantile_transform | 分位数变换 | 均匀/正态分布映射 |
| 72 | 🆕 clip_values | 数值截断 | 上下限截断 |
| 73 | 🆕 binning | 数据分箱 | 等宽/等频/自定义分箱 |
| 74 | 🆕 one_hot_encode | 独热编码 | 分类变量编码 |
| 75 | 🆕 label_encode | 标签编码 | 有序分类编码 |
| 76 | 🆕 target_encode | 目标编码 | 基于目标变量编码 |
| 77 | 🆕 frequency_encode | 频率编码 | 基于出现频率编码 |

### 2.4 数据采样与平衡（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 78 | 🆕 random_sample | 随机采样 | 按比例/数量采样 |
| 79 | 🆕 stratified_sample | 分层采样 | 保持类别比例 |
| 80 | 🆕 smote_oversample | SMOTE过采样 | 合成少数类样本（故障样本增强） |
| 81 | 🆕 adasyn_oversample | ADASYN过采样 | 自适应合成采样 |
| 82 | 🆕 random_undersample | 随机欠采样 | 减少多数类样本 |
| 83 | 🆕 tomek_links | Tomek Links清洗 | 边界样本清理 |
| 84 | 🆕 sliding_window | 滑动窗口切片 | 时序数据窗口化 |
| 85 | 🆕 data_augmentation_ts | 时序数据增强 | 抖动/缩放/裁剪/翻转 |

### 2.5 数据质量评估（15 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 86 | 🆕 data_profile | 数据概况分析 | 统计摘要/分布/缺失率 |
| 87 | 🆕 missing_pattern | 缺失模式分析 | MCAR/MAR/MNAR判断 |
| 88 | 🆕 correlation_analysis | 相关性分析 | Pearson/Spearman/Kendall |
| 89 | 🆕 stationarity_test | 平稳性检验 | ADF/KPSS/PP检验 |
| 90 | 🆕 normality_test | 正态性检验 | Shapiro-Wilk/K-S/Anderson |
| 91 | 🆕 data_drift_detect | 数据漂移检测 | KS/PSI/Wasserstein距离 |
| 92 | 🆕 class_imbalance_check | 类别不平衡检测 | 不平衡比/熵分析 |
| 93 | 🆕 multicollinearity_check | 多重共线性检测 | VIF/条件数 |
| 94 | 🆕 seasonality_detect | 季节性检测 | 自相关/周期图分析 |
| 95 | 🆕 trend_detect | 趋势检测 | Mann-Kendall/Sen斜率 |
| 96 | 🆕 changepoint_detect | 变点检测 | CUSUM/PELT/Bayesian |
| 97 | 🆕 granger_causality | 格兰杰因果检验 | 时序因果关系 |
| 98 | 🆕 data_completeness | 数据完整性评分 | 综合质量评分 |
| 99 | 🆕 outlier_score | 异常值评分 | 每条记录异常程度 |
| 100 | 🆕 data_consistency_check | 数据一致性检查 | 跨源数据比对 |

### 2.6 工业数据专用处理（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 101 | 🆕 unit_convert | 单位转换 | 工程单位互转（kW↔MW/℃↔℉） |
| 102 | 🆕 coordinate_transform | 坐标变换 | 经纬度/UTM/高斯投影 |
| 103 | 🆕 data_align | 多源数据对齐 | 时间戳/采样率对齐 |
| 104 | 🆕 data_impute_ml | 机器学习填充 | KNN/RF/MICE缺失填充 |
| 105 | 🆕 data_validate_rule | 规则校验 | 范围/逻辑/一致性规则 |
| 106 | 🆕 data_tag | 数据标注 | 半自动标注/主动学习 |

---

## 3. 特征工程 (feature_engineering) — 82 个

### 3.1 时间特征（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 107 | ✅ extract_time_features | 时间特征提取 | 小时/星期/月份/节假日 |
| 108 | 🆕 cyclical_encode | 周期性编码 | sin/cos编码时间特征 |
| 109 | 🆕 holiday_features | 节假日特征 | 中国法定节假日标记 |
| 110 | 🆕 workday_features | 工作日特征 | 工作日/休息日/班次 |
| 111 | 🆕 time_since_event | 事件间隔特征 | 距上次故障/维护的时间 |
| 112 | 🆕 time_to_event | 距下次事件时间 | 距下次维护/换班时间 |
| 113 | 🆕 shift_features | 班次特征 | 早/中/晚班标记 |
| 114 | 🆕 peak_valley_features | 峰谷时段特征 | 电价峰/平/谷时段标记 |

### 3.2 统计特征（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 115 | ✅ extract_statistical_features | 统计特征提取 | 均值/方差/偏度/峰度 |
| 116 | 🆕 rolling_statistics | 滚动统计特征 | 滚动均值/标准差/分位数 |
| 117 | 🆕 expanding_statistics | 扩展窗口统计 | 累计均值/最大/最小 |
| 118 | 🆕 ewm_statistics | 指数加权统计 | 指数加权均值/方差 |
| 119 | 🆕 percentile_features | 分位数特征 | 多分位数提取 |
| 120 | 🆕 entropy_features | 信息熵特征 | 样本熵/近似熵/排列熵 |
| 121 | 🆕 complexity_features | 复杂度特征 | Lempel-Ziv/Hjorth参数 |
| 122 | 🆕 distribution_features | 分布特征 | 偏度/峰度/JB统计量 |
| 123 | 🆕 range_features | 范围特征 | 极差/四分位距/变异系数 |
| 124 | 🆕 count_features | 计数特征 | 过零率/峰值计数/阈值穿越 |

### 3.3 滞后与差分特征（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 125 | ✅ create_lag_features | 滞后特征生成 | 多步滞后 |
| 126 | 🆕 diff_features | 差分特征 | 一阶/二阶/季节差分 |
| 127 | 🆕 pct_change_features | 变化率特征 | 百分比变化 |
| 128 | 🆕 autocorrelation_features | 自相关特征 | ACF/PACF值 |
| 129 | 🆕 cross_correlation_features | 互相关特征 | 多变量互相关 |
| 130 | 🆕 lead_features | 超前特征 | 未来值（仅训练用） |

### 3.4 频域特征（7 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 131 | ✅ extract_frequency_features | 频域特征提取 | FFT/功率谱/主频率 |
| 132 | 🆕 wavelet_features | 小波特征 | 多尺度小波系数 |
| 133 | 🆕 spectral_features | 频谱特征 | 频谱质心/带宽/滚降 |
| 134 | 🆕 cepstrum_features | 倒谱特征 | 实倒谱/复倒谱 |
| 135 | 🆕 harmonic_features | 谐波特征 | 谐波比/THD |
| 136 | 🆕 band_energy_features | 频带能量特征 | 各频段能量占比 |
| 137 | 🆕 envelope_features | 包络特征 | 包络均值/峰值/RMS |

### 3.5 归一化与编码（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 138 | ✅ normalize_features | 特征归一化 | minmax/zscore/robust |
| 139 | 🆕 max_abs_scaler | 最大绝对值缩放 | 保持稀疏性 |
| 140 | 🆕 unit_vector_normalize | 单位向量归一化 | L1/L2范数归一化 |
| 141 | 🆕 decimal_scaling | 小数定标归一化 | 按数量级缩放 |
| 142 | 🆕 woe_encode | WOE编码 | 证据权重编码 |
| 143 | 🆕 hash_encode | 哈希编码 | 高基数分类特征 |

### 3.6 特征选择（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 144 | 🆕 variance_threshold | 方差阈值选择 | 去除低方差特征 |
| 145 | 🆕 mutual_info_select | 互信息选择 | 基于互信息排序 |
| 146 | 🆕 chi2_select | 卡方检验选择 | 分类特征选择 |
| 147 | 🆕 f_test_select | F检验选择 | ANOVA F值排序 |
| 148 | 🆕 rfe_select | 递归特征消除 | 模型驱动的特征选择 |
| 149 | 🆕 lasso_select | Lasso特征选择 | L1正则化选择 |
| 150 | 🆕 tree_importance_select | 树模型重要性选择 | 基于特征重要性 |
| 151 | 🆕 boruta_select | Boruta特征选择 | 全相关特征选择 |
| 152 | 🆕 forward_select | 前向特征选择 | 逐步添加特征 |
| 153 | 🆕 backward_select | 后向特征选择 | 逐步删除特征 |

### 3.7 降维（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 154 | 🆕 pca_reduce | PCA降维 | 主成分分析 |
| 155 | 🆕 kernel_pca | 核PCA降维 | 非线性降维 |
| 156 | 🆕 lda_reduce | LDA降维 | 线性判别分析 |
| 157 | 🆕 tsne_reduce | t-SNE降维 | 高维可视化 |
| 158 | 🆕 umap_reduce | UMAP降维 | 均匀流形近似 |
| 159 | 🆕 autoencoder_reduce | 自编码器降维 | 深度学习降维 |
| 160 | 🆕 ica_reduce | ICA独立成分分析 | 信号源分离 |
| 161 | 🆕 nmf_reduce | NMF非负矩阵分解 | 非负数据降维 |
| 162 | 🆕 truncated_svd | 截断SVD | 稀疏数据降维 |
| 163 | 🆕 factor_analysis | 因子分析 | 潜在因子提取 |

### 3.8 交叉与组合特征（7 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 164 | 🆕 polynomial_features | 多项式特征 | 交叉/平方/立方项 |
| 165 | 🆕 interaction_features | 交互特征 | 两两特征乘积 |
| 166 | 🆕 ratio_features | 比率特征 | 特征间比值（如功率因数） |
| 167 | 🆕 diff_pair_features | 差值特征 | 特征间差值（如温差） |
| 168 | 🆕 group_aggregate_features | 分组聚合特征 | 按设备/区域分组统计 |
| 169 | 🆕 target_statistics_features | 目标统计特征 | 基于目标的分组统计 |
| 170 | 🆕 auto_feature_generate | 自动特征生成 | Featuretools自动化 |

### 3.9 视觉与自动特征（18 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 171 | 🆕 image_histogram_features | 图像直方图特征 | 颜色/灰度直方图 |
| 172 | 🆕 hog_features | HOG特征 | 方向梯度直方图 |
| 173 | 🆕 lbp_features | LBP特征 | 局部二值模式 |
| 174 | 🆕 deep_image_features | 深度图像特征 | CNN预训练特征提取 |
| 175 | 🆕 glcm_features | GLCM纹理特征 | 灰度共生矩阵 |
| 176 | 🆕 gabor_features | Gabor纹理特征 | Gabor滤波器响应 |
| 177 | 🆕 shape_features | 形状特征 | 面积/周长/圆度/矩 |
| 178 | 🆕 color_features | 颜色特征 | HSV/LAB颜色统计 |
| 179 | 🆕 edge_features | 边缘特征 | Canny/Sobel边缘统计 |
| 180 | 🆕 contour_features | 轮廓特征 | 轮廓面积/凸包/缺陷 |
| 181 | 🆕 thermal_features | 热成像特征 | 红外温度分布特征 |
| 182 | 🆕 optical_flow_features | 光流特征 | 运动估计特征 |
| 183 | 🆕 tsfresh_extract | TSFresh自动特征 | 时序自动特征提取 |
| 184 | 🆕 catch22_features | Catch22特征 | 22个经典时序特征 |
| 185 | 🆕 rocket_features | ROCKET特征 | 随机卷积核特征 |
| 186 | 🆕 weather_features | 气象特征工程 | 温度/辐照/风速衍生 |
| 187 | 🆕 device_meta_features | 设备元数据特征 | 型号/年限/容量 |
| 188 | 🆕 graph_features | 图特征提取 | 节点度/中心性/PageRank |

---

## 4. 时序预测 (ts_forecast) — 60 个

### 4.1 经典统计模型（13 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 189 | ✅ arima_forecast | ARIMA时序预测 | 自回归积分滑动平均 |
| 190 | 🆕 sarima_forecast | SARIMA季节性预测 | 季节性ARIMA |
| 191 | 🆕 sarimax_forecast | SARIMAX外生变量预测 | 带外生变量的SARIMA |
| 192 | 🆕 var_forecast | VAR向量自回归 | 多变量时序预测 |
| 193 | 🆕 vecm_forecast | VECM向量误差修正 | 协整关系预测 |
| 194 | 🆕 ets_forecast | ETS指数平滑 | 误差-趋势-季节分解 |
| 195 | 🆕 holt_winters_forecast | Holt-Winters预测 | 三次指数平滑 |
| 196 | 🆕 theta_forecast | Theta方法预测 | M3竞赛冠军方法 |
| 197 | 🆕 croston_forecast | Croston间歇需求预测 | 备件/稀疏需求预测 |
| 198 | 🆕 tbats_forecast | TBATS预测 | 多季节性/非整数周期 |
| 199 | 🆕 garch_forecast | GARCH波动率预测 | 电价/负荷波动率 |
| 200 | 🆕 stl_decompose | STL时序分解 | 趋势/季节/残差分解 |
| 201 | 🆕 mstl_decompose | MSTL多季节分解 | 日/周/年多周期分解 |

### 4.2 机器学习模型（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 202 | ✅ xgboost_forecast | XGBoost时序预测 | 梯度提升树 |
| 203 | 🆕 lightgbm_forecast | LightGBM时序预测 | 轻量梯度提升 |
| 204 | 🆕 catboost_forecast | CatBoost时序预测 | 类别特征友好 |
| 205 | 🆕 random_forest_forecast | 随机森林时序预测 | 集成学习 |
| 206 | 🆕 svr_forecast | SVR时序预测 | 支持向量回归 |
| 207 | 🆕 knn_forecast | KNN时序预测 | K近邻回归 |
| 208 | 🆕 elastic_net_forecast | 弹性网络时序预测 | L1+L2正则化 |
| 209 | 🆕 bayesian_ridge_forecast | 贝叶斯岭回归预测 | 贝叶斯线性模型 |
| 210 | 🆕 gpr_forecast | 高斯过程回归预测 | 不确定性量化 |
| 211 | 🆕 quantile_regression_forecast | 分位数回归预测 | 预测区间估计 |

### 4.3 深度学习模型（17 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 212 | ✅ lstm_forecast | LSTM时序预测 | 长短期记忆网络 |
| 213 | 🆕 gru_forecast | GRU时序预测 | 门控循环单元 |
| 214 | 🆕 bilstm_forecast | BiLSTM时序预测 | 双向LSTM |
| 215 | 🆕 cnn_forecast | CNN时序预测 | 一维卷积网络 |
| 216 | 🆕 tcn_forecast | TCN时序预测 | 时间卷积网络 |
| 217 | 🆕 wavenet_forecast | WaveNet时序预测 | 因果膨胀卷积 |
| 218 | 🆕 transformer_forecast | Transformer时序预测 | 自注意力机制 |
| 219 | 🆕 informer_forecast | Informer时序预测 | 高效长序列预测 |
| 220 | 🆕 autoformer_forecast | Autoformer时序预测 | 自相关分解 |
| 221 | 🆕 patchtst_forecast | PatchTST时序预测 | 补丁化Transformer |
| 222 | 🆕 timesnet_forecast | TimesNet时序预测 | 多周期变换 |
| 223 | 🆕 nbeats_forecast | N-BEATS时序预测 | 纯深度学习基线 |
| 224 | 🆕 nhits_forecast | N-HiTS时序预测 | 分层插值 |
| 225 | 🆕 deepar_forecast | DeepAR概率预测 | 自回归概率模型 |
| 226 | 🆕 tft_forecast | TFT时序预测 | 时间融合Transformer |
| 227 | 🆕 dlinear_forecast | DLinear时序预测 | 简单线性分解 |
| 228 | 🆕 tide_forecast | TiDE时序预测 | 编码器-解码器 |

### 4.4 集成与专用模型（14 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 229 | 🆕 ensemble_forecast | 集成预测 | 多模型加权平均 |
| 230 | 🆕 stacking_forecast | Stacking预测 | 元学习集成 |
| 231 | 🆕 prophet_forecast | Prophet预测 | Facebook时序预测 |
| 232 | 🆕 neuralprophet_forecast | NeuralProphet预测 | 神经网络版Prophet |
| 233 | 🆕 hybrid_arima_lstm | ARIMA-LSTM混合预测 | 线性+非线性混合 |
| 234 | 🆕 multi_step_forecast | 多步预测 | 递归/直接/混合策略 |
| 235 | 🆕 multi_target_forecast | 多目标预测 | 同时预测多个变量 |
| 236 | 🆕 hierarchical_forecast | 层次预测 | 自顶向下/自底向上 |
| 237 | 🆕 conformal_prediction | 保形预测 | 预测区间校准 |
| 238 | 🆕 online_forecast | 在线学习预测 | 流式更新模型 |
| 239 | 🆕 transfer_forecast | 迁移学习预测 | 跨电站/跨设备迁移 |
| 240 | 🆕 few_shot_forecast | 小样本预测 | 新设备少量数据建模 |
| 241 | 🆕 probabilistic_forecast | 概率预测 | 预测分布而非点值 |
| 242 | 🆕 scenario_forecast | 场景预测 | 多场景概率预测 |

### 4.5 能源行业专用预测（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 243 | 🆕 pv_power_forecast | 光伏发电功率预测 | 辐照度+气象→发电量 |
| 244 | 🆕 wind_power_forecast | 风电功率预测 | 风速+风向→发电量 |
| 245 | 🆕 load_demand_forecast | 电力负荷预测 | 短期/中期/长期负荷 |
| 246 | 🆕 battery_soc_forecast | 储能SOC预测 | 电池荷电状态预测 |
| 247 | 🆕 electricity_price_forecast | 电价预测 | 现货/日前电价 |
| 248 | 🆕 gas_consumption_forecast | 天然气消耗预测 | 工业用气量预测 |

---

## 5. 异常检测 (anomaly_detection) — 55 个

### 5.1 统计方法（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 249 | 🆕 zscore_anomaly | Z-Score异常检测 | 标准差阈值 |
| 250 | 🆕 iqr_anomaly | IQR异常检测 | 四分位距方法 |
| 251 | 🆕 grubbs_anomaly | Grubbs检验 | 单个异常值检验 |
| 252 | 🆕 esd_anomaly | ESD检验 | 多个异常值检验 |
| 253 | 🆕 mad_anomaly | MAD异常检测 | 中位数绝对偏差 |
| 254 | 🆕 moving_zscore_anomaly | 滑动Z-Score检测 | 时序局部异常 |
| 255 | 🆕 cusum_anomaly | CUSUM累积和检测 | 均值偏移检测 |
| 256 | 🆕 ewma_anomaly | EWMA控制图检测 | 指数加权异常 |
| 257 | 🆕 hotelling_t2_anomaly | Hotelling T²检测 | 多变量统计异常 |
| 258 | 🆕 mahalanobis_anomaly | 马氏距离异常检测 | 考虑协方差 |

### 5.2 机器学习方法（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 259 | ✅ isolation_forest_anomaly | 孤立森林异常检测 | 随机分割隔离 |
| 260 | 🆕 lof_anomaly | LOF局部异常因子 | 密度偏差检测 |
| 261 | 🆕 ocsvm_anomaly | One-Class SVM检测 | 单类支持向量机 |
| 262 | 🆕 elliptic_envelope_anomaly | 椭圆包络检测 | 高斯分布假设 |
| 263 | 🆕 dbscan_anomaly | DBSCAN异常检测 | 密度聚类异常 |
| 264 | 🆕 knn_anomaly | KNN异常检测 | K近邻距离异常 |
| 265 | 🆕 hbos_anomaly | HBOS异常检测 | 直方图异常 |
| 266 | 🆕 copod_anomaly | COPOD异常检测 | Copula异常 |
| 267 | 🆕 ecod_anomaly | ECOD异常检测 | 经验累积分布 |
| 268 | 🆕 xgbod_anomaly | XGBOD异常检测 | XGBoost增强 |

### 5.3 深度学习方法（11 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 269 | 🆕 autoencoder_anomaly | 自编码器异常检测 | 重构误差检测 |
| 270 | 🆕 vae_anomaly | VAE异常检测 | 变分自编码器 |
| 271 | 🆕 lstm_anomaly | LSTM异常检测 | 预测误差检测 |
| 272 | 🆕 gan_anomaly | GAN异常检测 | 生成对抗网络 |
| 273 | 🆕 transformer_anomaly | Transformer异常检测 | 注意力机制异常 |
| 274 | 🆕 usad_anomaly | USAD异常检测 | 对抗训练自编码器 |
| 275 | 🆕 anomaly_transformer | AnomalyTransformer | 关联差异检测 |
| 276 | 🆕 deep_svdd_anomaly | Deep SVDD异常检测 | 深度单类分类 |
| 277 | 🆕 dagmm_anomaly | DAGMM异常检测 | 深度自编码高斯混合 |
| 278 | 🆕 omnianomaly | OmniAnomaly检测 | 随机变量连接 |
| 279 | 🆕 mtad_gat_anomaly | MTAD-GAT异常检测 | 多变量图注意力 |

### 5.4 时序与工业专用异常检测（24 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 280 | 🆕 spectral_residual_anomaly | 频谱残差异常检测 | SR方法 |
| 281 | 🆕 matrix_profile_anomaly | Matrix Profile异常 | 子序列异常 |
| 282 | 🆕 contextual_anomaly | 上下文异常检测 | 条件异常（如夜间光伏） |
| 283 | 🆕 collective_anomaly | 集体异常检测 | 群体行为异常 |
| 284 | 🆕 multivariate_anomaly | 多变量联合异常 | 多传感器协同检测 |
| 285 | 🆕 root_cause_anomaly | 异常根因分析 | 异常归因 |
| 286 | 🆕 streaming_anomaly | 流式异常检测 | 在线实时检测 |
| 287 | 🆕 ensemble_anomaly | 集成异常检测 | 多方法投票 |
| 288 | 🆕 dynamic_threshold | 动态阈值 | 自适应阈值调整 |
| 289 | 🆕 thresholding_adaptive | 自适应阈值设定 | 统计/百分位/3σ自适应 |
| 290 | 🆕 alarm_correlation | 告警关联分析 | 告警压缩/根因 |
| 291 | 🆕 alarm_suppression | 告警抑制 | 重复/抖动告警过滤 |
| 292 | 🆕 pattern_anomaly | 模式异常检测 | 偏离正常运行模式 |
| 293 | 🆕 energy_anomaly_detect | 能耗异常检测 | 异常用能识别 |
| 294 | 🆕 power_quality_anomaly | 电能质量异常检测 | 谐波/闪变/骤升骤降 |
| 295 | 🆕 thermal_anomaly_detect | 热异常检测 | 红外热像异常区域 |
| 296 | 🆕 leakage_detect | 泄漏检测 | 管道/阀门泄漏 |
| 297 | 🆕 arc_fault_detect | 电弧故障检测 | 光伏/电气电弧 |
| 298 | 🆕 insulation_anomaly | 绝缘异常检测 | 局放/介损异常 |
| 299 | 🆕 corrosion_detect | 腐蚀检测 | 管道/设备腐蚀 |
| 300 | 🆕 vibration_anomaly | 振动异常检测 | 旋转设备振动异常 |
| 301 | 🆕 process_anomaly | 工艺过程异常 | 工艺参数偏离 |
| 302 | 🆕 battery_anomaly_detect | 电池异常检测 | 电芯一致性/热失控预警 |
| 303 | 🆕 grid_anomaly_detect | 电网异常检测 | 频率/电压/功率异常 |

---

## 6. 分类识别 (classification) — 52 个

### 6.1 经典分类算法（17 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 304 | ✅ svm_classifier | 支持向量机分类 | linear/rbf/poly核 |
| 305 | ✅ random_forest_classifier | 随机森林分类 | 集成学习分类 |
| 306 | 🆕 logistic_regression | 逻辑回归分类 | 线性分类基线 |
| 307 | 🆕 decision_tree_classifier | 决策树分类 | CART/ID3/C4.5 |
| 308 | 🆕 knn_classifier | KNN分类 | K近邻分类 |
| 309 | 🆕 naive_bayes_classifier | 朴素贝叶斯分类 | 高斯/多项式/伯努利 |
| 310 | 🆕 xgboost_classifier | XGBoost分类 | 梯度提升分类 |
| 311 | 🆕 lightgbm_classifier | LightGBM分类 | 轻量梯度提升分类 |
| 312 | 🆕 catboost_classifier | CatBoost分类 | 类别特征友好分类 |
| 313 | 🆕 adaboost_classifier | AdaBoost分类 | 自适应提升 |
| 314 | 🆕 extra_trees_classifier | 极端随机树分类 | 更随机的森林 |
| 315 | 🆕 voting_classifier | 投票分类器 | 多模型投票 |
| 316 | 🆕 stacking_classifier | Stacking分类器 | 元学习集成 |
| 317 | 🆕 gradient_boosting_classifier | 梯度提升分类 | sklearn GBDT |
| 318 | 🆕 lda_classifier | LDA线性判别分类 | Fisher判别 |
| 319 | 🆕 qda_classifier | QDA二次判别分类 | 二次判别 |
| 320 | 🆕 sgd_classifier | SGD分类器 | 随机梯度下降 |

### 6.2 深度学习与特殊分类（11 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 321 | 🆕 mlp_classifier | MLP多层感知机分类 | 全连接网络 |
| 322 | 🆕 cnn_classifier | CNN分类 | 卷积神经网络 |
| 323 | 🆕 resnet_classifier | ResNet分类 | 残差网络 |
| 324 | 🆕 lstm_classifier | LSTM分类 | 序列分类 |
| 325 | 🆕 transformer_classifier | Transformer分类 | 注意力分类 |
| 326 | 🆕 rocket_classifier | ROCKET分类 | 随机卷积核（时序分类） |
| 327 | 🆕 multilabel_classifier | 多标签分类 | 一个样本多个标签 |
| 328 | 🆕 ordinal_classifier | 有序分类 | 等级/严重度分类 |
| 329 | 🆕 cost_sensitive_classifier | 代价敏感分类 | 不等代价（漏报代价高） |
| 330 | 🆕 calibrated_classifier | 概率校准分类 | Platt/Isotonic校准 |
| 331 | 🆕 online_classifier | 在线学习分类 | 流式增量分类 |

### 6.3 设备故障诊断与工业分类（24 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 332 | 🆕 bearing_fault_classifier | 轴承故障诊断 | 内圈/外圈/滚动体/保持架 |
| 333 | 🆕 motor_fault_classifier | 电机故障诊断 | 转子/定子/轴承/偏心 |
| 334 | 🆕 gearbox_fault_classifier | 齿轮箱故障诊断 | 齿面/断齿/磨损 |
| 335 | 🆕 pump_fault_classifier | 泵故障诊断 | 气蚀/密封/轴承 |
| 336 | 🆕 compressor_fault_classifier | 压缩机故障诊断 | 喘振/阀片/轴承 |
| 337 | 🆕 transformer_fault_classifier | 变压器故障诊断 | DGA油色谱分析 |
| 338 | 🆕 inverter_fault_classifier | 逆变器故障诊断 | IGBT/电容/散热 |
| 339 | 🆕 pv_module_fault_classifier | 光伏组件故障分类 | 热斑/隐裂/PID/遮挡 |
| 340 | 🆕 wind_turbine_fault_classifier | 风机故障诊断 | 叶片/齿轮箱/发电机 |
| 341 | 🆕 battery_fault_classifier | 电池故障分类 | 内短路/析锂/容量衰减 |
| 342 | 🆕 switchgear_fault_classifier | 开关柜故障诊断 | 局放/过热/机械故障 |
| 343 | 🆕 conveyor_fault_classifier | 输送带故障诊断 | 撕裂/跑偏/打滑 |
| 344 | 🆕 vibration_pattern_classifier | 振动模式分类 | 不平衡/不对中/松动 |
| 345 | 🆕 acoustic_fault_classifier | 声学故障分类 | 异音/泄漏检测 |
| 346 | 🆕 thermal_fault_classifier | 热故障分类 | 红外热像分析 |
| 347 | 🆕 multi_fault_classifier | 复合故障诊断 | 多故障同时识别 |
| 348 | 🆕 fault_severity_classifier | 故障严重度分级 | 轻微/中等/严重/紧急 |
| 349 | 🆕 remaining_useful_life | 剩余寿命预测(RUL) | 设备寿命估计 |
| 350 | 🆕 health_indicator | 健康指标构建 | 退化趋势量化 |
| 351 | 🆕 degradation_stage_classifier | 退化阶段分类 | 正常/退化/故障 |
| 352 | 🆕 steel_grade_classifier | 钢材牌号分类 | 成分→牌号 |
| 353 | 🆕 product_quality_classifier | 产品质量分级 | 合格/降级/废品 |
| 354 | 🆕 energy_label_classifier | 能效等级分类 | 设备能效标识 |
| 355 | 🆕 passive_aggressive_classifier | PA分类器 | 在线大规模分类 |

---

## 7. 回归分析 (regression) — 35 个

### 7.1 线性回归族（9 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 356 | 🆕 linear_regression | 线性回归 | OLS最小二乘 |
| 357 | 🆕 ridge_regression | 岭回归 | L2正则化 |
| 358 | 🆕 lasso_regression | Lasso回归 | L1正则化 |
| 359 | 🆕 elastic_net_regression | 弹性网络回归 | L1+L2正则化 |
| 360 | 🆕 polynomial_regression | 多项式回归 | 非线性拟合 |
| 361 | 🆕 quantile_regression | 分位数回归 | 条件分位数 |
| 362 | 🆕 huber_regression | Huber回归 | 鲁棒回归 |
| 363 | 🆕 bayesian_regression | 贝叶斯回归 | 后验分布估计 |
| 364 | 🆕 pls_regression | PLS偏最小二乘 | 高维/共线性 |

### 7.2 非线性回归（9 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 365 | 🆕 svr_regression | SVR支持向量回归 | 核方法回归 |
| 366 | 🆕 gpr_regression | 高斯过程回归 | 不确定性估计 |
| 367 | 🆕 decision_tree_regression | 决策树回归 | CART回归树 |
| 368 | 🆕 random_forest_regression | 随机森林回归 | 集成回归 |
| 369 | 🆕 xgboost_regression | XGBoost回归 | 梯度提升回归 |
| 370 | 🆕 lightgbm_regression | LightGBM回归 | 轻量梯度提升 |
| 371 | 🆕 catboost_regression | CatBoost回归 | 类别特征友好 |
| 372 | 🆕 knn_regression | KNN回归 | K近邻回归 |
| 373 | 🆕 mlp_regression | MLP回归 | 多层感知机 |

### 7.3 高级回归（17 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 374 | 🆕 gam_regression | GAM广义加性模型 | 非参数回归 |
| 375 | 🆕 symbolic_regression | 符号回归 | 物理公式发现 |
| 376 | 🆕 multi_target_regression | 多目标回归 | 同时预测多变量 |
| 377 | 🆕 stacking_regression | Stacking回归 | 元学习集成 |
| 378 | 🆕 tabnet_regression | TabNet回归 | 注意力表格回归 |
| 379 | 🆕 conformal_regression | 保形回归 | 预测区间 |
| 380 | 🆕 monotone_regression | 单调约束回归 | 物理约束（温度↑→效率↓） |
| 381 | 🆕 censored_regression | 截尾回归 | 寿命/可靠性 |
| 382 | 🆕 mixture_regression | 混合回归 | 多工况数据 |
| 383 | 🆕 spline_regression | 样条回归 | 分段多项式 |
| 384 | 🆕 neural_additive_regression | NAM神经加性模型 | 可解释深度回归 |
| 385 | 🆕 deep_ensemble_regression | 深度集成回归 | 不确定性量化 |
| 386 | 🆕 ransac_regression | RANSAC鲁棒回归 | 异常值鲁棒 |
| 387 | 🆕 theil_sen_regression | Theil-Sen回归 | 中位数斜率 |
| 388 | 🆕 isotonic_regression | 保序回归 | 单调约束 |
| 389 | 🆕 tweedie_regression | Tweedie回归 | 复合泊松 |
| 390 | 🆕 gamma_regression | Gamma回归 | 正偏分布 |

---

## 8. 聚类分析 (clustering) — 35 个

### 8.1 经典聚类（13 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 391 | 🆕 kmeans_cluster | K-Means聚类 | 质心聚类 |
| 392 | 🆕 kmedoids_cluster | K-Medoids聚类 | 中心点聚类 |
| 393 | 🆕 mini_batch_kmeans | Mini-Batch K-Means | 大数据K-Means |
| 394 | 🆕 dbscan_cluster | DBSCAN聚类 | 密度聚类 |
| 395 | 🆕 hdbscan_cluster | HDBSCAN聚类 | 层次密度聚类 |
| 396 | 🆕 optics_cluster | OPTICS聚类 | 有序密度聚类 |
| 397 | 🆕 mean_shift_cluster | Mean-Shift聚类 | 均值漂移 |
| 398 | 🆕 agglomerative_cluster | 层次聚类 | Ward/Complete/Average |
| 399 | 🆕 spectral_cluster | 谱聚类 | 图拉普拉斯 |
| 400 | 🆕 gmm_cluster | GMM高斯混合聚类 | 概率聚类 |
| 401 | 🆕 bayesian_gmm_cluster | 贝叶斯GMM聚类 | 自动确定K |
| 402 | 🆕 som_cluster | SOM自组织映射 | 拓扑保持聚类 |
| 403 | 🆕 fuzzy_cmeans_cluster | 模糊C均值聚类 | 软聚类 |

### 8.2 时序聚类与模式发现（9 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 404 | 🆕 timeseries_kmeans | 时序K-Means | DTW距离聚类 |
| 405 | 🆕 timeseries_kshape | K-Shape聚类 | 形状聚类 |
| 406 | 🆕 dtw_cluster | DTW聚类 | 动态时间规整 |
| 407 | 🆕 subsequence_cluster | 子序列聚类 | 时序模式聚类 |
| 408 | 🆕 streaming_cluster | 流式聚类 | 在线增量聚类 |
| 409 | 🆕 optimal_k_search | 最优K值搜索 | 肘部法/轮廓系数/Gap |
| 410 | 🆕 cluster_profiling | 聚类画像 | 各簇特征描述 |
| 411 | 🆕 density_estimation | 密度估计 | KDE/GMM密度 |
| 412 | 🆕 multiview_cluster | 多视图聚类 | 多特征空间融合 |

### 8.3 工业场景聚类（13 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 413 | 🆕 mode_detection | 工况模式识别 | 运行模式自动识别 |
| 414 | 🆕 regime_detection | 运行状态识别 | HMM状态切换 |
| 415 | 🆕 motif_discovery | 时序Motif发现 | 频繁子序列 |
| 416 | 🆕 shapelet_discovery | Shapelet发现 | 判别性子序列 |
| 417 | 🆕 load_pattern_cluster | 负荷模式聚类 | 用电行为分类 |
| 418 | 🆕 generation_pattern_cluster | 发电模式聚类 | 发电曲线分类 |
| 419 | 🆕 weather_pattern_cluster | 气象模式聚类 | 典型气象日分类 |
| 420 | 🆕 equipment_group_cluster | 设备分组聚类 | 相似设备自动分组 |
| 421 | 🆕 process_state_cluster | 工艺状态聚类 | 生产工况识别 |
| 422 | 🆕 energy_profile_cluster | 能耗画像聚类 | 用能模式分类 |
| 423 | 🆕 fault_pattern_cluster | 故障模式聚类 | 故障类型自动发现 |
| 424 | 🆕 customer_segment | 用户分群 | 用电/用能客户分群 |
| 425 | 🆕 anomaly_cluster | 异常聚类 | 异常事件分类 |

---

## 9. 深度学习 (deep_learning) — 72 个

### 9.1 基础网络架构（12 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 426 | 🆕 build_mlp | 构建MLP网络 | 全连接网络 |
| 427 | 🆕 build_cnn_1d | 构建1D-CNN | 一维卷积（时序/信号） |
| 428 | 🆕 build_cnn_2d | 构建2D-CNN | 二维卷积（图像） |
| 429 | 🆕 build_lstm | 构建LSTM网络 | 长短期记忆 |
| 430 | 🆕 build_gru | 构建GRU网络 | 门控循环 |
| 431 | 🆕 build_bilstm | 构建BiLSTM网络 | 双向LSTM |
| 432 | 🆕 build_attention | 构建注意力层 | Self/Cross Attention |
| 433 | 🆕 build_transformer | 构建Transformer | 编码器-解码器 |
| 434 | 🆕 build_resnet | 构建ResNet | 残差连接 |
| 435 | 🆕 build_unet | 构建U-Net | 编码器-解码器分割 |
| 436 | 🆕 build_autoencoder | 构建自编码器 | 编码-解码 |
| 437 | 🆕 build_vae | 构建VAE | 变分自编码器 |

### 9.2 生成模型（5 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 438 | 🆕 gan_generate | GAN数据生成 | 生成对抗网络 |
| 439 | 🆕 timegan_generate | TimeGAN时序生成 | 时序数据合成（故障样本增强） |
| 440 | 🆕 vae_generate | VAE数据生成 | 变分生成 |
| 441 | 🆕 diffusion_generate | 扩散模型生成 | DDPM/DDIM |
| 442 | 🆕 data_synthesis | 合成数据生成 | 隐私保护数据合成 |

### 9.3 迁移学习（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 443 | 🆕 pretrained_feature_extract | 预训练特征提取 | 冻结层特征 |
| 444 | 🆕 fine_tune_model | 模型微调 | 解冻层微调 |
| 445 | 🆕 domain_adaptation | 域适应 | 源电站→目标电站 |
| 446 | 🆕 knowledge_distillation | 知识蒸馏 | 大模型→边缘小模型 |
| 447 | 🆕 few_shot_learning | 小样本学习 | 新设备少量数据 |
| 448 | 🆕 continual_learning | 持续学习 | 避免灾难性遗忘 |

### 9.4 图神经网络（5 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 449 | 🆕 gcn_model | GCN图卷积网络 | 电网拓扑分析 |
| 450 | 🆕 gat_model | GAT图注意力网络 | 注意力图网络 |
| 451 | 🆕 stgcn_model | ST-GCN时空图网络 | 时空预测（电网/交通） |
| 452 | 🆕 graph_autoencoder | 图自编码器 | 图嵌入/链接预测 |
| 453 | 🆕 knowledge_graph_embed | 知识图谱嵌入 | 设备关系/故障知识 |

### 9.5 强化学习（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 454 | 🆕 dqn_agent | DQN智能体 | 深度Q网络 |
| 455 | 🆕 ppo_agent | PPO智能体 | 近端策略优化 |
| 456 | 🆕 sac_agent | SAC智能体 | 软演员-评论家 |
| 457 | 🆕 ddpg_agent | DDPG智能体 | 连续动作空间 |
| 458 | 🆕 multi_agent_rl | 多智能体强化学习 | 多设备协同控制 |
| 459 | 🆕 offline_rl | 离线强化学习 | 历史数据学习策略 |

### 9.6 模型解释（7 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 460 | 🆕 shap_explain | SHAP解释 | Shapley值特征归因 |
| 461 | 🆕 lime_explain | LIME解释 | 局部可解释模型 |
| 462 | 🆕 gradcam_explain | Grad-CAM解释 | CNN热力图（缺陷定位） |
| 463 | 🆕 attention_explain | 注意力可视化 | 注意力权重分析 |
| 464 | 🆕 feature_importance | 特征重要性 | 排列/内置重要性 |
| 465 | 🆕 partial_dependence | 部分依赖图 | PDP/ICE |
| 466 | 🆕 counterfactual_explain | 反事实解释 | 最小改变翻转 |

### 9.7 训练技巧（11 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 467 | 🆕 learning_rate_scheduler | 学习率调度 | Step/Cosine/Warmup |
| 468 | 🆕 early_stopping | 早停策略 | 防止过拟合 |
| 469 | 🆕 gradient_clipping | 梯度裁剪 | 防止梯度爆炸 |
| 470 | 🆕 dropout_regularization | Dropout正则化 | 随机失活 |
| 471 | 🆕 label_smoothing | 标签平滑 | 软标签 |
| 472 | 🆕 mixup_augmentation | Mixup数据增强 | 样本混合 |
| 473 | 🆕 focal_loss | Focal Loss | 难样本聚焦（故障样本少） |
| 474 | 🆕 contrastive_loss | 对比学习损失 | SimCLR/MoCo |
| 475 | 🆕 self_supervised_pretrain | 自监督预训练 | 无标签预训练 |
| 476 | 🆕 mixed_precision_train | 混合精度训练 | FP16加速 |
| 477 | 🆕 distributed_train | 分布式训练 | 多GPU/多节点 |

### 9.8 LLM与工业智能（13 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 478 | 🆕 llm_chat | LLM对话 | 大语言模型调用 |
| 479 | 🆕 rag_query | RAG检索增强 | 设备手册/工艺知识问答 |
| 480 | 🆕 llm_function_call | LLM函数调用 | 自然语言→算法调用 |
| 481 | 🆕 log_parse | 工业日志解析 | 设备日志结构化 |
| 482 | 🆕 alarm_text_parse | 告警文本解析 | 告警信息结构化 |
| 483 | 🆕 report_generate | 报告自动生成 | 分析报告模板 |
| 484 | 🆕 fine_tune_llm | LLM微调 | LoRA/QLoRA工业微调 |
| 485 | 🆕 embedding_generate | 文本嵌入生成 | 向量化 |
| 486 | 🆕 vector_search | 向量检索 | 相似故障/工单搜索 |
| 487 | 🆕 document_ocr | 文档OCR识别 | 仪表读数/铭牌识别 |
| 488 | 🆕 table_ocr | 表格OCR识别 | 报表/记录识别 |
| 489 | 🆕 knowledge_extract | 知识抽取 | 设备知识三元组 |
| 490 | 🆕 intent_recognition | 意图识别 | 运维指令理解 |

### 9.9 网络架构补充（7 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 491 | 🆕 build_tcn | 构建TCN网络 | 时间卷积网络 |
| 492 | 🆕 build_wavenet | 构建WaveNet | 因果膨胀卷积 |
| 493 | 🆕 build_gan | 构建GAN网络 | 生成对抗网络 |
| 494 | 🆕 build_graph_network | 构建图网络 | GNN通用构建 |
| 495 | 🆕 build_siamese | 构建孪生网络 | 相似度学习 |
| 496 | 🆕 build_capsule_net | 构建胶囊网络 | 空间关系建模 |
| 497 | 🆕 neural_architecture_search | 神经架构搜索 | NAS自动设计 |

---

## 10. 工业视觉 (industrial_vision) — 45 个

### 10.1 图像分类与检测（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 498 | 🆕 resnet_classify | ResNet图像分类 | 残差网络 |
| 499 | 🆕 efficientnet_classify | EfficientNet分类 | 高效缩放 |
| 500 | 🆕 mobilenet_classify | MobileNet分类 | 轻量级边缘端 |
| 501 | 🆕 vit_classify | ViT图像分类 | Vision Transformer |
| 502 | 🆕 yolov8_detect | YOLOv8目标检测 | 实时检测 |
| 503 | 🆕 faster_rcnn_detect | Faster R-CNN检测 | 两阶段检测 |
| 504 | 🆕 detr_detect | DETR目标检测 | Transformer检测 |
| 505 | 🆕 small_object_detect | 小目标检测 | 微小缺陷检测 |

### 10.2 语义分割（5 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 506 | 🆕 unet_segment | U-Net语义分割 | 编码器-解码器 |
| 507 | 🆕 deeplabv3_segment | DeepLabV3分割 | 空洞卷积 |
| 508 | 🆕 segformer_segment | SegFormer分割 | Transformer分割 |
| 509 | 🆕 mask_rcnn_segment | Mask R-CNN实例分割 | 实例级分割 |
| 510 | 🆕 sam_segment | SAM分割一切 | 通用分割模型 |

### 10.3 工业缺陷检测（13 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 511 | 🆕 surface_inspect | 表面缺陷检测 | 划痕/凹坑/裂纹 |
| 512 | 🆕 dimension_measure | 尺寸测量 | 像素→物理尺寸 |
| 513 | 🆕 color_inspect | 颜色检测 | 色差/均匀性 |
| 514 | 🆕 texture_inspect | 纹理检测 | 纹理异常 |
| 515 | 🆕 weld_inspect | 焊缝检测 | 焊接质量评估 |
| 516 | 🆕 steel_surface_inspect | 钢材表面检测 | 热轧/冷轧缺陷 |
| 517 | 🆕 pv_cell_inspect | 光伏电池片检测 | EL/PL隐裂/色差 |
| 518 | 🆕 pv_module_ir_inspect | 光伏组件红外检测 | 热斑/异常发热 |
| 519 | 🆕 battery_xray_inspect | 电池X-Ray检测 | 极片对齐/焊接 |
| 520 | 🆕 pcb_inspect | PCB板检测 | 电路板缺陷 |
| 521 | 🆕 coating_inspect | 涂层检测 | 涂层均匀性/缺陷 |
| 522 | 🆕 anomaly_detect_image | 图像异常检测 | PatchCore/STFPM |
| 523 | 🆕 few_shot_defect | 小样本缺陷检测 | 少量样本训练 |

### 10.4 图像处理（19 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 524 | 🆕 image_resize | 图像缩放 | 双线性/双三次 |
| 525 | 🆕 image_crop | 图像裁剪 | ROI区域裁剪 |
| 526 | 🆕 image_enhance | 图像增强 | 对比度/亮度/锐化 |
| 527 | 🆕 image_denoise | 图像去噪 | 高斯/中值/NLM |
| 528 | 🆕 image_threshold | 图像二值化 | Otsu/自适应阈值 |
| 529 | 🆕 morphology_ops | 形态学操作 | 腐蚀/膨胀/开闭 |
| 530 | 🆕 edge_detect | 边缘检测 | Canny/Sobel/Laplacian |
| 531 | 🆕 contour_detect | 轮廓检测 | 轮廓提取/过滤 |
| 532 | 🆕 template_match | 模板匹配 | 图像模板搜索 |
| 533 | 🆕 image_stitch | 图像拼接 | 全景拼接（大面积检测） |
| 534 | 🆕 image_register | 图像配准 | 多图对齐 |
| 535 | 🆕 super_resolution | 超分辨率 | 低分辨率增强 |
| 536 | 🆕 color_space_convert | 颜色空间转换 | RGB/HSV/LAB/Gray |
| 537 | 🆕 histogram_equalize | 直方图均衡化 | 对比度增强 |
| 538 | 🆕 perspective_transform | 透视变换 | 视角校正 |
| 539 | 🆕 camera_calibrate | 相机标定 | 内外参标定 |
| 540 | 🆕 image_augment | 图像数据增强 | 随机变换组合 |
| 541 | 🆕 thermal_image_process | 热成像处理 | 红外图像增强/伪彩色 |
| 542 | 🆕 drone_image_process | 无人机图像处理 | 光伏/风电巡检图像 |

---

## 11. 信号处理 (signal_processing) — 56 个

### 11.1 频域分析（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 543 | 🆕 fft_analysis | FFT频谱分析 | 快速傅里叶变换 |
| 544 | 🆕 stft_analysis | STFT短时傅里叶 | 时频联合分析 |
| 545 | 🆕 power_spectrum | 功率谱密度 | Welch/周期图法 |
| 546 | 🆕 cross_spectrum | 互功率谱 | 双通道频域关系 |
| 547 | 🆕 coherence_analysis | 相干函数分析 | 频域相关性 |
| 548 | 🆕 transfer_function | 传递函数估计 | 系统频率响应 |
| 549 | 🆕 cepstrum_analysis | 倒谱分析 | 齿轮/轴承故障特征 |
| 550 | 🆕 order_analysis | 阶次分析 | 旋转机械转速跟踪 |
| 551 | 🆕 harmonic_analysis | 谐波分析 | 电力谐波含量/THD |
| 552 | 🆕 interharmonic_analysis | 间谐波分析 | 非整数次谐波 |

### 11.2 时频分析（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 553 | 🆕 cwt_analysis | 连续小波变换 | 多尺度时频分析 |
| 554 | 🆕 dwt_analysis | 离散小波变换 | 多分辨率分解 |
| 555 | 🆕 wavelet_packet | 小波包分解 | 精细频带分析 |
| 556 | 🆕 emd_decompose | EMD经验模态分解 | 自适应分解 |
| 557 | 🆕 eemd_decompose | EEMD集合EMD | 噪声辅助分解 |
| 558 | 🆕 vmd_decompose | VMD变分模态分解 | 变分优化分解 |
| 559 | 🆕 hilbert_transform | 希尔伯特变换 | 瞬时频率/幅值 |
| 560 | 🆕 hilbert_huang | 希尔伯特-黄变换 | EMD+Hilbert时频谱 |
| 561 | 🆕 wigner_ville | Wigner-Ville分布 | 高分辨率时频 |
| 562 | 🆕 synchrosqueeze | 同步压缩变换 | 锐化时频表示 |

### 11.3 滤波与信号处理（13 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 563 | 🆕 fir_filter_design | FIR滤波器设计 | 有限脉冲响应 |
| 564 | 🆕 iir_filter_design | IIR滤波器设计 | Butterworth/Chebyshev |
| 565 | 🆕 adaptive_filter | 自适应滤波 | LMS/RLS自适应 |
| 566 | 🆕 wiener_filter | 维纳滤波 | 最优线性滤波 |
| 567 | 🆕 matched_filter | 匹配滤波 | 信号检测 |
| 568 | 🆕 comb_filter | 梳状滤波 | 周期性干扰去除 |
| 569 | 🆕 anti_aliasing_filter | 抗混叠滤波 | 采样前滤波 |
| 570 | 🆕 signal_resample | 信号重采样 | 上采样/下采样/插值 |
| 571 | 🆕 signal_interpolate | 信号插值 | 线性/样条/sinc插值 |
| 572 | 🆕 signal_envelope | 包络提取 | Hilbert包络 |
| 573 | 🆕 acoustic_emission_analyze | 声发射分析 | 裂纹/泄漏声发射 |
| 574 | 🆕 ultrasonic_analyze | 超声波分析 | 壁厚/缺陷检测 |
| 575 | 🆕 eddy_current_analyze | 涡流分析 | 表面/近表面缺陷 |

### 11.4 振动分析（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 576 | 🆕 vibration_rms | 振动有效值 | RMS/峰值/峰峰值 |
| 577 | 🆕 vibration_spectrum | 振动频谱分析 | 特征频率提取 |
| 578 | 🆕 envelope_spectrum | 包络谱分析 | 轴承故障频率 |
| 579 | 🆕 orbit_analysis | 轴心轨迹分析 | 转子运动轨迹 |
| 580 | 🆕 modal_analysis | 模态分析 | 固有频率/阻尼比 |
| 581 | 🆕 torsional_vibration | 扭振分析 | 扭转振动检测 |
| 582 | 🆕 shock_pulse_method | 冲击脉冲法 | 轴承状态评估 |
| 583 | 🆕 kurtogram_analysis | 峭度图分析 | 最优解调频带 |
| 584 | 🆕 signal_correlation | 信号相关分析 | 自相关/互相关 |
| 585 | 🆕 signal_compress | 信号压缩 | 有损/无损压缩 |

### 11.5 电力信号分析（13 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 586 | 🆕 power_quality_analyze | 电能质量分析 | 电压/电流质量 |
| 587 | 🆕 flicker_analyze | 闪变分析 | 电压波动/闪变 |
| 588 | 🆕 sag_swell_detect | 暂降暂升检测 | 电压骤变事件 |
| 589 | 🆕 transient_analyze | 暂态分析 | 暂态过电压/过电流 |
| 590 | 🆕 frequency_deviation | 频率偏差分析 | 电网频率监测 |
| 591 | 🆕 phase_angle_analyze | 相角分析 | 功率因数/相位差 |
| 592 | 🆕 symmetrical_component | 对称分量分析 | 正/负/零序分量 |
| 593 | 🆕 impedance_analyze | 阻抗分析 | 电气阻抗谱 |
| 594 | 🆕 partial_discharge_analyze | 局部放电分析 | 绝缘状态评估 |
| 595 | 🆕 traveling_wave_analyze | 行波分析 | 故障测距 |
| 596 | 🆕 pmu_data_analyze | PMU数据分析 | 同步相量分析 |
| 597 | 🆕 power_oscillation_detect | 功率振荡检测 | 低频振荡监测 |
| 598 | 🆕 islanding_detect | 孤岛检测 | 分布式电源孤岛 |

---

## 12. 优化算法 (optimization) — 51 个

### 12.1 数学优化（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 599 | 🆕 linear_programming | 线性规划 | LP求解 |
| 600 | 🆕 integer_programming | 整数规划 | MIP/MILP |
| 601 | 🆕 quadratic_programming | 二次规划 | QP求解 |
| 602 | 🆕 nonlinear_programming | 非线性规划 | NLP求解 |
| 603 | 🆕 convex_optimization | 凸优化 | CVXPY求解 |
| 604 | 🆕 stochastic_programming | 随机规划 | 不确定性优化 |
| 605 | 🆕 robust_optimization | 鲁棒优化 | 最坏情况优化 |
| 606 | 🆕 multi_objective_optimize | 多目标优化 | Pareto前沿 |
| 607 | 🆕 constraint_satisfaction | 约束满足 | CSP求解 |
| 608 | 🆕 dynamic_programming | 动态规划 | 最优子结构 |

### 12.2 智能优化算法（16 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 609 | 🆕 genetic_algorithm | 遗传算法 | 进化搜索 |
| 610 | 🆕 pso_optimize | 粒子群优化 | 群体智能 |
| 611 | 🆕 de_optimize | 差分进化 | 连续空间优化 |
| 612 | 🆕 simulated_annealing | 模拟退火 | 概率搜索 |
| 613 | 🆕 ant_colony_optimize | 蚁群算法 | 路径优化 |
| 614 | 🆕 whale_optimize | 鲸鱼优化 | 仿生优化 |
| 615 | 🆕 grey_wolf_optimize | 灰狼优化 | 群体捕猎 |
| 616 | 🆕 cma_es_optimize | CMA-ES进化策略 | 协方差矩阵自适应 |
| 617 | 🆕 nsga2_optimize | NSGA-II多目标 | 非支配排序 |
| 618 | 🆕 moead_optimize | MOEA/D多目标 | 分解多目标 |
| 619 | 🆕 bayesian_optimize_bo | 贝叶斯优化(BO) | 高斯过程代理 |
| 620 | 🆕 tabu_search | 禁忌搜索 | 组合优化 |
| 621 | 🆕 branch_and_bound | 分支定界 | 精确求解 |
| 622 | 🆕 lagrangian_relaxation | 拉格朗日松弛 | 约束松弛 |
| 623 | 🆕 benders_decomposition | Benders分解 | 大规模分解 |
| 624 | 🆕 column_generation | 列生成 | 大规模LP |

### 12.3 能源调度优化（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 625 | 🆕 unit_commitment | 机组组合优化 | 发电机组启停 |
| 626 | 🆕 economic_dispatch | 经济调度 | 最小发电成本 |
| 627 | 🆕 optimal_power_flow | 最优潮流 | OPF求解 |
| 628 | 🆕 battery_schedule | 储能调度优化 | 充放电策略 |
| 629 | 🆕 ev_charging_schedule | 电动车充电调度 | 有序充电 |
| 630 | 🆕 demand_response_optimize | 需求响应优化 | 负荷削减策略 |
| 631 | 🆕 microgrid_dispatch | 微网调度优化 | 源网荷储协同 |
| 632 | 🆕 vpp_dispatch | 虚拟电厂调度 | 聚合资源优化 |
| 633 | 🆕 energy_trading_optimize | 电力交易优化 | 市场竞价策略 |
| 634 | 🆕 carbon_emission_optimize | 碳排放优化 | 碳成本最小化 |


### 12.4 工业过程优化（15 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 635 | 🆕 process_parameter_optimize | 工艺参数优化 | 最优工艺参数搜索 |
| 636 | 🆕 production_schedule | 生产排程优化 | 多产线排产 |
| 637 | 🆕 maintenance_schedule | 检修计划优化 | 最优维护时间窗 |
| 638 | 🆕 inventory_optimize | 库存优化 | 备件/原料库存策略 |
| 639 | 🆕 logistics_route_optimize | 物流路径优化 | 港口/园区运输路线 |
| 640 | 🆕 bin_packing_optimize | 装箱优化 | 集装箱/货物装载 |
| 641 | 🆕 job_shop_schedule | 作业车间调度 | 多机多工序 |
| 642 | 🆕 cutting_stock_optimize | 下料优化 | 钢材/板材切割 |
| 643 | 🆕 blend_optimize | 配料优化 | 原料配比（钢铁/电池） |
| 644 | 🆕 energy_efficiency_optimize | 能效优化 | 设备能效最大化 |
| 645 | 🆕 hvac_optimize | 暖通空调优化 | 楼宇舒适度+能耗 |
| 646 | 🆕 pid_tune | PID参数整定 | 自动PID调参 |
| 647 | 🆕 mpc_control | 模型预测控制 | MPC滚动优化 |
| 648 | 🆕 setpoint_optimize | 设定值优化 | 最优运行设定点 |
| 649 | 🆕 portfolio_optimize | 资产组合优化 | 能源资产配置 |

---

## 13. 数学与统计 (math_statistics) — 45 个

### 13.1 矩阵运算（5 个 ✅ 已有）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 650 | ✅ matrix_multiply | 矩阵乘法 | 矩阵相乘 |
| 651 | ✅ matrix_inverse | 矩阵求逆 | 方阵求逆 |
| 652 | ✅ matrix_determinant | 矩阵行列式 | 行列式计算 |
| 653 | ✅ matrix_eigenvalue | 特征值分解 | 特征值/特征向量 |
| 654 | ✅ matrix_svd | 奇异值分解 | SVD分解 |

### 13.2 线性代数扩展（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 655 | 🆕 matrix_lu | LU分解 | 下三角×上三角 |
| 656 | 🆕 matrix_qr | QR分解 | 正交×上三角 |
| 657 | 🆕 matrix_cholesky | Cholesky分解 | 正定矩阵分解 |
| 658 | 🆕 matrix_rank | 矩阵秩 | 秩计算 |
| 659 | 🆕 matrix_norm | 矩阵范数 | L1/L2/Frobenius |
| 660 | 🆕 matrix_condition | 条件数 | 数值稳定性 |
| 661 | 🆕 linear_solve | 线性方程组求解 | Ax=b |
| 662 | 🆕 least_squares_solve | 最小二乘求解 | 超定方程组 |
| 663 | 🆕 sparse_matrix_ops | 稀疏矩阵运算 | CSR/CSC格式 |
| 664 | 🆕 kronecker_product | Kronecker积 | 张量积 |

### 13.3 描述统计（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 665 | 🆕 descriptive_stats | 描述性统计 | 均值/中位数/众数/方差 |
| 666 | 🆕 weighted_stats | 加权统计 | 加权均值/方差 |
| 667 | 🆕 robust_stats | 鲁棒统计 | 中位数/MAD/截尾均值 |
| 668 | 🆕 moment_stats | 矩统计 | 原点矩/中心矩 |
| 669 | 🆕 quantile_stats | 分位数统计 | 任意分位数计算 |
| 670 | 🆕 covariance_matrix | 协方差矩阵 | 多变量协方差 |
| 671 | 🆕 correlation_matrix | 相关系数矩阵 | Pearson/Spearman |
| 672 | 🆕 contingency_table | 列联表分析 | 交叉频率表 |

### 13.4 假设检验（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 673 | 🆕 t_test | t检验 | 单样本/双样本/配对 |
| 674 | 🆕 anova_test | 方差分析 | 单因素/多因素ANOVA |
| 675 | 🆕 chi_square_test | 卡方检验 | 独立性/拟合优度 |
| 676 | 🆕 mann_whitney_test | Mann-Whitney U检验 | 非参数两样本 |
| 677 | 🆕 kruskal_wallis_test | Kruskal-Wallis检验 | 非参数多样本 |
| 678 | 🆕 wilcoxon_test | Wilcoxon符号秩检验 | 非参数配对 |
| 679 | 🆕 ks_test | K-S检验 | 分布拟合检验 |
| 680 | 🆕 levene_test | Levene检验 | 方差齐性 |
| 681 | 🆕 durbin_watson_test | Durbin-Watson检验 | 自相关检验 |
| 682 | 🆕 bootstrap_test | Bootstrap检验 | 重采样推断 |

### 13.5 概率分布与拟合（7 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 683 | 🆕 distribution_fit | 分布拟合 | 正态/Weibull/Gamma等 |
| 684 | 🆕 kde_estimate | 核密度估计 | 非参数密度 |
| 685 | 🆕 mixture_distribution | 混合分布 | GMM/混合Weibull |
| 686 | 🆕 copula_model | Copula模型 | 多变量联合分布 |
| 687 | 🆕 extreme_value_dist | 极值分布 | GEV/GPD极端事件 |
| 688 | 🆕 survival_analysis | 生存分析 | Kaplan-Meier/Cox回归 |
| 689 | 🆕 reliability_analysis | 可靠性分析 | Weibull/指数寿命 |

### 13.6 数值计算（5 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 690 | 🆕 numerical_integrate | 数值积分 | 梯形/Simpson/Gauss |
| 691 | 🆕 numerical_differentiate | 数值微分 | 有限差分 |
| 692 | 🆕 ode_solve | 常微分方程求解 | Euler/RK4/自适应 |
| 693 | 🆕 root_finding | 方程求根 | Newton/二分/割线法 |
| 694 | 🆕 interpolation | 插值计算 | 线性/样条/Lagrange |

---

## 14. 模型训练 (model_training) — 40 个

### 14.1 已有训练函数（8 个 ✅）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 695 | ✅ train_model | 通用模型训练 | 统一训练接口 |
| 696 | ✅ cross_validate | 交叉验证 | K折/分层/时序CV |
| 697 | ✅ hyperparameter_tune | 超参数调优 | Grid/Random/Bayesian |
| 698 | ✅ train_test_split | 数据集划分 | 训练/验证/测试 |
| 699 | ✅ save_model | 模型保存 | pickle/joblib/ONNX |
| 700 | ✅ load_model | 模型加载 | 加载已保存模型 |
| 701 | ✅ model_summary | 模型摘要 | 参数量/结构 |
| 702 | ✅ feature_importance_report | 特征重要性报告 | 排序+可视化 |

### 14.2 数据集管理（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 703 | 🆕 timeseries_split | 时序数据划分 | 滚动/扩展窗口 |
| 704 | 🆕 stratified_kfold | 分层K折 | 保持类别比例 |
| 705 | 🆕 group_kfold | 分组K折 | 按设备/批次分组 |
| 706 | 🆕 dataset_version | 数据集版本管理 | 版本追踪/回溯 |
| 707 | 🆕 data_loader_create | 数据加载器 | 批量/流式加载 |
| 708 | 🆕 feature_store_manage | 特征仓库管理 | 特征注册/复用 |

### 14.3 高级训练策略（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 709 | 🆕 auto_ml | AutoML自动建模 | 自动选模型+调参 |
| 710 | 🆕 optuna_tune | Optuna超参搜索 | TPE/CMA-ES采样 |
| 711 | 🆕 hyperband_tune | Hyperband调优 | 早停+资源分配 |
| 712 | 🆕 multi_fidelity_tune | 多保真度调优 | 低精度快速筛选 |
| 713 | 🆕 ensemble_train | 集成模型训练 | Bagging/Boosting/Stacking |
| 714 | 🆕 curriculum_learning | 课程学习 | 由易到难训练 |
| 715 | 🆕 active_learning_train | 主动学习训练 | 最有价值样本标注 |
| 716 | 🆕 semi_supervised_train | 半监督训练 | 少量标签+大量无标签 |
| 717 | 🆕 federated_learning | 联邦学习 | 多电站隐私保护训练 |
| 718 | 🆕 incremental_train | 增量训练 | 新数据增量更新 |

### 14.4 实验管理（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 719 | 🆕 experiment_track | 实验追踪 | MLflow/W&B记录 |
| 720 | 🆕 experiment_compare | 实验对比 | 多实验结果比较 |
| 721 | 🆕 model_registry | 模型注册 | 模型版本管理 |
| 722 | 🆕 training_callback | 训练回调 | 自定义回调函数 |
| 723 | 🆕 checkpoint_manage | 检查点管理 | 断点续训/最优保存 |
| 724 | 🆕 training_visualize | 训练可视化 | Loss/Metric曲线 |
| 725 | 🆕 reproducibility_set | 可复现性设置 | 随机种子/环境固定 |
| 726 | 🆕 training_profile | 训练性能分析 | GPU/内存/时间分析 |

### 14.5 模型压缩与优化（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 727 | 🆕 model_prune | 模型剪枝 | 结构化/非结构化剪枝 |
| 728 | 🆕 model_quantize | 模型量化 | INT8/FP16量化 |
| 729 | 🆕 knowledge_distill_train | 知识蒸馏训练 | 教师→学生模型 |
| 730 | 🆕 neural_arch_search_train | NAS训练 | 架构搜索+训练 |
| 731 | 🆕 model_compile | 模型编译优化 | TorchScript/TensorRT |
| 732 | 🆕 onnx_convert | ONNX格式转换 | 跨框架模型转换 |
| 733 | 🆕 tflite_convert | TFLite转换 | 边缘端模型转换 |
| 734 | 🆕 model_benchmark | 模型基准测试 | 推理速度/内存/精度 |

---

## 15. 模型部署 (model_deployment) — 32 个

### 15.1 模型服务化（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 735 | 🆕 model_serve_rest | REST API部署 | FastAPI/Flask服务 |
| 736 | 🆕 model_serve_grpc | gRPC部署 | 高性能RPC服务 |
| 737 | 🆕 model_serve_batch | 批量推理服务 | 大批量离线推理 |
| 738 | 🆕 model_serve_stream | 流式推理服务 | Kafka/MQTT实时推理 |
| 739 | 🆕 model_serve_triton | Triton推理服务 | NVIDIA推理服务器 |
| 740 | 🆕 model_serve_torchserve | TorchServe部署 | PyTorch模型服务 |
| 741 | 🆕 model_serve_tfserving | TF Serving部署 | TensorFlow模型服务 |
| 742 | 🆕 model_serve_onnxruntime | ONNX Runtime部署 | 跨平台推理 |

### 15.2 容器化与编排（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 743 | 🆕 docker_package | Docker打包 | 模型容器化 |
| 744 | 🆕 k8s_deploy | Kubernetes部署 | K8s编排部署 |
| 745 | 🆕 helm_chart_generate | Helm Chart生成 | K8s模板 |
| 746 | 🆕 auto_scale_config | 自动扩缩容配置 | HPA/VPA策略 |
| 747 | 🆕 canary_deploy | 金丝雀发布 | 灰度发布策略 |
| 748 | 🆕 blue_green_deploy | 蓝绿部署 | 零停机切换 |

### 15.3 边缘部署（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 749 | 🆕 edge_deploy_jetson | Jetson边缘部署 | NVIDIA Jetson |
| 750 | 🆕 edge_deploy_rpi | 树莓派部署 | Raspberry Pi |
| 751 | 🆕 edge_deploy_openvino | OpenVINO部署 | Intel边缘推理 |
| 752 | 🆕 edge_deploy_tpu | TPU边缘部署 | Google Coral |
| 753 | 🆕 edge_deploy_npu | NPU部署 | 国产AI芯片 |
| 754 | 🆕 edge_model_sync | 边缘模型同步 | 云边模型同步更新 |

### 15.4 监控与运维（12 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 755 | 🆕 model_monitor | 模型监控 | 性能/漂移/健康 |
| 756 | 🆕 data_drift_monitor | 数据漂移监控 | 输入分布变化 |
| 757 | 🆕 concept_drift_monitor | 概念漂移监控 | 模型效果衰减 |
| 758 | 🆕 prediction_log | 预测日志记录 | 输入/输出/延迟 |
| 759 | 🆕 ab_test_deploy | A/B测试部署 | 模型对比实验 |
| 760 | 🆕 model_rollback | 模型回滚 | 版本回退 |
| 761 | 🆕 model_explain_online | 在线解释 | 实时SHAP/LIME |
| 762 | 🆕 alert_rule_config | 告警规则配置 | 性能阈值告警 |
| 763 | 🆕 model_retrain_trigger | 自动重训触发 | 漂移→重训流水线 |
| 764 | 🆕 inference_cache | 推理缓存 | 相似输入缓存 |
| 765 | 🆕 model_pipeline_dag | 模型流水线DAG | 多模型编排 |
| 766 | 🆕 model_governance | 模型治理 | 审批/合规/审计 |

---

## 16. 评估指标 (evaluation_metrics) — 40 个

### 16.1 已有评估函数（7 个 ✅）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 767 | ✅ accuracy_score | 准确率 | 分类准确率 |
| 768 | ✅ precision_recall_f1 | 精确率/召回率/F1 | 分类综合指标 |
| 769 | ✅ confusion_matrix_eval | 混淆矩阵 | 分类混淆矩阵 |
| 770 | ✅ roc_auc_score | ROC-AUC | 分类排序能力 |
| 771 | ✅ mse_rmse_mae | MSE/RMSE/MAE | 回归误差指标 |
| 772 | ✅ r2_score | R²决定系数 | 回归拟合优度 |
| 773 | ✅ mape_score | MAPE平均百分比误差 | 回归百分比误差 |

### 16.2 分类指标扩展（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 774 | 🆕 balanced_accuracy | 平衡准确率 | 不平衡数据准确率 |
| 775 | 🆕 matthews_corrcoef | MCC马修斯相关系数 | 不平衡友好指标 |
| 776 | 🆕 cohen_kappa | Cohen's Kappa | 一致性系数 |
| 777 | 🆕 log_loss_eval | 对数损失 | 概率预测评估 |
| 778 | 🆕 brier_score | Brier评分 | 概率校准评估 |
| 779 | 🆕 pr_auc_score | PR-AUC | 精确率-召回率曲线下面积 |
| 780 | 🆕 top_k_accuracy | Top-K准确率 | 多分类Top-K |
| 781 | 🆕 multi_label_metrics | 多标签指标 | Hamming/Jaccard/子集 |

### 16.3 回归指标扩展（7 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 782 | 🆕 smape_score | SMAPE对称百分比误差 | 对称MAPE |
| 783 | 🆕 mase_score | MASE平均绝对缩放误差 | 时序基线比较 |
| 784 | 🆕 quantile_loss | 分位数损失 | 概率预测评估 |
| 785 | 🆕 pinball_loss | Pinball损失 | 分位数回归评估 |
| 786 | 🆕 crps_score | CRPS连续排序概率 | 概率预测综合 |
| 787 | 🆕 explained_variance | 解释方差 | 方差解释比例 |
| 788 | 🆕 max_error_eval | 最大误差 | 最坏情况评估 |

### 16.4 聚类与异常检测指标（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 789 | 🆕 silhouette_score | 轮廓系数 | 聚类质量 |
| 790 | 🆕 calinski_harabasz | CH指数 | 聚类紧密度/分离度 |
| 791 | 🆕 davies_bouldin | DB指数 | 聚类相似度 |
| 792 | 🆕 adjusted_rand_index | 调整兰德指数 | 聚类一致性 |
| 793 | 🆕 nmi_score | 归一化互信息 | 聚类信息论指标 |
| 794 | 🆕 anomaly_detection_metrics | 异常检测指标 | 精确率@K/AUPRC |

### 16.5 工业与业务指标（12 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 795 | 🆕 prediction_interval_coverage | 预测区间覆盖率 | PICP/PINAW |
| 796 | 🆕 forecast_skill_score | 预测技巧评分 | 相对基线提升 |
| 797 | 🆕 early_detection_score | 早期检测评分 | 故障提前检出 |
| 798 | 🆕 false_alarm_rate | 误报率 | 虚警率评估 |
| 799 | 🆕 detection_delay | 检测延迟 | 异常发现延迟 |
| 800 | 🆕 rul_metrics | RUL评估指标 | 剩余寿命预测评估 |
| 801 | 🆕 energy_saving_rate | 节能率评估 | 能效提升量化 |
| 802 | 🆕 roi_calculate | ROI投资回报 | 算法经济效益 |
| 803 | 🆕 model_fairness_metrics | 模型公平性指标 | 偏差/公平性 |
| 804 | 🆕 model_robustness_eval | 模型鲁棒性评估 | 对抗/噪声鲁棒 |
| 805 | 🆕 cross_validation_report | 交叉验证报告 | 综合CV报告 |
| 806 | 🆕 model_comparison_report | 模型对比报告 | 多模型综合对比 |

---

## 17. 可视化 (visualization) — 49 个

### 17.1 基础图表（12 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 807 | 🆕 line_chart | 折线图 | 时序趋势 |
| 808 | 🆕 bar_chart | 柱状图 | 分类对比 |
| 809 | 🆕 scatter_chart | 散点图 | 相关性/分布 |
| 810 | 🆕 pie_chart | 饼图/环形图 | 占比分析 |
| 811 | 🆕 area_chart | 面积图 | 堆叠趋势 |
| 812 | 🆕 histogram_chart | 直方图 | 分布展示 |
| 813 | 🆕 box_chart | 箱线图 | 分布/异常值 |
| 814 | 🆕 violin_chart | 小提琴图 | 密度分布 |
| 815 | 🆕 heatmap_chart | 热力图 | 矩阵/相关性 |
| 816 | 🆕 radar_chart | 雷达图 | 多维对比 |
| 817 | 🆕 waterfall_chart | 瀑布图 | 增减分析 |
| 818 | 🆕 funnel_chart | 漏斗图 | 流程转化 |

### 17.2 高级图表（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 819 | 🆕 sankey_chart | 桑基图 | 能量流/物料流 |
| 820 | 🆕 treemap_chart | 矩形树图 | 层次占比 |
| 821 | 🆕 sunburst_chart | 旭日图 | 多层级占比 |
| 822 | 🆕 parallel_coord_chart | 平行坐标图 | 多维数据 |
| 823 | 🆕 contour_chart | 等高线图 | 二维密度 |
| 824 | 🆕 bubble_chart | 气泡图 | 三维散点 |
| 825 | 🆕 candlestick_chart | K线图 | 电价/交易 |
| 826 | 🆕 gantt_chart | 甘特图 | 排程/计划 |
| 827 | 🆕 network_graph | 网络关系图 | 拓扑/关系 |
| 828 | 🆕 chord_chart | 弦图 | 关联关系 |

### 17.3 时序与信号可视化（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 829 | 🆕 timeseries_plot | 时序曲线图 | 多通道时序 |
| 830 | 🆕 spectrogram_plot | 频谱图 | 时频热力图 |
| 831 | 🆕 waveform_plot | 波形图 | 信号波形 |
| 832 | 🆕 phase_diagram | 相图 | 相空间轨迹 |
| 833 | 🆕 control_chart | 控制图 | SPC控制图 |
| 834 | 🆕 forecast_plot | 预测结果图 | 实际vs预测+区间 |
| 835 | 🆕 anomaly_plot | 异常标注图 | 异常点高亮 |
| 836 | 🆕 decomposition_plot | 分解结果图 | 趋势/季节/残差 |

### 17.4 工业专用可视化（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 837 | 🆕 scada_dashboard | SCADA仪表盘 | 工控监控面板 |
| 838 | 🆕 energy_flow_diagram | 能流图 | 能量流向可视化 |
| 839 | 🆕 single_line_diagram | 单线图 | 电气接线图 |
| 840 | 🆕 pid_diagram | P&ID工艺图 | 管道仪表流程图 |
| 841 | 🆕 geo_map_chart | 地理地图 | 电站/设备分布 |
| 842 | 🆕 3d_scatter_chart | 3D散点图 | 三维数据 |
| 843 | 🆕 polar_chart | 极坐标图 | 风玫瑰图/方向 |
| 844 | 🆕 gauge_chart | 仪表盘图 | KPI指标 |
| 845 | 🆕 thermal_map | 热成像可视化 | 红外温度分布 |
| 846 | 🆕 equipment_status_board | 设备状态看板 | 设备健康总览 |

### 17.5 交互与报告（9 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 847 | 🆕 interactive_dashboard | 交互式仪表盘 | 可筛选/联动 |
| 848 | 🆕 realtime_chart | 实时刷新图表 | WebSocket推送 |
| 849 | 🆕 drill_down_chart | 下钻图表 | 层级钻取 |
| 850 | 🆕 chart_annotation | 图表标注 | 事件/阈值标注 |
| 851 | 🆕 multi_axis_chart | 多轴图表 | 双Y轴/多指标 |
| 852 | 🆕 subplot_layout | 子图布局 | 多图组合排列 |
| 853 | 🆕 chart_theme | 图表主题 | 自定义样式/配色 |
| 854 | 🆕 chart_export | 图表导出 | PNG/SVG/PDF |
| 855 | 🆕 report_template | 报告模板 | 自动化分析报告 |

---

## 18. 数据输出 (data_output) — 37 个

### 18.1 文件输出（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 856 | 🆕 export_csv | 导出CSV | CSV/TSV格式 |
| 857 | 🆕 export_excel | 导出Excel | 多Sheet/格式化 |
| 858 | 🆕 export_json | 导出JSON | JSON/JSONL格式 |
| 859 | 🆕 export_parquet | 导出Parquet | 列式存储 |
| 860 | 🆕 export_hdf5 | 导出HDF5 | 大数据文件 |
| 861 | 🆕 export_pdf | 导出PDF报告 | 图表+文字报告 |
| 862 | 🆕 export_html | 导出HTML报告 | 交互式报告 |
| 863 | 🆕 export_markdown | 导出Markdown | 文档格式 |
| 864 | 🆕 export_latex | 导出LaTeX | 学术论文格式 |
| 865 | 🆕 export_image | 导出图片 | PNG/SVG/TIFF |

### 18.2 数据库写入（7 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 866 | 🆕 write_database | 写入关系数据库 | MySQL/PostgreSQL/SQLite |
| 867 | 🆕 write_timeseries_db | 写入时序数据库 | InfluxDB/TDengine |
| 868 | 🆕 write_mongodb | 写入MongoDB | 文档存储 |
| 869 | 🆕 write_elasticsearch | 写入Elasticsearch | 日志/告警索引 |
| 870 | 🆕 write_redis | 写入Redis | 缓存/实时数据 |
| 871 | 🆕 write_clickhouse | 写入ClickHouse | OLAP分析 |
| 872 | 🆕 write_hive | 写入Hive | 大数据仓库 |

### 18.3 消息与API推送（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 873 | 🆕 push_mqtt | MQTT消息发布 | IoT设备指令下发 |
| 874 | 🆕 push_kafka | Kafka消息发布 | 流式数据输出 |
| 875 | 🆕 push_rabbitmq | RabbitMQ消息发布 | 消息队列 |
| 876 | 🆕 push_webhook | Webhook推送 | HTTP回调通知 |
| 877 | 🆕 push_email | 邮件发送 | 报告/告警邮件 |
| 878 | 🆕 push_sms | 短信发送 | 紧急告警短信 |
| 879 | 🆕 push_dingtalk | 钉钉消息推送 | 钉钉机器人 |
| 880 | 🆕 push_wechat | 企业微信推送 | 企微机器人 |

### 18.4 工业协议输出（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 881 | 🆕 write_opcua | OPC UA写入 | 控制指令下发 |
| 882 | 🆕 write_modbus | Modbus写入 | 寄存器写入 |
| 883 | 🆕 write_s7 | S7协议写入 | 西门子PLC写入 |
| 884 | 🆕 write_iec61850 | IEC 61850控制 | 变电站控制 |
| 885 | 🆕 write_bacnet | BACnet写入 | 楼宇控制 |
| 886 | 🆕 write_canbus | CAN总线写入 | 车辆/机械控制 |

### 18.5 数据格式转换与管道（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 887 | 🆕 data_format_convert | 数据格式转换 | CSV↔JSON↔Parquet |
| 888 | 🆕 data_compress | 数据压缩 | gzip/lz4/snappy |
| 889 | 🆕 data_encrypt | 数据加密 | AES/RSA加密 |
| 890 | 🆕 data_pipeline_output | 管道输出 | 多目标同时输出 |
| 891 | 🆕 data_archive | 数据归档 | 历史数据归档策略 |
| 892 | 🆕 data_sync | 数据同步 | 多系统数据同步 |

---

## 19. 能源管理 (energy_management) — 60 个

### 19.1 发电侧管理（12 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 893 | 🆕 pv_power_curve | 光伏出力曲线建模 | 辐照→功率映射 |
| 894 | 🆕 pv_degradation_analyze | 光伏衰减分析 | 组件衰减率评估 |
| 895 | 🆕 pv_soiling_detect | 光伏积灰检测 | 清洗决策 |
| 896 | 🆕 pv_string_mismatch | 组串失配分析 | 组串电流差异 |
| 897 | 🆕 pv_iv_curve_analyze | IV曲线分析 | 组件特性诊断 |
| 898 | 🆕 wind_power_curve | 风机功率曲线建模 | 风速→功率映射 |
| 899 | 🆕 wind_wake_analyze | 风机尾流分析 | 尾流效应评估 |
| 900 | 🆕 wind_yaw_optimize | 风机偏航优化 | 偏航角优化 |
| 901 | 🆕 curtailment_analyze | 弃风弃光分析 | 限电损失评估 |
| 902 | 🆕 generation_plan | 发电计划编制 | 日前/日内计划 |
| 903 | 🆕 capacity_factor_analyze | 容量因子分析 | 发电效率评估 |
| 904 | 🆕 renewable_resource_assess | 新能源资源评估 | 风光资源分析 |

### 19.2 储能管理（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 905 | 🆕 battery_soh_estimate | 电池SOH估计 | 健康状态评估 |
| 906 | 🆕 battery_soc_estimate | 电池SOC估计 | 荷电状态估计 |
| 907 | 🆕 battery_rul_predict | 电池寿命预测 | 剩余循环次数 |
| 908 | 🆕 battery_thermal_manage | 电池热管理 | 温控策略优化 |
| 909 | 🆕 battery_balance | 电池均衡策略 | 主动/被动均衡 |
| 910 | 🆕 battery_charge_optimize | 充电策略优化 | CC-CV/脉冲/快充 |
| 911 | 🆕 ess_capacity_plan | 储能容量规划 | 最优容量配置 |
| 912 | 🆕 ess_revenue_optimize | 储能收益优化 | 峰谷套利/辅助服务 |
| 913 | 🆕 ess_degradation_model | 储能衰减模型 | 循环/日历老化 |
| 914 | 🆕 hydrogen_storage_manage | 氢储能管理 | 制氢/储氢/用氢 |

### 19.3 电网与微网（12 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 915 | 🆕 power_flow_calculate | 潮流计算 | 牛顿-拉夫逊/PQ分解 |
| 916 | 🆕 short_circuit_calculate | 短路计算 | 对称/不对称短路 |
| 917 | 🆕 relay_protection_setting | 继电保护整定 | 保护定值计算 |
| 918 | 🆕 voltage_stability_analyze | 电压稳定性分析 | PV/QV曲线 |
| 919 | 🆕 frequency_stability_analyze | 频率稳定性分析 | 频率响应评估 |
| 920 | 🆕 harmonic_power_flow | 谐波潮流计算 | 谐波分布分析 |
| 921 | 🆕 microgrid_sizing | 微网容量配置 | 源网荷储优化配置 |
| 922 | 🆕 microgrid_control | 微网控制策略 | 并网/孤岛切换 |
| 923 | 🆕 distributed_gen_plan | 分布式电源规划 | 选址定容 |
| 924 | 🆕 network_reconfigure | 网络重构 | 拓扑优化/故障恢复 |
| 925 | 🆕 volt_var_optimize | 电压无功优化 | VVO策略 |
| 926 | 🆕 line_loss_calculate | 线损计算 | 理论/统计线损 |

### 19.4 负荷与需求侧管理（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 927 | 🆕 load_profile_analyze | 负荷曲线分析 | 用电模式分析 |
| 928 | 🆕 peak_shaving | 削峰填谷 | 负荷平移策略 |
| 929 | 🆕 demand_response_model | 需求响应建模 | 响应潜力评估 |
| 930 | 🆕 flexible_load_manage | 柔性负荷管理 | 可调负荷调度 |
| 931 | 🆕 ev_fleet_manage | 电动车队管理 | V2G/有序充电 |
| 932 | 🆕 building_energy_model | 建筑能耗模型 | 楼宇能耗仿真 |
| 933 | 🆕 hvac_load_predict | 暖通负荷预测 | 冷/热负荷预测 |
| 934 | 🆕 industrial_load_optimize | 工业负荷优化 | 生产排程+用电 |
| 935 | 🆕 tariff_optimize | 电价策略优化 | 分时电价响应 |
| 936 | 🆕 power_purchase_optimize | 购电策略优化 | 中长期/现货组合 |

### 19.5 碳管理与综合能源（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 937 | 🆕 carbon_emission_calculate | 碳排放计算 | 范围1/2/3核算 |
| 938 | 🆕 carbon_footprint_trace | 碳足迹追踪 | 产品全生命周期 |
| 939 | 🆕 carbon_intensity_analyze | 碳强度分析 | 单位产值碳排放 |
| 940 | 🆕 carbon_trading_strategy | 碳交易策略 | CCER/配额交易 |
| 941 | 🆕 green_certificate_manage | 绿证管理 | 绿电证书追踪 |
| 942 | 🆕 energy_audit | 能源审计 | 用能诊断分析 |
| 943 | 🆕 energy_benchmark | 能效对标 | 行业/历史对标 |
| 944 | 🆕 combined_heat_power | 热电联产优化 | CHP运行优化 |
| 945 | 🆕 cold_heat_power | 冷热电三联供 | CCHP优化 |
| 946 | 🆕 energy_internet_optimize | 能源互联网优化 | 多能互补协同 |

### 19.6 能源市场与交易（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 947 | 🆕 spot_market_simulate | 现货市场仿真 | 电力市场模拟 |
| 948 | 🆕 bilateral_contract_optimize | 双边合约优化 | 中长期合约 |
| 949 | 🆕 ancillary_service_optimize | 辅助服务优化 | 调频/调峰/备用 |
| 950 | 🆕 virtual_power_plant_bid | 虚拟电厂竞价 | 聚合资源报价 |
| 951 | 🆕 peer_to_peer_trading | P2P能源交易 | 分布式交易 |
| 952 | 🆕 renewable_quota_manage | 可再生能源配额 | 消纳责任权重 |

---

## 20. 工业专用 (industrial) — 60 个

### 20.1 设备健康管理（12 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 953 | 🆕 cbm_strategy | 状态检修策略 | 基于状态的维护 |
| 954 | 🆕 predictive_maintenance | 预测性维护 | 故障预警+维护建议 |
| 955 | 🆕 reliability_centered_maint | RCM可靠性维护 | 以可靠性为中心 |
| 956 | 🆕 spare_parts_predict | 备件需求预测 | 备件库存优化 |
| 957 | 🆕 maintenance_cost_optimize | 维护成本优化 | 维护策略经济性 |
| 958 | 🆕 asset_lifecycle_manage | 资产全生命周期 | 采购→运维→退役 |
| 959 | 🆕 equipment_ranking | 设备健康排名 | 多设备优先级 |
| 960 | 🆕 failure_mode_analyze | 失效模式分析 | FMEA/FMECA |
| 961 | 🆕 fault_tree_analyze | 故障树分析 | FTA逻辑推理 |
| 962 | 🆕 weibull_life_analyze | Weibull寿命分析 | 寿命分布建模 |
| 963 | 🆕 condition_index_calculate | 设备状态指数 | 综合健康评分 |
| 964 | 🆕 maintenance_window_optimize | 维护窗口优化 | 最优检修时间 |

### 20.2 钢铁行业（10 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 965 | 🆕 blast_furnace_optimize | 高炉优化 | 炉况预测/配料优化 |
| 966 | 🆕 steel_quality_predict | 钢材质量预测 | 力学性能预测 |
| 967 | 🆕 rolling_force_predict | 轧制力预测 | 轧制参数优化 |
| 968 | 🆕 steel_temperature_predict | 钢温预测 | 连铸/轧制温度 |
| 969 | 🆕 slab_scheduling | 板坯排程 | 连铸-热轧衔接 |
| 970 | 🆕 alloy_optimize | 合金配比优化 | 成本最低配比 |
| 971 | 🆕 energy_balance_steel | 钢铁能量平衡 | 工序能耗分析 |
| 972 | 🆕 coke_quality_predict | 焦炭质量预测 | 配煤优化 |
| 973 | 🆕 sintering_optimize | 烧结优化 | 烧结终点预测 |
| 974 | 🆕 steel_defect_classify | 钢材缺陷分类 | 表面/内部缺陷 |

### 20.3 光伏制造（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 975 | 🆕 wafer_defect_detect | 硅片缺陷检测 | 线痕/崩边/隐裂 |
| 976 | 🆕 cell_efficiency_predict | 电池片效率预测 | 工艺→效率映射 |
| 977 | 🆕 cell_color_sort | 电池片色差分选 | 颜色一致性 |
| 978 | 🆕 module_power_predict | 组件功率预测 | CTM损失分析 |
| 979 | 🆕 pv_process_optimize | 光伏工艺优化 | 扩散/PECVD/印刷 |
| 980 | 🆕 pv_yield_optimize | 光伏良率优化 | 良率提升分析 |
| 981 | 🆕 pv_traceability | 光伏全流程追溯 | 硅片→组件追溯 |
| 982 | 🆕 pv_equipment_oee | 光伏设备OEE | 设备综合效率 |

### 20.4 动力电池制造（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 983 | 🆕 electrode_coating_optimize | 极片涂布优化 | 面密度/厚度控制 |
| 984 | 🆕 cell_formation_optimize | 化成分容优化 | 充放电工艺 |
| 985 | 🆕 cell_consistency_analyze | 电芯一致性分析 | 容量/内阻分选 |
| 986 | 🆕 battery_pack_design | 电池包设计优化 | 串并联/热设计 |
| 987 | 🆕 electrolyte_optimize | 电解液配方优化 | 成分配比 |
| 988 | 🆕 battery_safety_predict | 电池安全预测 | 热失控预警 |
| 989 | 🆕 battery_recycling_assess | 电池回收评估 | 梯次利用评估 |
| 990 | 🆕 battery_production_trace | 电池生产追溯 | 全流程质量追溯 |

### 20.5 港口与运输（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 991 | 🆕 berth_allocation | 泊位分配优化 | 船舶靠泊调度 |
| 992 | 🆕 crane_schedule | 岸桥调度优化 | 装卸作业排序 |
| 993 | 🆕 yard_management | 堆场管理优化 | 集装箱堆放策略 |
| 994 | 🆕 agv_dispatch | AGV调度优化 | 无人车路径规划 |
| 995 | 🆕 truck_queue_optimize | 集卡排队优化 | 闸口/堆场排队 |
| 996 | 🆕 vessel_eta_predict | 船舶到港预测 | ETA预测 |
| 997 | 🆕 port_energy_optimize | 港口能耗优化 | 岸电/油改电 |
| 998 | 🆕 logistics_carbon_calculate | 物流碳排放计算 | 运输碳足迹 |

### 20.6 楼宇园区（8 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 999 | 🆕 building_energy_audit | 楼宇能源审计 | 用能诊断 |
| 1000 | 🆕 occupancy_detect | 人员占用检测 | 红外/WiFi/CO₂ |
| 1001 | 🆕 lighting_optimize | 照明优化 | 自然光+人工光 |
| 1002 | 🆕 elevator_dispatch | 电梯调度优化 | 群控策略 |
| 1003 | 🆕 water_consumption_optimize | 用水优化 | 节水策略 |
| 1004 | 🆕 indoor_air_quality | 室内空气质量 | CO₂/PM2.5/VOC |
| 1005 | 🆕 fire_risk_assess | 消防风险评估 | 火灾风险预警 |
| 1006 | 🆕 parking_optimize | 停车场优化 | 车位引导/充电桩 |

### 20.7 通用工业（6 个）
| # | 函数ID | 函数名称 | 说明 |
|---|--------|---------|------|
| 1007 | 🆕 oee_calculate | OEE综合效率 | 可用率×性能×质量 |
| 1008 | 🆕 spc_control | SPC统计过程控制 | 控制图/过程能力 |
| 1009 | 🆕 six_sigma_analyze | 六西格玛分析 | DMAIC流程 |
| 1010 | 🆕 lean_value_stream | 精益价值流 | VSM分析 |
| 1011 | 🆕 digital_twin_simulate | 数字孪生仿真 | 设备/产线仿真 |
| 1012 | 🆕 safety_risk_assess | 安全风险评估 | 危险源辨识/风险矩阵 |

---

## 汇总统计

| # | 分类 | 分类ID | 数量 | 已有 | 新增 | 定位 |
|---|------|--------|------|------|------|------|
| 1 | 数据源 | data_source | 40 | 7 | 33 | 数据接入层 |
| 2 | 数据预处理 | data_preprocessing | 66 | 3 | 63 | 数据处理层 |
| 3 | 特征工程 | feature_engineering | 82 | 6 | 76 | 数据处理层 |
| 4 | 时序预测 | ts_forecast | 60 | 4 | 56 | 算法模型层 |
| 5 | 异常检测 | anomaly_detection | 55 | 1 | 54 | 算法模型层 |
| 6 | 分类识别 | classification | 52 | 2 | 50 | 算法模型层 |
| 7 | 回归分析 | regression | 35 | 0 | 35 | 算法模型层 |
| 8 | 聚类分析 | clustering | 35 | 0 | 35 | 算法模型层 |
| 9 | 深度学习 | deep_learning | 72 | 0 | 72 | 算法模型层 |
| 10 | 工业视觉 | industrial_vision | 45 | 0 | 45 | 算法模型层 |
| 11 | 信号处理 | signal_processing | 56 | 0 | 56 | 算法模型层 |
| 12 | 优化算法 | optimization | 51 | 0 | 51 | 算法模型层 |
| 13 | 数学与统计 | math_statistics | 45 | 5 | 40 | 基础计算层 |
| 14 | 模型训练 | model_training | 40 | 8 | 32 | MLOps层 |
| 15 | 模型部署 | model_deployment | 32 | 0 | 32 | MLOps层 |
| 16 | 评估指标 | evaluation_metrics | 40 | 7 | 33 | MLOps层 |
| 17 | 可视化 | visualization | 49 | 0 | 49 | 输出展示层 |
| 18 | 数据输出 | data_output | 37 | 0 | 37 | 输出展示层 |
| 19 | 能源管理 | energy_management | 60 | 0 | 60 | 行业场景层 |
| 20 | 工业专用 | industrial | 60 | 0 | 60 | 行业场景层 |
| | **合计** | | **1012** | **43** | **969** | |

---

## 推荐实施阶段

### 第一阶段：基础扩展（+200 函数，累计 ~236）
- 优先级：数据预处理、特征工程、时序预测、异常检测
- 目标：覆盖最常用的数据处理和核心算法
- 周期：4-6 周

### 第二阶段：算法深化（+300 函数，累计 ~536）
- 优先级：分类识别、回归分析、聚类分析、深度学习、评估指标
- 目标：完善算法模型层，支持多种建模场景
- 周期：6-8 周

### 第三阶段：工业场景（+250 函数，累计 ~786）
- 优先级：信号处理、工业视觉、优化算法、能源管理
- 目标：覆盖核心工业场景，形成行业解决方案
- 周期：6-8 周

### 第四阶段：全面覆盖（+226 函数，累计 1012）
- 优先级：模型部署、数据输出、工业专用、可视化、数学统计
- 目标：完成全部函数，形成完整的工业AI算法库
- 周期：4-6 周

---

## 效率维度覆盖

| 效率维度 | 核心分类 | 典型场景 |
|---------|---------|---------|
| 能源效率 | 能源管理、优化算法、时序预测 | 光伏/风电功率预测、储能调度、碳管理、微网优化、能效对标 |
| 设备效率 | 异常检测、分类识别、信号处理、工业视觉 | 故障诊断、预测性维护、RUL预测、缺陷检测、振动分析 |
| 运营效率 | 数据预处理、特征工程、模型训练、数据输出 | 自动化数据处理、AutoML、生产排程、质量预测、数字孪生 |

---

> 版本：V3.0
> 更新日期：2026-03-13
> 总函数数：1012（已有 43 + 新增 969）
> 分类数：20
> 行业覆盖：新能源发电、工业制造（钢铁/光伏/动力电池）、源网荷储充、碳管理、微网/新电网、楼宇园区、港口运输