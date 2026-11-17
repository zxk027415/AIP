# -*- coding: utf-8 -*-
"""
共享常量和全局设置

集中管理 CUDA 设置、warnings 过滤、场景配置表等
"""
import os
import warnings
from dataclasses import dataclass

warnings.filterwarnings(action="ignore")
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

# 预测表名映射
FCST_TABLE_MAPPING = {"D": "da", "DI": "di", "W": "wa", "WI": "wi", "M": "ma", "MI": "mi"}


@dataclass(frozen=True)
class ScenarioConfig:
    """
    场景配置 - 捕获 DI/D/WI/W/MI/M 六种预测场景的行为差异

    每种场景类型对应一个固定的 ScenarioConfig 实例，
    替代 feature_eng / model_prefer / model_wrap 中大量重复的 if-else 分支
    """
    task_type: str

    # --- feature_eng 差异参数 ---
    rounding_unit: str          # "hour" (DI) / "day" (其余)
    look_back_multiplier: int   # 4 (DI,D) / 2 (WI,W,MI) / 1 (M)
    prefer_unit_len: int        # 7 (DI) / 2 (D) / 1 (WI,W,MI,M)

    # --- model_prefer 差异参数 ---
    default_retrain: bool       # False (DI,MI,M) / True (D,WI,W)
    use_separate_modeling: bool # False (DI) / True (D,WI,W,MI,M)


# 六种场景的固定配置
SCENARIO_CONFIGS = {
    "DI": ScenarioConfig(
        task_type="DI",
        rounding_unit="hour",
        look_back_multiplier=4,
        prefer_unit_len=7,
        default_retrain=False,
        use_separate_modeling=False,
    ),
    "D": ScenarioConfig(
        task_type="D",
        rounding_unit="day",
        look_back_multiplier=4,
        prefer_unit_len=2,
        default_retrain=True,
        use_separate_modeling=True,
    ),
    "WI": ScenarioConfig(
        task_type="WI",
        rounding_unit="day",
        look_back_multiplier=2,
        prefer_unit_len=1,
        default_retrain=True,
        use_separate_modeling=True,
    ),
    "W": ScenarioConfig(
        task_type="W",
        rounding_unit="day",
        look_back_multiplier=2,
        prefer_unit_len=1,
        default_retrain=True,
        use_separate_modeling=True,
    ),
    "MI": ScenarioConfig(
        task_type="MI",
        rounding_unit="day",
        look_back_multiplier=2,
        prefer_unit_len=1,
        default_retrain=False,
        use_separate_modeling=True,
    ),
    "M": ScenarioConfig(
        task_type="M",
        rounding_unit="day",
        look_back_multiplier=1,
        prefer_unit_len=1,
        default_retrain=False,
        use_separate_modeling=True,
    ),
}
