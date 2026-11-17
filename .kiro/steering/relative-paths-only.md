---
inclusion: always
---

# 路径规范：全项目强制使用相对路径

本项目需要在 macOS 开发机和 Linux 服务器之间部署，**禁止在代码和数据文件中使用绝对路径**。

## 规则

1. **代码中引用文件一律使用相对路径**。
   - 相对于项目根目录（`AIP/`），例如 `fault-diag-algo-release-3.1/相关数据/all_labeled_combined.parquet`
   - 或相对于 `backend-service/`，例如 `data/models/xxx.pkl`、`data/uploads/xxx.csv`

2. **禁止 `os.path.abspath()` 写入持久化结果**。
   - 模型路径、执行历史、会话数据等持久化字段必须存储相对路径。
   - 使用 `os.path.relpath(path, start=backend_service_dir)` 代替 `os.path.abspath(path)`。

3. **后端路径解析约定**：
   - `backend-service/api/iterative_labeling.py` 中已有 `_resolve_data_path(path)` 工具函数。
   - 其他模块如需解析用户传入的路径，优先复用 `load_csv` 算子内置的相对路径搜索逻辑（搜索 project_root → backend_dir → cwd）。
   - 项目根目录的计算方式：`backend-service/` 的父目录。

4. **前端传路径给后端时**：
   - 只传相对路径（相对于项目根）。
   - 示例：`fault-diag-algo-release-3.1/enos_fault_diag/test/predict_small.parquet`
   - 不传 `/Users/xxx/Desktop/project/AIP/...` 这样的绝对路径。

5. **工作流模板 JSON 中的 `file_path`**：
   - 使用 `../` 前缀表示项目根下的文件（因为工作流执行时 CWD 是 `backend-service/`）。
   - 示例：`../fault-diag-algo-release-3.1/相关数据/all_labeled_combined.parquet`
   - 或使用纯相对路径，`load_csv` 算子会自动在多个目录中搜索。

6. **数据文件存储位置约定**：
   - 模型产物 → `backend-service/data/models/`
   - 上传文件 → `backend-service/data/uploads/`
   - 迭代标注 → `backend-service/data/iterative_labeling/`
   - 外部数据集 → 项目根下的独立目录（如 `fault-diag-algo-release-3.1/`）

## 已知的路径解析入口

| 模块 | 函数/位置 | 作用 |
|------|-----------|------|
| `backend-service/api/iterative_labeling.py` | `_resolve_data_path(path)` | 相对于项目根解析，兼容旧绝对路径 |
| `backend-service/services/operator_backends/load_csv.py` | `execute()` 内部搜索逻辑 | 搜索 workspace_root → aip_dir → backend_dir → cwd |
| `backend-service/services/operator_backends/stratified_cv_eval.py` | 模型保存 | 使用 `os.path.relpath` 输出相对路径 |

## 违反示例（不要这样做）

```python
# BAD: 绝对路径写入持久化
result["model_path"] = os.path.abspath(model_path)

# BAD: 前端硬编码绝对路径
const trainPath = '/Users/zxk/Desktop/project/AIP/fault-diag-algo-release-3.1/...'

# BAD: 数据 JSON 中存绝对路径
"source_csv_path": "/Users/zxk/Desktop/project/AIP/backend-service/data/..."
```

## 正确示例

```python
# GOOD: 相对路径写入持久化
result["model_path"] = os.path.relpath(model_path, start=backend_service_dir)

# GOOD: 前端使用相对路径
const trainPath = 'fault-diag-algo-release-3.1/相关数据/all_labeled_combined.parquet'

# GOOD: 数据 JSON 中存相对路径
"source_csv_path": "fault-diag-algo-release-3.1/enos_fault_diag/test/predict_small.parquet"
```
