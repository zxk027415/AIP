"""
算法模板执行引擎
负责按拓扑顺序执行算法模板节点
"""
from typing import Dict, List, Any, Set, Optional
from collections import defaultdict, deque
import time
from models.workflow_models import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
    ExecutionResult,
    NodeResult,
    ExecutionStatus
)


class WorkflowExecutor:
    """算法模板执行器"""
    
    def __init__(self, workflow: WorkflowDefinition):
        """
        初始化执行器
        
        Args:
            workflow: 算法模板定义
        """
        self.workflow = workflow
        self.node_results: Dict[str, NodeResult] = {}
        self.node_map: Dict[str, WorkflowNode] = {
            node.id: node for node in workflow.nodes
        }
    
    async def execute(self, inputs: Dict[str, Any] = None) -> ExecutionResult:
        """
        执行算法模板
        
        Args:
            inputs: 输入数据
            
        Returns:
            ExecutionResult: 执行结果
        """
        execution_id = f"exec-{int(time.time() * 1000)}"
        start_time = time.time()
        
        try:
            # 1. 构建执行图
            execution_graph = self._build_execution_graph()
            
            # 2. 拓扑排序
            execution_order = self._topological_sort(execution_graph)
            
            # 3. 按顺序执行节点
            for node_id in execution_order:
                node_start_time = time.time()
                
                try:
                    # 执行节点
                    output = await self._execute_node(node_id, inputs or {})
                    
                    # 记录结果
                    self.node_results[node_id] = NodeResult(
                        nodeId=node_id,
                        status=ExecutionStatus.COMPLETED,
                        output=output,
                        executionTime=time.time() - node_start_time,
                        startTime=time.strftime('%Y-%m-%dT%H:%M:%S')
                    )
                    
                except Exception as e:
                    # 节点执行失败
                    self.node_results[node_id] = NodeResult(
                        nodeId=node_id,
                        status=ExecutionStatus.FAILED,
                        error=str(e),
                        executionTime=time.time() - node_start_time,
                        startTime=time.strftime('%Y-%m-%dT%H:%M:%S')
                    )
                    
                    # 算法模板执行失败
                    return ExecutionResult(
                        workflowId=self.workflow.metadata.version if self.workflow.metadata else "unknown",
                        executionId=execution_id,
                        status=ExecutionStatus.FAILED,
                        startTime=time.strftime('%Y-%m-%dT%H:%M:%S'),
                        endTime=time.strftime('%Y-%m-%dT%H:%M:%S'),
                        nodeResults=self.node_results,
                        error=f"Node {node_id} failed: {str(e)}"
                    )
            
            # 4. 执行成功
            return ExecutionResult(
                workflowId=self.workflow.metadata.version if self.workflow.metadata else "unknown",
                executionId=execution_id,
                status=ExecutionStatus.COMPLETED,
                startTime=time.strftime('%Y-%m-%dT%H:%M:%S'),
                endTime=time.strftime('%Y-%m-%dT%H:%M:%S'),
                nodeResults=self.node_results
            )
            
        except Exception as e:
            # 算法模板执行失败
            return ExecutionResult(
                workflowId=self.workflow.metadata.version if self.workflow.metadata else "unknown",
                executionId=execution_id,
                status=ExecutionStatus.FAILED,
                startTime=time.strftime('%Y-%m-%dT%H:%M:%S'),
                endTime=time.strftime('%Y-%m-%dT%H:%M:%S'),
                nodeResults=self.node_results,
                error=str(e)
            )
    
    def _build_execution_graph(self) -> Dict[str, List[str]]:
        """
        构建执行图（邻接表）
        
        Returns:
            Dict[str, List[str]]: 节点ID -> 依赖节点ID列表
        """
        graph = defaultdict(list)
        
        # 初始化所有节点
        for node in self.workflow.nodes:
            if node.id not in graph:
                graph[node.id] = []
        
        # 添加边
        for edge in self.workflow.edges:
            # source -> target 表示 target 依赖 source
            graph[edge.source].append(edge.target)
        
        return dict(graph)
    
    def _topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        """
        拓扑排序（Kahn算法）
        
        Args:
            graph: 执行图
            
        Returns:
            List[str]: 执行顺序
            
        Raises:
            ValueError: 如果存在循环依赖
        """
        # 计算入度
        in_degree = {node: 0 for node in graph}
        
        for node in graph:
            for neighbor in graph[node]:
                in_degree[neighbor] += 1
        
        # 找到所有入度为0的节点
        queue = deque([node for node in in_degree if in_degree[node] == 0])
        result = []
        
        while queue:
            node = queue.popleft()
            result.append(node)
            
            # 减少邻居的入度
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # 检查是否有循环
        if len(result) != len(graph):
            raise ValueError("Workflow contains cycles")
        
        return result
    
    async def _execute_node(self, node_id: str, workflow_inputs: Dict[str, Any]) -> Any:
        """
        执行单个节点
        
        Args:
            node_id: 节点ID
            workflow_inputs: 算法模板输入
            
        Returns:
            Any: 节点输出
        """
        node = self.node_map[node_id]
        
        # 获取节点输入（从前置节点的输出）
        node_inputs = self._get_node_inputs(node_id)
        
        # 根据节点类型执行
        if node.type.value == 'function':
            return await self._execute_function_node(node, node_inputs)
        elif node.type.value == 'matrix':
            return await self._execute_matrix_node(node, node_inputs)
        elif node.type.value == 'visualization':
            return await self._execute_visualization_node(node, node_inputs)
        else:
            raise ValueError(f"Unknown node type: {node.type}")
    
    def _get_node_inputs(self, node_id: str) -> Dict[str, Any]:
        """
        获取节点的输入数据（从前置节点的输出）
        
        Args:
            node_id: 节点ID
            
        Returns:
            Dict[str, Any]: 输入数据
        """
        inputs = {}
        
        # 找到所有指向该节点的边
        for edge in self.workflow.edges:
            if edge.target == node_id:
                # 获取源节点的输出
                source_result = self.node_results.get(edge.source)
                if source_result and source_result.output is not None:
                    # 使用 targetHandle 作为输入键
                    input_key = edge.targetHandle or 'input'
                    inputs[input_key] = source_result.output
        
        return inputs
    
    async def _execute_function_node(self, node: WorkflowNode, inputs: Dict[str, Any]) -> Any:
        """
        执行函数节点
        
        Args:
            node: 节点定义
            inputs: 输入数据
            
        Returns:
            Any: 函数输出
        """
        # TODO: 集成函数库服务
        # 这里先返回模拟结果
        function_id = node.data.functionId
        return {
            "type": "function_result",
            "functionId": function_id,
            "result": f"Function {function_id} executed with inputs: {inputs}"
        }
    
    async def _execute_matrix_node(self, node: WorkflowNode, inputs: Dict[str, Any]) -> Any:
        """
        执行矩阵运算节点
        
        Args:
            node: 节点定义
            inputs: 输入数据
            
        Returns:
            Any: 矩阵运算结果
        """
        # TODO: 集成矩阵服务
        # 这里先返回模拟结果
        operation = node.data.operation
        return {
            "type": "matrix_result",
            "operation": operation,
            "result": f"Matrix operation {operation} executed with inputs: {inputs}"
        }
    
    async def _execute_visualization_node(self, node: WorkflowNode, inputs: Dict[str, Any]) -> Any:
        """
        执行数据可视化节点
        
        Args:
            node: 节点定义
            inputs: 输入数据
            
        Returns:
            Any: 可视化配置
        """
        # TODO: 生成可视化配置
        # 这里先返回模拟结果
        chart_type = node.data.chartType
        return {
            "type": "visualization_result",
            "chartType": chart_type,
            "config": {
                "title": node.data.label,
                "data": inputs
            }
        }
