"""
数据加载器模块
负责从数据库读取场站数据
"""

import os
import pandas as pd
import pymysql
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, timedelta
from backend.db_config import DB_CONFIG, TABLE_NAMES
from functools import reduce
import logging

logger = logging.getLogger(__name__)


class DataLoader:
    """数据加载器类，用于从数据库加载场站数据"""
    
    def __init__(self):
        """
        初始化数据加载器
        
        Args:
            data_dir: 数据目录路径（保留用于兼容性，但主要从数据库读取）
        """
        self.db_config = DB_CONFIG
        
    def _get_db_connection(self):
        """
        获取数据库连接
        
        Returns:
            pymysql连接对象
        """
        try:
            connection = pymysql.connect(**self.db_config)
            return connection
        except Exception as e:
            logger.error(f"数据库连接失败: {str(e)}")
            raise ConnectionError(f"无法连接到数据库: {str(e)}")

    def fetch_farm_true_data(self, station_id: str, start_date: str, end_date: str) -> pd.DataFrame:
        '''
        拉取场站真实数据
        :param station_id:
        :param start_date:
        :param end_date:
        :return:
        '''
        try:
            connection = self._get_db_connection()

            # 1. 加载真实数据 (actual_data表)
            true_query = f"""
                SELECT timestamp, wind_speed, wind_speed_min, wind_speed_median, wind_speed_max, power
                FROM {TABLE_NAMES['actual_data']} 
                WHERE master_id = %s 
                  AND timestamp >= %s 
                  AND timestamp <= %s
                ORDER BY timestamp
            """

            true_df = pd.read_sql(true_query, connection,
                                  params=(station_id, start_date, end_date))
            connection.close()
        except pymysql.Error as e:
            logger.error(f"数据库查询错误: {str(e)}")
            raise ValueError(f"从数据库加载数据失败: {str(e)}")

        if true_df.empty or true_df is None:
            raise FileNotFoundError(f"场站 {station_id} 在指定时间范围内没有真实数据")

        true_df['timestamp'] = pd.to_datetime(true_df['timestamp'])
        true_df.columns = ['timestamp', 'WS', 'WS_min', 'WS_median', 'WS_max', 'POWER']  # 重命名为WS
        return true_df


    def fetch_farm_nwp_data(self, station_id: str, start_date: str, end_date: str, load_all=False) -> pd.DataFrame:
        '''
        拉取场站的选定气象数据
        :param station_id:
        :param start_date:
        :param end_date:
        :param load_all: 是否使用所有气象数据，数据库中单时次气象预报未来48小时
        :return:
        '''
        nwp_data_frames = []

        connection = self._get_db_connection()
        sources = self.get_station_sources(station_id)
        for source in sources:
            table_name = source.lower()
            try:
                # 使用反引号包裹表名，支持特殊字符
                source_query = f"""
                    SELECT forecast_time, timestamp, wind_speed, wind_direction, temperature, pressure
                    FROM `{table_name}` 
                    WHERE master_id = %s 
                      AND forecast_time >= %s 
                      AND forecast_time <= %s
                    ORDER BY forecast_time, timestamp
                """

                source_df = pd.read_sql(source_query, connection,
                                        params=(station_id, start_date, end_date))

                if not source_df.empty:
                    source_df['forecast_time'] = pd.to_datetime(source_df['forecast_time'])
                    source_df['timestamp'] = pd.to_datetime(source_df['timestamp'])

                    # 使用表名作为前缀（转换为大写以保持一致性）
                    source_prefix = table_name.upper()
                    source_df.columns = [
                        'forecast_time',
                        'timestamp',
                        f'{source_prefix}_WS',
                        f'{source_prefix}_WD',
                        f'{source_prefix}_TMP',
                        f'{source_prefix}_PRES'
                    ]

                    nwp_data_frames.append(source_df)
                else:
                    logger.warning(f"气象源表 {table_name} 在指定时间范围内没有数据")

            except Exception as e:
                logger.warning(f"加载气象源表 {table_name} 数据失败: {str(e)}")
                continue

        connection.close()

        if not nwp_data_frames:
            raise FileNotFoundError(f"场站 {station_id} 没有可用的气象源数据")

        # 合并所有气象源数据
        nwp_df = reduce(lambda x, y: pd.merge(x, y, on=['timestamp', 'forecast_time']), nwp_data_frames)
        nwp_df['dist'] = (nwp_df['timestamp'] - nwp_df['forecast_time']).dt.total_seconds() / 3600

        if not load_all:
            nwp_df = nwp_df[nwp_df['dist'].isin(range(24))]
            nwp_df.reset_index(drop=True, inplace=True)

        # CMC_ENHANCE/DWD气象要素的缺失使用EC_10D填充
        if 'CMC_ENHANCE_WS' in nwp_df.columns:
            nwp_df['CMC_ENHANCE_TMP'] = nwp_df['EC_10D_TMP']
            nwp_df['CMC_ENHANCE_PRES'] = nwp_df['EC_10D_PRES']
        if 'DWD_WS' in nwp_df.columns:
            nwp_df['DWD_TMP'] = nwp_df['EC_10D_TMP']
            nwp_df['DWD_PRES'] = nwp_df['EC_10D_PRES']

        return nwp_df

    
    def scan_stations(self) -> List[str]:
        """
        从数据库farm_info表中读取所有场站ID
        
        Returns:
            场站ID列表，按字母顺序排序
            
        Raises:
            ConnectionError: 数据库连接失败
        """
        try:
            connection = self._get_db_connection()
            
            query = f"SELECT master_id FROM {TABLE_NAMES['farm_info']}"
            
            with connection.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
            
            connection.close()
            
            # 提取场站ID
            station_ids = [row[0] for row in results]
            
            logger.info(f"从数据库读取到 {len(station_ids)} 个场站")
            
            return sorted(station_ids)
            
        except Exception as e:
            logger.error(f"扫描场站失败: {str(e)}")
            raise ConnectionError(f"从数据库读取场站列表失败: {str(e)}")
    
    def get_station_info(self, station_id: str) -> Dict[str, any]:
        """
        获取指定场站的完整信息
        
        Args:
            station_id: 场站ID
            
        Returns:
            包含场站信息的字典，包括容量、气象源等
        """
        try:
            connection = self._get_db_connection()
            
            query = f"""
                SELECT master_id, capacity, weather_sources 
                FROM {TABLE_NAMES['farm_info']} 
                WHERE master_id = %s
            """
            
            with connection.cursor() as cursor:
                cursor.execute(query, (station_id,))
                result = cursor.fetchone()
            
            connection.close()
            
            if result:
                import json
                
                station_info = {
                    'master_id': result[0],
                    'capacity': float(result[1]) if result[1] is not None else None,
                    'weather_sources': []
                }
                
                # 解析气象源
                if result[2]:
                    try:
                        sources = json.loads(result[2])
                        if isinstance(sources, list):
                            station_info['weather_sources'] = [s.strip() for s in sources if isinstance(s, str) and s.strip()]
                    except json.JSONDecodeError:
                        logger.warning(f"场站 {station_id} 的气象源数据解析失败")
                
                logger.info(f"场站 {station_id} 信息获取成功")
                return station_info
            else:
                logger.warning(f"场站 {station_id} 不存在")
                return {}
                
        except Exception as e:
            logger.error(f"获取场站信息失败: {str(e)}")
            return {}
    
    def get_station_capacity(self, station_id: str) -> Optional[float]:
        """
        获取指定场站的容量信息
        
        Args:
            station_id: 场站ID
            
        Returns:
            场站容量（单位：MW），如果未找到则返回None
        """
        try:
            connection = self._get_db_connection()
            
            query = f"""
                SELECT capacity 
                FROM {TABLE_NAMES['farm_info']} 
                WHERE master_id = %s
            """
            
            with connection.cursor() as cursor:
                cursor.execute(query, (station_id,))
                result = cursor.fetchone()
            
            connection.close()
            
            if result and result[0] is not None:
                capacity = float(result[0])
                logger.info(f"场站 {station_id} 的容量: {capacity} MW")
                return capacity
            else:
                logger.warning(f"场站 {station_id} 没有配置容量信息")
                return None
                
        except Exception as e:
            logger.error(f"获取场站容量失败: {str(e)}")
            return None
    
    def get_station_sources(self, station_id: str) -> List[str]:
        """
        获取指定场站的气象源列表
        
        Args:
            station_id: 场站ID
            
        Returns:
            气象源名称列表（返回实际的表名）
        """
        try:
            connection = self._get_db_connection()
            
            query = f"""
                SELECT weather_sources 
                FROM {TABLE_NAMES['farm_info']} 
                WHERE master_id = %s
            """
            
            with connection.cursor() as cursor:
                cursor.execute(query, (station_id,))
                result = cursor.fetchone()
            
            connection.close()
            
            if result and result[0]:
                import json
                
                # weather_sources字段存储的是JSON数组
                try:
                    # 尝试解析为JSON
                    sources = json.loads(result[0])
                    
                    # 确保是列表
                    if isinstance(sources, list):
                        # 清理每个表名
                        cleaned_sources = []
                        for s in sources:
                            if isinstance(s, str):
                                table_name = s.strip()
                                if table_name:
                                    cleaned_sources.append(table_name)
                        
                        logger.info(f"场站 {station_id} 的气象源表: {cleaned_sources}")
                        return cleaned_sources
                    else:
                        logger.warning(f"场站 {station_id} 的 weather_sources 不是列表格式")
                        return []
                        
                except json.JSONDecodeError as e:
                    logger.error(f"解析 weather_sources JSON 失败: {str(e)}, 原始数据: {result[0]}")
                    return []
            else:
                logger.warning(f"场站 {station_id} 没有配置气象源")
                return []
                
        except Exception as e:
            logger.error(f"获取场站气象源失败: {str(e)}")
            return []
    
    def validate_data_files(self, station_id: str) -> Dict[str, bool]:
        """
        验证场站的数据是否可用
        
        Args:
            station_id: 场站ID
            
        Returns:
            字典，包含数据可用状态
            {"nwp": bool, "true": bool}
        """
        validation_result = {
            "nwp": False,
            "true": False,
        }
        
        try:
            # 检查场站是否存在
            sources = self.get_station_sources(station_id)
            validation_result["nwp"] = len(sources) > 0
            
            # 检查真实数据表是否有该场站的数据
            connection = self._get_db_connection()
            
            query = f"""
                SELECT COUNT(*) 
                FROM {TABLE_NAMES['actual_data']} 
                WHERE master_id = %s
                LIMIT 1
            """
            
            with connection.cursor() as cursor:
                cursor.execute(query, (station_id,))
                count = cursor.fetchone()[0]
            
            connection.close()
            
            validation_result["true"] = count > 0
            
        except Exception as e:
            logger.error(f"验证场站数据失败: {str(e)}")
        
        return validation_result

    def load_station_data(self, station_id: str, 
                         start_date: Optional[str] = None,
                         end_date: Optional[str] = None, load_all=False) -> Dict[str, pd.DataFrame]:
        """
        从数据库加载指定场站的nwp、true
        
        Args:
            station_id: 场站ID
            start_date: 开始日期，格式'YYYY-MM-DD'，默认为当前时间往前2个月
            end_date: 结束日期，格式'YYYY-MM-DD'，默认为当前时间
            load_all: 是否使用全量的气象源数据, 默认为False
            
        Returns:
            包含三个DataFrame的字典
            {"nwp": DataFrame, "true": DataFrame}
            
        Raises:
            FileNotFoundError: 场站不存在或数据缺失
            ValueError: 数据格式错误或无法读取
        """
        # 设置默认日期范围（当前时间往前2个月）
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        if start_date is None:
            start_datetime = datetime.now() - timedelta(days=60)  # 2个月
            start_date = start_datetime.strftime('%Y-%m-%d')
        
        logger.info(f"加载场站 {station_id} 数据，时间范围: {start_date} 至 {end_date}")

        try:
            true_df = self.fetch_farm_true_data(station_id, start_date, end_date)
            nwp_df = self.fetch_farm_nwp_data(station_id, start_date, end_date, load_all=load_all)

            result = {
                "nwp": nwp_df,
                "true": true_df,
            }

            logger.info(f"场站 {station_id} 数据加载完成")
            return result
            
        except pymysql.Error as e:
            logger.error(f"数据库查询错误: {str(e)}")
            raise ValueError(f"从数据库加载数据失败: {str(e)}")
        except Exception as e:
            logger.error(f"加载数据时发生错误: {str(e)}")
            raise ValueError(f"加载数据时发生错误: {str(e)}")
