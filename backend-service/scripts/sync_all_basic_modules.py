# @AI_GENERATED: Kiro v1.0
"""
将 basicModuleFunctions.ts 中的 763 个基础算法模块全部同步到 functions.json
保留已有函数的详细参数定义，新增函数自动生成合理参数。
"""
import json
import re
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FUNCTIONS_JSON = os.path.join(SCRIPT_DIR, '..', 'data', 'functions.json')
BASIC_MODULES_TS = os.path.join(SCRIPT_DIR, '..', '..', 'frontend', 'src', 'data', 'basicModuleFunctions.ts')
CATEGORIES_TS = os.path.join(SCRIPT_DIR, '..', '..', 'frontend', 'src', 'data', 'basicModuleCategories.ts')


def parse_basic_module_functions(ts_path: str) -> dict:
    """解析 basicModuleFunctions.ts，提取所有函数"""
    with open(ts_path, 'r', encoding='utf-8') as f:
        content = f.read()

    result = {}

    # 找到 BASIC_MODULE_FUNCTIONS 对象的内容
    start = content.find('const BASIC_MODULE_FUNCTIONS')
    if start == -1:
        raise ValueError("Cannot find BASIC_MODULE_FUNCTIONS")

    text = content[start:]

    # 策略：逐行扫描，跟踪当前 category
    current_category = None
    # 匹配顶层 category key: xxx: [
    cat_re = re.compile(r"^  (\w+):\s*\[")
    # 匹配函数条目 — 支持单引号和双引号
    func_re = re.compile(r"""id:\s*'([^']+)'\s*,\s*name:\s*(?:'([^']+)'|"([^"]+)")\s*,\s*description:\s*'([^']*)'""")

    for line in text.split('\n'):
        cat_m = cat_re.match(line)
        if cat_m:
            current_category = cat_m.group(1)
            if current_category not in result:
                result[current_category] = []
            continue

        if current_category:
            func_m = func_re.search(line)
            if func_m:
                fid = func_m.group(1)
                fname = func_m.group(2) or func_m.group(3)  # 单引号或双引号
                fdesc = func_m.group(4)
                result[current_category].append((fid, fname, fdesc))

    return result


def parse_categories(ts_path: str) -> list:
    """解析 basicModuleCategories.ts，提取所有分类"""
    with open(ts_path, 'r', encoding='utf-8') as f:
        content = f.read()

    categories = []
    # 匹配 { id: '...', name: '...', ... description: '...', ... }
    cat_pattern = re.compile(
        r"\{\s*id:\s*'(\w+)'\s*,\s*name:\s*'([^']+)'\s*,\s*icon:\s*'[^']*'\s*,\s*description:\s*'([^']+)'",
        re.DOTALL
    )

    for m in cat_pattern.finditer(content):
        categories.append({
            "id": m.group(1),
            "name": m.group(2),
            "description": m.group(3),
            "subcategories": []
        })

    return categories


# 根据分类和描述推断合理的默认参数
CATEGORY_DEFAULT_PARAMS = {
    'data_source': [
        {"name": "source", "type": "STRING", "required": True, "description": "数据源路径或连接字符串"},
        {"name": "options", "type": "STRING", "required": False, "description": "附加选项(JSON)", "default": "{}"},
    ],
    'data_preprocessing': [
        {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
        {"name": "options", "type": "STRING", "required": False, "description": "处理参数(JSON)", "default": "{}"},
    ],
    'feature_engineering': [
        {"name": "data", "type": "MATRIX", "required": True, "description": "输入特征矩阵"},
        {"name": "options", "type": "STRING", "required": False, "description": "特征工程参数(JSON)", "default": "{}"},
    ],
    'ts_forecast': [
        {"name": "train_data", "type": "ARRAY", "required": True, "description": "训练数据"},
        {"name": "forecast_steps", "type": "NUMBER", "required": True, "description": "预测步数"},
        {"name": "options", "type": "STRING", "required": False, "description": "模型参数(JSON)", "default": "{}"},
    ],
    'anomaly_detection': [
        {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
        {"name": "threshold", "type": "NUMBER", "required": False, "description": "检测阈值", "default": 3.0},
    ],
    'classification': [
        {"name": "train_data", "type": "MATRIX", "required": True, "description": "训练特征矩阵"},
        {"name": "labels", "type": "ARRAY", "required": True, "description": "标签数组"},
        {"name": "options", "type": "STRING", "required": False, "description": "模型参数(JSON)", "default": "{}"},
    ],
    'regression': [
        {"name": "X", "type": "MATRIX", "required": True, "description": "特征矩阵"},
        {"name": "y", "type": "ARRAY", "required": True, "description": "目标变量"},
        {"name": "options", "type": "STRING", "required": False, "description": "模型参数(JSON)", "default": "{}"},
    ],
    'clustering': [
        {"name": "data", "type": "MATRIX", "required": True, "description": "输入数据矩阵"},
        {"name": "n_clusters", "type": "NUMBER", "required": False, "description": "聚类数", "default": 3},
    ],
    'deep_learning': [
        {"name": "train_data", "type": "MATRIX", "required": True, "description": "训练数据"},
        {"name": "labels", "type": "ARRAY", "required": False, "description": "标签(监督学习时)"},
        {"name": "epochs", "type": "NUMBER", "required": False, "description": "训练轮数", "default": 100},
        {"name": "options", "type": "STRING", "required": False, "description": "模型参数(JSON)", "default": "{}"},
    ],
    'industrial_vision': [
        {"name": "image", "type": "MATRIX", "required": True, "description": "输入图像数据"},
        {"name": "options", "type": "STRING", "required": False, "description": "处理参数(JSON)", "default": "{}"},
    ],
    'signal_processing': [
        {"name": "signal", "type": "ARRAY", "required": True, "description": "输入信号数据"},
        {"name": "sample_rate", "type": "NUMBER", "required": False, "description": "采样率(Hz)", "default": 1000},
        {"name": "options", "type": "STRING", "required": False, "description": "处理参数(JSON)", "default": "{}"},
    ],
    'optimization': [
        {"name": "objective", "type": "STRING", "required": True, "description": "目标函数或问题描述"},
        {"name": "constraints", "type": "STRING", "required": False, "description": "约束条件(JSON)", "default": "{}"},
        {"name": "options", "type": "STRING", "required": False, "description": "优化参数(JSON)", "default": "{}"},
    ],
    'math_statistics': [
        {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
        {"name": "options", "type": "STRING", "required": False, "description": "计算参数(JSON)", "default": "{}"},
    ],
    'model_training': [
        {"name": "model", "type": "STRING", "required": True, "description": "模型标识或配置"},
        {"name": "train_data", "type": "MATRIX", "required": True, "description": "训练数据"},
        {"name": "options", "type": "STRING", "required": False, "description": "训练参数(JSON)", "default": "{}"},
    ],
    'model_deployment': [
        {"name": "model_path", "type": "STRING", "required": True, "description": "模型路径或标识"},
        {"name": "options", "type": "STRING", "required": False, "description": "部署参数(JSON)", "default": "{}"},
    ],
    'evaluation_metrics': [
        {"name": "y_true", "type": "ARRAY", "required": True, "description": "真实值"},
        {"name": "y_pred", "type": "ARRAY", "required": True, "description": "预测值"},
    ],
    'visualization': [
        {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
        {"name": "chart_type", "type": "STRING", "required": False, "description": "图表类型", "default": "line"},
        {"name": "options", "type": "STRING", "required": False, "description": "可视化参数(JSON)", "default": "{}"},
    ],
    'data_output': [
        {"name": "data", "type": "ARRAY", "required": True, "description": "输出数据"},
        {"name": "target", "type": "STRING", "required": True, "description": "输出目标路径或连接"},
        {"name": "options", "type": "STRING", "required": False, "description": "输出参数(JSON)", "default": "{}"},
    ],
}

CATEGORY_RETURN_TYPES = {
    'data_source': 'ARRAY',
    'data_preprocessing': 'ARRAY',
    'feature_engineering': 'MATRIX',
    'ts_forecast': 'ARRAY',
    'anomaly_detection': 'ARRAY',
    'classification': 'ARRAY',
    'regression': 'ARRAY',
    'clustering': 'ARRAY',
    'deep_learning': 'MATRIX',
    'industrial_vision': 'MATRIX',
    'signal_processing': 'ARRAY',
    'optimization': 'ARRAY',
    'math_statistics': 'ARRAY',
    'model_training': 'STRING',
    'model_deployment': 'STRING',
    'evaluation_metrics': 'NUMBER',
    'visualization': 'STRING',
    'data_output': 'STRING',
}


def main():
    # 1. 读取现有 functions.json
    with open(FUNCTIONS_JSON, 'r', encoding='utf-8') as f:
        existing = json.load(f)

    existing_funcs = {fn['id']: fn for fn in existing.get('functions', [])}
    print(f"现有 functions.json: {len(existing_funcs)} 个函数, {len(existing.get('categories', []))} 个分类")

    # 2. 解析 basicModuleFunctions.ts
    all_modules = parse_basic_module_functions(BASIC_MODULES_TS)
    total_ts = sum(len(funcs) for funcs in all_modules.values())
    print(f"basicModuleFunctions.ts: {total_ts} 个函数, {len(all_modules)} 个分类")

    # 3. 解析 basicModuleCategories.ts
    new_categories = parse_categories(CATEGORIES_TS)
    print(f"basicModuleCategories.ts: {len(new_categories)} 个分类")

    # 4. 构建新的 functions 列表
    new_functions = []
    kept = 0
    added = 0

    for cat_id, funcs in all_modules.items():
        for fid, fname, fdesc in funcs:
            if fid in existing_funcs:
                # 保留已有的详细定义，但更新 category 如果需要
                fn = existing_funcs[fid].copy()
                # 如果原来的 category 是 algorithm_model，映射到更精确的分类
                if fn.get('category') == 'algorithm_model' and cat_id != 'algorithm_model':
                    fn['category'] = cat_id
                elif fn.get('category') not in [c['id'] for c in new_categories]:
                    fn['category'] = cat_id
                new_functions.append(fn)
                kept += 1
            else:
                # 新增函数，使用默认参数
                params = CATEGORY_DEFAULT_PARAMS.get(cat_id, [
                    {"name": "data", "type": "ARRAY", "required": True, "description": "输入数据"},
                ])
                ret_type = CATEGORY_RETURN_TYPES.get(cat_id, 'ARRAY')
                new_fn = {
                    "id": fid,
                    "name": fname,
                    "category": cat_id,
                    "description": fdesc,
                    "parameters": [p.copy() for p in params],
                    "return_type": ret_type,
                    "examples": [f"result = {fid}(...)"]
                }
                new_functions.append(new_fn)
                added += 1

    # 5. 检查 existing 中有但 ts 中没有的函数（保留它们）
    ts_ids = set()
    for funcs in all_modules.values():
        for fid, _, _ in funcs:
            ts_ids.add(fid)

    orphaned = 0
    for fid, fn in existing_funcs.items():
        if fid not in ts_ids:
            new_functions.append(fn)
            orphaned += 1

    print(f"\n结果: 保留 {kept} + 新增 {added} + 孤立 {orphaned} = {len(new_functions)} 个函数")

    # 6. 去重（以 id 为准）
    seen = set()
    deduped = []
    for fn in new_functions:
        if fn['id'] not in seen:
            seen.add(fn['id'])
            deduped.append(fn)
    new_functions = deduped
    print(f"去重后: {len(new_functions)} 个函数")

    # 7. 写入 functions.json
    output = {
        "categories": new_categories,
        "functions": new_functions
    }

    with open(FUNCTIONS_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已写入 {FUNCTIONS_JSON}")
    print(f"   分类: {len(new_categories)} 个")
    print(f"   函数: {len(new_functions)} 个")

    # 8. 按分类统计
    cat_counts = {}
    for fn in new_functions:
        cat = fn.get('category', 'unknown')
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    print("\n按分类统计:")
    for cat_id, count in sorted(cat_counts.items()):
        cat_name = next((c['name'] for c in new_categories if c['id'] == cat_id), cat_id)
        print(f"  {cat_name} ({cat_id}): {count}")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
