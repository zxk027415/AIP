"""
算法模板验证服务
负责验证算法模板的正确性
"""
from typing import Dict, List, Set
from collections import defaultdict, deque
from models.workflow_models import (
    WorkflowDefinition,
    ValidationResult,
    ValidationError,
    ValidationSeverity
)


class WorkflowValidator:
    """算法模板验证器"""
    
    def __init__(self, workflow: WorkflowDefinition):
        """
        初始化验证器
        
        Args:
            workflow: 算法模板定义
        """
        self.workflow = workflow
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
    
    def validate(self) -> ValidationResult:
        """
        验证算法模板
        
        Returns:
            ValidationResult: 验证结果
        """
        # 1. 检查断开连接的节点
        self._check_disconnected_nodes()
        
        # 2. 检查循环依赖
        self._check_cycles()
        
        # 3. 验证节点配置
        self._validate_node_configs()
        
        # 4. 验证连接类型兼容性
        self._validate_connection_types()
        
        return ValidationResult(
            valid=len(self.errors) == 0,
            errors=self.errors,
            warnings=self.warnings
        )
    
    def _check_disconnected_nodes(self):
        """检查是否有孤立节点"""
        if len(self.workflow.nodes) == 0:
            self.warnings.append(ValidationError(
                type="empty_workflow",
                message="算法模板中没有节点",
                severity=ValidationSeverity.WARNING
            ))
            return
        
        # 收集所有连接的节点
        connected_nodes = set()
        for edge in self.workflow.edges:
            connected_nodes.add(edge.source)
            connected_nodes.add(edge.target)
        
        # 检查孤立节点
        for node in self.workflow.nodes:
            if node.id not in connected_nodes:
                self.warnings.append(ValidationError(
                    type="disconnected_node",
                    message=f"节点 '{node.data.label}' 未连接到任何其他节点",
                    severity=ValidationSeverity.WARNING,
                    nodeId=node.id,
                    suggestion="连接此节点或删除它"
                ))
    
    def _check_cycles(self):
        """检查是否存在循环依赖"""
        # 构建图
        graph = defaultdict(list)
        for node in self.workflow.nodes:
            graph[node.id] = []
        
        for edge in self.workflow.edges:
            graph[edge.source].append(edge.target)
        
        # 使用 DFS 检测循环
        visited = set()
        rec_stack = set()
        
        def has_cycle(node_id: str, path: List[str]) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)
            
            for neighbor in graph[node_id]:
                if neighbor not in visited:
                    if has_cycle(neighbor, path):
                        return True
                elif neighbor in rec_stack:
                    # 找到循环
                    cycle_start = path.index(neighbor)
                    cycle_path = path[cycle_start:] + [neighbor]
                    self.errors.append(ValidationError(
                        type="cycle_detected",
                        message=f"检测到循环依赖: {' -> '.join(cycle_path)}",
                        severity=ValidationSeverity.ERROR,
                        suggestion="移除导致循环的连接"
                    ))
                    return True
            
            path.pop()
            rec_stack.remove(node_id)
            return False
        
        for node in self.workflow.nodes:
            if node.id not in visited:
                if has_cycle(node.id, []):
                    break
    
    def _validate_node_configs(self):
        """验证节点配置"""
        for node in self.workflow.nodes:
            # 检查必需字段
            if not node.data.label:
                self.errors.append(ValidationError(
                    type="missing_label",
                    message=f"节点 {node.id} 缺少标签",
                    severity=ValidationSeverity.ERROR,
                    nodeId=node.id
                ))
            
            # 根据节点类型验证特定配置
            if node.type.value == 'function':
                if not node.data.functionId:
                    self.errors.append(ValidationError(
                        type="missing_function_id",
                        message=f"函数节点 '{node.data.label}' 未指定函数ID",
                        severity=ValidationSeverity.ERROR,
                        nodeId=node.id,
                        suggestion="在属性面板中选择一个函数"
                    ))
            
            elif node.type.value == 'matrix':
                if not node.data.operation:
                    self.errors.append(ValidationError(
                        type="missing_operation",
                        message=f"矩阵节点 '{node.data.label}' 未指定运算类型",
                        severity=ValidationSeverity.ERROR,
                        nodeId=node.id,
                        suggestion="在属性面板中选择一个矩阵运算"
                    ))
            
            elif node.type.value == 'visualization':
                if not node.data.chartType:
                    self.errors.append(ValidationError(
                        type="missing_chart_type",
                        message=f"可视化节点 '{node.data.label}' 未指定图表类型",
                        severity=ValidationSeverity.ERROR,
                        nodeId=node.id,
                        suggestion="在属性面板中选择一个图表类型"
                    ))
            
            # 检查必需的输入端口是否已连接
            required_inputs = [port for port in node.data.inputs if port.required]
            if required_inputs:
                connected_inputs = set()
                for edge in self.workflow.edges:
                    if edge.target == node.id:
                        connected_inputs.add(edge.targetHandle)
                
                for port in required_inputs:
                    if port.id not in connected_inputs:
                        self.warnings.append(ValidationError(
                            type="missing_required_input",
                            message=f"节点 '{node.data.label}' 的必需输入 '{port.name}' 未连接",
                            severity=ValidationSeverity.WARNING,
                            nodeId=node.id,
                            port=port.id,
                            suggestion="连接此输入端口"
                        ))
    
    def _validate_connection_types(self):
        """验证连接的类型兼容性"""
        # 构建节点映射
        node_map = {node.id: node for node in self.workflow.nodes}
        
        for edge in self.workflow.edges:
            source_node = node_map.get(edge.source)
            target_node = node_map.get(edge.target)
            
            # 检查节点是否存在
            if not source_node:
                self.errors.append(ValidationError(
                    type="invalid_connection",
                    message=f"连接的源节点不存在: {edge.source}",
                    severity=ValidationSeverity.ERROR,
                    edgeId=edge.id
                ))
                continue
            
            if not target_node:
                self.errors.append(ValidationError(
                    type="invalid_connection",
                    message=f"连接的目标节点不存在: {edge.target}",
                    severity=ValidationSeverity.ERROR,
                    edgeId=edge.id
                ))
                continue
            
            # 检查端口是否存在
            source_port = None
            for port in source_node.data.outputs:
                if port.id == edge.sourceHandle:
                    source_port = port
                    break
            
            target_port = None
            for port in target_node.data.inputs:
                if port.id == edge.targetHandle:
                    target_port = port
                    break
            
            if not source_port:
                self.errors.append(ValidationError(
                    type="invalid_port",
                    message=f"源节点 '{source_node.data.label}' 的输出端口 '{edge.sourceHandle}' 不存在",
                    severity=ValidationSeverity.ERROR,
                    edgeId=edge.id,
                    nodeId=edge.source
                ))
                continue
            
            if not target_port:
                self.errors.append(ValidationError(
                    type="invalid_port",
                    message=f"目标节点 '{target_node.data.label}' 的输入端口 '{edge.targetHandle}' 不存在",
                    severity=ValidationSeverity.ERROR,
                    edgeId=edge.id,
                    nodeId=edge.target
                ))
                continue
            
            # 检查类型兼容性
            if not self._are_types_compatible(source_port.type, target_port.type):
                self.warnings.append(ValidationError(
                    type="type_mismatch",
                    message=f"类型不匹配: {source_node.data.label}.{source_port.name} ({source_port.type}) -> {target_node.data.label}.{target_port.name} ({target_port.type})",
                    severity=ValidationSeverity.WARNING,
                    edgeId=edge.id,
                    suggestion="检查数据类型是否兼容"
                ))
    
    def _are_types_compatible(self, source_type: str, target_type: str) -> bool:
        """
        检查两个数据类型是否兼容
        
        Args:
            source_type: 源类型
            target_type: 目标类型
            
        Returns:
            bool: 是否兼容
        """
        # any 类型与所有类型兼容
        if source_type == 'any' or target_type == 'any':
            return True
        
        # 相同类型兼容
        if source_type == target_type:
            return True
        
        # 特殊兼容性规则
        compatibility_rules = {
            ('number', 'array'): True,
            ('matrix', 'array'): True,
            ('array', 'matrix'): True,
            ('matrix', 'vector'): True,
            ('vector', 'array'): True,
        }
        
        return compatibility_rules.get((source_type, target_type), False)
