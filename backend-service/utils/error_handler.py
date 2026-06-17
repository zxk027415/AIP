"""
算法模板错误处理工具
"""
from typing import Optional, Any
from enum import Enum


class ErrorType(str, Enum):
    """错误类型枚举"""
    VALIDATION_ERROR = "validation_error"
    EXECUTION_ERROR = "execution_error"
    CONNECTION_ERROR = "connection_error"
    TYPE_ERROR = "type_error"
    NETWORK_ERROR = "network_error"
    NOT_FOUND = "not_found"
    INTERNAL_ERROR = "internal_error"


class WorkflowException(Exception):
    """算法模板异常基类"""
    
    def __init__(
        self,
        error_type: ErrorType,
        message: str,
        node_id: Optional[str] = None,
        details: Optional[Any] = None
    ):
        """
        初始化异常
        
        Args:
            error_type: 错误类型
            message: 错误消息
            node_id: 相关节点ID（可选）
            details: 详细信息（可选）
        """
        self.error_type = error_type
        self.message = message
        self.node_id = node_id
        self.details = details
        super().__init__(message)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "type": self.error_type.value,
            "message": self.message,
            "nodeId": self.node_id,
            "details": self.details
        }


class ValidationException(WorkflowException):
    """验证异常"""
    
    def __init__(self, message: str, node_id: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(ErrorType.VALIDATION_ERROR, message, node_id, details)


class ExecutionException(WorkflowException):
    """执行异常"""
    
    def __init__(self, message: str, node_id: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(ErrorType.EXECUTION_ERROR, message, node_id, details)


class ConnectionException(WorkflowException):
    """连接异常"""
    
    def __init__(self, message: str, node_id: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(ErrorType.CONNECTION_ERROR, message, node_id, details)


class TypeException(WorkflowException):
    """类型异常"""
    
    def __init__(self, message: str, node_id: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(ErrorType.TYPE_ERROR, message, node_id, details)


class NotFoundException(WorkflowException):
    """未找到异常"""
    
    def __init__(self, message: str, node_id: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(ErrorType.NOT_FOUND, message, node_id, details)
