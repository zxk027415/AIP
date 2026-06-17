"""
矩阵计算服务
使用 NumPy 实现矩阵运算和分解
"""
import numpy as np
from typing import List, Tuple
from models.matrix import (
    Matrix,
    LUDecomposition,
    QRDecomposition,
    SVDDecomposition,
    EigenDecomposition,
)


class MatrixService:
    """矩阵计算服务类"""

    @staticmethod
    def create(rows: int, cols: int, initial_value: float = 0.0) -> Matrix:
        """
        创建矩阵
        
        Args:
            rows: 行数
            cols: 列数
            initial_value: 初始值
            
        Returns:
            Matrix: 创建的矩阵
        """
        data = [[initial_value for _ in range(cols)] for _ in range(rows)]
        return Matrix(rows=rows, cols=cols, data=data)

    @staticmethod
    def from_array(data: List[List[float]]) -> Matrix:
        """
        从二维数组创建矩阵
        
        Args:
            data: 二维数组
            
        Returns:
            Matrix: 创建的矩阵
        """
        if not data or not data[0]:
            raise ValueError("数据不能为空")
        
        rows = len(data)
        cols = len(data[0])
        
        # 验证所有行的列数相同
        for row in data:
            if len(row) != cols:
                raise ValueError("所有行必须有相同的列数")
        
        return Matrix(rows=rows, cols=cols, data=data)

    @staticmethod
    def _to_numpy(matrix: Matrix) -> np.ndarray:
        """将 Matrix 转换为 NumPy 数组"""
        return np.array(matrix.data)

    @staticmethod
    def _from_numpy(arr: np.ndarray) -> Matrix:
        """将 NumPy 数组转换为 Matrix"""
        return Matrix(
            rows=arr.shape[0],
            cols=arr.shape[1],
            data=arr.tolist()
        )

    @staticmethod
    def add(a: Matrix, b: Matrix) -> Matrix:
        """
        矩阵加法（支持广播运算）
        
        支持的运算类型：
        - 标量 + 标量 → 标量
        - 标量 + 向量 → 向量
        - 标量 + 矩阵 → 矩阵
        - 向量 + 向量 → 向量（要求长度相同）
        - 向量 + 矩阵 → 矩阵（向量广播到每一行）
        - 矩阵 + 矩阵 → 矩阵（要求维度相同）
        
        Args:
            a: 矩阵 A（可以是标量1×1、向量1×n或n×1、矩阵m×n）
            b: 矩阵 B（可以是标量1×1、向量1×n或n×1、矩阵m×n）
            
        Returns:
            Matrix: A + B
            
        Raises:
            ValueError: 如果矩阵维度不兼容
        """
        np_a = MatrixService._to_numpy(a)
        np_b = MatrixService._to_numpy(b)
        
        # 判断是否为标量（1×1矩阵）
        is_scalar_a = (a.rows == 1 and a.cols == 1)
        is_scalar_b = (b.rows == 1 and b.cols == 1)
        
        # 判断是否为向量
        is_vector_a = (a.rows == 1 or a.cols == 1) and not is_scalar_a
        is_vector_b = (b.rows == 1 or b.cols == 1) and not is_scalar_b
        
        try:
            # NumPy 会自动处理广播运算
            result = np_a + np_b
            return MatrixService._from_numpy(result)
        except ValueError as e:
            # 提供更友好的错误信息
            a_type = "标量" if is_scalar_a else ("向量" if is_vector_a else "矩阵")
            b_type = "标量" if is_scalar_b else ("向量" if is_vector_b else "矩阵")
            
            raise ValueError(
                f"无法进行加法运算: {a_type}({a.rows}×{a.cols}) + {b_type}({b.rows}×{b.cols})\n"
                f"原因: {str(e)}"
            )

    @staticmethod
    def subtract(a: Matrix, b: Matrix) -> Matrix:
        """
        矩阵减法（支持广播运算）
        
        支持的运算类型：
        - 标量 - 标量 → 标量
        - 标量 - 向量 → 向量
        - 标量 - 矩阵 → 矩阵
        - 向量 - 向量 → 向量（要求长度相同）
        - 向量 - 矩阵 → 矩阵（向量广播到每一行）
        - 矩阵 - 矩阵 → 矩阵（要求维度相同）
        
        Args:
            a: 矩阵 A（可以是标量1×1、向量1×n或n×1、矩阵m×n）
            b: 矩阵 B（可以是标量1×1、向量1×n或n×1、矩阵m×n）
            
        Returns:
            Matrix: A - B
            
        Raises:
            ValueError: 如果矩阵维度不兼容
        """
        np_a = MatrixService._to_numpy(a)
        np_b = MatrixService._to_numpy(b)
        
        # 判断是否为标量（1×1矩阵）
        is_scalar_a = (a.rows == 1 and a.cols == 1)
        is_scalar_b = (b.rows == 1 and b.cols == 1)
        
        # 判断是否为向量
        is_vector_a = (a.rows == 1 or a.cols == 1) and not is_scalar_a
        is_vector_b = (b.rows == 1 or b.cols == 1) and not is_scalar_b
        
        try:
            # NumPy 会自动处理广播运算
            result = np_a - np_b
            return MatrixService._from_numpy(result)
        except ValueError as e:
            # 提供更友好的错误信息
            a_type = "标量" if is_scalar_a else ("向量" if is_vector_a else "矩阵")
            b_type = "标量" if is_scalar_b else ("向量" if is_vector_b else "矩阵")
            
            raise ValueError(
                f"无法进行减法运算: {a_type}({a.rows}×{a.cols}) - {b_type}({b.rows}×{b.cols})\n"
                f"原因: {str(e)}"
            )

    @staticmethod
    def multiply(a: Matrix, b: Matrix) -> Matrix:
        """
        矩阵乘法
        
        Args:
            a: 矩阵 A
            b: 矩阵 B
            
        Returns:
            Matrix: A * B
            
        Raises:
            ValueError: 如果矩阵维度不兼容
        """
        if a.cols != b.rows:
            raise ValueError(
                f"矩阵维度不兼容: ({a.rows}x{a.cols}) * ({b.rows}x{b.cols})"
            )
        
        np_a = MatrixService._to_numpy(a)
        np_b = MatrixService._to_numpy(b)
        result = np.matmul(np_a, np_b)
        
        return MatrixService._from_numpy(result)

    @staticmethod
    def transpose(a: Matrix) -> Matrix:
        """
        矩阵转置
        
        Args:
            a: 矩阵 A
            
        Returns:
            Matrix: A^T
        """
        np_a = MatrixService._to_numpy(a)
        result = np_a.T
        
        return MatrixService._from_numpy(result)

    @staticmethod
    def inverse(a: Matrix) -> Matrix:
        """
        矩阵求逆
        
        Args:
            a: 矩阵 A
            
        Returns:
            Matrix: A^(-1)
            
        Raises:
            ValueError: 如果矩阵不是方阵或不可逆
        """
        if a.rows != a.cols:
            raise ValueError(f"只有方阵才能求逆，当前矩阵: {a.rows}x{a.cols}")
        
        np_a = MatrixService._to_numpy(a)
        
        try:
            result = np.linalg.inv(np_a)
            return MatrixService._from_numpy(result)
        except np.linalg.LinAlgError:
            raise ValueError("矩阵不可逆（奇异矩阵）")

    @staticmethod
    def get(matrix: Matrix, row: int, col: int) -> float:
        """
        获取矩阵元素
        
        Args:
            matrix: 矩阵
            row: 行索引（从0开始）
            col: 列索引（从0开始）
            
        Returns:
            float: 元素值
            
        Raises:
            IndexError: 如果索引越界
        """
        if row < 0 or row >= matrix.rows:
            raise IndexError(f"行索引越界: {row} (矩阵行数: {matrix.rows})")
        if col < 0 or col >= matrix.cols:
            raise IndexError(f"列索引越界: {col} (矩阵列数: {matrix.cols})")
        
        return matrix.data[row][col]

    @staticmethod
    def set(matrix: Matrix, row: int, col: int, value: float) -> Matrix:
        """
        设置矩阵元素
        
        Args:
            matrix: 矩阵
            row: 行索引（从0开始）
            col: 列索引（从0开始）
            value: 新值
            
        Returns:
            Matrix: 更新后的矩阵
            
        Raises:
            IndexError: 如果索引越界
        """
        if row < 0 or row >= matrix.rows:
            raise IndexError(f"行索引越界: {row} (矩阵行数: {matrix.rows})")
        if col < 0 or col >= matrix.cols:
            raise IndexError(f"列索引越界: {col} (矩阵列数: {matrix.cols})")
        
        # 创建新矩阵（不修改原矩阵）
        new_data = [row[:] for row in matrix.data]
        new_data[row][col] = value
        
        return Matrix(rows=matrix.rows, cols=matrix.cols, data=new_data)

    @staticmethod
    def lu_decomposition(a: Matrix) -> LUDecomposition:
        """
        LU 分解
        
        Args:
            a: 矩阵 A
            
        Returns:
            LUDecomposition: LU 分解结果
            
        Raises:
            ValueError: 如果矩阵不是方阵
        """
        if a.rows != a.cols:
            raise ValueError(f"LU分解要求方阵，当前矩阵: {a.rows}x{a.cols}")
        
        np_a = MatrixService._to_numpy(a)
        P, L, U = scipy.linalg.lu(np_a)
        
        return LUDecomposition(
            L=MatrixService._from_numpy(L),
            U=MatrixService._from_numpy(U),
            P=MatrixService._from_numpy(P)
        )

    @staticmethod
    def qr_decomposition(a: Matrix) -> QRDecomposition:
        """
        QR 分解
        
        Args:
            a: 矩阵 A
            
        Returns:
            QRDecomposition: QR 分解结果
        """
        np_a = MatrixService._to_numpy(a)
        Q, R = np.linalg.qr(np_a)
        
        return QRDecomposition(
            Q=MatrixService._from_numpy(Q),
            R=MatrixService._from_numpy(R)
        )

    @staticmethod
    def svd_decomposition(a: Matrix) -> SVDDecomposition:
        """
        SVD 分解（奇异值分解）
        
        Args:
            a: 矩阵 A
            
        Returns:
            SVDDecomposition: SVD 分解结果
        """
        np_a = MatrixService._to_numpy(a)
        U, s, Vt = np.linalg.svd(np_a, full_matrices=True)
        
        # 将奇异值转换为对角矩阵
        S = np.zeros((a.rows, a.cols))
        np.fill_diagonal(S, s)
        
        return SVDDecomposition(
            U=MatrixService._from_numpy(U),
            S=MatrixService._from_numpy(S),
            V=MatrixService._from_numpy(Vt.T)  # 注意：返回V而不是V^T
        )

    @staticmethod
    def eigen_decomposition(a: Matrix) -> EigenDecomposition:
        """
        特征值分解
        
        Args:
            a: 矩阵 A
            
        Returns:
            EigenDecomposition: 特征值分解结果
            
        Raises:
            ValueError: 如果矩阵不是方阵
        """
        if a.rows != a.cols:
            raise ValueError(f"特征值分解要求方阵，当前矩阵: {a.rows}x{a.cols}")
        
        np_a = MatrixService._to_numpy(a)
        eigenvalues, eigenvectors = np.linalg.eig(np_a)
        
        return EigenDecomposition(
            values=eigenvalues.real.tolist(),  # 只返回实部
            vectors=MatrixService._from_numpy(eigenvectors.real)
        )


# 导入 scipy（用于 LU 分解）
try:
    import scipy.linalg
except ImportError:
    # 如果没有 scipy，提供一个简单的 LU 分解实现
    def _simple_lu(A):
        """简单的 LU 分解实现（不带选主元）"""
        n = A.shape[0]
        L = np.eye(n)
        U = A.copy()
        P = np.eye(n)
        
        for i in range(n-1):
            for j in range(i+1, n):
                if U[i, i] == 0:
                    raise ValueError("矩阵不可进行 LU 分解（需要选主元）")
                L[j, i] = U[j, i] / U[i, i]
                U[j, i:] -= L[j, i] * U[i, i:]
        
        return P, L, U
    
    # 替换 scipy.linalg.lu
    class _MockScipy:
        class linalg:
            @staticmethod
            def lu(A):
                return _simple_lu(A)
    
    scipy = _MockScipy()
