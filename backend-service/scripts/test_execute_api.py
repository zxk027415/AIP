# @AI_GENERATED: Kiro v1.0
"""
测试工作流执行 API

运行方式：
    cd backend
    python scripts/test_execute_api.py
    python scripts/test_execute_api.py kaggle  # 测试 Kaggle 太阳能工作流
"""
import sys
import os
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_execute_api(workflow_id='workflow-pv-power-demo'):
    """测试执行 API 的核心逻辑"""
    from api.workflows_enhanced import load_workflow_from_file
    from services.pv_execution_service import PVExecutionService
    from services.kaggle_solar_execution_service import KaggleSolarExecutionService
    import networkx as nx
    import time
    
    print("=" * 60)
    print(f"测试工作流执行 API: {workflow_id}")
    print("=" * 60)
    
    # 1. 加载工作流
    print("\n1. 加载工作流...")
    workflow = load_workflow_from_file(workflow_id)
    if workflow is None:
        print(f"❌ 工作流不存在: {workflow_id}")
        return False
    
    print(f"   工作流名称: {workflow.name}")
    print(f"   节点数: {len(workflow.nodes)}")
    print(f"   连接数: {len(workflow.edges)}")
    
    # 2. 初始化执行服务
    print("\n2. 初始化执行服务...")
    pv_service = PVExecutionService()
    kaggle_service = KaggleSolarExecutionService()
    
    # Kaggle 太阳能相关函数列表
    kaggle_functions = [
        'load_kaggle_solar', 'data_exploration', 'feature_engineering',
        'train_test_split_ml', 'linear_regression_train', 'random_forest_train',
        'gradient_boosting_train', 'evaluate_regression', 
        'prediction_scatter_plot', 'feature_importance_plot'
    ]
    print("   ✅ 服务初始化成功")
    
    # 3. 构建执行图
    print("\n3. 构建执行图...")
    nodes = workflow.nodes
    edges = workflow.edges
    
    G = nx.DiGraph()
    for node in nodes:
        G.add_node(node.id)
    for edge in edges:
        G.add_edge(edge.source, edge.target)
    
    execution_order = list(nx.topological_sort(G))
    print(f"   执行顺序: {execution_order}")
    
    # 4. 执行节点
    print("\n4. 开始执行节点...")
    start_time = time.time()
    node_outputs = {}
    node_results = {}
    
    for node_id in execution_order:
        node = next((n for n in nodes if n.id == node_id), None)
        if not node:
            continue
        
        node_start = time.time()
        node_label = node.data.label
        
        try:
            # 收集输入数据
            inputs = {}
            for edge in edges:
                if edge.target == node_id:
                    source_output = node_outputs.get(edge.source)
                    if source_output is not None:
                        target_handle = edge.targetHandle or 'data'
                        port_name = target_handle.split('-')[-1] if '-' in target_handle else target_handle
                        inputs[port_name] = source_output
            
            # 获取函数ID和配置
            config = node.data.config.dict() if hasattr(node.data.config, 'dict') else dict(node.data.config)
            function_id = config.get('functionId')
            
            if not function_id:
                raise ValueError(f"节点 {node_label} 缺少 functionId")
            
            print(f"\n   执行: {node_label} (functionId={function_id})")
            
            # 根据 functionId 选择执行服务
            if function_id in kaggle_functions:
                output = kaggle_service.execute_function(function_id, config, inputs)
            else:
                output = pv_service.execute_function(function_id, config, inputs)
            node_outputs[node_id] = output
            
            # 记录结果摘要
            output_summary = {}
            if isinstance(output, dict):
                for k, v in output.items():
                    if isinstance(v, (int, float, str, bool)):
                        output_summary[k] = v
                    elif isinstance(v, list):
                        output_summary[k] = f"list[{len(v)}]"
                    elif isinstance(v, dict):
                        output_summary[k] = f"dict[{len(v)}]"
            
            node_results[node_id] = {
                "status": "success",
                "outputSummary": output_summary,
                "executionTime": time.time() - node_start
            }
            
            print(f"      ✅ 成功 ({time.time() - node_start:.3f}s)")
            print(f"      输出: {output_summary}")
            
        except Exception as e:
            print(f"      ❌ 失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    total_time = time.time() - start_time
    
    # 5. 汇总结果
    print("\n" + "=" * 60)
    print("执行结果汇总")
    print("=" * 60)
    print(f"   总耗时: {total_time:.3f}s")
    print(f"   成功节点: {len(node_results)}/{len(nodes)}")
    
    # 显示评估指标
    for node_id, result in node_results.items():
        summary = result.get('outputSummary', {})
        if 'mape' in summary:
            print(f"   MAPE: {summary['mape']}%")
        if 'rmse' in summary:
            print(f"   RMSE: {summary['rmse']} kW")
        if 'r2' in summary:
            print(f"   R²: {summary['r2']}")
        # Kaggle 模型评估指标
        if 'train_r2' in summary:
            print(f"   训练集 R²: {summary['train_r2']}")
        if 'test_r2' in summary:
            print(f"   测试集 R²: {summary['test_r2']}")
    
    print("\n✅ 工作流执行测试通过!")
    return True


if __name__ == '__main__':
    # 支持命令行参数选择工作流
    if len(sys.argv) > 1 and sys.argv[1] == 'kaggle':
        workflow_id = 'workflow-kaggle-solar-ml'
    else:
        workflow_id = 'workflow-pv-power-demo'
    
    success = test_execute_api(workflow_id)
    sys.exit(0 if success else 1)
# @AI_GENERATED: end
