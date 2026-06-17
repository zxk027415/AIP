/**
 * 错误处理工具
 * 
 * 提供统一的错误处理、日志记录和用户反馈功能
 */

import { message, notification } from 'antd';

/**
 * 错误类型
 */
export const ErrorType = {
  VALIDATION: 'validation' as const,
  EXECUTION: 'execution' as const,
  NETWORK: 'network' as const,
  AUTH: 'auth' as const,
  UNKNOWN: 'unknown' as const,
};

export type ErrorTypeValue = typeof ErrorType[keyof typeof ErrorType];

/**
 * 错误严重级别
 */
export const ErrorSeverity = {
  INFO: 'info' as const,
  WARNING: 'warning' as const,
  ERROR: 'error' as const,
  CRITICAL: 'critical' as const,
};

export type ErrorSeverityValue = typeof ErrorSeverity[keyof typeof ErrorSeverity];

/**
 * 错误信息接口
 */
export interface ErrorInfo {
  type: ErrorTypeValue;
  severity: ErrorSeverityValue;
  message: string;
  details?: string;
  code?: string;
  timestamp: Date;
  context?: Record<string, any>;
}

/**
 * 错误日志记录器
 */
class ErrorLogger {
  private logs: ErrorInfo[] = [];
  private maxLogs = 100;

  /**
   * 记录错误
   */
  log(error: ErrorInfo): void {
    this.logs.push(error);
    
    // 保持日志数量在限制内
    if (this.logs.length > this.maxLogs) {
      this.logs.shift();
    }

    // 在开发环境打印到控制台
    if (import.meta.env.DEV) {
      console.error('[ErrorLogger]', error);
    }
  }

  /**
   * 获取所有日志
   */
  getLogs(): ErrorInfo[] {
    return [...this.logs];
  }

  /**
   * 获取指定类型的日志
   */
  getLogsByType(type: ErrorTypeValue): ErrorInfo[] {
    return this.logs.filter(log => log.type === type);
  }

  /**
   * 清除日志
   */
  clear(): void {
    this.logs = [];
  }
}

// 全局错误日志记录器实例
export const errorLogger = new ErrorLogger();

/**
 * 错误消息映射
 */
const ERROR_MESSAGES: Record<string, string> = {
  // 网络错误
  'ERR_NETWORK': '网络连接失败，请检查网络设置',
  'ERR_TIMEOUT': '请求超时，请稍后重试',
  'ERR_CONNECTION_REFUSED': '无法连接到服务器，请确认服务器是否启动',
  
  // 认证错误
  'ERR_UNAUTHORIZED': '未授权，请先登录',
  'ERR_FORBIDDEN': '没有权限执行此操作',
  'ERR_TOKEN_EXPIRED': '登录已过期，请重新登录',
  
  // 验证错误
  'ERR_VALIDATION_CYCLE': '算法模板中存在循环依赖',
  'ERR_VALIDATION_DISCONNECTED': '存在未连接的节点',
  'ERR_VALIDATION_MISSING_INPUT': '节点缺少必需的输入',
  'ERR_VALIDATION_TYPE_MISMATCH': '端口类型不兼容',
  
  // 执行错误
  'ERR_EXECUTION_FAILED': '算法模板执行失败',
  'ERR_NODE_EXECUTION_FAILED': '节点执行失败',
  'ERR_FUNCTION_NOT_FOUND': '函数不存在',
  
  // 数据错误
  'ERR_NOT_FOUND': '资源不存在',
  'ERR_ALREADY_EXISTS': '资源已存在',
  'ERR_INVALID_DATA': '数据格式无效',
};

/**
 * 错误修复建议
 */
const ERROR_SUGGESTIONS: Record<string, string[]> = {
  'ERR_VALIDATION_CYCLE': [
    '检查算法模板中是否有节点形成了循环连接',
    '移除导致循环的连接',
    '重新组织节点的连接顺序',
  ],
  'ERR_VALIDATION_DISCONNECTED': [
    '检查是否有节点没有连接到算法模板',
    '删除未使用的节点',
    '或者将节点连接到算法模板中',
  ],
  'ERR_VALIDATION_MISSING_INPUT': [
    '检查节点的必需输入端口是否都已连接',
    '为缺少的输入添加连接',
    '或者在属性面板中配置默认值',
  ],
  'ERR_VALIDATION_TYPE_MISMATCH': [
    '检查连接的端口类型是否兼容',
    '使用类型转换节点进行转换',
    '或者选择类型兼容的函数',
  ],
  'ERR_NETWORK': [
    '检查网络连接是否正常',
    '确认后端服务是否启动',
    '检查防火墙设置',
  ],
  'ERR_UNAUTHORIZED': [
    '请先登录系统',
    '如果已登录，请刷新页面重试',
    '检查登录凭证是否过期',
  ],
};

/**
 * 解析错误对象
 */
export function parseError(error: any): ErrorInfo {
  const timestamp = new Date();
  
  // Axios 错误
  if (error.response) {
    const status = error.response.status;
    const data = error.response.data;
    
    let type: ErrorTypeValue = ErrorType.UNKNOWN;
    let severity: ErrorSeverityValue = ErrorSeverity.ERROR;
    
    if (status === 401 || status === 403) {
      type = ErrorType.AUTH;
      severity = ErrorSeverity.WARNING;
    } else if (status >= 400 && status < 500) {
      type = ErrorType.VALIDATION;
      severity = ErrorSeverity.WARNING;
    } else if (status >= 500) {
      type = ErrorType.EXECUTION;
      severity = ErrorSeverity.ERROR;
    }
    
    return {
      type,
      severity,
      message: data.detail || data.message || '请求失败',
      details: data.details,
      code: data.code || `HTTP_${status}`,
      timestamp,
      context: {
        url: error.config?.url,
        method: error.config?.method,
        status,
      },
    };
  }
  
  // 网络错误
  if (error.request) {
    return {
      type: ErrorType.NETWORK,
      severity: ErrorSeverity.ERROR,
      message: '网络请求失败',
      details: error.message,
      code: 'ERR_NETWORK',
      timestamp,
    };
  }
  
  // 其他错误
  return {
    type: ErrorType.UNKNOWN,
    severity: ErrorSeverity.ERROR,
    message: error.message || '未知错误',
    details: error.stack,
    timestamp,
  };
}

/**
 * 获取友好的错误消息
 */
export function getFriendlyMessage(errorInfo: ErrorInfo): string {
  if (errorInfo.code && ERROR_MESSAGES[errorInfo.code]) {
    return ERROR_MESSAGES[errorInfo.code];
  }
  return errorInfo.message;
}

/**
 * 获取错误修复建议
 */
export function getErrorSuggestions(errorInfo: ErrorInfo): string[] {
  if (errorInfo.code && ERROR_SUGGESTIONS[errorInfo.code]) {
    return ERROR_SUGGESTIONS[errorInfo.code];
  }
  return [];
}

/**
 * 显示错误通知
 */
export function showErrorNotification(error: any, title?: string): void {
  const errorInfo = parseError(error);
  errorLogger.log(errorInfo);
  
  const friendlyMessage = getFriendlyMessage(errorInfo);
  const suggestions = getErrorSuggestions(errorInfo);
  
  // 根据严重级别选择通知方式
  if (errorInfo.severity === ErrorSeverity.INFO) {
    message.info(friendlyMessage);
  } else if (errorInfo.severity === ErrorSeverity.WARNING) {
    let description = friendlyMessage;
    if (suggestions.length > 0) {
      description += '\n\n建议：\n' + suggestions.map((s, i) => `${i + 1}. ${s}`).join('\n');
    }
    
    notification.warning({
      message: title || '警告',
      description,
      duration: 6,
      style: { whiteSpace: 'pre-line' },
    });
  } else {
    let description = friendlyMessage;
    if (errorInfo.details) {
      description += `\n\n详情：${errorInfo.details}`;
    }
    if (suggestions.length > 0) {
      description += '\n\n建议：\n' + suggestions.map((s, i) => `${i + 1}. ${s}`).join('\n');
    }
    
    notification.error({
      message: title || '错误',
      description,
      duration: 8,
      style: { whiteSpace: 'pre-line' },
    });
  }
}

/**
 * 显示成功消息
 */
export function showSuccess(msg: string): void {
  message.success(msg);
}

/**
 * 显示警告消息
 */
export function showWarning(msg: string): void {
  message.warning(msg);
}

/**
 * 显示信息消息
 */
export function showInfo(msg: string): void {
  message.info(msg);
}

/**
 * 处理 API 错误
 */
export function handleApiError(error: any, context?: string): void {
  const errorInfo = parseError(error);
  errorLogger.log(errorInfo);
  
  const title = context ? `${context}失败` : '操作失败';
  showErrorNotification(error, title);
}

/**
 * 创建错误处理装饰器
 */
export function withErrorHandler<T extends (...args: any[]) => Promise<any>>(
  fn: T,
  context?: string
): T {
  return (async (...args: any[]) => {
    try {
      return await fn(...args);
    } catch (error) {
      handleApiError(error, context);
      throw error;
    }
  }) as T;
}
