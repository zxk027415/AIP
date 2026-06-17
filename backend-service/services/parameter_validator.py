# @AI_GENERATED: Kiro v1.0
"""
参数验证服务

为风电预测模块提供参数验证功能，支持以下验证规则类型：
- range: 数值范围约束
- enum: 枚举值约束
- pattern: 正则表达式约束
- min_length/max_length: 数组长度约束
- min_rows/min_columns: 矩阵维度约束
- required_columns: 必需列约束
- no_nan: 禁止NaN值
- type_check: 类型检查
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]


class ParameterValidator:
    """参数验证器"""
    
    def validate_parameter(
        self, 
        param_name: str, 
        param_value: Any, 
        param_def: Dict[str, Any]
    ) -> ValidationResult:
        """
        验证单个参数
        
        Args:
            param_name: 参数名称
            param_value: 参数值
            param_def: 参数定义（包含validation字段）
            
        Returns:
            ValidationResult: 验证结果
        """
        errors = []
        warnings = []
        
        # 获取验证规则
        validation = param_def.get('validation', {})
        if not validation:
            return ValidationResult(is_valid=True, errors=[], warnings=[])
        
        param_type = param_def.get('type', 'ANY')
        
        # 类型检查
        if 'type_check' in validation:
            type_error = self._validate_type(param_name, param_value, validation['type_check'])
            if type_error:
                errors.append(type_error)
        
        # 数值范围验证
        if 'range' in validation:
            range_error = self._validate_range(param_name, param_value, validation['range'])
            if range_error:
                errors.append(range_error)
        
        # 枚举值验证
        if 'enum' in validation:
            enum_error = self._validate_enum(param_name, param_value, validation['enum'])
            if enum_error:
                errors.append(enum_error)
        
        # 正则表达式验证
        if 'pattern' in validation:
            pattern_error = self._validate_pattern(param_name, param_value, validation['pattern'])
            if pattern_error:
                errors.append(pattern_error)
        
        # 数组长度验证
        if 'min_length' in validation or 'max_length' in validation:
            length_error = self._validate_array_length(
                param_name, param_value, 
                validation.get('min_length'), 
                validation.get('max_length')
            )
            if length_error:
                errors.append(length_error)
        
        # 数组元素验证
        if 'item_pattern' in validation and isinstance(param_value, list):
            item_errors = self._validate_array_items(
                param_name, param_value, validation['item_pattern']
            )
            errors.extend(item_errors)
        
        if 'item_range' in validation and isinstance(param_value, list):
            item_errors = self._validate_array_item_range(
                param_name, param_value, validation['item_range']
            )
            errors.extend(item_errors)
        
        # DataFrame验证（需要pandas）
        if param_type == 'MATRIX':
            matrix_errors = self._validate_matrix(param_name, param_value, validation)
            errors.extend(matrix_errors)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def validate_all_parameters(
        self,
        parameters: Dict[str, Any],
        param_definitions: List[Dict[str, Any]]
    ) -> ValidationResult:
        """
        验证所有参数
        
        Args:
            parameters: 参数字典
            param_definitions: 参数定义列表
            
        Returns:
            ValidationResult: 验证结果
        """
        all_errors = []
        all_warnings = []
        
        # 创建参数定义映射
        param_def_map = {p['name']: p for p in param_definitions}
        
        # 检查必需参数
        for param_def in param_definitions:
            param_name = param_def['name']
            if param_def.get('required', False) and param_name not in parameters:
                all_errors.append(f"缺少必需参数: {param_name}")
        
        # 验证每个提供的参数
        for param_name, param_value in parameters.items():
            if param_name in param_def_map:
                result = self.validate_parameter(
                    param_name, param_value, param_def_map[param_name]
                )
                all_errors.extend(result.errors)
                all_warnings.extend(result.warnings)
            else:
                all_warnings.append(f"未知参数: {param_name}")
        
        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings
        )
    
    def _validate_type(self, name: str, value: Any, expected_type: str) -> Optional[str]:
        """验证类型"""
        type_map = {
            'boolean': bool,
            'number': (int, float),
            'string': str,
            'array': list,
            'object': dict
        }
        
        expected = type_map.get(expected_type.lower())
        if expected and not isinstance(value, expected):
            return f"参数 {name} 类型错误: 期望 {expected_type}, 实际 {type(value).__name__}"
        return None
    
    def _validate_range(self, name: str, value: Any, range_def: List) -> Optional[str]:
        """验证数值范围"""
        if not isinstance(value, (int, float)):
            return None
        
        min_val, max_val = range_def
        if min_val is not None and value < min_val:
            return f"参数 {name} 值 {value} 小于最小值 {min_val}"
        if max_val is not None and value > max_val:
            return f"参数 {name} 值 {value} 大于最大值 {max_val}"
        return None
    
    def _validate_enum(self, name: str, value: Any, enum_values: List) -> Optional[str]:
        """验证枚举值"""
        if value not in enum_values:
            return f"参数 {name} 值 '{value}' 不在允许的值列表中: {enum_values}"
        return None
    
    def _validate_pattern(self, name: str, value: Any, pattern: str) -> Optional[str]:
        """验证正则表达式"""
        if not isinstance(value, str):
            return None
        
        if not re.match(pattern, value):
            return f"参数 {name} 值 '{value}' 不匹配模式: {pattern}"
        return None
    
    def _validate_array_length(
        self, name: str, value: Any, 
        min_length: Optional[int], max_length: Optional[int]
    ) -> Optional[str]:
        """验证数组长度"""
        if not isinstance(value, list):
            return None
        
        length = len(value)
        if min_length is not None and length < min_length:
            return f"参数 {name} 长度 {length} 小于最小长度 {min_length}"
        if max_length is not None and length > max_length:
            return f"参数 {name} 长度 {length} 大于最大长度 {max_length}"
        return None
    
    def _validate_array_items(
        self, name: str, value: List, item_pattern: str
    ) -> List[str]:
        """验证数组元素模式"""
        errors = []
        for i, item in enumerate(value):
            if isinstance(item, str) and not re.match(item_pattern, item):
                errors.append(f"参数 {name}[{i}] 值 '{item}' 不匹配模式: {item_pattern}")
        return errors
    
    def _validate_array_item_range(
        self, name: str, value: List, item_range: List
    ) -> List[str]:
        """验证数组元素范围"""
        errors = []
        min_val, max_val = item_range
        for i, item in enumerate(value):
            if isinstance(item, (int, float)):
                if min_val is not None and item < min_val:
                    errors.append(f"参数 {name}[{i}] 值 {item} 小于最小值 {min_val}")
                if max_val is not None and item > max_val:
                    errors.append(f"参数 {name}[{i}] 值 {item} 大于最大值 {max_val}")
        return errors
    
    def _validate_matrix(
        self, name: str, value: Any, validation: Dict
    ) -> List[str]:
        """验证矩阵/DataFrame"""
        errors = []
        
        # 尝试导入pandas
        try:
            import pandas as pd
            
            if isinstance(value, pd.DataFrame):
                # 验证行数
                if 'min_rows' in validation:
                    if len(value) < validation['min_rows']:
                        errors.append(
                            f"参数 {name} 行数 {len(value)} 小于最小行数 {validation['min_rows']}"
                        )
                
                # 验证列数
                if 'min_columns' in validation:
                    if len(value.columns) < validation['min_columns']:
                        errors.append(
                            f"参数 {name} 列数 {len(value.columns)} 小于最小列数 {validation['min_columns']}"
                        )
                
                # 验证必需列
                if 'required_columns' in validation:
                    missing_cols = set(validation['required_columns']) - set(value.columns)
                    if missing_cols:
                        errors.append(f"参数 {name} 缺少必需列: {missing_cols}")
                
                # 验证NaN
                if validation.get('no_nan', False):
                    if value.isna().any().any():
                        nan_cols = value.columns[value.isna().any()].tolist()
                        errors.append(f"参数 {name} 包含NaN值，列: {nan_cols}")
                
                # 验证索引类型
                if 'required_index' in validation:
                    if validation['required_index'] == 'datetime':
                        if not pd.api.types.is_datetime64_any_dtype(value.index):
                            errors.append(f"参数 {name} 索引必须是datetime类型")
        
        except ImportError:
            pass  # pandas未安装，跳过DataFrame验证
        
        return errors


# 单例实例
_validator_instance = None


def get_parameter_validator() -> ParameterValidator:
    """获取参数验证器单例"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = ParameterValidator()
    return _validator_instance
# @AI_GENERATED: end
