#!/usr/bin/env python
# encoding: utf-8
"""
@author: shengqi.ye
@datetime: 2022/07/26 10:27:02
@desc: 异常捕获处理文件
"""

import logging
import traceback

logger = logging.getLogger(__name__)


class ParamException(Exception):
    """
    parameter check exception
    """
    
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class AlgoException(Exception):
    """
    parameter check exception
    """

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def handle_exception(e, message):
    """
    handle exceptions.

    Parameters
    ----------
    e : Exception
        exception object
    message : str
        内部错误信息

    Returns
    ----------
    result : dict
        状态码、返回体信息
    """
    
    if isinstance(e, ParamException):
        code = 400
        message = str(e.message)
        logger.warning(f'参数错误: {message}')
    else:
        code = 500
        logger.error(f'程序内部错误: {message}')
        logger.error(traceback.format_exc())   # 严重错误，记录调用链
    
    result = {'code': code, 'message': message}

    return result
