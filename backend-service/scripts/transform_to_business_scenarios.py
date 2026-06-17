# @AI_GENERATED: Kiro v1.0
"""
将算法方案从技术方案（high-accuracy等）转换为业务场景方案（集中式光伏等）
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# 业务场景方案映射
BUSINESS_SCENARIOS = {
    # 光伏发电功率预测
    "pv_power_forecast": [
        {"id": "centralized_pv", "name": "集中式光伏电站", "description": "大型地面光伏电站功率预测"},
        {"id": "distributed_pv", "name": "分布式光伏", "description": "屋顶分布式光伏功率预测"},
        {"id": "floating_pv", "name": "水面光伏", "description": "水上漂浮式光伏电站功率预测"},
    ],
    # 风电功率预测
    "wind_power_forecast": [
        {"id": "onshore_wind", "name": "陆上风电", "description": "陆上风电场功率预测"},
        {"id": "offshore_wind", "name": "海上风电", "description": "海上风电场功率预测"},
        {"id": "distributed_wind", "name": "分散式风电", "description": "分散式风电功率预测"},
    ],
    # 电力负荷预测
    "load_forecast": [
        {"id": "industrial_load", "name": "工业负荷", "description": "工业园区电力负荷预测"},
        {"id": "commercial_load", "name": "商业负荷", "description": "商业建筑电力负荷预测"},
        {"id": "residential_load", "name": "居民负荷", "description": "居民区电力负荷预测"},
    ],
    # 逆变器故障诊断
    "inverter_fault": [
        {"id": "string_inverter", "name": "组串式逆变器", "description": "组串式逆变器故障诊断"},
        {"id": "central_inverter", "name": "集中式逆变器", "description": "集中式逆变器故障诊断"},
        {"id": "micro_inverter", "name": "微型逆变器", "description": "微型逆变器故障诊断"},
    ],
    # 光伏组件故障分类
    "pv_module_fault": [
        {"id": "mono_module", "name": "单晶硅组件", "description": "单晶硅光伏组件故障分类"},
        {"id": "poly_module", "name": "多晶硅组件", "description": "多晶硅光伏组件故障分类"},
        {"id": "thin_film", "name": "薄膜组件", "description": "薄膜光伏组件故障分类"},
    ],
    # 风机故障诊断
    "wind_turbine_fault": [
        {"id": "gearbox_fault", "name": "齿轮箱故障", "description": "风机齿轮箱故障诊断"},
        {"id": "generator_fault", "name": "发电机故障", "description": "风机发电机故障诊断"},
        {"id": "blade_fault", "name": "叶片故障", "description": "风机叶片故障诊断"},
    ],
    # 发电模式聚类
    "generation_pattern": [
        {"id": "seasonal_pattern", "name": "季节性模式", "description": "按季节特征聚类发电模式"},
        {"id": "weather_pattern", "name": "气象模式", "description": "按气象条件聚类发电模式"},
        {"id": "load_pattern", "name": "负荷模式", "description": "按负荷特征聚类发电模式"},
    ],
    # 气象模式聚类
    "weather_pattern": [
        {"id": "solar_radiation", "name": "辐照模式", "description": "太阳辐照强度模式聚类"},
        {"id": "wind_speed", "name": "风速模式", "description": "风速变化模式聚类"},
        {"id": "temperature", "name": "温度模式", "description": "温度变化模式聚类"},
    ],
    # 孤岛检测
    "island_detection": [
        {"id": "passive_detection", "name": "被动检测", "description": "被动式孤岛检测方案"},
        {"id": "active_detection", "name": "主动检测", "description": "主动式孤岛检测方案"},
        {"id": "hybrid_detection", "name": "混合检测", "description": "混合式孤岛检测方案"},
    ],
    # 光伏电站监控
    "pv_station_monitor": [
        {"id": "real_time_monitor", "name": "实时监控", "description": "光伏电站实时运行监控"},
        {"id": "performance_monitor", "name": "性能监控", "description": "光伏电站性能指标监控"},
        {"id": "alarm_monitor", "name": "告警监控", "description": "光伏电站告警事件监控"},
    ],
    # 风电场监控
    "wind_farm_monitor": [
        {"id": "turbine_monitor", "name": "风机监控", "description": "单台风机运行状态监控"},
        {"id": "farm_monitor", "name": "场站监控", "description": "整场风电运行监控"},
        {"id": "grid_monitor", "name": "并网监控", "description": "风电并网状态监控"},
    ],
    # 发电计划编制
    "generation_planning": [
        {"id": "day_ahead", "name": "日前计划", "description": "日前发电计划编制"},
        {"id": "intraday", "name": "日内计划", "description": "日内发电计划滚动修正"},
        {"id": "real_time", "name": "实时调度", "description": "实时发电调度优化"},
    ],
}

# 默认业务场景（用于没有特定映射的模板）
DEFAULT_SCENARIOS = [
    {"id": "standard", "name": "标准场景", "description": "标准应用场景"},
    {"id": "complex", "name": "复杂场景", "description": "复杂环境应用场景"},
    {"id": "edge", "name": "边缘场景", "description": "边缘计算应用场景"},
]


def transform_templates():
    """转换模板数据结构"""
    with open(os.path.join(DATA_DIR, "industry_templates.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
    
    new_templates = []
    
    for tpl in data["templates"]:
        tpl_id = tpl["id"]
        
        # 获取业务场景列表
        scenarios = BUSINESS_SCENARIOS.get(tpl_id, DEFAULT_SCENARIOS)
        
        # 创建新的业务场景方案
        business_scenarios = []
        for scenario in scenarios:
            business_scenarios.append({
                "id": scenario["id"],
                "name": scenario["name"],
                "description": scenario["description"],
                "mounted_workflows": [],  # 挂载的算法模板
            })
        
        # 更新模板
        new_tpl = {
            "id": tpl["id"],
            "name": tpl["name"],
            "scenario_id": tpl["scenario_id"],
            "display_category": tpl["display_category"],
            "description": tpl["description"],
            "business_scenarios": business_scenarios,
            # 保留原有的default_workflows作为参考
            "reference_workflows": tpl.get("default_workflows", []),
        }
        new_templates.append(new_tpl)
    
    # 保存新数据
    new_data = {
        "_comment": "行业算法方案库。每个算法方案包含多个业务场景，每个业务场景可挂载多个算法模板。",
        "total_templates": len(new_templates),
        "templates": new_templates,
    }
    
    # 备份原文件
    backup_path = os.path.join(DATA_DIR, "industry_templates_backup.json")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已备份原文件到: {backup_path}")
    
    # 保存新文件
    with open(os.path.join(DATA_DIR, "industry_templates.json"), "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    print(f"已更新模板文件，共 {len(new_templates)} 个算法方案")
    
    return new_data


if __name__ == "__main__":
    transform_templates()
# @AI_GENERATED: end
