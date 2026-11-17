"""
数据可视化节点
生成图表配置用于前端渲染
"""
from typing import Dict, Any, List


class VisualizationNode:
    """数据可视化节点"""
    
    def __init__(self, node_config: Dict[str, Any]):
        """
        初始化可视化节点
        
        Args:
            node_config: 节点配置
        """
        self.chart_type = node_config.get('chartType')
        self.chart_config = node_config.get('config', {})
    
    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成可视化配置
        
        Args:
            inputs: 输入数据
            
        Returns:
            Dict[str, Any]: 可视化配置
        """
        # 1. 获取输入数据
        data = self._extract_data(inputs)
        
        # 2. 验证数据格式
        self._validate_data(data)
        
        # 3. 构建图表配置
        chart_config = self._build_chart_config(data)
        
        return chart_config
    
    def _extract_data(self, inputs: Dict[str, Any]) -> Any:
        """
        从输入中提取数据
        
        Args:
            inputs: 输入数据
            
        Returns:
            Any: 提取的数据
        """
        # 尝试从不同的输入键获取数据
        if 'data' in inputs:
            return inputs['data']
        elif 'input' in inputs:
            return inputs['input']
        elif len(inputs) == 1:
            # 如果只有一个输入，使用它
            return list(inputs.values())[0]
        else:
            # 使用所有输入
            return inputs
    
    def _validate_data(self, data: Any):
        """
        验证数据格式
        
        Args:
            data: 数据
            
        Raises:
            ValueError: 如果数据格式无效
        """
        if data is None:
            raise ValueError("No data provided for visualization")
        
        # 根据图表类型验证数据格式
        if self.chart_type in ['line', 'bar', 'scatter']:
            # 这些图表需要数组或对象数据
            if not isinstance(data, (list, dict)):
                raise ValueError(f"Invalid data format for {self.chart_type} chart")
    
    def _build_chart_config(self, data: Any) -> Dict[str, Any]:
        """
        根据数据和图表类型构建配置
        
        Args:
            data: 数据
            
        Returns:
            Dict[str, Any]: 图表配置
        """
        base_config = {
            "type": self.chart_type,
            "data": data,
            "config": self.chart_config
        }
        
        # 根据图表类型添加特定配置
        if self.chart_type == 'line':
            return self._build_line_chart_config(data, base_config)
        elif self.chart_type == 'bar':
            return self._build_bar_chart_config(data, base_config)
        elif self.chart_type == 'scatter':
            return self._build_scatter_chart_config(data, base_config)
        else:
            return base_config
    
    def _build_line_chart_config(self, data: Any, base_config: Dict[str, Any]) -> Dict[str, Any]:
        """构建折线图配置"""
        config = base_config.copy()
        
        # 添加折线图特定配置
        config['options'] = {
            'xAxis': self.chart_config.get('xAxis', 'x'),
            'yAxis': self.chart_config.get('yAxis', 'y'),
            'title': self.chart_config.get('title', '折线图'),
            'smooth': self.chart_config.get('smooth', True),
            'showPoints': self.chart_config.get('showPoints', True)
        }
        
        return config
    
    def _build_bar_chart_config(self, data: Any, base_config: Dict[str, Any]) -> Dict[str, Any]:
        """构建柱状图配置"""
        config = base_config.copy()
        
        # 添加柱状图特定配置
        config['options'] = {
            'xAxis': self.chart_config.get('xAxis', 'x'),
            'yAxis': self.chart_config.get('yAxis', 'y'),
            'title': self.chart_config.get('title', '柱状图'),
            'horizontal': self.chart_config.get('horizontal', False),
            'stacked': self.chart_config.get('stacked', False)
        }
        
        return config
    
    def _build_scatter_chart_config(self, data: Any, base_config: Dict[str, Any]) -> Dict[str, Any]:
        """构建散点图配置"""
        config = base_config.copy()
        
        # 添加散点图特定配置
        config['options'] = {
            'xAxis': self.chart_config.get('xAxis', 'x'),
            'yAxis': self.chart_config.get('yAxis', 'y'),
            'title': self.chart_config.get('title', '散点图'),
            'pointSize': self.chart_config.get('pointSize', 5),
            'showTrendLine': self.chart_config.get('showTrendLine', False)
        }
        
        return config
