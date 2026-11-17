# @AI_GENERATED: Kiro v1.0
"""
清理非AI算法方案 - 从 industry_templates.json 中剔除非AI方案
"""
import json
from pathlib import Path

# 需要剔除的模板ID列表（非AI方案）
TEMPLATES_TO_REMOVE = {
    # 新能源发电 (renewable-energy) - 7个
    "pv_plant_monitor", "wind_farm_monitor", "generation_schedule",
    "curtailment_analyze", "capacity_factor", "soiling_loss_estimate", "performance_ratio",
    # 储能管理 (energy-storage) - 2个
    "energy_throughput", "cell_balancing",
    # 电网与微网 (power-grid) - 10个
    "flicker_analyze", "sag_swell_detect", "frequency_deviation", "phase_angle_analyze",
    "symmetrical_component", "power_flow_calc", "short_circuit_calc", "loss_reduction",
    "protection_coordination", "dg_integration",
    # 钢铁制造 (steel-manufacturing) - 3个
    "energy_balance", "surface_inspect", "steel_grade_classifier",
    # 光伏制造 (pv-manufacturing) - 2个
    "cell_sorting", "module_assembly_check",
    # 动力电池 (battery-manufacturing) - 2个
    "voltage_test", "resistance_test",
    # 工业制造(通用) (general-manufacturing) - 4个
    "production_report", "shift_handover", "work_order_manage", "material_tracking",
    # 港口运输 (port-logistics) - 3个
    "gate_management", "document_process", "customs_clearance",
    # 楼宇园区 (building-campus) - 3个
    "water_management", "fire_detection", "access_control",
    # 碳管理 (carbon-management) - 4个
    "carbon_report", "compliance_check", "carbon_data_collect", "carbon_dashboard",
    # 工业可视化 (industrial-visualization) - 19个
    "scada_dashboard", "energy_flow_diagram", "single_line_diagram", "pid_diagram",
    "geo_map_chart", "3d_scatter_chart", "polar_chart", "gauge_chart",
    "thermal_map", "equipment_status_board", "interactive_dashboard", "realtime_chart",
    "drill_down_chart", "chart_annotation", "multi_axis_chart", "subplot_layout",
    "chart_theme", "chart_export", "report_template",
    # 工业智能(LLM) (industrial-llm) - 2个
    "prompt_template", "llm_config",
    # 工业视觉 (industrial-vision) - 2个
    "image_preprocess", "camera_calibration",
    # 设备健康管理 (equipment-health) - 4个
    "maintenance_record", "work_order_create", "equipment_register", "inspection_checklist",
}

def main():
    data_path = Path(__file__).parent.parent / "data" / "industry_templates.json"
    
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    original_count = len(data["templates"])
    
    # 过滤掉非AI方案
    data["templates"] = [t for t in data["templates"] if t["id"] not in TEMPLATES_TO_REMOVE]
    
    # 更新 industrial-visualization 为 industrial-data-analysis
    for t in data["templates"]:
        if t["scenario_id"] == "industrial-visualization":
            t["scenario_id"] = "industrial-data-analysis"
    
    new_count = len(data["templates"])
    removed_count = original_count - new_count
    
    # 更新总数
    data["total_templates"] = new_count
    data["_comment"] = "行业算法模板数据（优化后）。层级：行业场景(L1) → 场景算法模板(L2) → 竞争算法模板(L3，由基础模块L4搭建)。display_category 仅用于前端展示分组。已剔除非AI方案。"
    
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 清理完成！")
    print(f"   原始模板数: {original_count}")
    print(f"   剔除模板数: {removed_count}")
    print(f"   剩余模板数: {new_count}")
    
    # 统计各场景模板数
    scenario_counts = {}
    for t in data["templates"]:
        sid = t["scenario_id"]
        scenario_counts[sid] = scenario_counts.get(sid, 0) + 1
    
    print("\n各场景模板数:")
    for sid, count in sorted(scenario_counts.items()):
        print(f"   {sid}: {count}")

if __name__ == "__main__":
    main()
# @AI_GENERATED: end
