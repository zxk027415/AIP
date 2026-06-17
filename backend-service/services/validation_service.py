"""
算法模板验证服务

该服务负责验证算法模板的正确性，包括：
1. 检测循环依赖
2. 检测断开的节点
3. 检查必需输入
4. 验证类型兼容性
"""
import networkx as nx
from typing import List, Dict, Tuple, Optional


class ValidationService:
    """算法模板验证服务"""
    
    def validate_workflow(self, workflow: Dict) -> Tuple[bool, List[Dict]]:
        """
        验证算法模板
        
        Args:
            workflow: 算法模板定义，包含nodes和edges
            
        Returns:
            (is_valid, errors_and_warnings): 
                - is_valid: 是否有效（无错误）
                - errors_and_warnings: 错误和警告列表
        """
        errors = []
        warnings = []
        
        # 1. 检测循环依赖
        if self._has_cycle(workflow):
            errors.append({
                'type': 'cycle',
                'message': '算法模板包含循环依赖',
                'severity': 'error',
                'suggestion': '请移除导致循环的连接'
            })
        
        # 2. 检测断开的模块
        disconnected = self._find_disconnected_nodes(workflow)
        if disconnected:
            warnings.append({
                'type': 'disconnected',
                'message': f'发现{len(disconnected)}个未连接的模块',
                'nodes': disconnected,
                'severity': 'warning',
                'suggestion': '断开的模块不会被执行，请连接它们或删除'
            })
        
        # 3. 检查必需输入
        missing_inputs = self._check_required_inputs(workflow)
        if missing_inputs:
            errors.extend([{
                'type': 'missing_input',
                'message': f'模块 {node_id} 缺少必需输入 {port}',
                'nodeId': node_id,
                'port': port,
                'severity': 'error',
                'suggestion': f'请为端口 {port} 提供输入连接'
            } for node_id, port in missing_inputs])
        
        # 4. 验证类型兼容性
        type_errors = self._validate_type_compatibility(workflow)
        errors.extend(type_errors)
        
        # 5. 检查空算法模板
        if not workflow.get('nodes'):
            warnings.append({
                'type': 'empty_workflow',
                'message': '算法模板为空',
                'severity': 'warning',
                'suggestion': '请添加至少一个节点'
            })
        
        is_valid = len(errors) == 0
        return is_valid, errors + warnings
    
    def _has_cycle(self, workflow: Dict) -> bool:
        """
        使用NetworkX检测有向图中的环
        
        Args:
            workflow: 算法模板定义
            
        Returns:
            bool: 是否存在环
        """
        nodes = workflow.get('nodes', [])
        edges = workflow.get('edges', [])
        
        if not nodes or not edges:
            return False
        
        G = nx.DiGraph()
        
        # 添加节点
        for node in nodes:
            G.add_node(node['id'])
        
        # 添加边
        for edge in edges:
            G.add_edge(edge['source'], edge['target'])
        
        try:
            # 尝试拓扑排序，如果有环会抛出异常
            list(nx.topological_sort(G))
            return False
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            return True
    
    def _find_disconnected_nodes(self, workflow: Dict) -> List[str]:
        """
        查找没有任何连接的节点
        
        Args:
            workflow: 算法模板定义
            
        Returns:
            List[str]: 断开节点的ID列表
        """
        nodes = workflow.get('nodes', [])
        edges = workflow.get('edges', [])
        
        if not nodes:
            return []
        
        connected_nodes = set()
        for edge in edges:
            connected_nodes.add(edge['source'])
            connected_nodes.add(edge['target'])
        
        all_nodes = {node['id'] for node in nodes}
        return list(all_nodes - connected_nodes)
    
    def _check_required_inputs(self, workflow: Dict) -> List[Tuple[str, str]]:
        """
        检查必需输入是否已连接
        
        Args:
            workflow: 算法模板定义
            
        Returns:
            List[Tuple[str, str]]: 缺失输入的列表，每项为(node_id, port_name)
        """
        nodes = workflow.get('nodes', [])
        edges = workflow.get('edges', [])
        
        if not nodes:
            return []
        
        missing = []
        
        # 构建连接映射：target_node_id:target_port_id -> edge
        connections = {}
        for edge in edges:
            target_key = f"{edge['target']}:{edge['targetHandle']}"
            connections[target_key] = edge
        
        # 检查每个节点的必需输入
        for node in nodes:
            node_data = node.get('data', {})
            inputs = node_data.get('inputs', [])
            
            for input_port in inputs:
                if input_port.get('required', False):
                    key = f"{node['id']}:{input_port['id']}"
                    if key not in connections:
                        missing.append((node['id'], input_port['name']))
        
        return missing
    
    def _validate_type_compatibility(self, workflow: Dict) -> List[Dict]:
        """
        验证连接的端口类型是否兼容
        
        Args:
            workflow: 算法模板定义
            
        Returns:
            List[Dict]: 类型不兼容的错误列表
        """
        nodes = workflow.get('nodes', [])
        edges = workflow.get('edges', [])
        
        if not nodes or not edges:
            return []
        
        errors = []
        
        # 构建节点映射
        nodes_map = {node['id']: node for node in nodes}
        
        for edge in edges:
            source_node_id = edge['source']
            target_node_id = edge['target']
            
            # 检查节点是否存在
            if source_node_id not in nodes_map or target_node_id not in nodes_map:
                errors.append({
                    'type': 'invalid_connection',
                    'message': f'连接引用了不存在的节点',
                    'edgeId': edge['id'],
                    'severity': 'error',
                    'suggestion': '请删除此无效连接'
                })
                continue
            
            source_node = nodes_map[source_node_id]
            target_node = nodes_map[target_node_id]
            
            # 查找端口定义
            source_outputs = source_node.get('data', {}).get('outputs', [])
            target_inputs = target_node.get('data', {}).get('inputs', [])
            
            source_port = next(
                (p for p in source_outputs if p['id'] == edge['sourceHandle']),
                None
            )
            target_port = next(
                (p for p in target_inputs if p['id'] == edge['targetHandle']),
                None
            )
            
            # 检查端口是否存在
            if not source_port:
                errors.append({
                    'type': 'invalid_port',
                    'message': f'源节点 {source_node_id} 不存在输出端口 {edge["sourceHandle"]}',
                    'edgeId': edge['id'],
                    'nodeId': source_node_id,
                    'severity': 'error',
                    'suggestion': '请删除此无效连接'
                })
                continue
            
            if not target_port:
                errors.append({
                    'type': 'invalid_port',
                    'message': f'目标节点 {target_node_id} 不存在输入端口 {edge["targetHandle"]}',
                    'edgeId': edge['id'],
                    'nodeId': target_node_id,
                    'severity': 'error',
                    'suggestion': '请删除此无效连接'
                })
                continue
            
            # 验证类型兼容性
            if not self._types_compatible(source_port['type'], target_port['type']):
                errors.append({
                    'type': 'type_mismatch',
                    'message': f'类型不兼容: {source_port["type"]} -> {target_port["type"]}',
                    'edgeId': edge['id'],
                    'severity': 'error',
                    'suggestion': f'源端口类型 {source_port["type"]} 无法连接到目标端口类型 {target_port["type"]}'
                })
        
        return errors
    
    def _types_compatible(self, source_type: str, target_type: str) -> bool:
        """
        检查两个类型是否兼容
        
        Args:
            source_type: 源端口类型
            target_type: 目标端口类型
            
        Returns:
            bool: 是否兼容
        """
        # 相同类型总是兼容
        if source_type == target_type:
            return True
        
        # any类型可以接受任何输入
        if target_type == 'any':
            return True
        
        # 定义类型兼容性规则
        compatibility_rules = {
            'number': ['array', 'any'],
            'array': ['matrix', 'any'],
            'matrix': ['any'],
            'string': ['any'],
            'boolean': ['any'],
            'object': ['any'],
        }
        
        # 检查是否存在兼容规则
        compatible_targets = compatibility_rules.get(source_type, [])
        return target_type in compatible_targets
    
    def get_validation_summary(self, workflow: Dict) -> Dict:
        """
        获取验证摘要信息
        
        Args:
            workflow: 算法模板定义
            
        Returns:
            Dict: 验证摘要，包含统计信息
        """
        is_valid, issues = self.validate_workflow(workflow)
        
        errors = [issue for issue in issues if issue.get('severity') == 'error']
        warnings = [issue for issue in issues if issue.get('severity') == 'warning']
        
        nodes = workflow.get('nodes', [])
        edges = workflow.get('edges', [])
        
        return {
            'valid': is_valid,
            'errorCount': len(errors),
            'warningCount': len(warnings),
            'nodeCount': len(nodes),
            'edgeCount': len(edges),
            'errors': errors,
            'warnings': warnings
        }
