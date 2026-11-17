"""
算法模板执行服务

该服务负责执行算法模板，包括：
1. 拓扑排序计算执行顺序
2. 按顺序执行节点
3. 收集和传递节点输入输出
4. 错误处理和状态跟踪
"""
import networkx as nx
from typing import Dict, Any, List, Optional
from datetime import datetime
import time
import os


class ExecutionService:
    """算法模板执行服务"""
    
    def __init__(self, function_library_service=None, matrix_service=None):
        """
        初始化执行服务
        
        Args:
            function_library_service: 函数库服务实例
            matrix_service: 矩阵服务实例
        """
        self.function_library = function_library_service
        self.matrix_service = matrix_service
    
    def execute_workflow(self, workflow: Dict, user_id: int) -> Dict:
        """
        执行算法模板（同步版本）
        
        Args:
            workflow: 算法模板定义，包含nodes和edges
            user_id: 用户ID
            
        Returns:
            Dict: 执行结果，包含status、nodeResults等
        """
        # 1. 计算拓扑排序
        try:
            execution_order = self._get_execution_order(workflow)
        except Exception as e:
            return {
                'status': 'failed',
                'error': f'无法计算执行顺序: {str(e)}',
                'startTime': datetime.now().isoformat(),
                'endTime': datetime.now().isoformat(),
                'nodeResults': {}
            }
        
        # 2. 初始化执行状态
        node_results = {}
        execution_data = {
            'status': 'running',
            'nodeResults': {},
            'startTime': datetime.now().isoformat()
        }
        
        try:
            # 3. 按拓扑顺序执行节点
            for node_id in execution_order:
                node = self._get_node_by_id(workflow, node_id)
                
                if not node:
                    raise ValueError(f'节点 {node_id} 不存在')
                
                # 更新节点状态为运行中
                execution_data['nodeResults'][node_id] = {
                    'nodeId': node_id,
                    'status': 'running',
                    'startTime': datetime.now().isoformat(),
                    'executionTime': 0
                }
                
                # 收集输入数据
                inputs = self._collect_node_inputs(
                    workflow, node_id, node_results
                )
                
                # 执行节点
                start_time = time.time()
                try:
                    output = self._execute_node(node, inputs)
                    node_results[node_id] = output
                    
                    execution_data['nodeResults'][node_id] = {
                        'nodeId': node_id,
                        'status': 'completed',
                        'output': output,
                        'executionTime': time.time() - start_time
                    }
                except Exception as e:
                    # 节点执行失败
                    execution_data['nodeResults'][node_id] = {
                        'nodeId': node_id,
                        'status': 'failed',
                        'error': str(e),
                        'executionTime': time.time() - start_time
                    }
                    raise
            
            # 4. 执行成功
            execution_data['status'] = 'completed'
            execution_data['endTime'] = datetime.now().isoformat()
            
        except Exception as e:
            # 执行失败
            execution_data['status'] = 'failed'
            execution_data['error'] = str(e)
            execution_data['endTime'] = datetime.now().isoformat()
        
        return execution_data
    
    def _get_execution_order(self, workflow: Dict) -> List[str]:
        """
        使用拓扑排序计算执行顺序
        
        Args:
            workflow: 算法模板定义
            
        Returns:
            List[str]: 节点ID的执行顺序列表
            
        Raises:
            ValueError: 如果算法模板包含环
        """
        nodes = workflow.get('nodes', [])
        edges = workflow.get('edges', [])
        
        if not nodes:
            return []
        
        G = nx.DiGraph()
        
        # 添加节点
        for node in nodes:
            G.add_node(node['id'])
        
        # 添加边
        for edge in edges:
            G.add_edge(edge['source'], edge['target'])
        
        # 拓扑排序
        try:
            return list(nx.topological_sort(G))
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            raise ValueError('算法模板包含循环依赖，无法执行')
    
    def _get_node_by_id(self, workflow: Dict, node_id: str) -> Optional[Dict]:
        """
        根据ID获取节点
        
        Args:
            workflow: 算法模板定义
            node_id: 节点ID
            
        Returns:
            Optional[Dict]: 节点定义，如果不存在则返回None
        """
        nodes = workflow.get('nodes', [])
        return next(
            (node for node in nodes if node['id'] == node_id),
            None
        )
    
    def _collect_node_inputs(
        self, 
        workflow: Dict, 
        node_id: str, 
        node_results: Dict
    ) -> Dict[str, Any]:
        """
        收集节点的输入数据
        
        Args:
            workflow: 算法模板定义
            node_id: 目标节点ID
            node_results: 已执行节点的结果字典
            
        Returns:
            Dict[str, Any]: 输入数据字典，key为端口ID，value为数据
        """
        edges = workflow.get('edges', [])
        inputs = {}
        
        # 查找所有连接到该节点的边
        for edge in edges:
            if edge['target'] == node_id:
                source_node_id = edge['source']
                source_port = edge['sourceHandle']
                target_port = edge['targetHandle']
                
                # 从源节点结果中获取输出
                if source_node_id in node_results:
                    source_output = node_results[source_node_id]
                    
                    # 如果源节点有多个输出，需要选择正确的端口
                    if isinstance(source_output, dict) and source_port in source_output:
                        inputs[target_port] = source_output[source_port]
                    else:
                        # 单输出节点，直接使用输出值
                        inputs[target_port] = source_output
        
        return inputs
    
    def _execute_node(self, node: Dict, inputs: Dict) -> Any:
        """
        执行单个节点
        
        Args:
            node: 节点定义
            inputs: 输入数据字典
            
        Returns:
            Any: 节点执行结果
            
        Raises:
            ValueError: 如果节点类型未知或执行失败
        """
        node_type = node.get('type')
        node_data = node.get('data', {})
        
        if node_type == 'function':
            return self._execute_function_node(node_data, inputs)
        
        elif node_type == 'matrix':
            return self._execute_matrix_node(node_data, inputs)
        
        elif node_type == 'visualization':
            return self._execute_visualization_node(node_data, inputs)
        
        else:
            raise ValueError(f'未知的节点类型: {node_type}')
    
    def _execute_function_node(self, node_data: Dict, inputs: Dict) -> Any:
        """
        执行函数节点
        
        Args:
            node_data: 节点数据
            inputs: 输入数据
            
        Returns:
            Any: 函数执行结果
        """
        if not self.function_library:
            raise ValueError('函数库服务未初始化')
        
        function_id = node_data.get('functionId')
        if not function_id:
            raise ValueError('函数节点缺少functionId')
        
        # 获取函数定义
        function_def = self.function_library.get_function(function_id)
        if not function_def:
            raise ValueError(f'函数 {function_id} 不存在')
        
        # 合并节点参数和输入数据
        parameters = {**node_data.get('parameters', {}), **inputs}
        
        # 执行具体的函数
        # 线性代数函数
        if function_id == 'matrix_add':
            if not self.matrix_service:
                raise ValueError('矩阵服务未初始化')
            a = parameters.get('A')
            b = parameters.get('B')
            if a is None or b is None:
                raise ValueError('矩阵加法需要输入A和B')
            result = self.matrix_service.add(a, b)
            # 返回矩阵的data字段（二维数组）
            return result.data
        
        elif function_id == 'matrix_multiply':
            if not self.matrix_service:
                raise ValueError('矩阵服务未初始化')
            a = parameters.get('A')
            b = parameters.get('B')
            if a is None or b is None:
                raise ValueError('矩阵乘法需要输入A和B')
            result = self.matrix_service.multiply(a, b)
            return result.data
        
        elif function_id == 'matrix_transpose':
            if not self.matrix_service:
                raise ValueError('矩阵服务未初始化')
            a = parameters.get('A')
            if a is None:
                raise ValueError('矩阵转置需要输入A')
            result = self.matrix_service.transpose(a)
            return result.data
        
        elif function_id == 'matrix_inverse':
            if not self.matrix_service:
                raise ValueError('矩阵服务未初始化')
            a = parameters.get('A')
            if a is None:
                raise ValueError('矩阵求逆需要输入A')
            result = self.matrix_service.inverse(a)
            return result.data
        
        elif function_id == 'matrix_determinant':
            if not self.matrix_service:
                raise ValueError('矩阵服务未初始化')
            a = parameters.get('A')
            if a is None:
                raise ValueError('行列式计算需要输入A')
            # 行列式返回标量
            np_a = self.matrix_service._to_numpy(a)
            import numpy as np
            result = float(np.linalg.det(np_a))
            return result
        
        elif function_id == 'matrix_eigenvalues':
            if not self.matrix_service:
                raise ValueError('矩阵服务未初始化')
            a = parameters.get('A')
            if a is None:
                raise ValueError('特征值计算需要输入A')
            # 特征值返回向量
            np_a = self.matrix_service._to_numpy(a)
            import numpy as np
            eigenvalues = np.linalg.eigvals(np_a)
            result = eigenvalues.real.tolist()
            return result
        
        # @AI_GENERATED
        # 负荷预测 Function 节点执行逻辑
        elif function_id == 'load_forecast_data_fetch':
            import sys
            _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            if _project_root not in sys.path:
                sys.path.insert(0, _project_root)
            from db_data_fetch import offline_load_data
            load_df, his_min_max = offline_load_data(
                parameters.get('task_type', 'D'),
                parameters.get('table_name', ''),
                parameters.get('parent_field', 'parent_id'),
                parameters.get('child_field', 'child_id'),
                parameters.get('time_field', 'record_time'),
                parameters.get('load_field', 'load'),
                parameters.get('parent_id', ''),
                parameters.get('child_id', ''),
                parameters.get('time_granularity', '15min'),
                parameters.get('is_training', 'true'),
                parameters.get('time_zone', 'Asia/Shanghai'),
                nowtime=parameters.get('nowtime'),
                other_cols=parameters.get('other_cols', []),
                csv_path=parameters.get('csv_path'),
            )
            return {'load_df': load_df, 'his_min_max': his_min_max}

        elif function_id == 'load_forecast_anomaly_detection':
            import sys
            _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            if _project_root not in sys.path:
                sys.path.insert(0, _project_root)
            from data_process import get_completed_timestamp, chebyshev_detector, get_completed_df, get_timestamp_freq
            load_df = parameters.get('load_df')
            time_field = parameters.get('time_field', 'record_time')
            load_field = parameters.get('load_field', 'load')
            is_training = parameters.get('is_training', 'true')
            original_time_freq = parameters.get('original_time_freq')
            daily_horizon = parameters.get('daily_horizon')
            if original_time_freq is None or daily_horizon is None:
                original_time_freq, daily_horizon = get_timestamp_freq(load_df, time_field=time_field)
            timestamp_completed_df = get_completed_timestamp(
                load_df, original_time_freq, daily_horizon, is_training, time_field=time_field)
            anomaly_detected_df = chebyshev_detector(timestamp_completed_df, load_field=load_field)
            completed_df = get_completed_df(anomaly_detected_df, delay_info={},
                                            time_field=time_field, load_field=load_field)
            return {'completed_df': completed_df, 'time_freq': original_time_freq, 'daily_horizon': daily_horizon}

        elif function_id == 'load_forecast_feature_engineering':
            import sys
            _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            if _project_root not in sys.path:
                sys.path.insert(0, _project_root)
            from features.engine import add_more_features
            from common.constants import SCENARIO_CONFIGS
            scenario_type = parameters.get('scenario_type', 'D')
            scenario = SCENARIO_CONFIGS.get(scenario_type)
            forecast_timestamps, feat_df, shift_info = add_more_features(
                scenario,
                task_id=parameters.get('task_id', ''),
                parent_id=parameters.get('parent_id', ''),
                child_id=parameters.get('child_id', ''),
                operate_status=parameters.get('operate_status', 'offline'),
                completed_df=parameters.get('completed_df'),
                original_time_freq=parameters.get('original_time_freq'),
                daily_horizon=parameters.get('daily_horizon'),
                forecast_horizon=parameters.get('forecast_horizon', 1),
                forecast_start_time=parameters.get('forecast_start_time', '00:15'),
                is_training=parameters.get('is_training', 'true'),
                time_zone=parameters.get('time_zone', 'Asia/Shanghai'),
                nowtime=parameters.get('nowtime'),
                separate_modeling=parameters.get('separate_modeling', 'true'),
                gaps_defined=None,
                time_field=parameters.get('time_field', 'record_time'),
                load_field=parameters.get('load_field', 'load'),
            )
            return {'feat_df': feat_df, 'forecast_timestamps': forecast_timestamps, 'shift_info': shift_info}

        elif function_id == 'load_forecast_model_train':
            import sys
            _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            if _project_root not in sys.path:
                sys.path.insert(0, _project_root)
            from models_pkg.trainer import model_prefer_trainer
            from common.constants import SCENARIO_CONFIGS
            scenario_type = parameters.get('scenario_type', 'D')
            scenario = SCENARIO_CONFIGS.get(scenario_type)
            total_model, total_feature_list, total_auto_model_tag, daily_horizon = model_prefer_trainer(
                parameters.get('feat_df'),
                parameters.get('daily_horizon'),
                parameters.get('forecast_horizon', 1),
                scenario=scenario,
                separate_modeling=parameters.get('separate_modeling', 'true'),
                time_field=parameters.get('time_field', 'record_time'),
                load_field=parameters.get('load_field', 'load'),
            )
            return {
                'model_dict': total_model,
                'feature_list': total_feature_list,
                'model_tag': total_auto_model_tag,
                'daily_horizon': daily_horizon,
            }

        elif function_id == 'load_forecast_model_predict':
            import sys
            _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            if _project_root not in sys.path:
                sys.path.insert(0, _project_root)
            import pandas as pd
            model_dict = parameters.get('model_dict')
            feature_list = parameters.get('feature_list')
            feat_df = parameters.get('feat_df')
            # 构造 MLflow predict 输入
            first_layer_keys = list(feat_df.keys())
            feat_df_dict = {}
            for tmp_key in first_layer_keys:
                if isinstance(feat_df[tmp_key], pd.DataFrame):
                    tmp_dict = {}
                    for c in feat_df[tmp_key].columns:
                        tmp_dict[c] = feat_df[tmp_key][c].values
                    feat_df_dict[tmp_key] = tmp_dict
                else:
                    feat_df_dict[tmp_key] = feat_df[tmp_key]
            inputs_df = pd.DataFrame()
            inputs_df['feat_df'] = [feat_df_dict]
            inputs_df['other_params'] = [parameters.get('other_params', {})]
            # model_dict should be a LoadForecastWrapper instance
            predict_output = model_dict.predict(None, inputs_df)
            return predict_output

        elif function_id == 'load_forecast_evaluate':
            import sys
            _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            if _project_root not in sys.path:
                sys.path.insert(0, _project_root)
            import numpy as np
            from forecast_utils import smape
            y_true = np.asarray(parameters.get('y_true'), dtype=float)
            y_pred = np.asarray(parameters.get('y_pred'), dtype=float)
            smape_val = smape(y_true, y_pred)
            mae_val = float(np.mean(np.abs(y_true - y_pred)))
            rmse_val = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
            return {'smape': smape_val, 'mae': mae_val, 'rmse': rmse_val}
        # @AI_GENERATED: end

        # 其他函数暂时返回模拟结果
        else:
            return {
                'result': f'Function {function_id} executed with params: {parameters}',
                'functionId': function_id
            }
    
    def _execute_matrix_node(self, node_data: Dict, inputs: Dict) -> Any:
        """
        执行矩阵运算节点
        
        Args:
            node_data: 节点数据
            inputs: 输入数据
            
        Returns:
            Any: 矩阵运算结果
        """
        if not self.matrix_service:
            raise ValueError('矩阵服务未初始化')
        
        operation = node_data.get('operation')
        if not operation:
            raise ValueError('矩阵节点缺少operation')
        
        # 根据操作类型执行相应的矩阵运算
        if operation == 'add':
            a = inputs.get('a')
            b = inputs.get('b')
            if a is None or b is None:
                raise ValueError('矩阵加法需要输入a和b')
            return self.matrix_service.add(a, b)
        
        elif operation == 'subtract':
            a = inputs.get('a')
            b = inputs.get('b')
            if a is None or b is None:
                raise ValueError('矩阵减法需要输入a和b')
            return self.matrix_service.subtract(a, b)
        
        elif operation == 'multiply':
            a = inputs.get('a')
            b = inputs.get('b')
            if a is None or b is None:
                raise ValueError('矩阵乘法需要输入a和b')
            return self.matrix_service.multiply(a, b)
        
        elif operation == 'transpose':
            a = inputs.get('a')
            if a is None:
                raise ValueError('矩阵转置需要输入a')
            return self.matrix_service.transpose(a)
        
        elif operation == 'inverse':
            a = inputs.get('a')
            if a is None:
                raise ValueError('矩阵求逆需要输入a')
            return self.matrix_service.inverse(a)
        
        else:
            raise ValueError(f'未知的矩阵操作: {operation}')
    
    def _execute_visualization_node(self, node_data: Dict, inputs: Dict) -> Any:
        """
        执行可视化节点
        
        Args:
            node_data: 节点数据
            inputs: 输入数据
            
        Returns:
            Dict: 可视化配置（不实际渲染）
        """
        chart_type = node_data.get('chartType')
        if not chart_type:
            raise ValueError('可视化节点缺少chartType')
        
        # 生成可视化配置（前端负责实际渲染）
        return {
            'type': chart_type,
            'data': inputs.get('data'),
            'config': node_data.get('config', {}),
            'title': node_data.get('parameters', {}).get('title', '图表')
        }
    
    def get_execution_summary(self, execution_data: Dict) -> Dict:
        """
        获取执行摘要信息
        
        Args:
            execution_data: 执行结果数据
            
        Returns:
            Dict: 执行摘要
        """
        node_results = execution_data.get('nodeResults', {})
        
        completed_count = sum(
            1 for result in node_results.values() 
            if result.get('status') == 'completed'
        )
        failed_count = sum(
            1 for result in node_results.values() 
            if result.get('status') == 'failed'
        )
        
        total_time = 0
        if execution_data.get('startTime') and execution_data.get('endTime'):
            start = datetime.fromisoformat(execution_data['startTime'])
            end = datetime.fromisoformat(execution_data['endTime'])
            total_time = (end - start).total_seconds()
        
        return {
            'status': execution_data.get('status'),
            'totalNodes': len(node_results),
            'completedNodes': completed_count,
            'failedNodes': failed_count,
            'totalExecutionTime': total_time,
            'hasError': execution_data.get('status') == 'failed'
        }
