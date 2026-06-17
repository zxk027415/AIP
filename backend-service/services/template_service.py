"""
算法模板模板服务

提供模板加载、缓存和管理功能
"""
import json
from typing import List, Dict, Optional
from pathlib import Path


class TemplateService:
    """算法模板模板服务"""
    
    def __init__(self, templates_dir: str = "data/templates"):
        """
        初始化模板服务
        
        Args:
            templates_dir: 模板文件目录
        """
        self.templates_dir = Path(templates_dir)
        self._cache: Dict[str, dict] = {}
        self._load_templates()
    
    def _load_templates(self):
        """从文件系统加载所有模板"""
        if not self.templates_dir.exists():
            print(f"模板目录不存在: {self.templates_dir}")
            return
        
        for template_file in self.templates_dir.glob("*.json"):
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    template = json.load(f)
                    self._cache[template['id']] = template
                    print(f"加载模板: {template['name']}")
            except Exception as e:
                print(f"加载模板失败 {template_file}: {e}")
    
    def get_all_templates(self) -> List[dict]:
        """
        获取所有模板列表
        
        Returns:
            模板列表
        """
        return list(self._cache.values())
    
    def get_template(self, template_id: str) -> Optional[dict]:
        """
        获取指定模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            模板数据，如果不存在返回None
        """
        return self._cache.get(template_id)
    
    def reload_templates(self):
        """重新加载所有模板"""
        self._cache.clear()
        self._load_templates()


# 全局模板服务实例
_template_service: Optional[TemplateService] = None


def get_template_service() -> TemplateService:
    """获取模板服务单例"""
    global _template_service
    if _template_service is None:
        _template_service = TemplateService()
    return _template_service
