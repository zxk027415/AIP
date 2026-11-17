# @AI_GENERATED
"""
算子执行框架模块 - Operator Execution Framework

提供统一的算子路由、执行、校验和数据适配能力。
"""
from .router import OperatorRouter, OperatorExecutionError
from .schema_validator import DataContract, SchemaValidator, ValidationResult
from .data_adapter import DataAdapter
from .global_config_injector import GlobalConfigInjector
from .data_contracts import LOAD_FORECAST_CONTRACTS

__all__ = [
    "OperatorRouter",
    "OperatorExecutionError",
    "DataContract",
    "SchemaValidator",
    "ValidationResult",
    "DataAdapter",
    "GlobalConfigInjector",
    "LOAD_FORECAST_CONTRACTS",
]
# @AI_GENERATED: end
