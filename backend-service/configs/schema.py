# -*- coding: utf-8 -*-
"""
配置数据类定义

定义 CustomerConfig (客户级配置，从 YAML 加载)
和 ScenarioConfig (场景级配置，固定常量)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from common.constants import ScenarioConfig, SCENARIO_CONFIGS


@dataclass
class DataSourceConfig:
    """数据源配置"""
    dataset_name: str = ""
    table_name: str = "sgms_hbuilding_load_quarter3"
    parent_field: str = "parent_id"
    child_field: str = "child_id"
    time_field: str = "record_time"
    load_field: str = "load"
    time_granularity: str = "15min"
    time_zone: str = "Asia/Shanghai"
    offline_csv_path: str = ""


@dataclass
class ForecastConfig:
    """预测任务配置"""
    task_type: str = "D"
    forecast_horizon: int = 1
    forecast_start_time: str = "00:15"
    specify_model: str = "xgb"
    separate_modeling: str = "true"
    operate_status: str = "local_offline"

    @property
    def scenario(self) -> ScenarioConfig:
        return SCENARIO_CONFIGS[self.task_type]


@dataclass
class BacktestConfig:
    """回测配置"""
    start_date: str = ""
    end_date: str = ""


@dataclass
class CustomerConfig:
    """客户级完整配置，从 YAML 文件加载"""
    name: str = ""
    task_id: str = ""
    output_dir: str = "./output"
    data_source: DataSourceConfig = field(default_factory=DataSourceConfig)
    forecast: ForecastConfig = field(default_factory=ForecastConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    id_lists: Dict[str, List[str]] = field(default_factory=dict)
    weather_cols: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def train_other_cols(self) -> List[str]:
        return self.weather_cols.get("train", [])

    @property
    def pred_other_cols(self) -> List[str]:
        return self.weather_cols.get("predict", [])
