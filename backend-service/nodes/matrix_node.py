"""
矩阵运算节点
执行矩阵计算操作
"""
from typing import Dict, Any, List
import numpy as np
from services.matrix_service import matrix_service


class MatrixNode:
    """矩阵运算节点"""
    
    def __init__(self, node_config: Dict[str, Any]):
        """
        初始化矩阵节点
        
        Args:
            node_config: 节点配置
        """
        self.operation = node_config.get('operation')
        self.operation_params = node_config.get('parameters', {})
    
    async def execute(self, inputs: Dict[str, Any]) -> Any:
        """
        执行矩阵运算
        
        Args:
            inputs: 输入数据
            
        Returns:
            Any: 矩阵运算结果
        """
        # 1. 获取输入矩阵
        matrices = self._get_input_matrices(inputs)
        
        # 2. 验证矩阵维度
        self._validate_dimensions(matrices)
        
        # 3. 执行矩阵运算
        result = await self._execute_operation(matrices)
        
        return result
    
    def _get_input_matrices(self, inputs: Dict[str, Any]) -> List[np.ndarray]:
        """
        从输入中提取矩阵
        
        Args:
            inputs: 输入数据
            
        Returns:
            List[np.ndarray]: 矩阵列表
        """
        matrices = []
        
        # 按顺序获取输入矩阵
        for key in sorted(inputs.keys()):
            value = inputs[key]
            
            # 转换为 numpy 数组
            if isinstance(value, list):
                matrix = np.array(value)
            elif isinstance(value, np.ndarray):
                matrix = value
            elif isinstance(value, dict) and 'data' in value:
                # 如果是矩阵对象，提取数据
                matrix = np.array(value['data'])
            else:
                raise ValueError(f"Invalid matrix input: {key}")
            
            matrices.append(matrix)
        
        return matrices
    
    def _validate_dimensions(self, matrices: List[np.ndarray]):
        """
        验证矩阵维度是否符合运算要求
        
        Args:
            matrices: 矩阵列表
            
        Raises:
            ValueError: 如果维度不兼容
        """
        if not matrices:
            raise ValueError("No input matrices provided")
        
        # 根据运算类型验证
        if self.operation == 'multiply':
            if len(matrices) < 2:
                raise ValueError("Matrix multiplication requires at least 2 matrices")
            
            # 检查矩阵乘法的维度兼容性
            for i in range(len(matrices) - 1):
                if matrices[i].shape[1] != matrices[i + 1].shape[0]:
                    raise ValueError(
                        f"Matrix dimensions incompatible for multiplication: "
                        f"{matrices[i].shape} x {matrices[i + 1].shape}"
                    )
        
        elif self.operation in ['add', 'subtract']:
            if len(matrices) < 2:
                raise ValueError(f"Matrix {self.operation} requires at least 2 matrices")
            
            # 检查所有矩阵形状是否相同
            first_shape = matrices[0].shape
            for i, matrix in enumerate(matrices[1:], 1):
                if matrix.shape != first_shape:
                    raise ValueError(
                        f"Matrix dimensions must match for {self.operation}: "
                        f"{first_shape} vs {matrix.shape}"
                    )
        
        elif self.operation == 'transpose':
            if len(matrices) != 1:
                raise ValueError("Matrix transpose requires exactly 1 matrix")
        
        elif self.operation == 'inverse':
            if len(matrices) != 1:
                raise ValueError("Matrix inverse requires exactly 1 matrix")
            
            # 检查是否为方阵
            if matrices[0].shape[0] != matrices[0].shape[1]:
                raise ValueError(
                    f"Matrix inverse requires a square matrix, got {matrices[0].shape}"
                )
    
    async def _execute_operation(self, matrices: List[np.ndarray]) -> Any:
        """
        执行矩阵运算
        
        Args:
            matrices: 矩阵列表
            
        Returns:
            Any: 运算结果
        """
        try:
            if self.operation == 'add':
                result = matrices[0]
                for matrix in matrices[1:]:
                    result = np.add(result, matrix)
            
            elif self.operation == 'subtract':
                result = matrices[0]
                for matrix in matrices[1:]:
                    result = np.subtract(result, matrix)
            
            elif self.operation == 'multiply':
                result = matrices[0]
                for matrix in matrices[1:]:
                    result = np.matmul(result, matrix)
            
            elif self.operation == 'transpose':
                result = np.transpose(matrices[0])
            
            elif self.operation == 'inverse':
                result = np.linalg.inv(matrices[0])
            
            elif self.operation == 'determinant':
                result = np.linalg.det(matrices[0])
            
            elif self.operation == 'eigenvalues':
                eigenvalues, eigenvectors = np.linalg.eig(matrices[0])
                result = {
                    'eigenvalues': eigenvalues.tolist(),
                    'eigenvectors': eigenvectors.tolist()
                }
            
            else:
                raise ValueError(f"Unknown matrix operation: {self.operation}")
            
            # 转换结果为可序列化格式
            if isinstance(result, np.ndarray):
                return {
                    "type": "matrix",
                    "operation": self.operation,
                    "data": result.tolist(),
                    "shape": result.shape
                }
            else:
                return {
                    "type": "matrix",
                    "operation": self.operation,
                    "result": result
                }
        
        except Exception as e:
            raise ValueError(f"Matrix operation failed: {str(e)}")
