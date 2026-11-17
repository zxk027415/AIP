# @AI_GENERATED: Kiro v1.0
"""
光伏发电功率预测 - 示例数据生成脚本

生成1年的光伏发电模拟数据，包含：
- 气象特征：辐照度、温度、湿度、风速、云量
- 发电功率：基于物理模型计算的模拟功率

数据特点：
- 15分钟间隔，共35,040条数据
- 模拟宁夏银川地区 (38.5°N, 106.2°E)
- 电站容量：10 MW
"""

import math
import random
from datetime import datetime, timedelta
import os
import json
import csv

# 配置参数
PLANT_CAPACITY_KW = 10000  # 10 MW
LATITUDE = 38.5  # 宁夏银川纬度
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 12, 31, 23, 45)
INTERVAL_MINUTES = 15

# 输出路径
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')
OUTPUT_FILE = 'pv_power_data.csv'


def calculate_solar_position(timestamp: datetime, latitude: float) -> tuple:
    """计算太阳位置（简化模型）"""
    day_of_year = timestamp.timetuple().tm_yday
    hour = timestamp.hour + timestamp.minute / 60
    
    # 太阳赤纬角
    declination = 23.45 * math.sin(math.radians(360 * (284 + day_of_year) / 365))
    
    # 时角
    hour_angle = 15 * (hour - 12)
    
    # 太阳高度角
    lat_rad = math.radians(latitude)
    dec_rad = math.radians(declination)
    ha_rad = math.radians(hour_angle)
    
    sin_elevation = (math.sin(lat_rad) * math.sin(dec_rad) + 
                     math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad))
    elevation = math.degrees(math.asin(max(-1, min(1, sin_elevation))))
    
    return max(0, elevation), declination


def generate_irradiance(timestamp: datetime, latitude: float, cloud_cover: float) -> float:
    """生成辐照度数据"""
    elevation, _ = calculate_solar_position(timestamp, latitude)
    
    if elevation <= 0:
        return 0.0
    
    # 晴天辐照度模型
    air_mass = 1 / math.sin(math.radians(max(elevation, 1)))
    clear_sky_irradiance = 1361 * (0.7 ** (air_mass ** 0.678))
    
    # 云量影响
    cloud_factor = 1 - 0.75 * ((cloud_cover / 100) ** 1.5)
    
    # 添加随机波动
    noise = random.gauss(1, 0.05)
    
    irradiance = clear_sky_irradiance * math.sin(math.radians(elevation)) * cloud_factor * noise
    return max(0, irradiance)


def generate_temperature(timestamp: datetime, irradiance: float) -> float:
    """生成温度数据"""
    day_of_year = timestamp.timetuple().tm_yday
    hour = timestamp.hour + timestamp.minute / 60
    
    # 年周期变化 (冬冷夏热)
    annual_variation = 15 * math.cos(2 * math.pi * (day_of_year - 200) / 365)
    
    # 日周期变化
    daily_variation = 8 * math.sin(2 * math.pi * (hour - 6) / 24)
    
    # 辐照度影响
    irradiance_effect = irradiance / 100
    
    # 基础温度 + 变化 + 噪声
    base_temp = 10  # 年平均温度
    noise = random.gauss(0, 2)
    
    temperature = base_temp + annual_variation + daily_variation + irradiance_effect * 0.5 + noise
    return round(temperature, 1)


def generate_humidity(timestamp: datetime, temperature: float) -> float:
    """生成湿度数据"""
    day_of_year = timestamp.timetuple().tm_yday
    
    # 季节变化 (夏季湿度较高)
    seasonal = 20 * math.sin(2 * math.pi * (day_of_year - 100) / 365)
    
    # 温度反相关
    temp_effect = -0.5 * temperature
    
    # 基础湿度 + 变化 + 噪声
    base_humidity = 50
    noise = random.gauss(0, 10)
    
    humidity = base_humidity + seasonal + temp_effect + noise
    return round(max(10, min(95, humidity)), 1)


def generate_wind_speed(timestamp: datetime) -> float:
    """生成风速数据"""
    hour = timestamp.hour
    
    # 日变化 (午后风速较大)
    daily_variation = 2 * math.sin(2 * math.pi * (hour - 6) / 24)
    
    # 基础风速 + 变化 + 噪声
    base_wind = 3
    noise = abs(random.gauss(0, 1.5))
    
    wind_speed = base_wind + daily_variation + noise
    return round(max(0, wind_speed), 1)


def generate_cloud_cover(timestamp: datetime) -> float:
    """生成云量数据"""
    day_of_year = timestamp.timetuple().tm_yday
    
    # 季节变化
    seasonal = 15 * math.sin(2 * math.pi * (day_of_year - 50) / 365)
    
    # 随机天气事件
    if random.random() < 0.1:  # 10%概率多云/阴天
        weather_event = random.uniform(40, 80)
    else:
        weather_event = 0
    
    # 基础云量 + 变化 + 噪声
    base_cloud = 25
    noise = random.gauss(0, 10)
    
    cloud_cover = base_cloud + seasonal + weather_event + noise
    return round(max(0, min(100, cloud_cover)), 1)


def calculate_power(irradiance: float, temperature: float, capacity_kw: float) -> float:
    """计算发电功率"""
    if irradiance <= 0:
        return 0.0
    
    # 标准测试条件 (STC): 1000 W/m², 25°C
    stc_irradiance = 1000
    stc_temperature = 25
    
    # 温度系数 (典型值 -0.4%/°C)
    temp_coefficient = -0.004
    temp_factor = 1 + temp_coefficient * (temperature - stc_temperature)
    
    # 系统效率 (考虑逆变器、线损等)
    system_efficiency = 0.85
    
    # 功率计算
    power = capacity_kw * (irradiance / stc_irradiance) * temp_factor * system_efficiency
    
    # 添加随机波动
    noise = random.gauss(1, 0.02)
    power = power * noise
    
    return round(max(0, min(power, capacity_kw)), 2)


def generate_dataset():
    """生成完整数据集"""
    print("开始生成光伏发电模拟数据...")
    
    # 生成时间序列
    timestamps = []
    current = START_DATE
    while current <= END_DATE:
        timestamps.append(current)
        current += timedelta(minutes=INTERVAL_MINUTES)
    
    print(f"数据点数量: {len(timestamps)}")
    
    data = []
    power_sum = 0
    irradiance_sum = 0
    temp_sum = 0
    irradiance_max = 0
    temp_max = -100
    temp_min = 100
    power_max = 0
    
    for i, ts in enumerate(timestamps):
        if i % 10000 == 0:
            print(f"处理进度: {i}/{len(timestamps)}")
        
        # 生成云量 (先生成，因为影响辐照度)
        cloud_cover = generate_cloud_cover(ts)
        
        # 生成辐照度
        irradiance = generate_irradiance(ts, LATITUDE, cloud_cover)
        
        # 生成温度
        temperature = generate_temperature(ts, irradiance)
        
        # 生成湿度
        humidity = generate_humidity(ts, temperature)
        
        # 生成风速
        wind_speed = generate_wind_speed(ts)
        
        # 计算发电功率
        power = calculate_power(irradiance, temperature, PLANT_CAPACITY_KW)
        
        # 统计
        power_sum += power
        irradiance_sum += irradiance
        temp_sum += temperature
        irradiance_max = max(irradiance_max, irradiance)
        temp_max = max(temp_max, temperature)
        temp_min = min(temp_min, temperature)
        power_max = max(power_max, power)
        
        data.append({
            'timestamp': ts.strftime('%Y-%m-%d %H:%M:%S'),
            'irradiance': round(irradiance, 2),
            'temperature': temperature,
            'humidity': humidity,
            'wind_speed': wind_speed,
            'cloud_cover': cloud_cover,
            'power_actual': power
        })
    
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 保存CSV
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'irradiance', 'temperature', 'humidity', 'wind_speed', 'cloud_cover', 'power_actual'])
        writer.writeheader()
        writer.writerows(data)
    print(f"数据已保存到: {output_path}")
    
    # 计算统计信息
    n = len(data)
    stats = {
        'total_records': n,
        'date_range': {
            'start': data[0]['timestamp'],
            'end': data[-1]['timestamp']
        },
        'plant_capacity_kw': PLANT_CAPACITY_KW,
        'location': {
            'latitude': LATITUDE,
            'region': '宁夏银川'
        },
        'statistics': {
            'irradiance': {
                'mean': round(irradiance_sum / n, 2),
                'max': round(irradiance_max, 2),
                'min': 0
            },
            'temperature': {
                'mean': round(temp_sum / n, 2),
                'max': round(temp_max, 2),
                'min': round(temp_min, 2)
            },
            'power_actual': {
                'mean': round(power_sum / n, 2),
                'max': round(power_max, 2),
                'total_generation_mwh': round(power_sum * INTERVAL_MINUTES / 60 / 1000, 2)
            }
        }
    }
    
    # 保存统计信息
    stats_path = os.path.join(OUTPUT_DIR, 'pv_power_data_stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"统计信息已保存到: {stats_path}")
    
    # 打印摘要
    print("\n=== 数据生成完成 ===")
    print(f"总记录数: {stats['total_records']}")
    print(f"时间范围: {stats['date_range']['start']} ~ {stats['date_range']['end']}")
    print(f"平均辐照度: {stats['statistics']['irradiance']['mean']} W/m²")
    print(f"平均温度: {stats['statistics']['temperature']['mean']} °C")
    print(f"平均功率: {stats['statistics']['power_actual']['mean']} kW")
    print(f"年发电量: {stats['statistics']['power_actual']['total_generation_mwh']} MWh")
    
    return data


if __name__ == '__main__':
    generate_dataset()
# @AI_GENERATED: end
