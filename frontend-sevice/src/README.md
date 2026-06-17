# 源代码目录

## 📁 目录结构

```
src/
├── assets/          # 静态资源（图片、字体等）
├── components/      # 可复用组件
├── pages/           # 页面组件
├── services/        # API 服务和业务逻辑
├── types/           # TypeScript 类型定义
├── utils/           # 工具函数
├── App.tsx          # 根组件
├── App.css          # 根组件样式
├── main.tsx         # 应用入口
├── index.css        # 全局样式
└── vite-env.d.ts    # Vite 类型声明
```

## 📦 模块说明

### assets/
存放静态资源文件：
- 图片 (SVG, PNG, JPG)
- 字体文件
- 其他静态资源

### components/
可复用的 UI 组件：
- **FunctionExecutor.tsx** - 函数执行器组件
- **FunctionLibrary.tsx** - AI算法库组件
- **MainLayout.tsx** - 主布局组件
- **MatrixInput.tsx** - 矩阵输入组件
- **ProtectedRoute.tsx** - 路由保护组件
- **VectorInput.tsx** - 向量输入组件

### pages/
页面级组件（路由对应的页面）：
- **HomePage.tsx** - 首页
- **LoginPage.tsx** - 登录页
- **RegisterPage.tsx** - 注册页
- **ProfilePage.tsx** - 用户资料页
- **FunctionLibraryPage.tsx** - AI算法库页面
- **SystemStatusPage.tsx** - 系统状态页

### services/
API 调用和业务逻辑：
- **api.ts** - API 客户端配置和接口定义

### types/
TypeScript 类型定义：
- **data.ts** - 数据类型
- **function.ts** - 函数相关类型
- **plot.ts** - 图表类型
- **template.ts** - 模板类型
- **validation.ts** - 验证类型
- **workflow.ts** - 算法模板类型
- **index.ts** - 类型导出

### utils/
工具函数和辅助方法（待添加）

## 🎨 样式规范

### 全局样式
- `index.css` - 全局样式和 CSS 变量
- `App.css` - 应用级样式

### 组件样式
- 优先使用 Ant Design 组件的内置样式
- 自定义样式使用 CSS Modules 或 styled-components
- 避免使用内联样式

## 🔧 开发指南

### 添加新组件
1. 在 `components/` 创建组件文件
2. 使用 TypeScript 定义 Props 接口
3. 导出组件供其他模块使用

### 添加新页面
1. 在 `pages/` 创建页面组件
2. 在 `App.tsx` 中配置路由
3. 如需保护，使用 `ProtectedRoute` 包装

### 添加 API 接口
1. 在 `services/api.ts` 中定义接口方法
2. 在 `types/` 中定义相关类型
3. 在组件中调用 API 方法

### 添加类型定义
1. 在 `types/` 对应文件中定义类型
2. 在 `types/index.ts` 中导出
3. 在需要的地方导入使用

## 📝 命名规范

### 文件命名
- 组件文件: PascalCase (例如: `UserProfile.tsx`)
- 工具文件: camelCase (例如: `formatDate.ts`)
- 类型文件: camelCase (例如: `user.ts`)

### 变量命名
- 组件: PascalCase
- 函数: camelCase
- 常量: UPPER_SNAKE_CASE
- 接口/类型: PascalCase (以 I 或 T 开头可选)

## 🔗 相关文档

- [前端 README](../README.md)
- [项目主文档](../../README.md)
- [开发文档](../../docs/development/README.md)
