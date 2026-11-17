# @AI_GENERATED: Kiro v1.0
"""
ScenarioAnalyzeAgent - 场景分析子 Agent
专门负责分析业务场景，细化需求
"""
import json
import os
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ScenarioAnalyzeAgent:
    """
    场景分析 Agent
    
    职责：
    1. 分析用户描述的业务场景
    2. 识别场景类型和数据需求
    3. 提出细化问题帮助明确需求
    4. 推荐技术方案
    """
    
    def __init__(self):
        self.backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self._scenario_knowledge = None
    
    def _load_scenario_knowledge(self) -> Dict[str, Any]:
        """加载场景知识库"""
        if self._scenario_knowledge is not None:
            return self._scenario_knowledge
        
        scenarios_path = os.path.join(self.backend_dir, "data/forecast_scenarios.json")
        if os.path.exists(scenarios_path):
            with open(scenarios_path, "r", encoding="utf-8") as f:
                self._scenario_knowledge = json.load(f)
        else:
            self._scenario_knowledge = {}
        
        return self._scenario_knowledge
    
    async def analyze(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        分析业务场景
        
        参数:
            query: 用户描述
            context: 上下文信息
        
        返回:
        {
            "scenario_type": str,  # 场景类型
            "energy_type": str,  # 能源类型（如适用）
            "forecast_type": str,  # 预测类型（如适用）
            "data_requirements": [...],  # 数据需求
            "recommended_approach": str,  # 推荐方案
            "clarification_questions": [...],  # 细化问题
        }
        """
        context = context or {}
        knowledge = self._load_scenario_knowledge()
        
        # 识别场景类型
        scenario_type = self._identify_scenario_type(query)
        
        # 识别能源类型
        energy_type = self._identify_energy_type(query)
        
        # 识别预测类型
        forecast_type = self._identify_forecast_type(query)
        
        # 获取数据需求
        data_requirements = self._get_data_requirements(scenario_type, energy_type, forecast_type, knowledge)
        
        # 生成推荐方案
        recommended_approach = self._generate_recommendation(scenario_type, energy_type, forecast_type, knowledge)
        
        # 生成细化问题
        clarification_questions = self._generate_clarification_questions(
            query, scenario_type, energy_type, forecast_type, context
        )
        
        return {
            "scenario_type": scenario_type,
            "energy_type": energy_type,
            "forecast_type": forecast_type,
            "data_requirements": data_requirements,
            "recommended_approach": recommended_approach,
            "clarification_questions": clarification_questions,
        }
    
    def _identify_scenario_type(self, query: str) -> str:
        """识别场景类型"""
        query_lower = query.lower()
        
        scenario_keywords = {
            "power_forecast": ["功率预测", "发电预测", "出力预测", "power forecast", "功率", "发电功率"],
            "load_forecast": ["负荷预测", "用电预测", "load forecast", "负荷"],
            "fault_diagnosis": ["故障诊断", "故障检测", "异常检测", "fault"],
            "quality_inspection": ["质量检测", "缺陷检测", "视觉检测", "quality"],
            "energy_optimization": ["能耗优化", "节能", "能效", "optimization"],
            "soc_estimation": ["soc", "荷电状态", "电池状态", "state of charge"],
            "carbon_accounting": ["碳核算", "碳排放", "碳足迹", "carbon"],
        }
        
        for scenario, keywords in scenario_keywords.items():
            if any(kw in query_lower for kw in keywords):
                return scenario
        
        return "general"
    
    def _identify_energy_type(self, query: str) -> Optional[str]:
        """识别能源类型"""
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in ["光伏", "pv", "solar", "太阳能"]):
            return "pv"
        elif any(kw in query_lower for kw in ["风电", "wind", "风力"]):
            return "wind"
        elif any(kw in query_lower for kw in ["储能", "电池", "battery"]):
            return "storage"
        elif any(kw in query_lower for kw in ["火电", "thermal", "燃煤"]):
            return "thermal"
        
        return None
    
    def _identify_forecast_type(self, query: str) -> Optional[str]:
        """识别预测类型"""
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in ["超短期", "实时", "15分钟", "0-4小时", "agc"]):
            return "ultra_short_term"
        elif any(kw in query_lower for kw in ["短期", "日前", "24小时", "day-ahead"]):
            return "short_term"
        elif any(kw in query_lower for kw in ["中长期", "月度", "年度", "长期"]):
            return "medium_long_term"
        
        return None
    
    def _get_data_requirements(
        self, 
        scenario_type: str, 
        energy_type: Optional[str],
        forecast_type: Optional[str],
        knowledge: Dict[str, Any]
    ) -> List[str]:
        """获取数据需求"""
        requirements = []
        
        # 基于场景类型的通用需求
        scenario_requirements = {
            "power_forecast": [
                "历史发电功率数据（至少30天）",
                "气象数据（辐照度、温度、风速等）",
                "设备参数（装机容量、倾角等）",
            ],
            "load_forecast": [
                "历史负荷数据（至少1年）",
                "气象数据（温度、湿度）",
                "日历特征（节假日、工作日）",
            ],
            "fault_diagnosis": [
                "设备运行数据（振动、温度、电流等）",
                "历史故障记录",
                "设备参数和规格",
            ],
            "quality_inspection": [
                "产品图像数据",
                "缺陷标注数据",
                "产品规格参数",
            ],
            "soc_estimation": [
                "电池充放电数据",
                "电压、电流、温度数据",
                "电池参数（容量、内阻等）",
            ],
        }
        
        requirements = scenario_requirements.get(scenario_type, ["请提供相关业务数据"])
        
        # 基于预测类型的额外需求
        if forecast_type:
            forecast_info = knowledge.get("forecast_types", {}).get(forecast_type, {})
            data_req = forecast_info.get("data_requirements", {})
            if data_req.get("history_length"):
                requirements.append(f"历史数据长度：{data_req['history_length']}")
            if data_req.get("update_frequency"):
                requirements.append(f"数据更新频率：{data_req['update_frequency']}")
        
        return requirements
    
    def _generate_recommendation(
        self, 
        scenario_type: str, 
        energy_type: Optional[str],
        forecast_type: Optional[str],
        knowledge: Dict[str, Any]
    ) -> str:
        """生成推荐方案"""
        recommendations = {
            "power_forecast": {
                "pv": "推荐使用 Ridge 回归或 XGBoost 进行光伏功率预测，结合气象特征工程",
                "wind": "推荐使用 LSTM 或 GRU 进行风电功率预测，捕捉时序特征",
                "default": "推荐使用集成学习方法进行功率预测",
            },
            "load_forecast": {
                "default": "推荐使用 XGBoost 或 LightGBM 进行负荷预测，结合日历和气象特征",
            },
            "fault_diagnosis": {
                "default": "推荐使用随机森林或 XGBoost 进行故障分类，结合特征工程",
            },
            "quality_inspection": {
                "default": "推荐使用 CNN 进行图像缺陷检测，如 ResNet 或 YOLO",
            },
            "soc_estimation": {
                "default": "推荐使用 LSTM 或卡尔曼滤波进行 SOC 估计",
            },
        }
        
        scenario_rec = recommendations.get(scenario_type, {})
        if energy_type and energy_type in scenario_rec:
            return scenario_rec[energy_type]
        return scenario_rec.get("default", "请描述更多细节，我将为您推荐合适的方案")
    
    def _generate_clarification_questions(
        self, 
        query: str,
        scenario_type: str, 
        energy_type: Optional[str],
        forecast_type: Optional[str],
        context: Dict[str, Any]
    ) -> List[str]:
        """生成细化问题"""
        questions = []
        
        # 如果未识别能源类型
        if scenario_type == "power_forecast" and not energy_type:
            questions.append("请问是光伏发电还是风力发电？")
        
        # 如果未识别预测类型
        if scenario_type in ["power_forecast", "load_forecast"] and not forecast_type:
            questions.append("请问需要什么时间尺度的预测？（超短期/短期/中长期）")
        
        # 数据相关问题
        if "数据" not in query.lower():
            questions.append("您目前有哪些可用的数据？")
        
        # 精度要求
        if "精度" not in query.lower() and "mape" not in query.lower():
            questions.append("对预测精度有什么要求？（如 MAPE < 10%）")
        
        # 业务场景
        if scenario_type == "power_forecast" and "调度" not in query.lower() and "交易" not in query.lower():
            questions.append("预测结果主要用于什么业务场景？（电网调度/电力交易/场站运营）")
        
        return questions[:3]  # 最多返回3个问题
# @AI_GENERATED: end
