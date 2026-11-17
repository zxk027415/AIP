# 风速优化预测数据分析工具

一个基于Web的交互式分析平台，用于分析和可视化风电场站的气象预测数据、历史预测结果和真实风速数据。

## 功能特性

### 核心功能

- **多场站数据管理**: 自动扫描和加载多个风电场站的数据文件
- **数据可视化**: 交互式时间序列图表，支持多气象源对比
- **时间分辨率调整**: 支持15分钟、30分钟、1小时等多种时间分辨率，自动插值处理
- **统计分析**: 
  - 相关性分析（皮尔逊相关系数、相关性矩阵热力图）
  - 误差指标计算（RMSE、MAE）
  - 数据分布统计（均值、中位数、标准差、箱线图、直方图）
  - 数据缺失率分析
- **特征工程**: 
  - 时间特征（小时、星期、月份、季节）
  - 统计特征（滚动窗口统计）
  - 差值特征（气象源间差值）
  - 交互特征
- **机器学习模型**: 
  - 线性回归
  - 决策树回归
  - 随机森林回归
  - 特征重要性分析
- **数据导出**: 支持导出CSV文件和图表图片

### 技术特点

- 前后端分离架构
- 响应式Web界面
- 实时交互式图表（Plotly.js）
- RESTful API设计
- 会话管理机制

## 系统要求

### 软件依赖

- **Python**: 3.8 或更高版本
- **操作系统**: Windows / Linux / macOS
- **浏览器**: Chrome、Firefox、Safari、Edge（最新版本）

### Python依赖包

```
Flask==3.1.2
pandas==3.0.0
numpy==2.4.1
scikit-learn==1.8.0
scipy==1.17.0
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 准备数据文件

将风电场站数据文件放置在 `data/` 目录下。每个场站需要三个CSV文件：

```
data/
├── <station_id>_nwp.csv        # 数值天气预报数据
├── <station_id>_true.csv       # 真实风速数据
```

**数据文件格式要求**:

- **nwp.csv**: 包含时间戳列和多个气象源的要素列（如 `DWD_WS`, `EC_10D_WS`, `DWD_WD` 等）
- **true.csv**: 包含时间戳列和真实风速列（`WS`）

示例数据文件已包含在项目中（如 `42ApNwtb_*.csv`）。

## 运行说明

### 启动开发服务器

```bash
python app.py
```

服务器将在 `http://localhost:5000` 启动。

### 配置环境变量（可选）

```bash
# Windows
set FLASK_ENV=development
set PORT=5000

# Linux/macOS
export FLASK_ENV=development
export PORT=5000
```

### 访问应用

在浏览器中打开: `http://localhost:5000`

## 使用指南

### 1. 选择场站

- 打开应用后，从顶部导航栏的下拉菜单中选择要分析的风电场站
- 系统会自动加载该场站的数据文件

### 2. 配置分析参数

在控制面板中设置：

- **日期范围**: 选择要分析的起始和结束日期（默认最近15天）
- **时间分辨率**: 选择数据的时间间隔（15T、30T、1H、3H）
- **气象源选择**: 勾选要对比的气象预报源
- **显示选项**:
  - ☑ 显示真实风速（true）

点击 **"应用设置"** 按钮加载数据。

### 3. 数据展示

切换到 **"数据展示"** 标签页：

- 查看时间序列折线图
- 使用鼠标缩放、平移图表
- 悬停查看具体数值
- 点击图例显示/隐藏特定曲线

### 4. 统计分析

切换到 **"统计分析"** 标签页，查看：

#### 相关性分析
- 各气象源与真实风速的相关系数表格
- 气象源之间的相关性矩阵热力图

#### 误差指标
- RMSE（均方根误差）和MAE（平均绝对误差）表格
- 误差对比柱状图

#### 数据分布
- 基本统计量（均值、中位数、标准差等）
- 直方图和箱线图

#### 缺失率分析
- 各数据源的缺失率统计表格和柱状图

### 5. 特征工程

切换到 **"特征工程"** 标签页：

1. 选择要生成的特征组：
   - 原始气象要素
   - 时间特征
   - 统计特征（滚动窗口）
   - 差值特征
   - 交互特征

2. 点击 **"生成特征"** 按钮

3. 查看生成的特征列表

### 6. 模型训练

切换到 **"模型训练"** 标签页：

1. 选择模型类型：
   - 线性回归
   - 决策树
   - 随机森林（推荐）

2. 设置模型参数（如随机森林的树数量）

3. 点击 **"训练模型"** 按钮

4. 查看结果：
   - 评估指标（RMSE、MAE、R²）
   - 预测值vs真实值对比图
   - 特征重要性排名

### 7. 导出数据

- 点击 **"导出CSV"** 按钮导出当前数据表格
- 点击 **"导出图表"** 按钮保存图表为PNG图片

## 项目结构

```
wind-speed-analysis-tool/
├── app.py                      # 应用入口
├── config.py                   # 配置文件
├── requirements.txt            # Python依赖
├── README.md                   # 项目文档
├── API_DOCUMENTATION.md        # API文档
├── backend/                    # 后端模块
│   ├── __init__.py
│   ├── routes.py              # API路由
│   ├── data_loader.py         # 数据加载器
│   ├── data_processor.py      # 数据处理器
│   ├── statistical_analyzer.py # 统计分析器
│   ├── feature_engineer.py    # 特征工程器
│   └── model_trainer.py       # 模型训练器
├── frontend/                   # 前端文件
│   ├── templates/
│   │   └── index.html         # 主页面
│   └── static/
│       ├── css/
│       │   └── style.css      # 样式文件
│       └── js/
│           └── app.js         # 前端逻辑
├── data/                       # 数据文件目录
│   ├── 42ApNwtb_nwp.csv
│   ├── 42ApNwtb_true.csv
│   └── ...
└── tests/                      # 测试文件
    ├── test_feature_engineer.py
    ├── test_model_trainer.py
    ├── test_statistical_analyzer.py
    └── test_integration.py
```

## API文档

详细的API文档请参考 [API_DOCUMENTATION.md](API_DOCUMENTATION.md)。

主要API端点：

- `GET /api/stations` - 获取所有场站列表
- `POST /api/data/load` - 加载场站数据
- `POST /api/data/timeseries` - 获取时间序列数据
- `POST /api/analysis/correlation` - 相关性分析
- `POST /api/analysis/error_metrics` - 误差指标计算
- `POST /api/model/train` - 训练机器学习模型

### 代码结构

项目采用模块化设计，主要模块包括：

- **DataLoader**: 从数据库中读取数据
- **DataProcessor**: 处理时间对齐、插值和数据过滤
- **StatisticalAnalyzer**: 执行各类统计分析
- **FeatureEngineer**: 构建机器学习特征
- **ModelTrainer**: 训练和评估预测模型

### 添加新的模型

在 `backend/model_trainer.py` 中添加新的训练方法：

```python
def train_new_model(self, **params):
    """训练新模型"""
    # 实现训练逻辑
    pass
```

在 `backend/routes.py` 中添加对应的API端点。

## 常见问题

### Q: 数据加载失败

**A**: 检查：
1. CSV文件命名格式是否正确（`<station_id>_nwp.csv` 等）
2. CSV文件是否包含必需的列（时间戳、WS等）
3. 文件编码是否为UTF-8

### Q: 图表不显示

**A**: 
1. 检查浏览器控制台是否有JavaScript错误
2. 确认已选择气象源并点击"应用设置"
3. 尝试刷新页面

### Q: 模型训练时间过长

**A**: 
1. 减少日期范围
2. 减少选择的特征组数量
3. 降低随机森林的树数量参数

### Q: 内存不足

**A**: 
1. 减少分析的日期范围
2. 使用更高的时间分辨率（如3H而不是15T）
3. 关闭不需要的特征组

## 性能优化建议

- **大数据集**: 对于超过100万行的数据，建议使用1H或3H时间分辨率
- **并发用户**: 生产环境建议使用Gunicorn + Nginx部署
- **会话管理**: 生产环境建议使用Redis存储会话数据

## 生产部署

### 使用Gunicorn部署

```bash
# 安装Gunicorn
pip install gunicorn

# 启动应用（4个工作进程）
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### 使用Docker部署

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```