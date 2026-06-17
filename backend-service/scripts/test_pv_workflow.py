# @AI_GENERATED: Kiro v1.0
"""
测试光伏发电功率预测工作流的真实执行

运行方式：
    cd backend
    python scripts/test_pv_workflow.py
"""
import os
import sys
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.pv_execution_service import PVExecutionService


def test_pv_workflow():
    """测试光伏预测工作流执行"""
    print("=" * 60)
    print("光伏发电功率预测工作流测试")
    print("=" * 60)
    
    service = PVExecutionService()
    
    # 步骤1: 加载数据
    print("\n[步骤1] 加载光伏示例数据...")
    data = service.execute_function('load_pv_demo', {}, {})
    print(f"  ✅ 加载成功: {data['rows']} 行, {data['cols']} 列")
    print(f"  列名: {data['columns']}")
    print(f"  前3行数据: {data['data'][:3]}")
    
    # 步骤2: 缺失值处理
    print("\n[步骤2] 缺失值处理...")
    processed = service.execute_function('handle_missing', {'method': 'interpolate'}, {'data': data})
    print(f"  ✅ 处理完成: 填充了 {processed.get('missing_filled', 0)} 个缺失值")
    
    # 步骤3: Z-Score标准化
    print("\n[步骤3] Z-Score标准化...")
    scaled = service.execute_function('z_score_scale', {}, {'data': processed})
    print(f"  ✅ 标准化完成")
    print(f"  均值: {list(scaled.get('means', {}).values())[:3]}...")
    print(f"  标准差: {list(scaled.get('stds', {}).values())[:3]}...")
    
    # 步骤4: XGBoost预测
    print("\n[步骤4] XGBoost预测...")
    # 使用原始数据进行预测（标准化数据用于特征，但预测目标用原始值）
    prediction = service.execute_function('xgboost_forecast', {'forecast_horizon': 4}, {'train_data': processed})
    print(f"  ✅ 预测完成")
    print(f"  模型: {prediction.get('model')}")
    print(f"  样本数: {prediction.get('n_samples')}")
    print(f"  特征数: {prediction.get('n_features')}")
    print(f"  预测值前5个: {prediction.get('predictions', [])[:5]}")
    print(f"  实际值前5个: {prediction.get('actuals', [])[:5]}")
    
    # 步骤5: MAPE评估
    print("\n[步骤5] MAPE评估...")
    mape = service.execute_function('mape_metric', {}, {'y_true': prediction})
    print(f"  ✅ {mape.get('description')}")
    
    # 步骤6: RMSE评估
    print("\n[步骤6] RMSE评估...")
    rmse = service.execute_function('rmse_metric', {}, {'y_true': prediction})
    print(f"  ✅ {rmse.get('description')}")
    
    # 步骤7: R²评估
    print("\n[步骤7] R²评估...")
    r2 = service.execute_function('r2_metric', {}, {'y_true': prediction})
    print(f"  ✅ {r2.get('description')}")
    
    # 步骤8: 生成可视化配置
    print("\n[步骤8] 生成可视化配置...")
    plot = service.execute_function('forecast_plot', {'title': '光伏功率预测结果'}, {'actual': prediction})
    print(f"  ✅ 图表类型: {plot.get('type')}")
    print(f"  数据点数: {len(plot.get('data', {}).get('actual', []))}")
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("执行结果汇总")
    print("=" * 60)
    print(f"  数据集: 宁夏银川光伏电站 2025年1月1日数据")
    print(f"  数据量: {data['rows']} 条记录 (15分钟间隔)")
    print(f"  模型: XGBoost (简化线性回归实现)")
    print(f"  MAPE: {mape.get('mape'):.2f}%")
    print(f"  RMSE: {rmse.get('rmse'):.2f} kW")
    print(f"  R²: {r2.get('r2'):.4f}")
    print("=" * 60)
    
    return {
        'success': True,
        'mape': mape.get('mape'),
        'rmse': rmse.get('rmse'),
        'r2': r2.get('r2'),
        'n_samples': prediction.get('n_samples')
    }


def test_workflow_api_format():
    """测试工作流API格式的执行"""
    print("\n" + "=" * 60)
    print("测试工作流API格式执行")
    print("=" * 60)
    
    # 加载工作流定义
    workflow_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'data', 'workflows_enhanced', 'workflow-pv-power-demo.json'
    )
    
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    
    print(f"\n工作流: {workflow['name']}")
    print(f"节点数: {len(workflow['nodes'])}")
    print(f"连接数: {len(workflow['edges'])}")
    
    # 模拟API执行逻辑
    import networkx as nx
    from services.pv_execution_service import PVExecutionService
    
    service = PVExecutionService()
    nodes = workflow['nodes']
    edges = workflow['edges']
    
    # 构建执行图
    G = nx.DiGraph()
    for node in nodes:
        G.add_node(node['id'])
    for edge in edges:
        G.add_edge(edge['source'], edge['target'])
    
    execution_order = list(nx.topological_sort(G))
    print(f"\n执行顺序: {execution_order}")
    
    # 执行节点
    node_outputs = {}
    
    for node_id in execution_order:
        node = next((n for n in nodes if n['id'] == node_id), None)
        if not node:
            continue
        
        label = node['data']['label']
        config = node['data']['config']
        function_id = config.get('functionId')
        
        # 收集输入
        inputs = {}
        for edge in edges:
            if edge['target'] == node_id:
                source_output = node_outputs.get(edge['source'])
                if source_output is not None:
                    target_handle = edge.get('targetHandle', 'data')
                    port_name = target_handle.split('-')[-1] if '-' in target_handle else target_handle
                    inputs[port_name] = source_output
        
        print(f"\n执行节点: {label} ({function_id})")
        
        try:
            output = service.execute_function(function_id, config, inputs)
            node_outputs[node_id] = output
            
            # 显示输出摘要
            if isinstance(output, dict):
                if 'mape' in output:
                    print(f"  结果: MAPE = {output['mape']:.2f}%")
                elif 'rmse' in output:
                    print(f"  结果: RMSE = {output['rmse']:.2f} kW")
                elif 'r2' in output:
                    print(f"  结果: R² = {output['r2']:.4f}")
                elif 'rows' in output:
                    print(f"  结果: {output['rows']} 行数据")
                elif 'predictions' in output:
                    print(f"  结果: {len(output['predictions'])} 个预测值")
                elif 'type' in output and output['type'] == 'echarts':
                    print(f"  结果: ECharts图表配置")
                else:
                    print(f"  结果: {list(output.keys())}")
            
            print(f"  ✅ 成功")
            
        except Exception as e:
            print(f"  ❌ 失败: {str(e)}")
            raise
    
    print("\n" + "=" * 60)
    print("工作流API格式执行测试完成")
    print("=" * 60)


if __name__ == '__main__':
    # 运行基础测试
    result = test_pv_workflow()
    
    # 运行API格式测试
    test_workflow_api_format()
    
    print("\n✅ 所有测试通过！")
# @AI_GENERATED: end
