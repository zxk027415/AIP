# @AI_GENERATED: Kiro v1.0
"""
补充 functions.json 中缺失的算法基础模块
从 industry_templates.json 中提取所有被引用但不存在的算法ID，生成完整定义并写入
"""
import json
import os

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 64个缺失算法的完整定义
MISSING_ALGOS = [
    # ===== data_source (5个) =====
    {
        "id": "load_canbus",
        "name": "CAN总线数据读取",
        "category": "data_source",
        "description": "从CAN总线读取工业设备通信数据，支持CAN 2.0A/B和CAN FD协议。",
        "parameters": [
            {"name": "interface", "type": "STRING", "required": True, "description": "CAN接口名称，如can0"},
            {"name": "bitrate", "type": "NUMBER", "required": False, "description": "波特率，默认500000", "default": "500000"},
            {"name": "duration_sec", "type": "NUMBER", "required": False, "description": "采集时长(秒)", "default": "60"}
        ],
        "return_type": "ARRAY",
        "examples": ["data = load_canbus('can0', 500000, 60)"]
    },
    {
        "id": "load_iec61850",
        "name": "IEC 61850数据读取",
        "category": "data_source",
        "description": "从IEC 61850变电站自动化系统读取电力数据，支持MMS和GOOSE协议。",
        "parameters": [
            {"name": "server_url", "type": "STRING", "required": True, "description": "IEC 61850服务器地址"},
            {"name": "dataset", "type": "STRING", "required": True, "description": "数据集路径"},
            {"name": "protocol", "type": "STRING", "required": False, "description": "协议类型: mms|goose", "default": "mms"}
        ],
        "return_type": "ARRAY",
        "examples": ["data = load_iec61850('192.168.1.10', 'LD0/LLN0$dataset1', 'mms')"]
    },
    {
        "id": "load_image",
        "name": "图像数据加载",
        "category": "data_source",
        "description": "加载图像文件或图像目录，支持PNG/JPG/BMP/TIFF格式，可批量加载。",
        "parameters": [
            {"name": "path", "type": "STRING", "required": True, "description": "图像文件或目录路径"},
            {"name": "resize", "type": "ARRAY", "required": False, "description": "目标尺寸[width, height]"},
            {"name": "color_mode", "type": "STRING", "required": False, "description": "颜色模式: rgb|grayscale", "default": "rgb"}
        ],
        "return_type": "ARRAY",
        "examples": ["images = load_image('./dataset/images/', [224, 224], 'rgb')"]
    },
    {
        "id": "load_video",
        "name": "视频流数据加载",
        "category": "data_source",
        "description": "加载视频文件或RTSP视频流，按帧提取图像数据。",
        "parameters": [
            {"name": "source", "type": "STRING", "required": True, "description": "视频文件路径或RTSP地址"},
            {"name": "fps", "type": "NUMBER", "required": False, "description": "提取帧率", "default": "1"},
            {"name": "max_frames", "type": "NUMBER", "required": False, "description": "最大帧数", "default": "1000"}
        ],
        "return_type": "ARRAY",
        "examples": ["frames = load_video('rtsp://camera:554/stream', 5, 500)"]
    },
    {
        "id": "load_bacnet",
        "name": "BACnet设备数据读取",
        "category": "data_source",
        "description": "从BACnet楼宇自动化设备读取数据，支持BACnet/IP协议。",
        "parameters": [
            {"name": "device_ip", "type": "STRING", "required": True, "description": "BACnet设备IP地址"},
            {"name": "object_list", "type": "ARRAY", "required": True, "description": "对象标识列表"},
            {"name": "poll_interval", "type": "NUMBER", "required": False, "description": "轮询间隔(秒)", "default": "10"}
        ],
        "return_type": "ARRAY",
        "examples": ["data = load_bacnet('192.168.1.50', ['AI:1', 'AI:2', 'AO:1'])"]
    },
    # ===== data_preprocessing (14个) =====
    {
        "id": "z_score_scale",
        "name": "Z-Score标准化",
        "category": "data_preprocessing",
        "description": "使用Z-Score方法将数据标准化为均值0、标准差1的分布。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
            {"name": "columns", "type": "ARRAY", "required": False, "description": "指定列名列表，默认全部数值列"}
        ],
        "return_type": "ARRAY",
        "examples": ["scaled = z_score_scale(data, ['temperature', 'pressure'])"]
    },
    {
        "id": "min_max_scale",
        "name": "Min-Max归一化",
        "category": "data_preprocessing",
        "description": "将数据线性缩放到指定范围（默认[0,1]）。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
            {"name": "feature_range", "type": "ARRAY", "required": False, "description": "目标范围[min, max]", "default": "[0, 1]"}
        ],
        "return_type": "ARRAY",
        "examples": ["scaled = min_max_scale(data, [0, 1])"]
    },
    {
        "id": "wavelet_denoise",
        "name": "小波去噪",
        "category": "data_preprocessing",
        "description": "使用小波变换对信号进行去噪处理，支持多种小波基函数。",
        "parameters": [
            {"name": "signal", "type": "ARRAY", "required": True, "description": "输入信号"},
            {"name": "wavelet", "type": "STRING", "required": False, "description": "小波基: db4|sym5|coif3", "default": "db4"},
            {"name": "level", "type": "NUMBER", "required": False, "description": "分解层数", "default": "4"}
        ],
        "return_type": "ARRAY",
        "examples": ["denoised = wavelet_denoise(signal, 'db4', 4)"]
    },
    {
        "id": "bandpass_filter",
        "name": "带通滤波器",
        "category": "data_preprocessing",
        "description": "对信号进行带通滤波，保留指定频率范围内的成分。",
        "parameters": [
            {"name": "signal", "type": "ARRAY", "required": True, "description": "输入信号"},
            {"name": "low_freq", "type": "NUMBER", "required": True, "description": "低截止频率(Hz)"},
            {"name": "high_freq", "type": "NUMBER", "required": True, "description": "高截止频率(Hz)"},
            {"name": "sample_rate", "type": "NUMBER", "required": True, "description": "采样率(Hz)"}
        ],
        "return_type": "ARRAY",
        "examples": ["filtered = bandpass_filter(signal, 0.1, 50, 1000)"]
    },
    {
        "id": "fft_transform",
        "name": "快速傅里叶变换",
        "category": "data_preprocessing",
        "description": "对时域信号进行FFT变换，提取频域特征。",
        "parameters": [
            {"name": "signal", "type": "ARRAY", "required": True, "description": "输入时域信号"},
            {"name": "sample_rate", "type": "NUMBER", "required": True, "description": "采样率(Hz)"},
            {"name": "window", "type": "STRING", "required": False, "description": "窗函数: hann|hamming|blackman", "default": "hann"}
        ],
        "return_type": "OBJECT",
        "examples": ["spectrum = fft_transform(signal, 1000, 'hann')"]
    },
    {
        "id": "pca_reduction",
        "name": "PCA降维",
        "category": "data_preprocessing",
        "description": "使用主成分分析进行特征降维，保留指定比例的方差。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入高维数据"},
            {"name": "n_components", "type": "NUMBER", "required": False, "description": "目标维度或方差保留比例", "default": "0.95"}
        ],
        "return_type": "ARRAY",
        "examples": ["reduced = pca_reduction(data, 0.95)"]
    },
    {
        "id": "feature_select",
        "name": "特征选择",
        "category": "data_preprocessing",
        "description": "基于统计方法或模型重要性进行特征选择。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入特征矩阵"},
            {"name": "target", "type": "ARRAY", "required": True, "description": "目标变量"},
            {"name": "method", "type": "STRING", "required": False, "description": "方法: mutual_info|f_test|importance", "default": "mutual_info"},
            {"name": "top_k", "type": "NUMBER", "required": False, "description": "选择前k个特征", "default": "10"}
        ],
        "return_type": "ARRAY",
        "examples": ["selected = feature_select(X, y, 'mutual_info', 10)"]
    },
    {
        "id": "kalman_filter",
        "name": "卡尔曼滤波",
        "category": "data_preprocessing",
        "description": "使用卡尔曼滤波对含噪声的时序数据进行状态估计和平滑。",
        "parameters": [
            {"name": "measurements", "type": "ARRAY", "required": True, "description": "观测数据序列"},
            {"name": "process_noise", "type": "NUMBER", "required": False, "description": "过程噪声方差", "default": "0.01"},
            {"name": "measurement_noise", "type": "NUMBER", "required": False, "description": "观测噪声方差", "default": "0.1"}
        ],
        "return_type": "ARRAY",
        "examples": ["smoothed = kalman_filter(measurements, 0.01, 0.1)"]
    },
    {
        "id": "image_resize",
        "name": "图像缩放",
        "category": "data_preprocessing",
        "description": "将图像缩放到指定尺寸，支持多种插值方法。",
        "parameters": [
            {"name": "images", "type": "ARRAY", "required": True, "description": "输入图像数组"},
            {"name": "target_size", "type": "ARRAY", "required": True, "description": "目标尺寸[width, height]"},
            {"name": "interpolation", "type": "STRING", "required": False, "description": "插值方法: bilinear|bicubic|nearest", "default": "bilinear"}
        ],
        "return_type": "ARRAY",
        "examples": ["resized = image_resize(images, [224, 224], 'bilinear')"]
    },
    {
        "id": "image_normalize",
        "name": "图像归一化",
        "category": "data_preprocessing",
        "description": "对图像像素值进行归一化处理，支持ImageNet标准化。",
        "parameters": [
            {"name": "images", "type": "ARRAY", "required": True, "description": "输入图像数组"},
            {"name": "method", "type": "STRING", "required": False, "description": "方法: scale|imagenet|custom", "default": "scale"},
            {"name": "mean", "type": "ARRAY", "required": False, "description": "自定义均值[R,G,B]"},
            {"name": "std", "type": "ARRAY", "required": False, "description": "自定义标准差[R,G,B]"}
        ],
        "return_type": "ARRAY",
        "examples": ["normalized = image_normalize(images, 'imagenet')"]
    },
    {
        "id": "image_augment",
        "name": "图像数据增强",
        "category": "data_preprocessing",
        "description": "对图像进行数据增强，包括翻转、旋转、裁剪、颜色抖动等。",
        "parameters": [
            {"name": "images", "type": "ARRAY", "required": True, "description": "输入图像数组"},
            {"name": "augmentations", "type": "ARRAY", "required": False, "description": "增强方法列表: flip|rotate|crop|color_jitter", "default": "['flip', 'rotate']"},
            {"name": "factor", "type": "NUMBER", "required": False, "description": "增强倍数", "default": "2"}
        ],
        "return_type": "ARRAY",
        "examples": ["augmented = image_augment(images, ['flip', 'rotate', 'color_jitter'], 3)"]
    },
    {
        "id": "sliding_window",
        "name": "滑动窗口切分",
        "category": "data_preprocessing",
        "description": "将时序数据按滑动窗口切分为样本，用于模型训练输入。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入时序数据"},
            {"name": "window_size", "type": "NUMBER", "required": True, "description": "窗口大小"},
            {"name": "step", "type": "NUMBER", "required": False, "description": "滑动步长", "default": "1"}
        ],
        "return_type": "ARRAY",
        "examples": ["windows = sliding_window(data, 24, 1)"]
    },
    {
        "id": "text_clean",
        "name": "文本清洗",
        "category": "data_preprocessing",
        "description": "对文本数据进行清洗，包括去除特殊字符、停用词过滤、大小写统一等。",
        "parameters": [
            {"name": "texts", "type": "ARRAY", "required": True, "description": "输入文本列表"},
            {"name": "remove_stopwords", "type": "STRING", "required": False, "description": "是否去停用词: true|false", "default": "true"},
            {"name": "language", "type": "STRING", "required": False, "description": "语言: zh|en", "default": "zh"}
        ],
        "return_type": "ARRAY",
        "examples": ["cleaned = text_clean(texts, 'true', 'zh')"]
    },
    {
        "id": "tokenize",
        "name": "文本分词",
        "category": "data_preprocessing",
        "description": "对文本进行分词处理，支持中英文分词和子词分词。",
        "parameters": [
            {"name": "texts", "type": "ARRAY", "required": True, "description": "输入文本列表"},
            {"name": "method", "type": "STRING", "required": False, "description": "分词方法: jieba|bpe|wordpiece", "default": "jieba"},
            {"name": "vocab_size", "type": "NUMBER", "required": False, "description": "词表大小(BPE/WordPiece)", "default": "30000"}
        ],
        "return_type": "ARRAY",
        "examples": ["tokens = tokenize(texts, 'jieba')"]
    },
    # ===== algorithm_model (25个) =====
    {
        "id": "cnn_classifier",
        "name": "CNN图像分类",
        "category": "algorithm_model",
        "description": "使用卷积神经网络进行图像分类，支持自定义网络结构和预训练模型。",
        "parameters": [
            {"name": "images", "type": "ARRAY", "required": True, "description": "输入图像数据"},
            {"name": "labels", "type": "ARRAY", "required": True, "description": "标签数据"},
            {"name": "backbone", "type": "STRING", "required": False, "description": "骨干网络: vgg16|resnet50|mobilenet", "default": "resnet50"},
            {"name": "epochs", "type": "NUMBER", "required": False, "description": "训练轮数", "default": "50"}
        ],
        "return_type": "OBJECT",
        "examples": ["model = cnn_classifier(images, labels, 'resnet50', 50)"]
    },
    {
        "id": "resnet_classifier",
        "name": "ResNet图像分类",
        "category": "algorithm_model",
        "description": "使用ResNet残差网络进行图像分类，支持ResNet18/34/50/101。",
        "parameters": [
            {"name": "images", "type": "ARRAY", "required": True, "description": "输入图像数据"},
            {"name": "labels", "type": "ARRAY", "required": True, "description": "标签数据"},
            {"name": "depth", "type": "NUMBER", "required": False, "description": "网络深度: 18|34|50|101", "default": "50"},
            {"name": "pretrained", "type": "STRING", "required": False, "description": "是否使用预训练权重", "default": "true"}
        ],
        "return_type": "OBJECT",
        "examples": ["model = resnet_classifier(images, labels, 50, 'true')"]
    },
    {
        "id": "yolo_detector",
        "name": "YOLO目标检测",
        "category": "algorithm_model",
        "description": "使用YOLO算法进行实时目标检测，支持YOLOv5/v8。",
        "parameters": [
            {"name": "images", "type": "ARRAY", "required": True, "description": "输入图像数据"},
            {"name": "model_size", "type": "STRING", "required": False, "description": "模型规格: n|s|m|l|x", "default": "m"},
            {"name": "conf_threshold", "type": "NUMBER", "required": False, "description": "置信度阈值", "default": "0.5"}
        ],
        "return_type": "ARRAY",
        "examples": ["detections = yolo_detector(images, 'm', 0.5)"]
    },
    {
        "id": "deeplabv3_segmentation",
        "name": "DeepLabV3语义分割",
        "category": "algorithm_model",
        "description": "使用DeepLabV3+进行语义分割，适用于工业缺陷区域分割。",
        "parameters": [
            {"name": "images", "type": "ARRAY", "required": True, "description": "输入图像数据"},
            {"name": "num_classes", "type": "NUMBER", "required": True, "description": "分割类别数"},
            {"name": "backbone", "type": "STRING", "required": False, "description": "骨干网络: resnet50|resnet101|xception", "default": "resnet50"}
        ],
        "return_type": "ARRAY",
        "examples": ["masks = deeplabv3_segmentation(images, 5, 'resnet50')"]
    },
    {
        "id": "unet_segmentation",
        "name": "U-Net语义分割",
        "category": "algorithm_model",
        "description": "使用U-Net进行语义分割，适用于医学影像和工业缺陷检测。",
        "parameters": [
            {"name": "images", "type": "ARRAY", "required": True, "description": "输入图像数据"},
            {"name": "masks", "type": "ARRAY", "required": True, "description": "标注掩码"},
            {"name": "depth", "type": "NUMBER", "required": False, "description": "网络深度", "default": "4"},
            {"name": "filters", "type": "NUMBER", "required": False, "description": "初始卷积核数", "default": "64"}
        ],
        "return_type": "OBJECT",
        "examples": ["model = unet_segmentation(images, masks, 4, 64)"]
    },
    {
        "id": "anomaly_detection_vision",
        "name": "视觉异常检测",
        "category": "algorithm_model",
        "description": "基于深度学习的视觉异常检测，适用于工业产品表面缺陷检测。",
        "parameters": [
            {"name": "images", "type": "ARRAY", "required": True, "description": "输入图像数据(正常样本)"},
            {"name": "method", "type": "STRING", "required": False, "description": "方法: patchcore|padim|fastflow", "default": "patchcore"},
            {"name": "threshold", "type": "NUMBER", "required": False, "description": "异常分数阈值", "default": "0.5"}
        ],
        "return_type": "OBJECT",
        "examples": ["detector = anomaly_detection_vision(normal_images, 'patchcore', 0.5)"]
    },
    {
        "id": "transformer_forecast",
        "name": "Transformer时序预测",
        "category": "algorithm_model",
        "description": "使用Transformer架构进行时序预测，支持多变量长序列预测。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入时序数据"},
            {"name": "target_col", "type": "STRING", "required": True, "description": "目标列名"},
            {"name": "seq_len", "type": "NUMBER", "required": False, "description": "输入序列长度", "default": "96"},
            {"name": "pred_len", "type": "NUMBER", "required": False, "description": "预测长度", "default": "24"}
        ],
        "return_type": "OBJECT",
        "examples": ["result = transformer_forecast(data, 'power', 96, 24)"]
    },
    {
        "id": "isolation_forest",
        "name": "孤立森林",
        "category": "algorithm_model",
        "description": "使用孤立森林进行无监督异常检测，适用于多维数据异常识别。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
            {"name": "contamination", "type": "NUMBER", "required": False, "description": "异常比例", "default": "0.1"},
            {"name": "n_estimators", "type": "NUMBER", "required": False, "description": "树的数量", "default": "100"}
        ],
        "return_type": "OBJECT",
        "examples": ["result = isolation_forest(data, 0.1, 100)"]
    },
    {
        "id": "autoencoder_anomaly",
        "name": "自编码器异常检测",
        "category": "algorithm_model",
        "description": "使用自编码器进行异常检测，通过重构误差识别异常样本。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据(正常样本)"},
            {"name": "encoding_dim", "type": "NUMBER", "required": False, "description": "编码维度", "default": "16"},
            {"name": "epochs", "type": "NUMBER", "required": False, "description": "训练轮数", "default": "100"}
        ],
        "return_type": "OBJECT",
        "examples": ["detector = autoencoder_anomaly(normal_data, 16, 100)"]
    },
    {
        "id": "moving_average",
        "name": "移动平均",
        "category": "algorithm_model",
        "description": "使用移动平均法进行时序平滑和短期预测，支持简单/加权/指数移动平均。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入时序数据"},
            {"name": "window", "type": "NUMBER", "required": True, "description": "窗口大小"},
            {"name": "method", "type": "STRING", "required": False, "description": "方法: simple|weighted|exponential", "default": "simple"}
        ],
        "return_type": "ARRAY",
        "examples": ["smoothed = moving_average(data, 7, 'exponential')"]
    },
    {
        "id": "linear_regression",
        "name": "线性回归",
        "category": "algorithm_model",
        "description": "使用线性回归进行趋势分析和预测，支持多元回归和正则化。",
        "parameters": [
            {"name": "X", "type": "ARRAY", "required": True, "description": "特征矩阵"},
            {"name": "y", "type": "ARRAY", "required": True, "description": "目标变量"},
            {"name": "regularization", "type": "STRING", "required": False, "description": "正则化: none|l1|l2", "default": "none"}
        ],
        "return_type": "OBJECT",
        "examples": ["model = linear_regression(X, y, 'l2')"]
    },
    {
        "id": "genetic_algorithm",
        "name": "遗传算法优化",
        "category": "algorithm_model",
        "description": "使用遗传算法进行全局优化，适用于调度、排产等组合优化问题。",
        "parameters": [
            {"name": "objective_fn", "type": "STRING", "required": True, "description": "目标函数名称"},
            {"name": "bounds", "type": "ARRAY", "required": True, "description": "变量边界[[min,max],...]"},
            {"name": "population_size", "type": "NUMBER", "required": False, "description": "种群大小", "default": "100"},
            {"name": "generations", "type": "NUMBER", "required": False, "description": "迭代代数", "default": "200"}
        ],
        "return_type": "OBJECT",
        "examples": ["result = genetic_algorithm('minimize_cost', [[0,100],[0,50]], 100, 200)"]
    },
    {
        "id": "linear_programming",
        "name": "线性规划求解",
        "category": "algorithm_model",
        "description": "使用线性规划求解资源分配和调度优化问题。",
        "parameters": [
            {"name": "c", "type": "ARRAY", "required": True, "description": "目标函数系数"},
            {"name": "A_ub", "type": "ARRAY", "required": False, "description": "不等式约束矩阵"},
            {"name": "b_ub", "type": "ARRAY", "required": False, "description": "不等式约束向量"},
            {"name": "bounds", "type": "ARRAY", "required": False, "description": "变量边界"}
        ],
        "return_type": "OBJECT",
        "examples": ["result = linear_programming(c, A_ub, b_ub, bounds)"]
    },
    {
        "id": "fft_analysis",
        "name": "FFT频谱分析",
        "category": "algorithm_model",
        "description": "基于FFT的频谱分析，提取主频率、谐波成分，用于振动分析和故障诊断。",
        "parameters": [
            {"name": "signal", "type": "ARRAY", "required": True, "description": "输入信号"},
            {"name": "sample_rate", "type": "NUMBER", "required": True, "description": "采样率(Hz)"},
            {"name": "top_k", "type": "NUMBER", "required": False, "description": "提取前k个主频", "default": "5"}
        ],
        "return_type": "OBJECT",
        "examples": ["spectrum = fft_analysis(vibration_signal, 10000, 5)"]
    },
    {
        "id": "wavelet_analysis",
        "name": "小波分析",
        "category": "algorithm_model",
        "description": "使用连续/离散小波变换进行时频分析，适用于非平稳信号分析。",
        "parameters": [
            {"name": "signal", "type": "ARRAY", "required": True, "description": "输入信号"},
            {"name": "wavelet", "type": "STRING", "required": False, "description": "小波基: cmor|morl|db4", "default": "cmor"},
            {"name": "scales", "type": "ARRAY", "required": False, "description": "尺度范围"}
        ],
        "return_type": "OBJECT",
        "examples": ["result = wavelet_analysis(signal, 'cmor')"]
    },
    {
        "id": "ekf_estimator",
        "name": "扩展卡尔曼滤波估计",
        "category": "algorithm_model",
        "description": "使用扩展卡尔曼滤波进行非线性系统状态估计，如电池SOC估计。",
        "parameters": [
            {"name": "measurements", "type": "ARRAY", "required": True, "description": "观测数据"},
            {"name": "state_model", "type": "STRING", "required": True, "description": "状态模型名称"},
            {"name": "initial_state", "type": "ARRAY", "required": False, "description": "初始状态向量"}
        ],
        "return_type": "OBJECT",
        "examples": ["states = ekf_estimator(voltage_data, 'battery_soc', [0.8])"]
    },
    {
        "id": "kmeans_cluster",
        "name": "K-Means聚类",
        "category": "algorithm_model",
        "description": "使用K-Means算法进行数据聚类分析。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
            {"name": "n_clusters", "type": "NUMBER", "required": True, "description": "聚类数"},
            {"name": "max_iter", "type": "NUMBER", "required": False, "description": "最大迭代次数", "default": "300"}
        ],
        "return_type": "OBJECT",
        "examples": ["result = kmeans_cluster(data, 5, 300)"]
    },
    {
        "id": "dbscan_cluster",
        "name": "DBSCAN密度聚类",
        "category": "algorithm_model",
        "description": "使用DBSCAN密度聚类算法，自动发现任意形状的簇。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
            {"name": "eps", "type": "NUMBER", "required": False, "description": "邻域半径", "default": "0.5"},
            {"name": "min_samples", "type": "NUMBER", "required": False, "description": "最小样本数", "default": "5"}
        ],
        "return_type": "OBJECT",
        "examples": ["result = dbscan_cluster(data, 0.5, 5)"]
    },
    {
        "id": "embedding_model",
        "name": "文本嵌入模型",
        "category": "algorithm_model",
        "description": "使用预训练模型将文本转换为向量表示，支持BERT/Word2Vec。",
        "parameters": [
            {"name": "texts", "type": "ARRAY", "required": True, "description": "输入文本列表"},
            {"name": "model", "type": "STRING", "required": False, "description": "模型: bert|word2vec|tfidf", "default": "bert"},
            {"name": "dim", "type": "NUMBER", "required": False, "description": "向量维度", "default": "768"}
        ],
        "return_type": "ARRAY",
        "examples": ["vectors = embedding_model(texts, 'bert', 768)"]
    },
    {
        "id": "keyword_extractor",
        "name": "关键词提取",
        "category": "algorithm_model",
        "description": "从文本中提取关键词，支持TF-IDF、TextRank等方法。",
        "parameters": [
            {"name": "texts", "type": "ARRAY", "required": True, "description": "输入文本列表"},
            {"name": "method", "type": "STRING", "required": False, "description": "方法: tfidf|textrank|yake", "default": "textrank"},
            {"name": "top_k", "type": "NUMBER", "required": False, "description": "提取前k个关键词", "default": "10"}
        ],
        "return_type": "ARRAY",
        "examples": ["keywords = keyword_extractor(texts, 'textrank', 10)"]
    },
    {
        "id": "tfidf_classifier",
        "name": "TF-IDF文本分类",
        "category": "algorithm_model",
        "description": "使用TF-IDF特征+分类器进行文本分类。",
        "parameters": [
            {"name": "texts", "type": "ARRAY", "required": True, "description": "输入文本列表"},
            {"name": "labels", "type": "ARRAY", "required": True, "description": "标签列表"},
            {"name": "classifier", "type": "STRING", "required": False, "description": "分类器: svm|nb|lr", "default": "svm"}
        ],
        "return_type": "OBJECT",
        "examples": ["model = tfidf_classifier(texts, labels, 'svm')"]
    },
    {
        "id": "a_star_pathfinding",
        "name": "A*路径规划",
        "category": "algorithm_model",
        "description": "使用A*算法进行最短路径规划，适用于AGV/机器人导航。",
        "parameters": [
            {"name": "grid_map", "type": "ARRAY", "required": True, "description": "网格地图(0=可通行,1=障碍)"},
            {"name": "start", "type": "ARRAY", "required": True, "description": "起点坐标[x,y]"},
            {"name": "goal", "type": "ARRAY", "required": True, "description": "终点坐标[x,y]"},
            {"name": "diagonal", "type": "STRING", "required": False, "description": "是否允许对角移动", "default": "true"}
        ],
        "return_type": "ARRAY",
        "examples": ["path = a_star_pathfinding(grid, [0,0], [9,9], 'true')"]
    },
    {
        "id": "pid_controller",
        "name": "PID控制器",
        "category": "algorithm_model",
        "description": "PID控制算法，用于工业过程控制和自动调节。",
        "parameters": [
            {"name": "setpoint", "type": "NUMBER", "required": True, "description": "目标设定值"},
            {"name": "kp", "type": "NUMBER", "required": True, "description": "比例系数"},
            {"name": "ki", "type": "NUMBER", "required": True, "description": "积分系数"},
            {"name": "kd", "type": "NUMBER", "required": True, "description": "微分系数"}
        ],
        "return_type": "OBJECT",
        "examples": ["controller = pid_controller(100.0, 1.0, 0.1, 0.05)"]
    },
    {
        "id": "power_flow_solver",
        "name": "潮流计算求解",
        "category": "algorithm_model",
        "description": "电力系统潮流计算，求解节点电压和支路功率分布。",
        "parameters": [
            {"name": "bus_data", "type": "ARRAY", "required": True, "description": "节点数据"},
            {"name": "branch_data", "type": "ARRAY", "required": True, "description": "支路数据"},
            {"name": "method", "type": "STRING", "required": False, "description": "求解方法: nr|gs|fdlf", "default": "nr"}
        ],
        "return_type": "OBJECT",
        "examples": ["result = power_flow_solver(bus_data, branch_data, 'nr')"]
    },
    {
        "id": "spc_analyzer",
        "name": "SPC统计过程控制",
        "category": "algorithm_model",
        "description": "统计过程控制分析，生成控制图并检测过程异常。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "过程数据"},
            {"name": "chart_type", "type": "STRING", "required": False, "description": "控制图类型: xbar_r|xbar_s|p|c", "default": "xbar_r"},
            {"name": "subgroup_size", "type": "NUMBER", "required": False, "description": "子组大小", "default": "5"}
        ],
        "return_type": "OBJECT",
        "examples": ["result = spc_analyzer(measurements, 'xbar_r', 5)"]
    },
    # ===== 补充遗漏 =====
    {
        "id": "data_aggregate",
        "name": "数据聚合",
        "category": "data_preprocessing",
        "description": "对数据进行分组聚合计算，支持求和、均值、最大最小值等聚合函数。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
            {"name": "group_by", "type": "ARRAY", "required": True, "description": "分组字段列表"},
            {"name": "agg_funcs", "type": "OBJECT", "required": False, "description": "聚合函数映射 {列名: 函数}", "default": "{'value': 'mean'}"}
        ],
        "return_type": "ARRAY",
        "examples": ["result = data_aggregate(data, ['device_id'], {'power': 'sum', 'temp': 'mean'})"]
    },
    # ===== evaluation_output (20个) =====
    # 注意: f1_metric/accuracy_metric/r2_metric 是模板中引用的ID，
    # functions.json已有 f1_score/accuracy_score/r2_score，这里用新ID添加别名
    {
        "id": "f1_metric",
        "name": "F1指标",
        "category": "evaluation_metrics",
        "description": "计算F1指标，综合精确率和召回率的调和平均，支持多分类。",
        "parameters": [
            {"name": "y_true", "type": "ARRAY", "required": True, "description": "真实标签"},
            {"name": "y_pred", "type": "ARRAY", "required": True, "description": "预测标签"},
            {"name": "average", "type": "STRING", "required": False, "description": "平均方式: micro|macro|weighted", "default": "weighted"}
        ],
        "return_type": "NUMBER",
        "examples": ["score = f1_metric(y_true, y_pred, 'weighted')"]
    },
    {
        "id": "accuracy_metric",
        "name": "准确率指标",
        "category": "evaluation_metrics",
        "description": "计算分类准确率，正确预测数占总样本数的比例。",
        "parameters": [
            {"name": "y_true", "type": "ARRAY", "required": True, "description": "真实标签"},
            {"name": "y_pred", "type": "ARRAY", "required": True, "description": "预测标签"}
        ],
        "return_type": "NUMBER",
        "examples": ["score = accuracy_metric(y_true, y_pred)"]
    },
    {
        "id": "r2_metric",
        "name": "R²决定系数",
        "category": "evaluation_metrics",
        "description": "计算R²决定系数，衡量回归模型拟合优度。",
        "parameters": [
            {"name": "y_true", "type": "ARRAY", "required": True, "description": "真实值"},
            {"name": "y_pred", "type": "ARRAY", "required": True, "description": "预测值"}
        ],
        "return_type": "NUMBER",
        "examples": ["score = r2_metric(y_true, y_pred)"]
    },
    {
        "id": "precision_metric",
        "name": "精确率指标",
        "category": "evaluation_metrics",
        "description": "计算精确率(Precision)，预测为正的样本中实际为正的比例。",
        "parameters": [
            {"name": "y_true", "type": "ARRAY", "required": True, "description": "真实标签"},
            {"name": "y_pred", "type": "ARRAY", "required": True, "description": "预测标签"},
            {"name": "average", "type": "STRING", "required": False, "description": "平均方式: micro|macro|weighted", "default": "weighted"}
        ],
        "return_type": "NUMBER",
        "examples": ["score = precision_metric(y_true, y_pred, 'weighted')"]
    },
    {
        "id": "map_metric",
        "name": "mAP目标检测指标",
        "category": "evaluation_metrics",
        "description": "计算目标检测的平均精度均值(mAP)，支持不同IoU阈值。",
        "parameters": [
            {"name": "predictions", "type": "ARRAY", "required": True, "description": "预测框列表"},
            {"name": "ground_truths", "type": "ARRAY", "required": True, "description": "真实框列表"},
            {"name": "iou_threshold", "type": "NUMBER", "required": False, "description": "IoU阈值", "default": "0.5"}
        ],
        "return_type": "NUMBER",
        "examples": ["score = map_metric(preds, gts, 0.5)"]
    },
    {
        "id": "dice_metric",
        "name": "Dice系数",
        "category": "evaluation_metrics",
        "description": "计算Dice系数，衡量分割结果与真实标注的重叠度。",
        "parameters": [
            {"name": "pred_mask", "type": "ARRAY", "required": True, "description": "预测掩码"},
            {"name": "true_mask", "type": "ARRAY", "required": True, "description": "真实掩码"}
        ],
        "return_type": "NUMBER",
        "examples": ["score = dice_metric(pred_mask, true_mask)"]
    },
    {
        "id": "iou_metric",
        "name": "IoU交并比",
        "category": "evaluation_metrics",
        "description": "计算交并比(IoU)，衡量预测区域与真实区域的重叠程度。",
        "parameters": [
            {"name": "pred_mask", "type": "ARRAY", "required": True, "description": "预测掩码或框"},
            {"name": "true_mask", "type": "ARRAY", "required": True, "description": "真实掩码或框"}
        ],
        "return_type": "NUMBER",
        "examples": ["score = iou_metric(pred_mask, true_mask)"]
    },
    {
        "id": "silhouette_metric",
        "name": "轮廓系数",
        "category": "evaluation_metrics",
        "description": "计算聚类结果的轮廓系数，衡量聚类质量，范围[-1,1]。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
            {"name": "labels", "type": "ARRAY", "required": True, "description": "聚类标签"}
        ],
        "return_type": "NUMBER",
        "examples": ["score = silhouette_metric(data, cluster_labels)"]
    },
    {
        "id": "forecast_plot",
        "name": "预测结果可视化",
        "category": "evaluation_metrics",
        "description": "绘制时序预测结果图，包含实际值、预测值和置信区间。",
        "parameters": [
            {"name": "actual", "type": "ARRAY", "required": True, "description": "实际值序列"},
            {"name": "predicted", "type": "ARRAY", "required": True, "description": "预测值序列"},
            {"name": "confidence_interval", "type": "ARRAY", "required": False, "description": "置信区间[lower, upper]"},
            {"name": "title", "type": "STRING", "required": False, "description": "图表标题", "default": "预测结果"}
        ],
        "return_type": "OBJECT",
        "examples": ["chart = forecast_plot(actual, predicted, ci, '功率预测')"]
    },
    {
        "id": "anomaly_plot",
        "name": "异常检测可视化",
        "category": "evaluation_metrics",
        "description": "绘制异常检测结果图，标注异常点和异常区间。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "原始数据"},
            {"name": "anomalies", "type": "ARRAY", "required": True, "description": "异常标记(0/1)"},
            {"name": "threshold", "type": "NUMBER", "required": False, "description": "异常阈值线"}
        ],
        "return_type": "OBJECT",
        "examples": ["chart = anomaly_plot(data, anomaly_flags, 3.0)"]
    },
    {
        "id": "spectrogram_plot",
        "name": "频谱图可视化",
        "category": "evaluation_metrics",
        "description": "绘制信号的频谱图或时频图，用于振动分析结果展示。",
        "parameters": [
            {"name": "signal", "type": "ARRAY", "required": True, "description": "输入信号"},
            {"name": "sample_rate", "type": "NUMBER", "required": True, "description": "采样率(Hz)"},
            {"name": "plot_type", "type": "STRING", "required": False, "description": "图类型: spectrum|spectrogram|waterfall", "default": "spectrogram"}
        ],
        "return_type": "OBJECT",
        "examples": ["chart = spectrogram_plot(signal, 10000, 'spectrogram')"]
    },
    {
        "id": "heatmap_render",
        "name": "热力图渲染",
        "category": "evaluation_metrics",
        "description": "渲染数据热力图，适用于相关性分析、空间分布展示。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "二维数据矩阵"},
            {"name": "x_labels", "type": "ARRAY", "required": False, "description": "X轴标签"},
            {"name": "y_labels", "type": "ARRAY", "required": False, "description": "Y轴标签"},
            {"name": "colormap", "type": "STRING", "required": False, "description": "配色方案: viridis|hot|coolwarm", "default": "viridis"}
        ],
        "return_type": "OBJECT",
        "examples": ["chart = heatmap_render(corr_matrix, features, features, 'coolwarm')"]
    },
    {
        "id": "scatter_plot",
        "name": "散点图可视化",
        "category": "evaluation_metrics",
        "description": "绘制散点图，支持聚类着色和回归线。",
        "parameters": [
            {"name": "x", "type": "ARRAY", "required": True, "description": "X轴数据"},
            {"name": "y", "type": "ARRAY", "required": True, "description": "Y轴数据"},
            {"name": "labels", "type": "ARRAY", "required": False, "description": "分组标签(用于着色)"},
            {"name": "regression_line", "type": "STRING", "required": False, "description": "是否添加回归线", "default": "false"}
        ],
        "return_type": "OBJECT",
        "examples": ["chart = scatter_plot(x, y, cluster_labels, 'true')"]
    },
    {
        "id": "timeseries_plot",
        "name": "时序图可视化",
        "category": "evaluation_metrics",
        "description": "绘制多变量时序数据图，支持多子图和双Y轴。",
        "parameters": [
            {"name": "data", "type": "ARRAY", "required": True, "description": "时序数据"},
            {"name": "columns", "type": "ARRAY", "required": True, "description": "要绘制的列名"},
            {"name": "subplots", "type": "STRING", "required": False, "description": "是否分子图: true|false", "default": "false"}
        ],
        "return_type": "OBJECT",
        "examples": ["chart = timeseries_plot(data, ['temp', 'pressure'], 'true')"]
    },
    {
        "id": "dashboard_render",
        "name": "仪表盘渲染",
        "category": "evaluation_metrics",
        "description": "渲染综合数据仪表盘，包含多种图表和KPI指标卡。",
        "parameters": [
            {"name": "metrics", "type": "OBJECT", "required": True, "description": "指标数据字典"},
            {"name": "charts", "type": "ARRAY", "required": False, "description": "图表配置列表"},
            {"name": "layout", "type": "STRING", "required": False, "description": "布局: grid|tabs|scroll", "default": "grid"}
        ],
        "return_type": "OBJECT",
        "examples": ["dashboard = dashboard_render(metrics, charts, 'grid')"]
    },
    {
        "id": "interactive_dashboard",
        "name": "交互式仪表盘",
        "category": "evaluation_metrics",
        "description": "生成交互式Web仪表盘，支持筛选、缩放和数据钻取。",
        "parameters": [
            {"name": "data_sources", "type": "ARRAY", "required": True, "description": "数据源配置列表"},
            {"name": "widgets", "type": "ARRAY", "required": False, "description": "组件配置列表"},
            {"name": "refresh_interval", "type": "NUMBER", "required": False, "description": "自动刷新间隔(秒)", "default": "30"}
        ],
        "return_type": "OBJECT",
        "examples": ["dashboard = interactive_dashboard(sources, widgets, 30)"]
    },
    {
        "id": "optimization_report",
        "name": "优化报告生成",
        "category": "evaluation_metrics",
        "description": "生成优化结果报告，包含目标函数收敛曲线、最优解和约束满足情况。",
        "parameters": [
            {"name": "result", "type": "OBJECT", "required": True, "description": "优化结果对象"},
            {"name": "format", "type": "STRING", "required": False, "description": "报告格式: html|pdf|json", "default": "html"}
        ],
        "return_type": "OBJECT",
        "examples": ["report = optimization_report(opt_result, 'html')"]
    },
    {
        "id": "energy_report",
        "name": "能源分析报告",
        "category": "evaluation_metrics",
        "description": "生成能源分析报告，包含能耗统计、节能建议和趋势分析。",
        "parameters": [
            {"name": "energy_data", "type": "ARRAY", "required": True, "description": "能源数据"},
            {"name": "period", "type": "STRING", "required": False, "description": "统计周期: daily|weekly|monthly", "default": "monthly"},
            {"name": "baseline", "type": "ARRAY", "required": False, "description": "基准数据(用于对比)"}
        ],
        "return_type": "OBJECT",
        "examples": ["report = energy_report(data, 'monthly', baseline)"]
    },
    {
        "id": "report_export",
        "name": "报告导出",
        "category": "evaluation_metrics",
        "description": "将分析结果导出为标准报告格式，支持PDF/Excel/HTML。",
        "parameters": [
            {"name": "content", "type": "OBJECT", "required": True, "description": "报告内容对象"},
            {"name": "format", "type": "STRING", "required": False, "description": "导出格式: pdf|excel|html", "default": "pdf"},
            {"name": "template", "type": "STRING", "required": False, "description": "报告模板名称", "default": "default"}
        ],
        "return_type": "STRING",
        "examples": ["path = report_export(content, 'pdf', 'default')"]
    },
    {
        "id": "single_line_diagram",
        "name": "单线图渲染",
        "category": "evaluation_metrics",
        "description": "渲染电力系统单线图，展示网络拓扑和潮流分布。",
        "parameters": [
            {"name": "network", "type": "OBJECT", "required": True, "description": "电网拓扑数据"},
            {"name": "flow_data", "type": "OBJECT", "required": False, "description": "潮流计算结果"},
            {"name": "highlight", "type": "ARRAY", "required": False, "description": "高亮节点/支路列表"}
        ],
        "return_type": "OBJECT",
        "examples": ["diagram = single_line_diagram(network, flow_result)"]
    },
]


def main():
    functions_path = os.path.join(base, "data", "functions.json")

    with open(functions_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_ids = {fn["id"] for fn in data["functions"]}
    print(f"现有算法数: {len(existing_ids)}")

    added = []
    skipped = []
    for algo in MISSING_ALGOS:
        if algo["id"] in existing_ids:
            skipped.append(algo["id"])
        else:
            # 将 Python bool 转为 JSON bool (True -> true)
            data["functions"].append(algo)
            added.append(algo["id"])

    print(f"新增: {len(added)}")
    if skipped:
        print(f"跳过(已存在): {skipped}")

    # 确保 evaluation_metrics 类别存在（模板引用的evaluation_output映射到此）
    cat_ids = {c["id"] for c in data.get("categories", [])}
    if "evaluation_metrics" not in cat_ids:
        data.setdefault("categories", []).append({
            "id": "evaluation_metrics",
            "name": "评估指标",
            "description": "模型性能评估和可视化输出",
            "subcategories": []
        })
        print("已添加 evaluation_metrics 类别")

    with open(functions_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n写入完成! 当前算法总数: {len(data['functions'])}")
    print(f"新增算法ID: {added}")


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
