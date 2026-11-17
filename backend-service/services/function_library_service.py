"""
函数库服务
管理函数定义的加载、搜索和访问
"""
import json
from typing import List, Optional, Dict, Union
from pathlib import Path
from models.function import FunctionDefinition, Category

# 与启动工作目录无关：始终相对于本文件定位 backend-service/data/functions.json
_DEFAULT_FUNCTIONS_JSON = Path(__file__).resolve().parent.parent / "data" / "functions.json"


class FunctionLibraryService:
    """函数库服务类"""
    
    def __init__(self, data_file: Optional[Union[str, Path]] = None):
        """
        初始化函数库服务
        
        Args:
            data_file: 函数库数据文件路径；默认使用 backend-service/data/functions.json
        """
        self.data_file = Path(data_file) if data_file is not None else _DEFAULT_FUNCTIONS_JSON
        self._functions: Dict[str, FunctionDefinition] = {}
        self._categories: Dict[str, Category] = {}
        self._loaded = False
    
    def _load_data(self):
        """加载函数库数据"""
        if self._loaded:
            return
        
        if not self.data_file.exists():
            raise FileNotFoundError(f"函数库数据文件不存在: {self.data_file}")
        
        with open(self.data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 加载分类
        for cat_data in data.get('categories', []):
            category = Category(**cat_data)
            self._categories[category.id] = category
        
        # 加载函数
        for func_data in data.get('functions', []):
            function = FunctionDefinition(**func_data)
            self._functions[function.id] = function
        
        self._loaded = True
    
    def get_function(self, function_id: str) -> Optional[FunctionDefinition]:
        """
        获取函数定义
        
        Args:
            function_id: 函数ID
            
        Returns:
            FunctionDefinition: 函数定义，如果不存在则返回 None
        """
        self._load_data()
        return self._functions.get(function_id)
    
    def get_all_functions(self) -> List[FunctionDefinition]:
        """
        获取所有函数定义
        
        Returns:
            List[FunctionDefinition]: 所有函数定义列表
        """
        self._load_data()
        return list(self._functions.values())
    
    def search_functions(
        self, 
        query: Optional[str] = None, 
        category: Optional[str] = None
    ) -> List[FunctionDefinition]:
        """
        搜索函数
        
        Args:
            query: 搜索关键词（在名称和描述中搜索）
            category: 分类ID
            
        Returns:
            List[FunctionDefinition]: 匹配的函数列表
        """
        self._load_data()
        results = list(self._functions.values())
        
        # 按分类过滤
        if category:
            results = [f for f in results if f.category == category]
        
        # 按关键词搜索
        if query:
            query_lower = query.lower()
            results = [
                f for f in results 
                if query_lower in f.name.lower() or query_lower in f.description.lower()
            ]
        
        return results
    
    def get_functions_by_category(self, category_id: str) -> List[FunctionDefinition]:
        """
        获取指定分类下的所有函数
        
        Args:
            category_id: 分类ID
            
        Returns:
            List[FunctionDefinition]: 函数列表
        """
        self._load_data()
        return [f for f in self._functions.values() if f.category == category_id]
    
    def get_category(self, category_id: str) -> Optional[Category]:
        """
        获取分类信息
        
        Args:
            category_id: 分类ID
            
        Returns:
            Category: 分类信息，如果不存在则返回 None
        """
        self._load_data()
        return self._categories.get(category_id)
    
    def get_all_categories(self) -> List[Category]:
        """
        获取所有分类
        
        Returns:
            List[Category]: 所有分类列表
        """
        self._load_data()
        return list(self._categories.values())
    
    def reload(self):
        """重新加载函数库数据"""
        self._loaded = False
        self._functions.clear()
        self._categories.clear()
        self._load_data()


# 全局单例
_function_library_service = None


def get_function_library_service() -> FunctionLibraryService:
    """获取函数库服务单例"""
    global _function_library_service
    if _function_library_service is None:
        _function_library_service = FunctionLibraryService()
    return _function_library_service
