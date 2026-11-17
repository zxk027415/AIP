# 前端项目

基于 React + TypeScript + Vite 的工业AI算法平台网页应用前端。

## 🚀 快速开始

### 安装依赖
```bash
npm install
```

### 启动开发服务器
```bash
npm run dev
```

访问: http://localhost:3001

### 构建生产版本
```bash
npm run build
```

### 预览生产构建
```bash
npm run preview
```

## 📦 技术栈

- **React 18** - UI 框架
- **TypeScript** - 类型安全
- **Vite** - 构建工具
- **Ant Design 5** - UI 组件库
- **React Router** - 路由管理
- **Axios** - HTTP 客户端
- **React Flow** - 流程图编辑
- **Zustand** - 状态管理

## 📁 项目结构

```
src/
├── assets/          # 静态资源
├── components/      # 可复用组件
│   ├── FunctionExecutor.tsx
│   ├── FunctionLibrary.tsx
│   ├── MainLayout.tsx
│   ├── MatrixInput.tsx
│   ├── ProtectedRoute.tsx
│   └── VectorInput.tsx
├── pages/           # 页面组件
│   ├── HomePage.tsx
│   ├── LoginPage.tsx
│   ├── RegisterPage.tsx
│   ├── ProfilePage.tsx
│   ├── FunctionLibraryPage.tsx
│   └── SystemStatusPage.tsx
├── services/        # API 服务
│   └── api.ts
├── types/           # TypeScript 类型定义
│   ├── data.ts
│   ├── function.ts
│   ├── plot.ts
│   ├── template.ts
│   ├── validation.ts
│   └── workflow.ts
├── utils/           # 工具函数
├── App.tsx          # 根组件
├── main.tsx         # 入口文件
└── index.css        # 全局样式
```

## 🔧 配置文件

- **vite.config.ts** - Vite 配置
- **tsconfig.json** - TypeScript 配置
- **eslint.config.js** - ESLint 配置
- **.prettierrc** - Prettier 配置
- **.env.development** - 开发环境变量
- **.env.production** - 生产环境变量

## 📝 开发规范

### 代码风格
- 使用 ESLint 进行代码检查
- 使用 Prettier 进行代码格式化
- 遵循 TypeScript 严格模式

### 组件规范
- 使用函数组件和 Hooks
- Props 使用 TypeScript 接口定义
- 组件文件使用 PascalCase 命名

### 目录规范
- `components/` - 可复用的 UI 组件
- `pages/` - 页面级组件
- `services/` - API 调用和业务逻辑
- `types/` - TypeScript 类型定义
- `utils/` - 工具函数和辅助方法

## 🔗 相关文档

- [项目主文档](../README.md)
- [响应式设计指南](../docs/development/RESPONSIVE-DESIGN.md)
- [函数库使用指南](../docs/guides/FUNCTION-LIBRARY-GUIDE.md)
- [用户认证指南](../docs/guides/USER-AUTH-GUIDE.md)

## 🌐 环境变量

### 开发环境 (.env.development)
```
VITE_API_BASE_URL=http://localhost:8000
```

### 生产环境 (.env.production)
```
VITE_API_BASE_URL=https://your-production-api.com
```

## 📦 依赖管理

### 添加依赖
```bash
npm install <package-name>
```

### 更新依赖
```bash
npm update
```

### 清理并重装
```bash
npm run clean-install
# 或手动
rm -rf node_modules package-lock.json
npm install
```

## 🐛 常见问题

### 端口被占用
修改 `vite.config.ts` 中的端口配置，或停止占用 3001 端口的进程。

### 依赖安装失败
1. 删除 `node_modules` 和 `package-lock.json`
2. 清理 npm 缓存: `npm cache clean --force`
3. 重新安装: `npm install`

### 类型错误
确保 TypeScript 版本与项目配置兼容，运行 `npm run type-check` 检查类型。

## 📄 许可证

MIT
