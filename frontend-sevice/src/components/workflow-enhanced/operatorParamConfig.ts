// @AI_GENERATED
/**
 * 负荷预测算子人性化参数配置
 * 为各算子定义中文标签、描述、默认值和控件类型
 * 支持 i18n 国际化：通过 getOperatorDescription() 获取翻译后的描述
 */
import i18n from '../../i18n';

export interface ParamConfig {
  label: string;
  description: string;
  defaultValue?: any;
  group: 'basic' | 'advanced';
  controlType?: 'input' | 'number' | 'slider' | 'switch' | 'select' | 'tags';
  options?: { label: string; value: any }[];
  min?: number;
  max?: number;
  step?: number;
}

/**
 * 获取算子描述（支持 i18n）
 */
export function getOperatorDescription(operatorId: string): string {
  const key = `operatorDesc.${operatorId}`;
  const translated = i18n.t(key);
  // 如果翻译键不存在，回退到静态描述
  if (translated === key) return OPERATOR_DESCRIPTIONS[operatorId] || '';
  return translated;
}

/**
 * 算子级别的描述（静态回退值）
 */
export const OPERATOR_DESCRIPTIONS: Record<string, string> = {
  load_csv: '从 CSV/Excel 文件加载时序数据。支持指定时间戳列、数值列、编码格式，可按父子节点 ID 过滤数据行。',
  row_filter: '按条件过滤数据行。支持精确匹配（如 parent_id=park_01）和 pandas 表达式过滤，保留原始列结构。',
  resample_timeseries: '将时序数据重采样到统一的时间粒度（如 15 分钟），自动补全缺失的时间戳，生成连续的时间网格。',
  detect_outliers: '检测时序数据中的异常值。支持 Z-Score、IQR、孤立森林三种方法，将异常点标记为 NaN 供下游填充。仅使用历史数据，避免未来信息泄露。',
  handle_missing: '处理时序数据中的缺失值（NaN）。支持线性插值、前向填充、后向填充、均值填充四种方法，确保输出数据无缺失。',
  extract_time_features: '自动提取时间相关特征（小时、星期、月份等）',
  holiday_features: '标记中国法定节假日。生成 is_holiday（是否节假日）和 holiday_name（节假日名称）两列，可选择剔除春节数据。',
  workday_features: '标记工作日和休息日。生成 is_workday 列，用于区分工作日和休息日的用电模式差异。',
  rolling_statistics: '计算滚动统计特征：滚动均值、标准差、分位数。可配置多个窗口大小（如 24/48/96/168），捕捉数据的局部趋势和波动。',
  create_lag_features: '生成滞后特征：将目标列按指定步数偏移（如 lag_1、lag_24、lag_168），利用历史值作为模型输入。',
  sliding_window: '将时序数据按滑动窗口切片为模型输入样本。窗口大小决定用多少历史数据点作为一次输入，步长控制相邻样本的偏移量。',
  train_test_split_ts: '按时间顺序将数据切分为训练集和测试集。保持时间顺序不打乱，支持按比例或按指定日期切分。',
  multi_step_forecast: '配置多步预测策略：预测步数（如 96 步 = 未来 24 小时）、预测策略（递归/直接/混合）、每步对应的时间单位。',
  xgboost_forecast: 'XGBoost 梯度提升树预测。训练模式下训练模型并返回预测结果；预测模式下加载已训练模型执行推理。支持自动调参和样本权重。',
  auto_tune_xgboost: '使用贝叶斯优化自动搜索 XGBoost 最优超参数（学习率、树深度、子采样率等），提升模型性能。',
  smape_score: '计算对称平均绝对百分比误差（SMAPE），衡量预测值与真实值的偏差程度，取值范围 0-200%，越小越好。',
  mse_rmse_mae: '同时计算三个回归评估指标：MSE（均方误差）、RMSE（均方根误差）、MAE（平均绝对误差），全面评估预测精度。',
  load_database: '从关系型数据库（MySQL/PostgreSQL/SQLite）执行 SQL 查询加载数据。',
  load_api: '通过 REST API 接口获取远程数据，支持 GET/POST 请求和自定义请求头。',
  diff_features: '计算差分特征：一阶差分和季节差分，捕捉数据的变化趋势和季节性模式。',
  pct_change_features: '计算百分比变化率特征，衡量数据在指定周期内的相对变化幅度。',
  extract_statistical_features: '计算历史同期统计特征：均值、最大值、最小值、标准差，捕捉数据的长期统计规律。',
  peak_valley_features: '标记峰谷时段：峰时段（用电高峰）、谷时段（用电低谷）、平时段，反映电价时段特征。',
  shift_features: '标记班次信息：早班、中班、晚班，反映不同工作班次的用电模式差异。',
  // 光伏故障诊断算子
  merge_label: '将光伏设备时序测量数据与故障标签数据按设备层级和日期对齐合并，输出含 label（整型故障类型）列的训练数据。',
  time_window_split: '将连续时序数据按诊断窗口（如 1 天）切分为独立诊断单元。每个设备在每个窗口内作为一个独立样本，输出新增 time_window 列。',
  ts_comparison_features: '对多个数值传感器变量两两计算对比特征：Spearman/Pearson 相关、欧氏距离、DTW 距离、线性回归斜率及差值统计，捕捉传感器间的异常关系。',
  feature_selection_mrmr: '使用 mRMR（最小冗余最大相关）算法从高维特征空间中选出最有价值的 Top-K 特征，降低模型复杂度并提升泛化性能。',
  smote_oversample: '对少数类故障样本进行 SMOTE 合成过采样，解决光伏故障诊断中正常样本远多于故障样本的类别不平衡问题。',
  random_forest_classifier: '随机森林多分类器：训练模式下 fit 并返回模型和特征重要性；预测模式下用已有模型推理，输出整型故障类型标签。',
  precision_recall_f1: '计算分类任务的 Accuracy / Precision / Recall / F1 四项指标，支持 macro/weighted/micro 三种平均方式。',
  confusion_matrix: '生成混淆矩阵（行=真实故障类型，列=预测故障类型）和详细分类报告，分析各故障类型的识别精度。',
  label_encode: '故障标签编码与反映射：encode 模式将业务标签（如 "suite-0"）映射为整数；decode 模式将预测整数还原为业务标签，供结果展示。',
  batch_predict_classifier: '对大量设备批量分类预测，支持分批执行和失败重试，输出各设备×窗口的故障类型预测标签。',
};

export const HUMANIZED_PARAMS: Record<string, Record<string, ParamConfig>> = {
  load_csv: {
    file_path: { label: '文件路径', description: 'CSV 数据文件的完整路径，如 datasets/load_true_weihai_260415.csv', group: 'basic' },
    timestamp_column: { label: '时间戳列', description: '数据中时间戳所在的列名，会被解析为日期时间格式', defaultValue: 'record_time', group: 'basic' },
    value_columns: { label: '数值列', description: '需要加载的数值列名列表，留空则加载所有列', group: 'basic', controlType: 'tags' },
    delimiter: { label: '分隔符', description: 'CSV 文件的列分隔符，通常为逗号', defaultValue: ',', group: 'advanced' },
    encoding: { label: '编码', description: '文件字符编码，中文数据常用 utf-8 或 gbk', defaultValue: 'utf-8', group: 'advanced' },
    header_row: { label: '表头行号', description: '表头所在行号（从 0 开始），0 表示第一行是表头', defaultValue: 0, group: 'advanced', controlType: 'number' },
    parent_field: { label: '父级字段', description: '数据表中父节点 ID 的列名，用于多测量点数据过滤', group: 'advanced' },
    child_field: { label: '子级字段', description: '数据表中子节点 ID 的列名，用于多测量点数据过滤', group: 'advanced' },
    parent_id: { label: '父级 ID', description: '要筛选的父节点 ID 值，如 park_01', group: 'advanced' },
    child_id: { label: '子级 ID', description: '要筛选的子节点 ID 值，如 yARGkDuq', group: 'advanced' },
  },
  resample_timeseries: {
    frequency: { label: '采样频率', description: '目标时间粒度，决定"一步"代表多长时间', defaultValue: '15min', group: 'basic', controlType: 'select',
      options: [
        { label: '5分钟', value: '5min' }, { label: '15分钟', value: '15min' },
        { label: '30分钟', value: '30min' }, { label: '1小时', value: '1h' },
      ],
    },
    method: { label: '聚合方法', description: '当一个时间窗口内有多个数据点时的聚合方式', defaultValue: 'mean', group: 'basic', controlType: 'select',
      options: [
        { label: '均值', value: 'mean' }, { label: '求和', value: 'sum' },
        { label: '最大值', value: 'max' }, { label: '最小值', value: 'min' },
      ],
    },
    time_field: { label: '时间列名', description: '时间戳列的名称', defaultValue: 'record_time', group: 'advanced' },
    load_field: { label: '数据列名', description: '要处理的数据列名称', defaultValue: 'value', group: 'advanced' },
    task_type: { label: '任务类型', description: '预测场景类型，影响重采样策略', group: 'advanced', controlType: 'select',
      options: [
        { label: '日内预测', value: 'DI' }, { label: '日前预测', value: 'D' },
        { label: '周内预测', value: 'WI' }, { label: '周前预测', value: 'W' },
      ],
    },
  },
  detect_outliers: {
    method: { label: '检测方法', description: '异常值检测算法：Z-Score 基于统计偏差，IQR 基于四分位距，孤立森林基于机器学习', defaultValue: 'zscore', group: 'basic', controlType: 'select',
      options: [
        { label: 'Z-Score（推荐）', value: 'zscore' }, { label: 'IQR 四分位距', value: 'iqr' },
        { label: '孤立森林', value: 'isolation_forest' },
      ],
    },
    threshold: { label: '阈值', description: '检测灵敏度：值越大越宽松（检出更少异常），值越小越严格（检出更多异常）', defaultValue: 6.0, group: 'basic', controlType: 'number', min: 1, max: 10, step: 0.5 },
    load_field: { label: '数据列名', description: '要处理的数据列名称', defaultValue: 'value', group: 'advanced' },
    window_size: { label: '窗口大小', description: '滚动统计的窗口大小（数据点数），96 对应 15 分钟粒度下的 24 小时', defaultValue: 96, group: 'advanced', controlType: 'number' },
  },
  handle_missing: {
    method: { label: '填充方法', description: '缺失值处理方式：线性插值最平滑，前向填充用上一个值，后向填充用下一个值', defaultValue: 'linear', group: 'basic', controlType: 'select',
      options: [
        { label: '线性插值（推荐）', value: 'linear' }, { label: '前向填充', value: 'ffill' },
        { label: '后向填充', value: 'bfill' }, { label: '均值填充', value: 'mean' },
      ],
    },
    time_field: { label: '时间列名', description: '时间戳列名，线性插值时用于基于时间的插值', defaultValue: 'record_time', group: 'advanced' },
    load_field: { label: '数据列名', description: '要处理的数据列名称', defaultValue: 'value', group: 'advanced' },
  },
  // @AI_GENERATED
  row_filter: {
    column_filters: { label: '数据过滤条件', description: '按列值过滤数据，格式为 JSON，如 {"parent_id": "park_01"}。留空则不过滤。', group: 'basic' },
  },
  extract_time_features: {
    features: { label: '时间特征', description: '自动提取的时间特征。默认提取：小时(hour)、星期(dayofweek)、月份(month)、日期(day)、季度(quarter)。通常无需修改。', defaultValue: ['hour', 'dayofweek', 'month', 'day', 'quarter'], group: 'advanced', controlType: 'tags' },
    time_field: { label: '时间列名', description: '时间戳列名', defaultValue: 'record_time', group: 'advanced' },
  },
  // @AI_GENERATED: end
  // @AI_GENERATED
  holiday_features: {
    remove_spring_festival: { label: '剔除春节异常数据（推荐开启）', description: '春节期间用电模式异常，开启后自动剔除春节前后数据', defaultValue: true, group: 'basic', controlType: 'switch' },
  },
  workday_features: {},
  // @AI_GENERATED: end
  // @AI_GENERATED
  rolling_statistics: {
    target_column: { label: '目标列', description: '计算滚动统计的列名', defaultValue: 'value', group: 'advanced' },
    window_sizes: { label: '窗口大小列表', description: '滚动窗口大小列表，如 24=6小时, 96=24小时, 168=7天（15分钟粒度下）', defaultValue: [24, 48, 96, 168], group: 'advanced', controlType: 'tags' },
    statistics: { label: '统计量', description: '要计算的统计量类型', defaultValue: ['mean', 'std'], group: 'advanced', controlType: 'tags' },
  },
  // @AI_GENERATED: end
  // @AI_GENERATED
  create_lag_features: {
    lags: { label: '滞后步数', description: '历史数据回看步数，默认回看1步(15分钟前)、24步(6小时前)、168步(7天前)', defaultValue: [1, 24, 168], group: 'basic', controlType: 'tags' },
    target_column: { label: '目标列', description: '要生成滞后特征的列名', defaultValue: 'value', group: 'advanced' },
  },
  // @AI_GENERATED: end
  // @AI_GENERATED
  sliding_window: {
    window_size: { label: '窗口大小', description: '输入窗口大小，96=过去24小时的数据作为一次输入', defaultValue: 96, group: 'basic', controlType: 'number', min: 1, max: 1000 },
    step: { label: '滑动步长', description: '相邻样本之间的偏移量，1=逐点滑动', defaultValue: 1, group: 'basic', controlType: 'number', min: 1 },
    target_column: { label: '目标列', description: '目标列名', defaultValue: 'value', group: 'advanced' },
  },
  // @AI_GENERATED: end
  // @AI_GENERATED
  train_test_split_ts: {
    train_ratio: { label: '训练集比例', description: '训练集占总数据的比例，0.8 表示 80% 用于训练', defaultValue: 0.8, group: 'basic', controlType: 'slider', min: 0.5, max: 0.95, step: 0.05 },
    val_ratio: { label: '验证集比例', description: '验证集占总数据的比例，剩余部分为测试集', defaultValue: 0.1, group: 'advanced', controlType: 'slider', min: 0, max: 0.3, step: 0.05 },
    split_date: { label: '切分日期', description: '按指定日期切分（优先于比例），格式 YYYY-MM-DD', group: 'advanced' },
    target_column: { label: '目标列', description: '预测目标列名，切分时会分离为特征和目标', defaultValue: 'value', group: 'advanced' },
    time_field: { label: '时间列名', description: '时间戳列名，用于保持时间顺序', defaultValue: 'record_time', group: 'advanced' },
    task_type: { label: '任务类型', description: '预测任务类型', defaultValue: 'D', group: 'advanced' },
  },
  // @AI_GENERATED: end
  // @AI_GENERATED
  multi_step_forecast: {
    forecast_steps: { label: '预测步数', description: '预测未来多少个时间点，96=预测未来24小时', defaultValue: 96, group: 'basic', controlType: 'number', min: 1, max: 1000 },
    strategy: { label: '预测策略', description: '递归=逐步预测（用上一步结果预测下一步），直接=一次性预测所有步', defaultValue: 'recursive', group: 'advanced', controlType: 'select',
      options: [
        { label: '递归预测（推荐）', value: 'recursive' },
        { label: '直接预测', value: 'direct' },
        { label: '混合预测', value: 'hybrid' },
      ],
    },
    step_size: { label: '步长大小', description: '每步对应多少个时间单位，通常为 1', defaultValue: 1, group: 'advanced', controlType: 'number', min: 1 },
    forecast_start_time: { label: '预测起始时刻', description: '每天预测的第一个时间点，如 00:15', defaultValue: '00:15', group: 'advanced' },
  },
  // @AI_GENERATED: end
  xgboost_forecast: {
    n_estimators: { label: '树数量', description: 'XGBoost 决策树的数量，越多模型越复杂但训练越慢', defaultValue: 200, group: 'basic', controlType: 'number', min: 50, max: 2000 },
    auto_tune: { label: '自动调参', description: '开启后使用贝叶斯优化自动搜索最优超参数，耗时较长但效果更好', defaultValue: false, group: 'basic', controlType: 'switch' },
    mode: { label: '运行模式', description: '训练模式=训练新模型，预测模式=使用已有模型推理', defaultValue: 'train', group: 'basic', controlType: 'select',
      options: [{ label: '训练', value: 'train' }, { label: '预测', value: 'predict' }],
    },
    model_id: { label: '模型 ID', description: '预测模式下需要指定已训练模型的 ID', group: 'basic' },
    separate_modeling: { label: '分类建模', description: '开启后分别为工作日和休息日训练独立模型，通常能提升精度', defaultValue: 'true', group: 'advanced', controlType: 'select',
      options: [{ label: '是（推荐）', value: 'true' }, { label: '否', value: 'false' }],
    },
    prefer_unit_len: { label: '验证集倍数', description: '验证集长度 = 倍数 × 预测步数，用于评估模型质量', defaultValue: 2, group: 'advanced', controlType: 'number' },
    default_retrain: { label: '全量重训练', description: '开启后先用部分数据训练验证，通过后再用全量数据重训最终模型', defaultValue: true, group: 'advanced', controlType: 'switch' },
    sample_weight_decay: { label: '权重衰减', description: '近期数据权重更高（0.99=缓慢衰减，0.9=快速衰减），让模型更关注近期趋势', defaultValue: 0.99, group: 'advanced', controlType: 'number', min: 0.9, max: 1, step: 0.01 },
    task_type: { label: '任务类型', description: '预测场景类型，影响训练策略', defaultValue: 'D', group: 'advanced' },
  },
  smape_score: {},
  mse_rmse_mae: {},
  // ── 光伏故障诊断算子 ──────────────────────────────────────────────────────
  merge_label: {
    id_fields: { label: '设备分组字段', description: '设备层级字段，用于按设备对齐源数据和标签数据，默认包含 site_id/device_id/branch_id', defaultValue: ['site_id', 'device_id', 'branch_id'], group: 'basic', controlType: 'tags' },
    time_field: { label: '时间列名', description: '两份数据中共用的时间列名称', defaultValue: 'time', group: 'basic' },
    label_col: { label: '标签列名', description: '标签数据中存储故障类型的列名（整型或字符串均可）', defaultValue: 'custom_label_id', group: 'basic' },
    output_label_col: { label: '输出标签列名', description: '合并后输出 DataFrame 中标签列的名称', defaultValue: 'label', group: 'advanced' },
  },
  time_window_split: {
    window: { label: '诊断窗口', description: '将时序数据按此周期切分为独立诊断单元，如 1d=按天切分，1w=按周切分', defaultValue: '1d', group: 'basic', controlType: 'select',
      options: [
        { label: '1天（推荐）', value: '1d' }, { label: '12小时', value: '12h' },
        { label: '1周', value: '1w' }, { label: '1小时', value: '1h' },
      ],
    },
    id_fields: { label: '设备分组字段', description: '按设备层级独立切分，通常为 site_id/device_id/branch_id', defaultValue: ['site_id', 'device_id', 'branch_id'], group: 'basic', controlType: 'tags' },
    time_field: { label: '时间列名', description: '时间列名称', defaultValue: 'time', group: 'advanced' },
  },
  ts_comparison_features: {
    id_fields: { label: '设备分组字段', description: '按设备×窗口分组独立计算对比特征', defaultValue: ['site_id', 'device_id', 'branch_id', 'time_window'], group: 'basic', controlType: 'tags' },
    value_fields: { label: '数值变量列', description: '需要两两对比的数值列，如 ["value", "i_cal"]，至少需要 2 列才会计算对比特征', defaultValue: ['value', 'i_cal'], group: 'basic', controlType: 'tags' },
  },
  feature_selection_mrmr: {
    k: { label: 'Top-K 特征数', description: 'mRMR 算法选出的最优特征数量，越少训练越快但可能损失信息', defaultValue: 50, group: 'basic', controlType: 'number', min: 5, max: 200 },
    mode: { label: '运行模式', description: 'fit=训练时计算并保存特征列表；transform=预测时按已有列表筛选列', defaultValue: 'fit', group: 'basic', controlType: 'select',
      options: [{ label: '训练（fit）', value: 'fit' }, { label: '预测（transform）', value: 'transform' }],
    },
    target_col: { label: '标签列名', description: '训练集中的目标标签列名', defaultValue: 'label', group: 'advanced' },
  },
  smote_oversample: {
    limit: { label: '少数类上限', description: '每个少数类最多合成到多少个样本，避免过度过采样', defaultValue: 500, group: 'basic', controlType: 'number', min: 50, max: 2000 },
  },
  random_forest_classifier: {
    n_estimators: { label: '树的数量', description: '随机森林中决策树的棵数，越多越稳定但训练越慢', defaultValue: 80, group: 'basic', controlType: 'number', min: 10, max: 500 },
    mode: { label: '运行模式', description: 'train=训练新模型；predict=使用已训练模型做推理', defaultValue: 'train', group: 'basic', controlType: 'select',
      options: [{ label: '训练', value: 'train' }, { label: '预测', value: 'predict' }],
    },
    random_state: { label: '随机种子', description: '固定随机种子保证结果可复现', defaultValue: 90, group: 'advanced', controlType: 'number' },
    n_jobs: { label: '并行线程数', description: '-1 表示使用全部 CPU 核心并行训练', defaultValue: -1, group: 'advanced', controlType: 'number', min: -1, max: 32 },
  },
  precision_recall_f1: {
    average: { label: '平均方式', description: 'macro=各类别等权平均（推荐，类别不平衡时更公平）；weighted=按样本数加权平均', defaultValue: 'macro', group: 'basic', controlType: 'select',
      options: [
        { label: 'Macro 等权平均（推荐）', value: 'macro' },
        { label: 'Weighted 加权平均', value: 'weighted' },
        { label: 'Micro 微平均', value: 'micro' },
      ],
    },
  },
  confusion_matrix: {},
  label_encode: {
    mode: { label: '运行模式', description: 'encode=训练时将业务标签映射为整数；decode=预测时将整数还原为业务标签', defaultValue: 'encode', group: 'basic', controlType: 'select',
      options: [{ label: '编码 encode（训练）', value: 'encode' }, { label: '反映射 decode（预测）', value: 'decode' }],
    },
    label_col: { label: '标签列名', description: '要处理的标签列名称', defaultValue: 'custom_label_id', group: 'basic' },
    label_map: { label: '标签映射', description: '业务标签→整数的映射字典，JSON格式，如 {"0":0,"1":1,"4":4,"7":7}', defaultValue: '{}', group: 'basic' },
  },
  batch_predict_classifier: {
    batch_size: { label: '批次大小', description: '每批处理的对象数，10000 表示每批最多预测 10000 个设备×窗口组合', defaultValue: 10000, group: 'basic', controlType: 'number', min: 100, max: 100000 },
    id_fields: { label: '设备分组字段', description: '设备标识字段，用于组织批次和输出结果', defaultValue: ['site_id', 'device_id', 'branch_id', 'time_window'], group: 'advanced', controlType: 'tags' },
  },
  // @AI_GENERATED
  auto_tune_xgboost: {
    n_trials: { label: '搜索轮数', description: '优化搜索轮数，越多越精确但越慢（推荐30轮）', defaultValue: 30, group: 'basic', controlType: 'number', min: 5, max: 100 },
    cv_folds: { label: '交叉验证折数', description: 'K折交叉验证的折数，每轮优化都会做K折CV评估', defaultValue: 5, group: 'advanced', controlType: 'number', min: 2, max: 10 },
    metric: { label: '优化指标', description: '贝叶斯优化的目标指标', defaultValue: 'rmse', group: 'advanced', controlType: 'select',
      options: [{ label: 'RMSE（推荐）', value: 'rmse' }, { label: 'MAE', value: 'mae' }, { label: 'MAPE', value: 'mape' }],
    },
  },
  // @AI_GENERATED: end
};
// @AI_GENERATED: end
