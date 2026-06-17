#!/usr/bin/env python
# encoding: utf-8
"""
@author: shengqi.ye
@datetime: 2022/07/26 10:12:23
@desc: 日志操作文件
"""

import os
import yaml
import logging
import logging.config
from datetime import datetime, timedelta

LOG_LEVEL_REPORT = 51

DIR_PATH = os.path.abspath((os.path.dirname(__file__)))
LOG_ABSOLUTE_PATH = os.path.join(DIR_PATH, 'logs')
LOG_YAML_ABSOLUTE_PATH = os.path.join(DIR_PATH, 'log.yaml')


def beijing(sec, what):
    beijing_time = datetime.utcnow() + timedelta(hours=8)
    return beijing_time.timetuple()


def setup_logging(log_path=LOG_ABSOLUTE_PATH,
                  default_path=LOG_YAML_ABSOLUTE_PATH,
                  default_level=logging.INFO):
    """
    开启日志监听

    Parameters
    ----------
    log_path : str
        日志文件存储路径
    default_path : str
        日志配置信息存储路径
    default_level : object
        默认日志等级

    Returns
    ----------
        返回体信息、状态码
    """

    if not os.path.exists(log_path):
        os.mkdir(log_path)

    if os.path.exists(default_path):
        with open(default_path, 'r', encoding='utf-8') as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
            logging.config.dictConfig(config)
    else:
        raise FileExistsError('log config file %s not exist' % default_path)
    logging.addLevelName(LOG_LEVEL_REPORT, "REPORT")
    logging.Formatter.converter = beijing
