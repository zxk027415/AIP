#!/usr/bin/env python3
# @AI_GENERATED: Kiro v1.0
"""
PV Power Demo 工作流详细执行测试
通过 HTTP API 调用后端，输出每个节点的具体执行结果

使用方法：
1. 启动后端服务: uvicorn main:app --reload --port 8000
2. 运行此脚本: python scripts/test_pv_workflow_detailed.py
"""

import json
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"


def api_call(method: str, endpoint: str, data: dict = None) -> dict:
    """调用 API"""
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    
    if data:
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method=method
        )
    else:
        req = urllib.request.Request(url, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"  HTTP Error {e.code}: {error_body}")
        return {"error": error_body}
    except urllib.error.URLError as e:
        print(f"  URL Error: {e.reason}")
        return {"error": str(e.reason)}
    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
        return {"error": str(e)}


def print_separator(title: str):
    """打印分隔线"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def format_value(value, indent=2):
    """格式化输出值"""
    prefix = "  " * indent
    if isinstance(value, list):
        if len(value) == 0:
            return "[]"
        if len(value) <= 5:
            if all(isinstance(v, (int, float)) for v in value):
                return f"[{', '.join(f'{v:.4f}' if isinstance(v, float) else str(v) for v in value)}]"
            return str(value)
        # 只显示前5项
        sample = value[:5]
        if all(isinstance(v, (int, float)) for v in sample):
            formatted = ', '.join(f'{v:.4f}' if isinstance(v, float) else str(v) for v in sample)
            return f"[{formatted}, ...] (共 {len(value)} 项)"
        return f"{sample[:3]}... (共 {len(value)} 项)"
    elif isinstance(value, dict):
        return f"{{...}} ({len(value)} 个键)"
    elif isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def main():
    print("\n" + "=" * 70)
    print("  光伏发电功率预测工作流 - 详细执行测试 (HTTP API)")
    print("=" * 70)
    
    # 检查后端服务
    print("\n检查后端服务...")
    try:
        health = api_call("GET", "/api/system/test")
        if "error" in health:
            print("❌ 后端服务未启动，请先运行: uvicorn main:app --reload --port 8000")
            return
        print("✅ 后端服务正常")
    except Exception as e:
        print(f"❌ 无法连接后端服务: {e}")
        print("请先启动后端: uvicorn main:app --reload --port 8000")
        return
    
    # 执行工作流
    print_separator("执行工作流: workflow-pv-power-demo")
    
    result = api_call("POST", "/api/workflows/enhanced/workflow-pv-power-demo/execute", {"inputs": {}})
    
    if "error" in result:
        print(f"❌ 执行失败: {result['error']}")
        return
    
    # 解析结果
    workflow_id = result.get('workflow_id', 'N/A')
    status = result.get('status', 'N/A')
    node_results = result.get('node_results', {})
    
    print(f"\n工作流ID: {workflow_id}")
    print(f"执行状态: {status}")
    print(f"节点数量: {len(node_results)}")
    
    # 按节点顺序输出结果
    node_order = [
        ('node-1', '加载光伏数据集', 'load_dataset'),
        ('node-2', '缺失值处理', 'handle_missing'),
        ('node-3', '数据标准化', 'min_max_scale'),
        ('node-4', '数据集划分', 'train_test_split'),
        ('node-5', '线性回归预测', 'linear_regression'),
        ('node-6', 'MAPE评估', 'mape_metric'),
        ('node-7', 'RMSE评估', 'rmse_metric'),
        ('node-8', 'R²评估', 'r2_metric'),
        ('node-9', '预测结果可视化', 'forecast_plot'),
    ]
    
    metrics = {}
    
    for node_id, node_name, func_id in node_order:
        print_separator(f"{node_id}: {node_name} ({func_id})")
        
        node_result = node_results.get(node_id, {})
        node_status = node_result.get('status', 'unknown')
        output = node_result.get('output', {})
        error = node_result.get('error')
        
        print(f"状态: {node_status}")
        
        if error:
            print(f"错误: {error}")
            continue
        
        if not output:
            print("输出: (空)")
            continue
        
        # 根据节点类型格式化输出
        if func_id == 'load_dataset':
            print(f"columns: {output.get('columns', [])}")
            data = output.get('data', [])
            print(f"data: 共 {len(data)} 行")
            if data:
                print(f"  前3行:")
                for i, row in enumerate(data[:3]):
                    print(f"    [{i}] {row[:4]}... ({len(row)} 列)")
            stats = output.get('stats', {})
            if stats:
                print(f"stats: {json.dumps(stats, ensure_ascii=False, indent=2)[:200]}...")
                
        elif func_id in ['handle_missing', 'min_max_scale']:
            print(f"columns: {output.get('columns', [])}")
            data = output.get('data', [])
            print(f"data: 共 {len(data)} 行")
            if data:
                print(f"  前3行 (数值已处理):")
                for i, row in enumerate(data[:3]):
                    formatted = [row[0]] + [f"{v:.4f}" if isinstance(v, float) else v for v in row[1:5]]
                    print(f"    [{i}] {formatted}...")
                    
        elif func_id == 'train_test_split':
            train = output.get('train', {})
            test = output.get('test', {})
            print(f"train: {len(train.get('data', []))} 行, columns={train.get('columns', [])[:3]}...")
            print(f"test: {len(test.get('data', []))} 行")
            print(f"train_size: {output.get('train_size')}")
            print(f"test_size: {output.get('test_size')}")
            
        elif func_id == 'linear_regression':
            print(f"model: {output.get('model')}")
            print(f"n_samples: {output.get('n_samples')}")
            print(f"n_features: {output.get('n_features')}")
            predictions = output.get('predictions', [])
            actuals = output.get('actuals', [])
            print(f"predictions: {format_value(predictions)}")
            print(f"actuals: {format_value(actuals)}")
            weights = output.get('weights', [])
            if weights:
                print(f"weights: [{', '.join(f'{w:.4f}' for w in weights[:5])}...]")
                
        elif func_id == 'mape_metric':
            mape = output.get('mape', 'N/A')
            print(f"MAPE: {mape}%")
            print(f"n_samples: {output.get('n_samples')}")
            print(f"description: {output.get('description')}")
            metrics['MAPE'] = f"{mape}%"
            
        elif func_id == 'rmse_metric':
            rmse = output.get('rmse', 'N/A')
            print(f"RMSE: {rmse} kW")
            print(f"n_samples: {output.get('n_samples')}")
            print(f"description: {output.get('description')}")
            metrics['RMSE'] = f"{rmse} kW"
            
        elif func_id == 'r2_metric':
            r2 = output.get('r2', 'N/A')
            print(f"R²: {r2}")
            print(f"n_samples: {output.get('n_samples')}")
            print(f"description: {output.get('description')}")
            metrics['R²'] = r2
            
        elif func_id == 'forecast_plot':
            print(f"type: {output.get('type')}")
            config = output.get('config', {})
            print(f"title: {config.get('title', {}).get('text')}")
            series = config.get('series', [])
            print(f"series: {len(series)} 个数据系列")
            for s in series:
                data = s.get('data', [])
                print(f"  - {s.get('name')}: {len(data)} 个数据点")
                if data:
                    sample = [f"{d:.2f}" if isinstance(d, float) else d for d in data[:5]]
                    print(f"    前5项: {sample}")
        else:
            # 通用输出
            for key, value in list(output.items())[:10]:
                print(f"{key}: {format_value(value)}")
    
    # 执行总结
    print_separator("执行总结")
    print(f"✅ 工作流执行完成")
    print(f"📊 数据集: 宁夏银川光伏电站 (pv-power-yinchuan)")
    print(f"📈 模型: 线性回归 (简化实现)")
    print(f"📉 评估指标:")
    for name, value in metrics.items():
        print(f"   - {name}: {value}")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
