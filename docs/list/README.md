# 工业AI算法平台 (Industrial AI Algorithm Platform)

一个基于浏览器的可视化工业AI算法平台，支持AI算法库、模板编辑、数据可视化和智能计算功能。

## ✨ 核心功能

### 🧠 AI算法库
- **智能输入系统**: 根据参数类型自动选择最佳输入方式
- **丰富的算法**: 数据源处理、特征工程、算法模型、评估指标
- **在线执行**: 函数执行器支持在线测试和验证
- **算法知识图谱**: 可视化展示算法间的关系和依赖

### 🎨 可视化模板编辑器
- **拖拽式编辑**: 从函数库拖拽函数到画布创建算法模板
- **智能连接**: 自动验证节点间的类型兼容性
- **实时验证**: 检测环路、断开节点、类型错误等问题
- **模板执行**: 拓扑排序执行，支持复杂的数据流
- **模板库**: 预置工业算法模板

### 📊 数据可视化
- **多种图表**: 折线图、散点图、柱状图、热力图
- **交互式图表**: 缩放、平移、数据视图、导出
- **ECharts集成**: 专业的数据可视化库
- **实时预览**: 算法执行结果即时可视化

### 🔐 用户认证和管理
- **安全认证**: JWT token认证
- **用户管理**: 注册、登录、个人信息管理
- **模板管理**: 保存、加载、删除个人算法模板
- **权限控制**: 基于角色的访问控制

### 🧮 智能计算
- **时序数据处理**: 支持工业时序数据的加载和处理
- **特征工程**: 统计特征、频域特征、滞后特征提取
- **机器学习**: LSTM、ARIMA、XGBoost等预测模型
- **模型评估**: MAE、RMSE、R²等评估指标

## 📚 文档导航

完整文档请访问 **[docs/](docs/README.md)**

### 快速链接
- 🚀 **[快速开始](QUICK_START.md)** - 5分钟快速启动
- 📝 **[变更日志](CHANGELOG.md)** - 查看最新更新
- 🔧 **[故障排除](TROUBLESHOOTING.md)** - 常见问题解决
- 📖 **[用户指南](docs/user-guide/)** - 功能使用说明
- 💻 **[开发文档](docs/developer-guide/)** - 项目结构和开发指南
- 🔌 **[API参考](docs/api-reference/)** - API接口文档
- 🚀 **[部署文档](docs/deployment/)** - 部署和配置指南

## 技术栈

### 前端
- **React 18.2** + **TypeScript 5.2** - 现代化前端框架
- **Ant Design 5.12** - 企业级UI组件库
- **React Flow 11.10** - 可视化流程图编辑
- **ECharts 5.6** - 专业数据可视化
- **Zustand 4.4** - 轻量级状态管理
- **Vite 5.0** - 快速构建工具

### 后端
- **Python 3.10+** - 现代Python
- **FastAPI** - 高性能Web框架
- **SQLAlchemy** - 强大的ORM
- **NumPy** - 科学计算
- **Pandas** - 数据处理
- **Scikit-learn** - 机器学习
- **NetworkX** - 图算法（模板验证）

## 项目结构

```
industrial-ai-platform/
├── frontend/              # 前端应用
│   ├── src/
│   │   ├── components/    # React组件
│   │   │   ├── workflow/  # 模板编辑器
│   │   │   ├── FunctionLibrary.tsx  # AI算法库
│   │   │   └── FunctionExecutor.tsx # 函数执行器
│   │   ├── pages/         # 页面组件
│   │   ├── services/      # API服务
│   │   ├── stores/        # 状态管理
│   │   └── types/         # TypeScript类型
│   └── package.json
├── backend/               # 后端服务
│   ├── api/               # API路由
│   │   ├── auth.py        # 认证API
│   │   ├── workflows.py   # 算法模板API
│   │   ├── functions.py   # 函数库API
│   │   └── system.py      # 系统API
│   ├── services/          # 业务逻辑
│   │   ├── validation_service.py  # 验证服务
│   │   ├── execution_service.py   # 执行服务
│   │   └── function_service.py    # 函数服务
│   ├── models/            # 数据模型
│   ├── data/              # 数据文件
│   │   ├── functions.json # 函数定义
│   │   └── templates/     # 算法模板
│   ├── tests/             # 测试文件
│   └── main.py            # 应用入口
├── docs/                  # 文档中心
│   ├── user-guide/        # 用户指南
│   ├── developer-guide/   # 开发指南
│   ├── api-reference/     # API参考
│   ├── deployment/        # 部署文档
│   └── archive/           # 历史文档
├── scripts/               # 辅助脚本
├── CHANGELOG.md           # 变更日志
├── QUICK_START.md         # 快速开始
└── README.md              # 本文件
```

## 快速开始

### 一键启动（推荐）

```bash
# Windows
scripts\start-all.bat

# Linux/Mac
./scripts/start-all.sh
```

启动后访问：
- **前端应用**: http://localhost:5173
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs

### 环境要求

**后端**:
- Python 3.10+
- Anaconda/Miniconda
- Conda环境: `cp_web`

**前端**:
- Node.js 18+
- npm 10+

### 详细安装步骤

查看 **[快速开始指南](QUICK_START.md)** 获取完整的安装和配置说明。

## 主要功能模块

### 1. AI算法库

**支持的算法类别**:
- 📥 **数据源**: 时序数据加载、重采样、缺失值处理、异常检测
- 🔧 **特征工程**: 统计特征、频域特征、滞后特征、时间特征、归一化
- 🤖 **算法模型**: LSTM预测、ARIMA预测、XGBoost、随机森林、SVM、孤立森林
- 📊 **评估指标**: MAE、RMSE、MAPE、R²、准确率、混淆矩阵、F1分数

**智能输入系统**:
- NUMBER类型 → 数字输入框
- STRING类型 → 下拉选择或文本输入
- ARRAY类型 → JSON输入或数据集选择
- MATRIX类型 → 数据集选择（开发中）

### 2. 模板编辑器

**核心能力**:
- 可视化拖拽编辑
- 自动类型检查
- 实时错误提示
- 模板保存和加载
- 模板快速创建

### 3. 数据可视化

**图表类型**:
- 折线图（时序数据）
- 散点图（相关性分析）
- 柱状图（对比分析）
- 热力图（矩阵可视化）

## 开发进度

### v1.0.0 (2026-03-06) ✅

**已完成**:
- ✅ AI算法库智能输入输出系统
- ✅ 模板编辑器核心功能
- ✅ 数据可视化组件
- ✅ 用户认证和管理
- ✅ 算法知识图谱
- ✅ 系统状态监控

**最新更新**:
- 智能参数输入识别
- 数据格式标准化（时间+数据）
- 菜单结构优化
- 文档重组和整理

查看完整变更: **[CHANGELOG.md](CHANGELOG.md)**

### 下一步计划

**短期 (1-2周)**:
- 数据集管理模块
- 数据集选择器组件
- CSV/Excel文件上传

**中期 (1个月)**:
- 数据集预览和编辑
- 数据集版本管理
- 性能优化

**长期 (2-3个月)**:
- 多用户协作
- 实时数据流处理
- 高级算法集成

## 辅助脚本

### 启动脚本 (`scripts/`)
- **start-all.bat** - 一键启动前后端（推荐）
- **start-frontend.bat** - 仅启动前端
- **start-backend.bat** - 仅启动后端
- **stop-all.bat** - 停止所有服务

### 清理脚本
- **cleanup_step1_cache_files.bat** - 清理缓存文件
- **cleanup_step2_organize_tests.bat** - 整理测试文件
- **cleanup_step3_reorganize_docs.bat** - 重组文档结构
- **cleanup_step4_clean_archive.bat** - 清理归档文件

## 贡献指南

我们欢迎所有形式的贡献！

### 如何贡献
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 代码规范
- 前端: ESLint + Prettier
- 后端: Black + Flake8
- 提交信息: 遵循 Conventional Commits

## 故障排除

遇到问题？查看 **[故障排除指南](TROUBLESHOOTING.md)**

常见问题:
- 端口占用
- 依赖安装失败
- 数据库连接错误
- 前端构建失败

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 联系方式

- 项目主页: [GitHub Repository]
- 问题反馈: [GitHub Issues]
- 文档中心: [docs/](docs/README.md)

---

**工业AI算法平台** - 让AI算法触手可及

*最后更新: 2026-03-06*
