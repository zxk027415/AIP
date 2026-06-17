# 后端项目

基于 FastAPI + Python 的工业AI算法平台网页应用后端。

## 🚀 快速开始

### 创建环境
```bash
conda create -n aip_web python=3.10 -y
conda activate aip_web
```

### 安装依赖
```bash
pip install -r requirements.txt
```

### 初始化数据库
```bash
python create_db.py
```

### 启动服务
```bash
uvicorn main:app --reload --port 8080
```

或使用启动脚本：
```bash
start-kiro.bat
```

访问：
- API: http://localhost:8080
- 文档: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

## 📦 技术栈

- **FastAPI** - 现代 Web 框架
- **Uvicorn** - ASGI 服务器
- **SQLAlchemy** - ORM 数据库
- **Pydantic** - 数据验证
- **NumPy** - 数值计算
- **SciPy** - 科学计算
- **Passlib** - 密码哈希
- **Python-JOSE** - JWT 认证
- **Pytest** - 测试框架

## 📁 项目结构

```
backend/
├── api/                 # API 路由
│   ├── __init__.py
│   ├── auth.py         # 认证接口
│   ├── functions.py    # 函数库接口
│   └── matrix.py       # 矩阵计算接口
├── models/              # 数据模型
│   ├── __init__.py
│   ├── user.py         # 用户模型
│   ├── function.py     # 函数模型
│   ├── matrix.py       # 矩阵模型
│   ├── execution.py    # 执行记录
│   ├── workflow.py     # 算法模板模型
│   └── validation.py   # 验证模型
├── services/            # 业务逻辑
│   ├── __init__.py
│   ├── auth_service.py              # 认证服务
│   ├── function_library_service.py  # 函数库服务
│   └── matrix_service.py            # 矩阵服务
├── tests/               # 测试文件
│   ├── __init__.py
│   ├── README.md
│   ├── test_matrix_service.py
│   ├── test_matrix_properties.py
│   └── test_matrix_broadcast.py
├── scripts/             # 辅助脚本
│   ├── setup/          # 安装脚本
│   ├── debug/          # 调试脚本
│   └── run-tests.bat   # 测试脚本
├── data/                # 数据文件
│   ├── functions.json  # 函数库数据
│   └── users.db        # 用户数据库
├── utils/               # 工具函数
│   └── __init__.py
├── main.py              # 应用入口
├── database.py          # 数据库配置
├── create_db.py         # 数据库初始化
├── requirements.txt     # 依赖列表
├── environment.yml      # Conda 环境
├── pytest.ini           # Pytest 配置
├── .env.example         # 环境变量示例
└── start-kiro.bat       # 启动脚本
```

## 🔧 配置文件

### 环境变量 (.env)
```bash
# 数据库
DATABASE_URL=sqlite:///./data/users.db

# JWT 密钥
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### Conda 环境 (environment.yml)
```yaml
name: aip_web
dependencies:
  - python=3.10
  - pip
  - pip:
    - -r requirements.txt
```

## 📝 API 端点

### 认证 (/api/auth)
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/me` - 获取当前用户
- `PUT /api/auth/me` - 更新用户信息

### 矩阵计算 (/api/matrix)
- `POST /api/matrix/add` - 矩阵加法
- `POST /api/matrix/multiply` - 矩阵乘法
- `POST /api/matrix/transpose` - 矩阵转置
- `POST /api/matrix/inverse` - 矩阵求逆
- `POST /api/matrix/determinant` - 计算行列式
- `POST /api/matrix/eigenvalues` - 计算特征值

### 函数库 (/api/functions)
- `GET /api/functions` - 获取函数列表
- `POST /api/functions/execute` - 执行函数
- `GET /api/functions/{id}` - 获取函数详情

## 🧪 测试

### 运行所有测试
```bash
pytest
```

### 运行特定测试
```bash
pytest tests/test_matrix_service.py
```

### 查看测试覆盖率
```bash
pytest --cov=. --cov-report=html
```

### 使用脚本运行
```bash
scripts\run-tests.bat
```

## 🛠️ 开发工具

### 调试脚本 (scripts/debug/)
- `debug_user.py` - 调试用户数据
- `test_password.py` - 测试密码哈希
- `test_imports.py` - 测试导入
- `verify_hash.py` - 验证密码哈希

### 安装脚本 (scripts/setup/)
- `install-auth-deps.bat` - 安装认证依赖
- `install-test-deps.bat` - 安装测试依赖

## 📊 数据库

### 初始化数据库
```bash
python create_db.py
```

### 数据库位置
- SQLite: `data/users.db`

### 数据模型
- User - 用户表
- Function - 函数表
- Execution - 执行记录表

## 🔐 安全

### 密码哈希
使用 bcrypt 进行密码哈希：
```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```

### JWT 认证
使用 python-jose 生成和验证 JWT：
```python
from jose import JWTError, jwt
```

### CORS 配置
在 `main.py` 中配置允许的源：
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 🐛 常见问题

### 端口被占用
修改启动命令中的端口：
```bash
uvicorn main:app --reload --port 8001
```

### 数据库锁定
关闭所有使用数据库的进程，或删除 `data/users.db` 重新初始化。

### 导入错误
确保在项目根目录运行，或设置 PYTHONPATH：
```bash
set PYTHONPATH=%CD%
```

## 🔗 相关文档

- [项目主文档](../README.md)
- [API 文档](http://localhost:8080/docs) - 启动服务后访问
- [用户认证指南](../docs/guides/USER-AUTH-GUIDE.md)
- [测试文档](tests/README.md)

## 📄 许可证

MIT
