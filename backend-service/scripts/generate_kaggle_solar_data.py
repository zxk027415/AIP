# @AI_GENERATED: Kiro v1.0
"""
生成模拟 Kaggle 印度太阳能发电数据集

基于 Kaggle 数据集: https://www.kaggle.com/anikannal/solar-power-generation-data
该数据集包含印度两个太阳能发电站 34 天的数据

特征说明:
- DATE_TIME: 时间戳 (15分钟间隔)
- PLANT_ID: 电站ID
- SOURCE_KEY: 逆变器ID
- DC_POWER: 直流功率 (kW) - 预测目标
- AC_POWER: 交流功率 (kW)
- DAILY_YIELD: 当日累计发电量 (kWh)
- TOTAL_YIELD: 总累计发电量 (kWh)
- AMBIENT_TEMPERATURE: 环境温度 (°C)
- MODULE_TEMPERATURE: 组件温度 (°C)
- IRRADIATION: 辐照度 (kW/m²)
"""
import os
import csv
import math
import random
from datetime import datetime, timedelta


def generate_solar_data():
    """生成模拟的太阳能发电数据"""
    
    # 数据参数
    start_date = datetime(2020, 5, 15)
    days = 34
    interval_minutes = 15
    samples_per_day = 24 * 60 // interval_minutes  # 96 samples per day
    
    # 电站参数 (模拟两个电站)
    plants = [
        {'id': 'Plant_1', 'capacity': 5000, 'efficiency': 0.85},  # 5MW
        {'id': 'Plant_2', 'capacity': 4000, 'efficiency': 0.82},  # 4MW
    ]
    
    # 逆变器数量
    inverters_per_plant = 22
    
    data = []
    
    for plant in plants:
        plant_id = plant['id']
        capacity = plant['capacity']
        efficiency = plant['efficiency']
        
        # 为每个逆变器生成数据
        for inv_idx in range(inverters_per_plant):
            source_key = f"{plant_id}_INV_{inv_idx + 1}"
            inv_capacity = capacity / inverters_per_plant
            
            total_yield = random.uniform(500000, 800000)  # 初始累计发电量
            
            for day in range(days):
                current_date = start_date + timedelta(days=day)
                daily_yield = 0
                
                for sample in range(samples_per_day):
                    current_time = current_date + timedelta(minutes=sample * interval_minutes)
                    hour = current_time.hour + current_time.minute / 60
                    
                    # 计算太阳位置因子 (简化模型)
                    # 日出约6点，日落约18点，正午12点最强
                    if 6 <= hour <= 18:
                        sun_factor = math.sin((hour - 6) * math.pi / 12)
                    else:
                        sun_factor = 0
                    
                    # 添加天气随机性
                    weather_factor = random.uniform(0.7, 1.0)
                    if random.random() < 0.1:  # 10% 概率多云
                        weather_factor *= random.uniform(0.3, 0.7)
                    
                    # 计算辐照度 (kW/m²)
                    max_irradiation = 1.2  # 最大辐照度
                    irradiation = max_irradiation * sun_factor * weather_factor
                    irradiation = max(0, irradiation + random.gauss(0, 0.02))
                    
                    # 环境温度 (°C) - 日变化
                    base_temp = 25 + 5 * math.sin((hour - 6) * math.pi / 12)
                    ambient_temp = base_temp + random.gauss(0, 2)
                    
                    # 组件温度 (通常比环境温度高)
                    module_temp = ambient_temp + irradiation * 25 + random.gauss(0, 1)
                    
                    # 温度效率系数 (温度越高效率越低)
                    temp_coeff = 1 - 0.004 * max(0, module_temp - 25)
                    
                    # 计算直流功率 (kW)
                    dc_power = inv_capacity * irradiation * efficiency * temp_coeff * weather_factor
                    dc_power = max(0, dc_power + random.gauss(0, dc_power * 0.02))
                    
                    # 计算交流功率 (逆变器效率约96%)
                    inverter_efficiency = 0.96
                    ac_power = dc_power * inverter_efficiency
                    
                    # 累计发电量
                    energy_increment = dc_power * (interval_minutes / 60)  # kWh
                    daily_yield += energy_increment
                    total_yield += energy_increment
                    
                    data.append({
                        'DATE_TIME': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'PLANT_ID': plant_id,
                        'SOURCE_KEY': source_key,
                        'DC_POWER': round(dc_power, 2),
                        'AC_POWER': round(ac_power, 2),
                        'DAILY_YIELD': round(daily_yield, 2),
                        'TOTAL_YIELD': round(total_yield, 2),
                        'AMBIENT_TEMPERATURE': round(ambient_temp, 2),
                        'MODULE_TEMPERATURE': round(module_temp, 2),
                        'IRRADIATION': round(irradiation, 4),
                    })
    
    return data


def save_generation_data(data, output_path):
    """保存发电数据"""
    columns = ['DATE_TIME', 'PLANT_ID', 'SOURCE_KEY', 'DC_POWER', 'AC_POWER', 
               'DAILY_YIELD', 'TOTAL_YIELD']
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in data:
            writer.writerow({k: row[k] for k in columns})
    
    print(f"发电数据已保存: {output_path}, 共 {len(data)} 条记录")


def save_weather_data(data, output_path):
    """保存传感器/天气数据"""
    columns = ['DATE_TIME', 'PLANT_ID', 'SOURCE_KEY', 'AMBIENT_TEMPERATURE', 
               'MODULE_TEMPERATURE', 'IRRADIATION']
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in data:
            writer.writerow({k: row[k] for k in columns})
    
    print(f"传感器数据已保存: {output_path}, 共 {len(data)} 条记录")


def save_merged_data(data, output_path):
    """保存合并后的完整数据（用于机器学习）"""
    columns = ['DATE_TIME', 'PLANT_ID', 'SOURCE_KEY', 'DC_POWER', 'AC_POWER',
               'DAILY_YIELD', 'TOTAL_YIELD', 'AMBIENT_TEMPERATURE', 
               'MODULE_TEMPERATURE', 'IRRADIATION']
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    
    print(f"合并数据已保存: {output_path}, 共 {len(data)} 条记录")


def create_aggregated_data(data, output_path):
    """
    创建聚合数据（按时间聚合所有逆变器）
    这是用于预测模型的主要数据集
    """
    from collections import defaultdict
    
    # 按时间戳聚合
    time_groups = defaultdict(list)
    for row in data:
        key = (row['DATE_TIME'], row['PLANT_ID'])
        time_groups[key].append(row)
    
    aggregated = []
    for (dt, plant_id), rows in sorted(time_groups.items()):
        n = len(rows)
        agg_row = {
            'DATE_TIME': dt,
            'PLANT_ID': plant_id,
            'DC_POWER': round(sum(r['DC_POWER'] for r in rows), 2),
            'AC_POWER': round(sum(r['AC_POWER'] for r in rows), 2),
            'DAILY_YIELD': round(sum(r['DAILY_YIELD'] for r in rows), 2),
            'AMBIENT_TEMPERATURE': round(sum(r['AMBIENT_TEMPERATURE'] for r in rows) / n, 2),
            'MODULE_TEMPERATURE': round(sum(r['MODULE_TEMPERATURE'] for r in rows) / n, 2),
            'IRRADIATION': round(sum(r['IRRADIATION'] for r in rows) / n, 4),
        }
        aggregated.append(agg_row)
    
    columns = ['DATE_TIME', 'PLANT_ID', 'DC_POWER', 'AC_POWER', 'DAILY_YIELD',
               'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'IRRADIATION']
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in aggregated:
            writer.writerow(row)
    
    print(f"聚合数据已保存: {output_path}, 共 {len(aggregated)} 条记录")
    return aggregated


def main():
    # 输出目录
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')
    os.makedirs(output_dir, exist_ok=True)
    
    print("=" * 60)
    print("生成模拟 Kaggle 印度太阳能发电数据集")
    print("=" * 60)
    
    # 生成数据
    print("\n1. 生成原始数据...")
    data = generate_solar_data()
    print(f"   生成 {len(data)} 条记录")
    
    # 保存各种格式
    print("\n2. 保存数据文件...")
    
    # 发电数据
    gen_path = os.path.join(output_dir, 'kaggle_solar_generation.csv')
    save_generation_data(data, gen_path)
    
    # 传感器数据
    weather_path = os.path.join(output_dir, 'kaggle_solar_weather.csv')
    save_weather_data(data, weather_path)
    
    # 合并数据
    merged_path = os.path.join(output_dir, 'kaggle_solar_merged.csv')
    save_merged_data(data, merged_path)
    
    # 聚合数据（用于ML）
    agg_path = os.path.join(output_dir, 'kaggle_solar_aggregated.csv')
    aggregated = create_aggregated_data(data, agg_path)
    
    # 统计信息
    print("\n3. 数据统计:")
    dc_powers = [r['DC_POWER'] for r in aggregated]
    irradiations = [r['IRRADIATION'] for r in aggregated]
    temps = [r['AMBIENT_TEMPERATURE'] for r in aggregated]
    
    print(f"   DC_POWER: min={min(dc_powers):.2f}, max={max(dc_powers):.2f}, mean={sum(dc_powers)/len(dc_powers):.2f}")
    print(f"   IRRADIATION: min={min(irradiations):.4f}, max={max(irradiations):.4f}")
    print(f"   AMBIENT_TEMP: min={min(temps):.2f}, max={max(temps):.2f}")
    
    print("\n" + "=" * 60)
    print("数据生成完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
