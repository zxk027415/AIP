# @AI_GENERATED: Kiro v1.0
"""
行业场景重构脚本
- 删除4个通用能力场景（general-manufacturing, industrial-data-analysis, industrial-llm, industrial-vision, equipment-health）
- 新增4个行业场景（thermal-power, semiconductor, chemical-process, water-environment）
- 更新 industry_scenarios.json 和 industry_templates.json
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# 新的13个行业场景定义
NEW_SCENARIOS = [
    {
        "id": "renewable-energy",
        "name": "新能源发电",
        "icon": "🔆",
        "description": "光伏/风电功率预测、设备故障诊断、发电资源评估、概率预测",
        "industry_tags": ["新能源"],
        "capabilities": ["功率预测", "故障诊断", "资源评估", "概率预测"],
        "template_count": 17,
        "function_count": 52,
        "color": "#faad14",
        "sort_order": 1
    },
    {
        "id": "thermal-power",
        "name": "火力发电",
        "icon": "🔥",
        "description": "燃烧优化、煤耗优化、煤价预测、库存预测、供应链优化、设备健康、环保监测",
        "industry_tags": ["传统能源"],
        "capabilities": ["燃烧优化", "煤耗优化", "煤价预测", "设备健康", "环保监测"],
        "template_count": 25,
        "function_count": 45,
        "color": "#fa541c",
        "sort_order": 2
    },
    {
        "id": "energy-storage",
        "name": "储能管理",
        "icon": "🔋",
        "description": "SOC/SOH估计、调度优化、寿命预测、安全预警、热管理",
        "industry_tags": ["新能源"],
        "capabilities": ["SOC估计", "调度优化", "寿命预测", "安全预警"],
        "template_count": 15,
        "function_count": 36,
        "color": "#52c41a",
        "sort_order": 3
    },
    {
        "id": "power-grid",
        "name": "电网与微网",
        "icon": "⚡",
        "description": "负荷预测、调度优化、电能质量分析、异常检测",
        "industry_tags": ["源网荷储"],
        "capabilities": ["负荷预测", "调度优化", "异常检测"],
        "template_count": 20,
        "function_count": 42,
        "color": "#1890ff",
        "sort_order": 4
    },
    {
        "id": "steel-manufacturing",
        "name": "钢铁制造",
        "icon": "🏭",
        "description": "质量预测、工艺优化、缺陷检测、轧制力预测、设备健康",
        "industry_tags": ["工业制造"],
        "capabilities": ["质量预测", "工艺优化", "缺陷检测", "设备健康"],
        "template_count": 17,
        "function_count": 38,
        "color": "#722ed1",
        "sort_order": 5
    },
    {
        "id": "pv-manufacturing",
        "name": "光伏制造",
        "icon": "☀️",
        "description": "缺陷检测、效率预测、良率优化、隐裂检测、EL图像分析",
        "industry_tags": ["工业制造"],
        "capabilities": ["缺陷检测", "效率预测", "良率优化"],
        "template_count": 13,
        "function_count": 30,
        "color": "#eb2f96",
        "sort_order": 6
    },
    {
        "id": "battery-manufacturing",
        "name": "动力电池",
        "icon": "🔌",
        "description": "一致性分析、安全预测、工艺优化、寿命预测",
        "industry_tags": ["工业制造"],
        "capabilities": ["一致性分析", "安全预测", "工艺优化"],
        "template_count": 10,
        "function_count": 32,
        "color": "#13c2c2",
        "sort_order": 7
    },
    {
        "id": "semiconductor",
        "name": "半导体制造",
        "icon": "💾",
        "description": "良率预测、缺陷检测、工艺优化、设备健康、晶圆检测",
        "industry_tags": ["工业制造"],
        "capabilities": ["良率预测", "缺陷检测", "工艺优化", "设备健康"],
        "template_count": 15,
        "function_count": 35,
        "color": "#2f54eb",
        "sort_order": 8
    },
    {
        "id": "chemical-process",
        "name": "化工流程",
        "icon": "⚗️",
        "description": "工艺优化、安全预警、质量预测、能耗优化、反应器优化",
        "industry_tags": ["工业制造"],
        "capabilities": ["工艺优化", "安全预警", "质量预测", "能耗优化"],
        "template_count": 15,
        "function_count": 35,
        "color": "#fadb14",
        "sort_order": 9
    },
    {
        "id": "port-logistics",
        "name": "港口运输",
        "icon": "🚢",
        "description": "泊位调度、AGV路径规划、能耗优化、吞吐预测",
        "industry_tags": ["港口运输"],
        "capabilities": ["泊位调度", "路径规划", "能耗优化"],
        "template_count": 10,
        "function_count": 26,
        "color": "#fa8c16",
        "sort_order": 10
    },
    {
        "id": "building-campus",
        "name": "楼宇园区",
        "icon": "🏢",
        "description": "暖通优化、能源审计、负荷预测、需求响应",
        "industry_tags": ["楼宇园区"],
        "capabilities": ["暖通优化", "能源审计", "负荷预测"],
        "template_count": 11,
        "function_count": 28,
        "color": "#a0d911",
        "sort_order": 11
    },
    {
        "id": "carbon-management",
        "name": "碳管理",
        "icon": "🌱",
        "description": "碳核算、碳交易策略、碳足迹追踪、减排优化",
        "industry_tags": ["碳管理"],
        "capabilities": ["碳核算", "碳交易", "碳足迹追踪"],
        "template_count": 12,
        "function_count": 22,
        "color": "#389e0d",
        "sort_order": 12
    },
    {
        "id": "water-environment",
        "name": "水务环保",
        "icon": "💧",
        "description": "水质预测、管网优化、污染检测、能耗优化、污水处理",
        "industry_tags": ["公用事业"],
        "capabilities": ["水质预测", "管网优化", "污染检测", "能耗优化"],
        "template_count": 12,
        "function_count": 28,
        "color": "#1890ff",
        "sort_order": 13
    }
]

# 新增场景的模板定义
NEW_TEMPLATES = {
    "thermal-power": [
        # 发电预测
        {"id": "thermal_power_forecast", "name": "火力发电功率预测", "display_category": "发电预测", "description": "基于负荷、煤质、机组状态预测发电功率"},
        {"id": "unit_output_forecast", "name": "机组出力预测", "display_category": "发电预测", "description": "预测单台机组的出力曲线"},
        {"id": "peak_shaving_capacity", "name": "调峰能力预测", "display_category": "发电预测", "description": "评估机组调峰能力和响应速度"},
        {"id": "startup_time_predict", "name": "启停时间预测", "display_category": "发电预测", "description": "预测机组冷态/热态启动时间"},
        # 燃烧优化
        {"id": "combustion_optimize", "name": "锅炉燃烧优化", "display_category": "燃烧优化", "description": "优化风煤配比、燃烧器摆角等参数"},
        {"id": "coal_blending_optimize", "name": "配煤掺烧优化", "display_category": "燃烧优化", "description": "多煤种掺烧比例优化"},
        {"id": "air_fuel_ratio_optimize", "name": "风煤比优化", "display_category": "燃烧优化", "description": "优化一二次风配比"},
        {"id": "oxygen_content_optimize", "name": "氧量优化", "display_category": "燃烧优化", "description": "烟气含氧量优化控制"},
        # 燃料供应链
        {"id": "coal_price_forecast", "name": "煤价预测", "display_category": "燃料供应链", "description": "基于市场数据预测煤炭价格走势"},
        {"id": "coal_inventory_forecast", "name": "煤炭库存预测", "display_category": "燃料供应链", "description": "预测煤炭库存消耗和补充需求"},
        {"id": "coal_transport_optimize", "name": "煤炭运输路径优化", "display_category": "燃料供应链", "description": "优化煤炭运输路线和方式"},
        {"id": "supplier_selection", "name": "供应商优选", "display_category": "燃料供应链", "description": "基于质量、价格、信誉的供应商评估"},
        {"id": "coal_procurement_optimize", "name": "煤炭采购优化", "display_category": "燃料供应链", "description": "采购时机和数量优化"},
        # 设备健康
        {"id": "turbine_vibration_diagnose", "name": "汽轮机振动诊断", "display_category": "设备健康", "description": "基于振动信号的故障诊断"},
        {"id": "boiler_tube_leak_predict", "name": "四管泄漏预警", "display_category": "设备健康", "description": "锅炉四管泄漏早期预警"},
        {"id": "generator_fault_diagnose", "name": "发电机故障诊断", "display_category": "设备健康", "description": "发电机电气和机械故障诊断"},
        {"id": "bearing_temp_predict", "name": "轴承温度预测", "display_category": "设备健康", "description": "关键轴承温度趋势预测"},
        # 能效优化
        {"id": "coal_consumption_optimize", "name": "供电煤耗优化", "display_category": "能效优化", "description": "降低供电标准煤耗"},
        {"id": "auxiliary_power_optimize", "name": "厂用电率优化", "display_category": "能效优化", "description": "降低厂用电消耗"},
        {"id": "thermal_efficiency_optimize", "name": "热效率优化", "display_category": "能效优化", "description": "提高锅炉热效率"},
        {"id": "condenser_vacuum_optimize", "name": "凝汽器真空优化", "display_category": "能效优化", "description": "优化凝汽器真空度"},
        # 环保监测
        {"id": "desulfur_efficiency_predict", "name": "脱硫效率预测", "display_category": "环保监测", "description": "预测脱硫系统效率"},
        {"id": "denox_efficiency_predict", "name": "脱硝效率预测", "display_category": "环保监测", "description": "预测脱硝系统效率"},
        {"id": "emission_predict", "name": "烟气排放预测", "display_category": "环保监测", "description": "预测SO2、NOx、粉尘排放"},
        # 安全预警
        {"id": "boiler_flameout_warn", "name": "锅炉灭火预警", "display_category": "安全预警", "description": "锅炉灭火早期预警"},
    ],
    "semiconductor": [
        {"id": "wafer_yield_predict", "name": "晶圆良率预测", "display_category": "良率预测", "description": "基于工艺参数预测晶圆良率"},
        {"id": "die_yield_predict", "name": "芯片良率预测", "display_category": "良率预测", "description": "预测单个芯片的良率"},
        {"id": "wafer_defect_detect", "name": "晶圆缺陷检测", "display_category": "缺陷检测", "description": "基于图像的晶圆缺陷检测"},
        {"id": "pattern_defect_classify", "name": "图案缺陷分类", "display_category": "缺陷检测", "description": "光刻图案缺陷分类"},
        {"id": "particle_contamination_detect", "name": "颗粒污染检测", "display_category": "缺陷检测", "description": "检测晶圆表面颗粒污染"},
        {"id": "etch_process_optimize", "name": "刻蚀工艺优化", "display_category": "工艺优化", "description": "优化刻蚀工艺参数"},
        {"id": "cvd_process_optimize", "name": "CVD工艺优化", "display_category": "工艺优化", "description": "化学气相沉积工艺优化"},
        {"id": "cmp_process_optimize", "name": "CMP工艺优化", "display_category": "工艺优化", "description": "化学机械抛光工艺优化"},
        {"id": "lithography_optimize", "name": "光刻工艺优化", "display_category": "工艺优化", "description": "光刻曝光参数优化"},
        {"id": "equipment_pm_predict", "name": "设备PM预测", "display_category": "设备健康", "description": "预测设备预防性维护时间"},
        {"id": "chamber_clean_predict", "name": "腔室清洗预测", "display_category": "设备健康", "description": "预测反应腔室清洗时机"},
        {"id": "consumable_life_predict", "name": "耗材寿命预测", "display_category": "设备健康", "description": "预测关键耗材剩余寿命"},
        {"id": "virtual_metrology", "name": "虚拟量测", "display_category": "质量预测", "description": "基于工艺数据预测量测结果"},
        {"id": "run_to_run_control", "name": "批次间控制", "display_category": "工艺优化", "description": "批次间工艺参数自动调整"},
        {"id": "fault_detection_classify", "name": "故障检测分类", "display_category": "设备健康", "description": "设备故障检测与分类"},
    ],
    "chemical-process": [
        {"id": "reactor_optimize", "name": "反应器优化", "display_category": "工艺优化", "description": "化学反应器参数优化"},
        {"id": "distillation_optimize", "name": "精馏塔优化", "display_category": "工艺优化", "description": "精馏塔操作参数优化"},
        {"id": "heat_exchanger_optimize", "name": "换热器优化", "display_category": "工艺优化", "description": "换热网络优化"},
        {"id": "yield_predict", "name": "产品收率预测", "display_category": "质量预测", "description": "预测化工产品收率"},
        {"id": "quality_predict", "name": "产品质量预测", "display_category": "质量预测", "description": "预测产品质量指标"},
        {"id": "energy_consumption_optimize", "name": "能耗优化", "display_category": "能效优化", "description": "化工过程能耗优化"},
        {"id": "steam_system_optimize", "name": "蒸汽系统优化", "display_category": "能效优化", "description": "蒸汽管网优化"},
        {"id": "leak_detection", "name": "泄漏检测", "display_category": "安全预警", "description": "管道和设备泄漏检测"},
        {"id": "corrosion_predict", "name": "腐蚀预测", "display_category": "安全预警", "description": "设备腐蚀速率预测"},
        {"id": "runaway_reaction_warn", "name": "失控反应预警", "display_category": "安全预警", "description": "化学反应失控早期预警"},
        {"id": "emission_control", "name": "排放控制优化", "display_category": "环保监测", "description": "VOCs等排放控制优化"},
        {"id": "catalyst_life_predict", "name": "催化剂寿命预测", "display_category": "设备健康", "description": "预测催化剂剩余寿命"},
        {"id": "pump_fault_diagnose", "name": "泵故障诊断", "display_category": "设备健康", "description": "化工泵故障诊断"},
        {"id": "compressor_fault_diagnose", "name": "压缩机故障诊断", "display_category": "设备健康", "description": "压缩机故障诊断"},
        {"id": "batch_process_optimize", "name": "间歇过程优化", "display_category": "工艺优化", "description": "间歇化工过程优化"},
    ],
    "water-environment": [
        {"id": "water_quality_predict", "name": "水质预测", "display_category": "水质预测", "description": "预测出水水质指标"},
        {"id": "cod_predict", "name": "COD预测", "display_category": "水质预测", "description": "预测化学需氧量"},
        {"id": "ammonia_nitrogen_predict", "name": "氨氮预测", "display_category": "水质预测", "description": "预测氨氮浓度"},
        {"id": "pipe_network_optimize", "name": "管网优化", "display_category": "管网优化", "description": "供水管网压力优化"},
        {"id": "leak_location", "name": "漏损定位", "display_category": "管网优化", "description": "管网漏损点定位"},
        {"id": "pump_schedule_optimize", "name": "泵站调度优化", "display_category": "管网优化", "description": "供水泵站调度优化"},
        {"id": "dosing_optimize", "name": "加药优化", "display_category": "工艺优化", "description": "污水处理加药量优化"},
        {"id": "aeration_optimize", "name": "曝气优化", "display_category": "工艺优化", "description": "曝气量优化控制"},
        {"id": "sludge_predict", "name": "污泥产量预测", "display_category": "工艺优化", "description": "预测污泥产生量"},
        {"id": "energy_consumption_optimize", "name": "能耗优化", "display_category": "能效优化", "description": "污水处理能耗优化"},
        {"id": "odor_predict", "name": "臭气预测", "display_category": "环保监测", "description": "预测臭气浓度"},
        {"id": "effluent_compliance_predict", "name": "出水达标预测", "display_category": "环保监测", "description": "预测出水是否达标"},
    ],
}

# 要删除的场景ID
SCENARIOS_TO_REMOVE = {
    "general-manufacturing",
    "industrial-data-analysis", 
    "industrial-llm",
    "industrial-vision",
    "equipment-health",
}


def update_scenarios():
    """更新 industry_scenarios.json"""
    scenarios_path = DATA_DIR / "industry_scenarios.json"
    
    with open(scenarios_path, "w", encoding="utf-8") as f:
        json.dump(NEW_SCENARIOS, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 更新 industry_scenarios.json: {len(NEW_SCENARIOS)} 个场景")


def update_templates():
    """更新 industry_templates.json"""
    templates_path = DATA_DIR / "industry_templates.json"
    
    with open(templates_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 删除旧场景的模板
    original_count = len(data["templates"])
    data["templates"] = [t for t in data["templates"] if t["scenario_id"] not in SCENARIOS_TO_REMOVE]
    removed_count = original_count - len(data["templates"])
    
    # 添加新场景的模板
    added_count = 0
    for scenario_id, templates in NEW_TEMPLATES.items():
        for tpl in templates:
            data["templates"].append({
                "id": tpl["id"],
                "name": tpl["name"],
                "scenario_id": scenario_id,
                "display_category": tpl["display_category"],
                "description": tpl.get("description", tpl["name"]),
                "default_workflows": []
            })
            added_count += 1
    
    # 更新总数
    data["total_templates"] = len(data["templates"])
    data["_comment"] = "行业算法模板数据（重构后）。13个行业场景，纯行业维度分类。"
    
    with open(templates_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 更新 industry_templates.json:")
    print(f"   删除模板: {removed_count}")
    print(f"   新增模板: {added_count}")
    print(f"   总模板数: {data['total_templates']}")
    
    # 统计各场景模板数
    scenario_counts = {}
    for t in data["templates"]:
        sid = t["scenario_id"]
        scenario_counts[sid] = scenario_counts.get(sid, 0) + 1
    
    print("\n各场景模板数:")
    for sid, count in sorted(scenario_counts.items()):
        print(f"   {sid}: {count}")


def main():
    print("=" * 50)
    print("行业场景重构")
    print("=" * 50)
    
    update_scenarios()
    update_templates()
    
    print("\n✅ 重构完成!")


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
