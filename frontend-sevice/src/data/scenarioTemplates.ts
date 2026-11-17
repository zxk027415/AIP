// @AI_GENERATED: Kiro v1.0
/**
 * 行业场景模板函数数据
 * 数据来源：docs/algorithm-library-split.md 第二、三部分
 * 每个场景的模板函数按子分类分组，函数名称和顺序与文档保持一致
 */

export interface TemplateFunction {
  id: string;
  name: string;
  scenario: string;
}

export interface TemplateCategory {
  category: string;
  color: string;
  functions: TemplateFunction[];
}

export type ScenarioTemplateMap = Record<string, TemplateCategory[]>;

const SCENARIO_TEMPLATES: ScenarioTemplateMap = {
  'renewable-energy': [
    {
      category: '能源预测',
      color: '#faad14',
      functions: [
        { id: 'pv_power_forecast', name: '光伏发电功率预测', scenario: '新能源发电' },
        { id: 'wind_power_forecast', name: '风电功率预测', scenario: '新能源发电' },
        { id: 'load_demand_forecast', name: '电力负荷预测', scenario: '源网荷储' },
        { id: 'electricity_price_forecast', name: '电价预测', scenario: '能源交易' },
      ],
    },
    {
      category: '故障诊断',
      color: '#f5222d',
      functions: [
        { id: 'inverter_fault_classifier', name: '逆变器故障诊断', scenario: '新能源发电' },
        { id: 'pv_module_fault_classifier', name: '光伏组件故障分类', scenario: '新能源发电' },
        { id: 'wind_turbine_fault_classifier', name: '风机故障诊断', scenario: '新能源发电' },
        { id: 'transformer_fault_classifier', name: '变压器故障诊断', scenario: '电力设备' },
      ],
    },
    {
      category: '工业聚类',
      color: '#722ed1',
      functions: [
        { id: 'generation_pattern_cluster', name: '发电模式聚类', scenario: '新能源发电' },
        { id: 'weather_pattern_cluster', name: '气象模式聚类', scenario: '新能源发电' },
      ],
    },
    {
      category: '电力信号分析',
      color: '#1890ff',
      functions: [
        { id: 'islanding_detect', name: '孤岛检测', scenario: '新能源发电' },
        { id: 'power_quality_analyze', name: '电能质量分析', scenario: '电网/微网' },
      ],
    },
    {
      category: '发电侧管理',
      color: '#52c41a',
      functions: [
        { id: 'pv_plant_monitor', name: '光伏电站监控', scenario: '新能源发电' },
        { id: 'wind_farm_monitor', name: '风电场监控', scenario: '新能源发电' },
        { id: 'generation_schedule', name: '发电计划编制', scenario: '新能源发电' },
        { id: 'curtailment_analyze', name: '弃风弃光分析', scenario: '新能源发电' },
        { id: 'resource_assessment', name: '资源评估', scenario: '新能源发电' },
        { id: 'capacity_factor', name: '容量因子计算', scenario: '新能源发电' },
        { id: 'wake_effect_model', name: '尾流效应模型', scenario: '新能源发电' },
        { id: 'soiling_loss_estimate', name: '灰尘损失估计', scenario: '新能源发电' },
        { id: 'inverter_clipping', name: '逆变器限幅分析', scenario: '新能源发电' },
        { id: 'string_mismatch', name: '组串失配分析', scenario: '新能源发电' },
        { id: 'performance_ratio', name: '性能比计算', scenario: '新能源发电' },
        { id: 'degradation_rate', name: '衰减率分析', scenario: '新能源发电' },
      ],
    },
  ],
  'energy-storage': [
    {
      category: '能源预测',
      color: '#faad14',
      functions: [
        { id: 'battery_soc_forecast', name: '储能SOC预测', scenario: '储能管理' },
        { id: 'load_demand_forecast', name: '电力负荷预测', scenario: '源网荷储' },
      ],
    },
    {
      category: '异常检测',
      color: '#f5222d',
      functions: [
        { id: 'battery_anomaly_detect', name: '电池异常检测', scenario: '储能/电池' },
        { id: 'thermal_anomaly_detect', name: '热异常检测', scenario: '设备管理' },
      ],
    },
    {
      category: '故障诊断',
      color: '#eb2f96',
      functions: [
        { id: 'battery_fault_classifier', name: '电池故障分类', scenario: '储能/电池' },
        { id: 'fault_severity_classifier', name: '故障严重度分级', scenario: '通用工业' },
      ],
    },
    {
      category: '调度优化',
      color: '#1890ff',
      functions: [
        { id: 'battery_schedule', name: '储能调度优化', scenario: '储能管理' },
        { id: 'ev_charging_schedule', name: '电动车充电调度', scenario: '源网荷储' },
      ],
    },
    {
      category: '储能管理',
      color: '#52c41a',
      functions: [
        { id: 'soc_estimate', name: 'SOC估计', scenario: '储能管理' },
        { id: 'soh_estimate', name: 'SOH估计', scenario: '储能管理' },
        { id: 'rul_battery', name: '电池寿命预测', scenario: '储能管理' },
        { id: 'thermal_management', name: '热管理优化', scenario: '储能管理' },
        { id: 'cell_balancing', name: '电芯均衡策略', scenario: '储能管理' },
        { id: 'charge_strategy', name: '充电策略优化', scenario: '储能管理' },
        { id: 'capacity_fade_model', name: '容量衰减模型', scenario: '储能管理' },
        { id: 'impedance_estimate', name: '阻抗估计', scenario: '储能管理' },
        { id: 'safety_warning', name: '安全预警', scenario: '储能管理' },
        { id: 'energy_throughput', name: '能量吞吐统计', scenario: '储能管理' },
      ],
    },
  ],
  'power-grid': [
    {
      category: '电力信号分析',
      color: '#1890ff',
      functions: [
        { id: 'power_quality_analyze', name: '电能质量分析', scenario: '电网/微网' },
        { id: 'flicker_analyze', name: '闪变分析', scenario: '电网/微网' },
        { id: 'sag_swell_detect', name: '暂降暂升检测', scenario: '电网/微网' },
        { id: 'transient_analyze', name: '暂态分析', scenario: '电力设备' },
        { id: 'frequency_deviation', name: '频率偏差分析', scenario: '电网/微网' },
        { id: 'phase_angle_analyze', name: '相角分析', scenario: '电力设备' },
        { id: 'symmetrical_component', name: '对称分量分析', scenario: '电力设备' },
        { id: 'impedance_analyze', name: '阻抗分析', scenario: '电力设备' },
        { id: 'partial_discharge_analyze', name: '局部放电分析', scenario: '电力设备' },
        { id: 'traveling_wave_analyze', name: '行波分析', scenario: '电网/微网' },
        { id: 'pmu_data_analyze', name: 'PMU数据分析', scenario: '电网/微网' },
        { id: 'power_oscillation_detect', name: '功率振荡检测', scenario: '电网/微网' },
        { id: 'islanding_detect', name: '孤岛检测', scenario: '新能源发电' },
      ],
    },
    {
      category: '能源调度优化',
      color: '#722ed1',
      functions: [
        { id: 'unit_commitment', name: '机组组合优化', scenario: '电网/微网' },
        { id: 'economic_dispatch', name: '经济调度', scenario: '电网/微网' },
        { id: 'optimal_power_flow', name: '最优潮流', scenario: '电网/微网' },
        { id: 'microgrid_dispatch', name: '微网调度优化', scenario: '微网/新电网' },
        { id: 'vpp_dispatch', name: '虚拟电厂调度', scenario: '源网荷储' },
      ],
    },
    {
      category: '电网与微网管理',
      color: '#52c41a',
      functions: [
        { id: 'power_flow_calc', name: '潮流计算', scenario: '电网/微网' },
        { id: 'short_circuit_calc', name: '短路计算', scenario: '电网/微网' },
        { id: 'voltage_stability', name: '电压稳定分析', scenario: '电网/微网' },
        { id: 'frequency_regulation', name: '频率调节', scenario: '电网/微网' },
        { id: 'reactive_power_optimize', name: '无功优化', scenario: '电网/微网' },
        { id: 'network_reconfiguration', name: '网络重构', scenario: '电网/微网' },
        { id: 'fault_location', name: '故障定位', scenario: '电网/微网' },
        { id: 'protection_coordination', name: '保护协调', scenario: '电网/微网' },
        { id: 'dg_integration', name: '分布式电源接入', scenario: '电网/微网' },
        { id: 'grid_resilience', name: '电网韧性评估', scenario: '电网/微网' },
        { id: 'loss_reduction', name: '线损分析', scenario: '电网/微网' },
        { id: 'contingency_analysis', name: '预想事故分析', scenario: '电网/微网' },
      ],
    },
    {
      category: '异常检测',
      color: '#f5222d',
      functions: [
        { id: 'power_quality_anomaly', name: '电能质量异常检测', scenario: '电网/微网' },
        { id: 'grid_anomaly_detect', name: '电网异常检测', scenario: '电网/微网' },
      ],
    },
  ],
  'steel-manufacturing': [
    {
      category: '工业过程优化',
      color: '#722ed1',
      functions: [
        { id: 'process_parameter_optimize', name: '工艺参数优化', scenario: '工业制造' },
        { id: 'production_schedule', name: '生产排程优化', scenario: '工业制造' },
        { id: 'cutting_stock_optimize', name: '下料优化', scenario: '钢铁行业' },
        { id: 'blend_optimize', name: '配料优化', scenario: '钢铁/电池' },
        { id: 'job_shop_schedule', name: '作业车间调度', scenario: '工业制造' },
      ],
    },
    {
      category: '钢铁行业专用',
      color: '#2f54eb',
      functions: [
        { id: 'steel_quality_predict', name: '钢材质量预测', scenario: '钢铁制造' },
        { id: 'steel_defect_classify', name: '钢材缺陷分类', scenario: '钢铁制造' },
        { id: 'rolling_force_predict', name: '轧制力预测', scenario: '钢铁制造' },
        { id: 'temperature_model', name: '温度场模型', scenario: '钢铁制造' },
        { id: 'composition_optimize', name: '成分优化', scenario: '钢铁制造' },
        { id: 'energy_balance', name: '能量平衡计算', scenario: '钢铁制造' },
        { id: 'yield_optimize', name: '成材率优化', scenario: '钢铁制造' },
        { id: 'furnace_optimize', name: '加热炉优化', scenario: '钢铁制造' },
        { id: 'cooling_control', name: '冷却控制', scenario: '钢铁制造' },
        { id: 'surface_inspect', name: '表面检测', scenario: '钢铁制造' },
      ],
    },
    {
      category: '故障诊断',
      color: '#f5222d',
      functions: [
        { id: 'steel_grade_classifier', name: '钢材牌号分类', scenario: '钢铁行业' },
        { id: 'product_quality_classifier', name: '产品质量分级', scenario: '工业制造' },
        { id: 'bearing_fault_classifier', name: '轴承故障诊断', scenario: '旋转设备' },
      ],
    },
    {
      category: '工业视觉',
      color: '#eb2f96',
      functions: [
        { id: 'steel_surface_defect', name: '钢材表面缺陷检测', scenario: '钢铁制造' },
        { id: 'hot_rolled_defect', name: '热轧缺陷检测', scenario: '钢铁制造' },
      ],
    },
  ],
  'pv-manufacturing': [
    {
      category: '光伏制造专用',
      color: '#eb2f96',
      functions: [
        { id: 'cell_efficiency_predict', name: '电池片效率预测', scenario: '光伏制造' },
        { id: 'wafer_defect_detect', name: '硅片缺陷检测', scenario: '光伏制造' },
        { id: 'el_image_analyze', name: 'EL图像分析', scenario: '光伏制造' },
        { id: 'color_sorting', name: '色选分级', scenario: '光伏制造' },
        { id: 'string_welding_inspect', name: '串焊检测', scenario: '光伏制造' },
        { id: 'lamination_quality', name: '层压质量检测', scenario: '光伏制造' },
        { id: 'iv_curve_analyze', name: 'IV曲线分析', scenario: '光伏制造' },
        { id: 'module_power_predict', name: '组件功率预测', scenario: '光伏制造' },
      ],
    },
    {
      category: '工业视觉',
      color: '#f5222d',
      functions: [
        { id: 'pv_cell_defect', name: '光伏电池缺陷检测', scenario: '光伏制造' },
        { id: 'micro_crack_detect', name: '隐裂检测', scenario: '光伏制造' },
        { id: 'hotspot_detect', name: '热斑检测', scenario: '光伏制造' },
      ],
    },
    {
      category: '故障诊断',
      color: '#faad14',
      functions: [
        { id: 'pv_module_fault_classifier', name: '光伏组件故障分类', scenario: '新能源发电' },
        { id: 'inverter_fault_classifier', name: '逆变器故障诊断', scenario: '新能源发电' },
        { id: 'degradation_stage_classifier', name: '退化阶段分类', scenario: '设备管理' },
      ],
    },
    {
      category: '工艺优化',
      color: '#52c41a',
      functions: [
        { id: 'process_parameter_optimize', name: '工艺参数优化', scenario: '工业制造' },
        { id: 'energy_efficiency_optimize', name: '能效优化', scenario: '能源管理' },
      ],
    },
  ],
  'battery-manufacturing': [
    {
      category: '动力电池制造专用',
      color: '#13c2c2',
      functions: [
        { id: 'cell_consistency', name: '电芯一致性分析', scenario: '电池制造' },
        { id: 'formation_optimize', name: '化成工艺优化', scenario: '电池制造' },
        { id: 'electrode_quality', name: '极片质量检测', scenario: '电池制造' },
        { id: 'electrolyte_optimize', name: '电解液配方优化', scenario: '电池制造' },
        { id: 'capacity_grading', name: '容量分选', scenario: '电池制造' },
        { id: 'self_discharge_test', name: '自放电测试', scenario: '电池制造' },
        { id: 'nail_penetration_sim', name: '针刺仿真', scenario: '电池制造' },
        { id: 'cycle_life_predict', name: '循环寿命预测', scenario: '电池制造' },
      ],
    },
    {
      category: '故障诊断',
      color: '#f5222d',
      functions: [
        { id: 'battery_fault_classifier', name: '电池故障分类', scenario: '储能/电池' },
        { id: 'fault_severity_classifier', name: '故障严重度分级', scenario: '通用工业' },
        { id: 'thermal_fault_classifier', name: '热故障分类', scenario: '通用工业' },
        { id: 'degradation_stage_classifier', name: '退化阶段分类', scenario: '设备管理' },
      ],
    },
    {
      category: '异常检测',
      color: '#faad14',
      functions: [
        { id: 'battery_anomaly_detect', name: '电池异常检测', scenario: '储能/电池' },
        { id: 'thermal_anomaly_detect', name: '热异常检测', scenario: '设备管理' },
        { id: 'process_anomaly', name: '工艺过程异常', scenario: '工业制造' },
      ],
    },
    {
      category: '工艺优化',
      color: '#52c41a',
      functions: [
        { id: 'blend_optimize', name: '配料优化', scenario: '钢铁/电池' },
        { id: 'process_parameter_optimize', name: '工艺参数优化', scenario: '工业制造' },
        { id: 'energy_efficiency_optimize', name: '能效优化', scenario: '能源管理' },
      ],
    },
  ],
  // @AI_GENERATED: Kiro v1.0
  'thermal-power': [
    {
      category: '燃料供应链',
      color: '#fa541c',
      functions: [
        { id: 'coal_price_forecast', name: '煤价预测', scenario: '火力发电' },
        { id: 'coal_inventory_forecast', name: '煤炭库存预测', scenario: '火力发电' },
        { id: 'coal_transport_optimize', name: '煤炭运输路径优化', scenario: '火力发电' },
        { id: 'supplier_selection', name: '供应商优选', scenario: '火力发电' },
        { id: 'coal_procurement_optimize', name: '煤炭采购优化', scenario: '火力发电' },
        { id: 'coal_quality_predict', name: '煤质预测', scenario: '火力发电' },
      ],
    },
    {
      category: '发电预测与优化',
      color: '#faad14',
      functions: [
        { id: 'thermal_power_forecast', name: '火力发电预测', scenario: '火力发电' },
        { id: 'load_demand_forecast', name: '电力负荷预测', scenario: '源网荷储' },
        { id: 'combustion_optimize', name: '燃烧优化', scenario: '火力发电' },
        { id: 'coal_consumption_optimize', name: '煤耗优化', scenario: '火力发电' },
        { id: 'boiler_efficiency', name: '锅炉效率优化', scenario: '火力发电' },
        { id: 'turbine_efficiency', name: '汽轮机效率优化', scenario: '火力发电' },
      ],
    },
    {
      category: '设备健康管理',
      color: '#f5222d',
      functions: [
        { id: 'boiler_fault_classifier', name: '锅炉故障诊断', scenario: '火力发电' },
        { id: 'turbine_fault_classifier', name: '汽轮机故障诊断', scenario: '火力发电' },
        { id: 'pump_fault_classifier', name: '泵故障诊断', scenario: '工业制造' },
        { id: 'fan_fault_classifier', name: '风机故障诊断', scenario: '火力发电' },
        { id: 'remaining_useful_life', name: '剩余寿命预测', scenario: '设备管理' },
      ],
    },
    {
      category: '环保监测',
      color: '#52c41a',
      functions: [
        { id: 'emission_predict', name: '排放预测', scenario: '火力发电' },
        { id: 'desulfurization_optimize', name: '脱硫优化', scenario: '火力发电' },
        { id: 'denitrification_optimize', name: '脱硝优化', scenario: '火力发电' },
        { id: 'dust_removal_optimize', name: '除尘优化', scenario: '火力发电' },
      ],
    },
  ],
  // @AI_GENERATED: end
  'port-logistics': [
    {
      category: '港口与运输专用',
      color: '#fa8c16',
      functions: [
        { id: 'berth_allocation', name: '泊位分配优化', scenario: '港口运输' },
        { id: 'agv_path_plan', name: 'AGV路径规划', scenario: '港口运输' },
        { id: 'crane_schedule', name: '岸桥调度', scenario: '港口运输' },
        { id: 'yard_management', name: '堆场管理', scenario: '港口运输' },
        { id: 'vessel_schedule', name: '船舶调度', scenario: '港口运输' },
        { id: 'container_tracking', name: '集装箱追踪', scenario: '港口运输' },
        { id: 'throughput_forecast', name: '吞吐量预测', scenario: '港口运输' },
        { id: 'port_energy_manage', name: '港口能耗管理', scenario: '港口运输' },
      ],
    },
    {
      category: '工业过程优化',
      color: '#722ed1',
      functions: [
        { id: 'logistics_route_optimize', name: '物流路径优化', scenario: '港口运输' },
        { id: 'bin_packing_optimize', name: '装箱优化', scenario: '港口运输' },
        { id: 'production_schedule', name: '生产排程优化', scenario: '工业制造' },
        { id: 'maintenance_schedule', name: '检修计划优化', scenario: '设备管理' },
        { id: 'inventory_optimize', name: '库存优化', scenario: '工业制造' },
        { id: 'energy_efficiency_optimize', name: '能效优化', scenario: '能源管理' },
        { id: 'pid_tune', name: 'PID参数整定', scenario: '通用工业' },
      ],
    },
  ],
  'building-campus': [
    {
      category: '楼宇园区专用',
      color: '#a0d911',
      functions: [
        { id: 'hvac_control', name: '暖通空调控制', scenario: '楼宇园区' },
        { id: 'lighting_optimize', name: '照明优化', scenario: '楼宇园区' },
        { id: 'energy_audit', name: '能源审计', scenario: '楼宇园区' },
        { id: 'comfort_index', name: '舒适度指数', scenario: '楼宇园区' },
        { id: 'occupancy_detect', name: '人员检测', scenario: '楼宇园区' },
        { id: 'elevator_optimize', name: '电梯调度优化', scenario: '楼宇园区' },
        { id: 'water_management', name: '水务管理', scenario: '楼宇园区' },
        { id: 'fire_detection', name: '消防检测', scenario: '楼宇园区' },
      ],
    },
    {
      category: '工业过程优化',
      color: '#722ed1',
      functions: [
        { id: 'hvac_optimize', name: '暖通空调优化', scenario: '楼宇园区' },
        { id: 'energy_efficiency_optimize', name: '能效优化', scenario: '能源管理' },
        { id: 'setpoint_optimize', name: '设定值优化', scenario: '通用工业' },
        { id: 'pid_tune', name: 'PID参数整定', scenario: '通用工业' },
      ],
    },
    {
      category: '负荷与需求侧管理',
      color: '#1890ff',
      functions: [
        { id: 'load_forecast', name: '负荷预测', scenario: '源网荷储' },
        { id: 'demand_response', name: '需求响应', scenario: '源网荷储' },
        { id: 'peak_shaving', name: '削峰填谷', scenario: '源网荷储' },
        { id: 'energy_baseline', name: '能耗基线', scenario: '源网荷储' },
      ],
    },
  ],
  'carbon-management': [
    {
      category: '碳管理与综合能源',
      color: '#389e0d',
      functions: [
        { id: 'carbon_accounting', name: '碳核算', scenario: '碳管理' },
        { id: 'carbon_footprint', name: '碳足迹追踪', scenario: '碳管理' },
        { id: 'carbon_trading_strategy', name: '碳交易策略', scenario: '碳管理' },
        { id: 'carbon_quota_manage', name: '碳配额管理', scenario: '碳管理' },
        { id: 'emission_factor', name: '排放因子计算', scenario: '碳管理' },
        { id: 'carbon_sink_estimate', name: '碳汇估算', scenario: '碳管理' },
        { id: 'green_certificate', name: '绿证管理', scenario: '碳管理' },
        { id: 'carbon_report', name: '碳报告生成', scenario: '碳管理' },
        { id: 'reduction_path', name: '减排路径规划', scenario: '碳管理' },
        { id: 'carbon_neutral_plan', name: '碳中和方案', scenario: '碳管理' },
      ],
    },
    {
      category: '能源调度优化',
      color: '#722ed1',
      functions: [
        { id: 'carbon_emission_optimize', name: '碳排放优化', scenario: '碳管理' },
        { id: 'energy_trading_optimize', name: '电力交易优化', scenario: '能源交易' },
        { id: 'demand_response_optimize', name: '需求响应优化', scenario: '源网荷储' },
        { id: 'economic_dispatch', name: '经济调度', scenario: '电网/微网' },
      ],
    },
  ],
  // @AI_GENERATED: Kiro v1.0
  'semiconductor': [
    {
      category: '良率与质量',
      color: '#2f54eb',
      functions: [
        { id: 'yield_predict', name: '良率预测', scenario: '半导体制造' },
        { id: 'wafer_defect_detect', name: '晶圆缺陷检测', scenario: '半导体制造' },
        { id: 'die_quality_classify', name: '芯片质量分级', scenario: '半导体制造' },
        { id: 'bin_map_analysis', name: 'Bin Map分析', scenario: '半导体制造' },
        { id: 'cp_test_analysis', name: 'CP测试分析', scenario: '半导体制造' },
        { id: 'ft_test_analysis', name: 'FT测试分析', scenario: '半导体制造' },
      ],
    },
    {
      category: '工艺优化',
      color: '#722ed1',
      functions: [
        { id: 'process_parameter_optimize', name: '工艺参数优化', scenario: '半导体制造' },
        { id: 'recipe_optimize', name: '配方优化', scenario: '半导体制造' },
        { id: 'etch_endpoint_detect', name: '刻蚀终点检测', scenario: '半导体制造' },
        { id: 'cmp_optimize', name: 'CMP优化', scenario: '半导体制造' },
        { id: 'lithography_optimize', name: '光刻优化', scenario: '半导体制造' },
        { id: 'deposition_optimize', name: '薄膜沉积优化', scenario: '半导体制造' },
      ],
    },
    {
      category: '设备健康',
      color: '#f5222d',
      functions: [
        { id: 'chamber_health', name: '腔室健康监测', scenario: '半导体制造' },
        { id: 'pm_schedule', name: 'PM计划优化', scenario: '半导体制造' },
        { id: 'equipment_fault_classifier', name: '设备故障诊断', scenario: '半导体制造' },
        { id: 'remaining_useful_life', name: '剩余寿命预测', scenario: '设备管理' },
      ],
    },
  ],
  'chemical-process': [
    {
      category: '工艺优化',
      color: '#fadb14',
      functions: [
        { id: 'reactor_optimize', name: '反应器优化', scenario: '化工流程' },
        { id: 'distillation_optimize', name: '精馏优化', scenario: '化工流程' },
        { id: 'heat_exchanger_optimize', name: '换热器优化', scenario: '化工流程' },
        { id: 'process_parameter_optimize', name: '工艺参数优化', scenario: '化工流程' },
        { id: 'yield_optimize', name: '收率优化', scenario: '化工流程' },
        { id: 'energy_efficiency_optimize', name: '能效优化', scenario: '化工流程' },
      ],
    },
    {
      category: '安全预警',
      color: '#f5222d',
      functions: [
        { id: 'safety_predict', name: '安全预警', scenario: '化工流程' },
        { id: 'leak_detect', name: '泄漏检测', scenario: '化工流程' },
        { id: 'runaway_predict', name: '失控反应预测', scenario: '化工流程' },
        { id: 'hazop_analysis', name: 'HAZOP分析', scenario: '化工流程' },
        { id: 'alarm_management', name: '报警管理优化', scenario: '化工流程' },
      ],
    },
    {
      category: '质量预测',
      color: '#52c41a',
      functions: [
        { id: 'product_quality_predict', name: '产品质量预测', scenario: '化工流程' },
        { id: 'soft_sensor', name: '软测量', scenario: '化工流程' },
        { id: 'blend_optimize', name: '调合优化', scenario: '化工流程' },
        { id: 'batch_quality_predict', name: '批次质量预测', scenario: '化工流程' },
      ],
    },
  ],
  'water-environment': [
    {
      category: '水质预测',
      color: '#1890ff',
      functions: [
        { id: 'water_quality_predict', name: '水质预测', scenario: '水务环保' },
        { id: 'cod_predict', name: 'COD预测', scenario: '水务环保' },
        { id: 'bod_predict', name: 'BOD预测', scenario: '水务环保' },
        { id: 'turbidity_predict', name: '浊度预测', scenario: '水务环保' },
        { id: 'ammonia_nitrogen_predict', name: '氨氮预测', scenario: '水务环保' },
      ],
    },
    {
      category: '管网优化',
      color: '#722ed1',
      functions: [
        { id: 'pipe_network_optimize', name: '管网优化', scenario: '水务环保' },
        { id: 'leak_detect', name: '漏损检测', scenario: '水务环保' },
        { id: 'pressure_optimize', name: '压力优化', scenario: '水务环保' },
        { id: 'pump_schedule', name: '泵站调度', scenario: '水务环保' },
        { id: 'demand_forecast', name: '用水需求预测', scenario: '水务环保' },
      ],
    },
    {
      category: '污水处理',
      color: '#52c41a',
      functions: [
        { id: 'aeration_optimize', name: '曝气优化', scenario: '水务环保' },
        { id: 'dosing_optimize', name: '加药优化', scenario: '水务环保' },
        { id: 'sludge_predict', name: '污泥预测', scenario: '水务环保' },
        { id: 'effluent_quality_predict', name: '出水水质预测', scenario: '水务环保' },
        { id: 'energy_efficiency_optimize', name: '能耗优化', scenario: '水务环保' },
      ],
    },
  ],
  // @AI_GENERATED: end
};

export default SCENARIO_TEMPLATES;
// @AI_GENERATED: end
