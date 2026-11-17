import { useState, useEffect, memo, useMemo } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import { 
  Card, 
  Space, 
  Typography, 
  Tag, 
  Button, 
  Grid, 
  Descriptions,
  Progress,
  Statistic,
  Row,
  Col,
  Tabs,
  ConfigProvider,
  Skeleton,
  Spin
} from 'antd';
import { 
  CheckCircleOutlined, 
  CloseCircleOutlined, 
  ReloadOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  ApiOutlined,
  CloudServerOutlined,
  UserOutlined,
  SettingOutlined,
  LoadingOutlined,
  SyncOutlined
} from '@ant-design/icons';
import { healthCheck, systemApi } from '../services/api';
import './SystemStatusPage.css';

const { Title, Text } = Typography;
const { useBreakpoint } = Grid;

/**
 * 服务状态卡片组件（使用 memo 和自定义比较函数）
 */
const ServiceStatusCard = memo(({ 
  frontendStatus,
  apiStatus,
  apiVersion,
  serviceLoading,
  dbStatus,
  lastCheckTime,
  frontendUptime,
  backendUptime,
  isMobile,
  onRefresh,
  formatUptime
}: {
  frontendStatus: string;
  apiStatus: string;
  apiVersion: string;
  serviceLoading: boolean;
  dbStatus: string;
  lastCheckTime: string;
  frontendUptime: number;
  backendUptime: number;
  isMobile: boolean;
  onRefresh: () => void;
  formatUptime: (seconds: number) => string;
}) => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  return (
    <Card 
      title={t('systemStatus.serviceStatus')} 
      extra={
        <Space>
          {lastCheckTime && <Text type="secondary" style={{ fontSize: '12px' }}>{t('systemStatus.lastCheck')} {lastCheckTime}</Text>}
          <Button
            type="text"
            icon={<ReloadOutlined spin={serviceLoading} />}
            onClick={onRefresh}
            loading={serviceLoading}
            size="small"
          >
            {t('systemStatus.refresh')}
          </Button>
        </Space>
      }
    >
      <Descriptions column={isMobile ? 1 : 2} bordered size={isMobile ? 'small' : 'middle'}>
        <Descriptions.Item label={t('systemStatus.frontendService')}>
          <Space direction="vertical" size="small">
            <Space>
              {frontendStatus === 'checking' ? (
                <Tag color="processing" icon={<SyncOutlined spin />}>{t('systemStatus.checking')}</Tag>
              ) : frontendStatus === 'connected' ? (
                <Tag color="success" icon={<CheckCircleOutlined />}>
                  {t('systemStatus.running')}
                </Tag>
              ) : (
                <Tag color="error" icon={<CloseCircleOutlined />}>
                  {t('systemStatus.connectionFailed')}
                </Tag>
              )}
              {!isMobile && <Text type="secondary">http://localhost:3001</Text>}
            </Space>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {t('systemStatus.uptime')} {formatUptime(frontendUptime)}
            </Text>
          </Space>
        </Descriptions.Item>

        <Descriptions.Item label={t('systemStatus.backendService')}>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <Space>
              {apiStatus === 'checking' || serviceLoading ? (
                <Tag color="processing" icon={<SyncOutlined spin />}>{t('systemStatus.checking')}</Tag>
              ) : apiStatus === 'connected' ? (
                <Tag color="success" icon={<CheckCircleOutlined />}>
                  {t('systemStatus.connected')}
                </Tag>
              ) : (
                <Tag color="error" icon={<CloseCircleOutlined />}>
                  {t('systemStatus.connectionFailed')}
                </Tag>
              )}
              {!isMobile && <Text type="secondary">http://localhost:8080</Text>}
            </Space>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {t('systemStatus.uptime')} {formatUptime(backendUptime)}
            </Text>
            {apiStatus === 'error' && !serviceLoading && (
              <Text type="secondary" style={{ fontSize: isMobile ? '12px' : '14px' }}>
                {t('systemStatus.ensureBackendStarted')}
              </Text>
            )}
          </Space>
        </Descriptions.Item>

        <Descriptions.Item label={t('systemStatus.databaseConnection')}>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <Space>
              {dbStatus === 'checking' ? (
                <Tag color="processing" icon={<SyncOutlined spin />}>{t('systemStatus.checking')}</Tag>
              ) : dbStatus === 'connected' ? (
                <Tag color="success" icon={<DatabaseOutlined />}>
                  {t('systemStatus.connected')}
                </Tag>
              ) : (
                <Tag color="error" icon={<CloseCircleOutlined />}>
                  {t('systemStatus.connectionFailed')}
                </Tag>
              )}
              {!isMobile && <Text type="secondary">SQLite</Text>}
            </Space>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {t('systemStatus.uptime')} {formatUptime(backendUptime)}
            </Text>
            {dbStatus === 'error' && (
              <Text type="secondary" style={{ fontSize: isMobile ? '12px' : '14px' }}>
                {t('systemStatus.databaseConnectionError')}
              </Text>
            )}
          </Space>
        </Descriptions.Item>

        {(apiStatus === 'connected' || serviceLoading) && (
          <Descriptions.Item label={t('systemStatus.apiVersion')}>
            <Text>{serviceLoading ? apiVersion || '0.2.0' : apiVersion}</Text>
          </Descriptions.Item>
        )}
      </Descriptions>
    </Card>
  );
}, (prevProps, nextProps) => {
  // 自定义比较函数：只在关键属性变化时才重新渲染
  // 忽略运行时间的变化，除非是在刷新状态时
  if (prevProps.frontendStatus !== nextProps.frontendStatus) return false;
  if (prevProps.serviceLoading !== nextProps.serviceLoading) return false;
  if (prevProps.apiStatus !== nextProps.apiStatus) return false;
  if (prevProps.dbStatus !== nextProps.dbStatus) return false;
  if (prevProps.apiVersion !== nextProps.apiVersion) return false;
  if (prevProps.lastCheckTime !== nextProps.lastCheckTime) return false;
  if (prevProps.isMobile !== nextProps.isMobile) return false;
  
  // 运行时间变化时不重新渲染（返回 true 表示 props 相等，跳过渲染）
  return true;
});

/**
 * 数据库状态卡片组件（使用 memo 防止不必要的重新渲染）
 */
const DatabaseStatusCard = memo(({ 
  apiStatus, 
  dbStatus, 
  dbStatusLoading, 
  dbInfo, 
  isMobile,
  onRefresh 
}: {
  apiStatus: string;
  dbStatus: string;
  dbStatusLoading: boolean;
  dbInfo: { size_mb: number; table_count: number };
  isMobile: boolean;
  onRefresh: () => void;
}) => {
  // 只有在从未连接过时才不显示（初始状态除外）
  if (apiStatus === 'error' && dbStatus === 'error') return null;
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  
  return (
    <Card 
      title={t('systemStatus.databaseStatus')}
      extra={
        <Button
          type="text"
          icon={<ReloadOutlined spin={dbStatusLoading} />}
          onClick={onRefresh}
          loading={dbStatusLoading}
          size="small"
        >
          {t('systemStatus.refresh')}
        </Button>
      }
    >
      <Descriptions column={1} bordered size={isMobile ? 'small' : 'middle'}>
        <Descriptions.Item label={t('systemStatus.databaseType')}>
          <Space>
            <Tag color="blue">SQLite</Tag>
            <Text type="secondary">{t('systemStatus.localFileDatabase')}</Text>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label={t('systemStatus.connectionStatus')}>
          {dbStatusLoading ? (
            <Tag color="processing" icon={<SyncOutlined spin />}>{t('systemStatus.checking')}</Tag>
          ) : dbStatus === 'connected' ? (
            <Tag color="success" icon={<CheckCircleOutlined />}>
              {t('systemStatus.normal')}
            </Tag>
          ) : (
            <Tag color="error" icon={<CloseCircleOutlined />}>
              {t('systemStatus.connectionFailed')}
            </Tag>
          )}
        </Descriptions.Item>
        <Descriptions.Item label={t('systemStatus.databaseSize')}>
          <Text>{dbInfo.size_mb} MB</Text>
        </Descriptions.Item>
        <Descriptions.Item label={t('systemStatus.tableCount')}>
          <Text>{dbInfo.table_count} {t('systemStatus.tables')}</Text>
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
});

DatabaseStatusCard.displayName = 'DatabaseStatusCard';

/**
 * 性能监控卡片组件（使用 memo 防止不必要的重新渲染）
 */
const PerformanceMonitorCard = memo(({ 
  apiStatus, 
  metricsLoading, 
  performanceData,
  isMobile,
  onRefresh 
}: {
  apiStatus: string;
  metricsLoading: boolean;
  performanceData: { cpu: number; memory: number; disk: number; network: number };
  isMobile: boolean;
  onRefresh: () => void;
}) => {
  // 只有在连接失败时才不显示
  if (apiStatus === 'error') return null;
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  return (
    <Card 
      title={t('systemStatus.perfMonitor')}
      extra={
        <Space>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            {metricsLoading ? t('systemStatus.updating') : t('systemStatus.autoUpdate')}
          </Text>
          <Button
            type="text"
            icon={<ReloadOutlined spin={metricsLoading} />}
            onClick={onRefresh}
            loading={metricsLoading}
            size="small"
          >
            {t('systemStatus.refresh')}
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div>
          <Text>{t('systemStatus.cpuUsage')}</Text>
          <Progress 
            percent={performanceData.cpu} 
            status={performanceData.cpu > 80 ? 'exception' : 'active'}
            strokeColor={performanceData.cpu > 80 ? '#ff4d4f' : '#1890ff'}
          />
        </div>
        <div>
          <Text>{t('systemStatus.memoryUsage')}</Text>
          <Progress 
            percent={performanceData.memory} 
            status={performanceData.memory > 80 ? 'exception' : 'active'}
            strokeColor={performanceData.memory > 80 ? '#ff4d4f' : '#52c41a'}
          />
        </div>
        <div>
          <Text>{t('systemStatus.diskUsage')}</Text>
          <Progress 
            percent={performanceData.disk}
            strokeColor="#faad14"
          />
        </div>
        <div>
          <Text>{t('systemStatus.networkLoad')}</Text>
          <Progress 
            percent={performanceData.network}
            strokeColor="#13c2c2"
          />
        </div>
      </Space>
    </Card>
  );
});

PerformanceMonitorCard.displayName = 'PerformanceMonitorCard';

/**
 * 系统状态页面
 * 
 * 显示系统运行状态、性能指标、资源使用情况
 * 支持响应式布局
 */
const SystemStatusPage: React.FC = () => {
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end
  const [apiStatus, setApiStatus] = useState<'checking' | 'connected' | 'error'>('checking');
  const [apiVersion, setApiVersion] = useState<string>('');
  const [lastCheckTime, setLastCheckTime] = useState<string>('');
  const [backendUptime, setBackendUptime] = useState<number>(0);
  const [frontendUptime, setFrontendUptime] = useState<number>(0);
  const [dbStatus, setDbStatus] = useState<'checking' | 'connected' | 'error'>('checking');
  // 服务状态卡片中显示的数据库连接状态（与数据库状态卡片独立）
  const [serviceDbStatus, setServiceDbStatus] = useState<'checking' | 'connected' | 'error'>('checking');
  // 前端服务状态
  const [frontendStatus, setFrontendStatus] = useState<'checking' | 'connected' | 'error'>('connected');
  const [activeTab, setActiveTab] = useState('service');
  const [tabsKey, setTabsKey] = useState(0);
  const [tabsVisible, setTabsVisible] = useState(false);
  
  // 分别追踪各个部分的加载状态
  const [serviceLoading, setServiceLoading] = useState(true);
  const [dbInfoLoading, setDbInfoLoading] = useState(true);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [dbStatusLoading, setDbStatusLoading] = useState(true);
  
  // 性能数据
  const [performanceData, setPerformanceData] = useState({
    cpu: 0,
    memory: 0,
    disk: 0,
    network: 0,
  });
  
  // 统计数据
  const [statistics, setStatistics] = useState({
    totalUsers: 0,
    activeUsers: 0,
    totalWorkflows: 0,
    todayExecutions: 0,
  });
  
  // 数据库信息
  const [dbInfo, setDbInfo] = useState({
    size_mb: 0,
    table_count: 0,
  });
  
  const screens = useBreakpoint();
  const isMobile = !screens.md;

  // 检查API连接（检查所有服务状态）
  const checkApiConnection = async () => {
    setFrontendStatus('checking');
    setApiStatus('checking');
    setServiceDbStatus('checking');
    setServiceLoading(true);
    
    try {
      // 添加10秒延迟用于测试
      await new Promise(resolve => setTimeout(resolve, 10000));
      
      const response = await healthCheck();
      
      // 前端服务：如果能执行到这里，说明前端服务正常
      setFrontendStatus('connected');
      
      // 后端服务
      setApiStatus('connected');
      setApiVersion(response.version || '0.2.0');
      setLastCheckTime(new Date().toLocaleString('zh-CN'));
      
      // 设置后端运行时间（从API返回）
      if (response.uptime_seconds !== undefined) {
        setBackendUptime(response.uptime_seconds);
      }
      
      // 数据库连接：如果API连接成功，假设数据库也连接成功
      setServiceDbStatus('connected');
      setServiceLoading(false);
      
    } catch (error) {
      console.error('API connection failed:', error);
      
      // 前端服务：如果能执行到这里，说明前端服务正常（只是后端连接失败）
      setFrontendStatus('connected');
      
      // 后端服务和数据库连接失败
      setApiStatus('error');
      setServiceDbStatus('error');
      setLastCheckTime(new Date().toLocaleString('zh-CN'));
      setServiceLoading(false);
    }
  };
  
  // 刷新服务状态（独立刷新，不影响其他模块）
  const refreshServiceStatus = async () => {
    await checkApiConnection();
  };
  
  // 刷新数据库信息（独立刷新按钮）
  const refreshDatabaseInfo = async () => {
    await fetchDatabaseInfo();
  };
  
  // 获取性能指标
  const fetchMetrics = async () => {
    setMetricsLoading(true);
    try {
      const metrics = await systemApi.getMetrics();
      setPerformanceData({
        cpu: metrics.cpu_percent || 0,
        memory: metrics.memory?.percent || 0,
        disk: metrics.disk?.percent || 0,
        network: Math.min(100, ((metrics.network?.mb_sent || 0) / 1000) * 100),
      });
    } catch (error) {
      console.error('Failed to fetch metrics:', error);
    } finally {
      setMetricsLoading(false);
    }
  };
  
  // 获取统计数据
  const fetchStatistics = async () => {
    setStatsLoading(true);
    try {
      const stats = await systemApi.getStatistics();
      setStatistics({
        totalUsers: stats.total_users || 0,
        activeUsers: stats.active_users || 0,
        totalWorkflows: stats.total_workflows || 0,
        todayExecutions: stats.today_executions || 0,
      });
    } catch (error) {
      console.error('Failed to fetch statistics:', error);
    } finally {
      setStatsLoading(false);
    }
  };
  
  // 获取数据库信息
  const fetchDatabaseInfo = async () => {
    setDbInfoLoading(true);
    setDbStatusLoading(true);
    try {
      const info = await systemApi.getDatabaseInfo();
      setDbInfo({
        size_mb: info.size_mb || 0,
        table_count: info.table_count || 0,
      });
      // 数据库信息获取成功，更新连接状态
      setDbStatus('connected');
    } catch (error) {
      console.error('Failed to fetch database info:', error);
      setDbStatus('error');
    } finally {
      setDbInfoLoading(false);
      setDbStatusLoading(false);
    }
  };

  // 延迟显示Tabs，避免初始渲染时的弹动
  useEffect(() => {
    requestAnimationFrame(() => {
      setTabsVisible(true);
      setTimeout(() => {
        setTabsKey(prev => prev + 1);
      }, 0);
    });
  }, []);

  useEffect(() => {
    setTabsKey((prev) => prev + 1);
  }, [i18n.language]);

  useEffect(() => {
    // 首次进入页面时检查服务状态
    checkApiConnection();
    
    // 首次加载其他数据
    fetchDatabaseInfo();
    fetchStatistics();
    
    // 前端运行时间 - 从服务器信息文件读取启动时间
    const fetchFrontendStartTime = async () => {
      try {
        const response = await fetch('/server-info.json');
        const data = await response.json();
        const startTime = data.timestamp;
        
        // 立即更新一次运行时间
        setFrontendUptime(Math.floor((Date.now() - startTime) / 1000));
        
        // 每秒更新运行时间
        const frontendTimer = setInterval(() => {
          setFrontendUptime(Math.floor((Date.now() - startTime) / 1000));
        }, 1000);
        
        return frontendTimer;
      } catch (error) {
        console.error('无法读取前端服务器启动时间:', error);
        // 降级方案：使用当前时间
        const startTime = Date.now();
        const frontendTimer = setInterval(() => {
          setFrontendUptime(Math.floor((Date.now() - startTime) / 1000));
        }, 1000);
        return frontendTimer;
      }
    };
    
    let frontendTimer: NodeJS.Timeout;
    fetchFrontendStartTime().then(timer => {
      frontendTimer = timer;
    });

    // 定期更新后端运行时间（每秒递增）
    const backendTimer = setInterval(() => {
      setBackendUptime(prev => prev > 0 ? prev + 1 : prev);
    }, 1000);

    return () => {
      if (frontendTimer) clearInterval(frontendTimer);
      clearInterval(backendTimer);
    };
  }, []);

  // 性能监控独立定时更新
  useEffect(() => {
    if (apiStatus !== 'connected') return;
    
    // 首次加载性能数据
    fetchMetrics();
    
    // 每5秒更新一次性能数据
    const metricsTimer = setInterval(() => {
      fetchMetrics();
    }, 5000);

    return () => {
      clearInterval(metricsTimer);
    };
  }, [apiStatus]);

  // 格式化运行时间
  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    // @AI_GENERATED
    return `${hours}${t('systemStatus.hours')} ${minutes}${t('systemStatus.minutes')} ${secs}${t('systemStatus.seconds')}`;
    // @AI_GENERATED: end
  };
  
  // 格式化运行时间（返回对象，便于只更新数字部分）
  const formatUptimeObject = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return { hours, minutes, secs };
  };

  return (
    <ConfigProvider>
      <div 
        className="system-status-page"
        style={{ 
          padding: '16px',
          height: '100%',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column'
        }}
      >
        <Tabs
          key={tabsKey}
          activeKey={activeTab}
          onChange={setActiveTab}
          size={isMobile ? 'small' : 'large'}
          className="system-status-tabs"
          tabBarGutter={isMobile ? 16 : 32}
          style={{ 
            flex: 1,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            opacity: tabsVisible ? 1 : 0,
            transition: 'opacity 0.1s ease'
          }}
          items={[
            {
              key: 'service',
              label: (
                <span style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: isMobile ? '4px' : '8px',
                  fontWeight: 500
                }}>
                  <SettingOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
                  {!isMobile && <span>{t('systemStatus.serviceTab')}</span>}
                </span>
              ),
              children: (
                <div style={{ height: '100%', overflow: 'auto' }}>
                  <Space direction="vertical" size="large" style={{ width: '100%' }}>
                    {/* 服务状态概览 */}
                    <ServiceStatusCard
                      frontendStatus={frontendStatus}
                      apiStatus={apiStatus}
                      apiVersion={apiVersion}
                      serviceLoading={serviceLoading}
                      dbStatus={serviceDbStatus}
                      lastCheckTime={lastCheckTime}
                      frontendUptime={frontendUptime}
                      backendUptime={backendUptime}
                      isMobile={isMobile}
                      onRefresh={refreshServiceStatus}
                      formatUptime={formatUptime}
                    />

                    {/* 数据库状态 */}
                    <DatabaseStatusCard
                      apiStatus={apiStatus}
                      dbStatus={dbStatus}
                      dbStatusLoading={dbStatusLoading}
                      dbInfo={dbInfo}
                      isMobile={isMobile}
                      onRefresh={refreshDatabaseInfo}
                    />

                    {/* 性能监控 */}
                    <PerformanceMonitorCard
                      apiStatus={apiStatus}
                      metricsLoading={metricsLoading}
                      performanceData={performanceData}
                      isMobile={isMobile}
                      onRefresh={fetchMetrics}
                    />
                  </Space>
                </div>
              ),
            },
            {
              key: 'user',
              label: (
                <span style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: isMobile ? '4px' : '8px',
                  fontWeight: 500
                }}>
                  <UserOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
                  {!isMobile && <span>{t('systemStatus.userTab')}</span>}
                </span>
              ),
              children: (
                <div style={{ height: '100%', overflow: 'auto' }}>
                  <Space direction="vertical" size="large" style={{ width: '100%' }}>
                    {/* 系统统计 */}
                    {apiStatus === 'connected' && (
                      <Card title={t('systemStatus.systemStats')}>
                        {statsLoading ? (
                          <Skeleton active paragraph={{ rows: 2 }} />
                        ) : (
                          <Row gutter={[16, 16]}>
                            <Col xs={12} sm={12} md={6}>
                              <Statistic
                                title={t('systemStatus.totalUsers')}
                                value={statistics.totalUsers}
                                prefix={<DatabaseOutlined />}
                              />
                            </Col>
                            <Col xs={12} sm={12} md={6}>
                              <Statistic
                                title={t('systemStatus.onlineUsers')}
                                value={statistics.activeUsers}
                                valueStyle={{ color: '#3f8600' }}
                                prefix={<ApiOutlined />}
                              />
                            </Col>
                            <Col xs={12} sm={12} md={6}>
                              <Statistic
                                title={t('systemStatus.totalTemplates')}
                                value={statistics.totalWorkflows}
                                prefix={<CloudServerOutlined />}
                              />
                            </Col>
                            <Col xs={12} sm={12} md={6}>
                              <Statistic
                                title={t('systemStatus.todayExecutions')}
                                value={statistics.todayExecutions}
                                valueStyle={{ color: '#1890ff' }}
                              />
                            </Col>
                          </Row>
                        )}
                      </Card>
                    )}

                    {/* 最近活动 */}
                    {apiStatus === 'connected' && (
                      <Card title={t('systemStatus.recentActivity')}>
                        <Space direction="vertical" style={{ width: '100%' }} size="small">
                          <div>
                            <Tag color="success">{t('systemStatus.success')}</Tag>
                            <Text type="secondary">2 {t('systemStatus.minutesAgo')} - {t('systemStatus.userLogin')}</Text>
                          </div>
                          <div>
                            <Tag color="processing">{t('systemStatus.executing')}</Tag>
                            <Text type="secondary">5 {t('systemStatus.minutesAgo')} - {t('systemStatus.templateExecution')}</Text>
                          </div>
                          <div>
                            <Tag color="success">{t('systemStatus.success')}</Tag>
                            <Text type="secondary">10 {t('systemStatus.minutesAgo')} - {t('systemStatus.templateSave')}</Text>
                          </div>
                          <div>
                            <Tag color="success">{t('systemStatus.success')}</Tag>
                            <Text type="secondary">15 {t('systemStatus.minutesAgo')} - {t('systemStatus.functionCall')}</Text>
                          </div>
                        </Space>
                      </Card>
                    )}
                  </Space>
                </div>
              ),
            },
          ]}
        />
      </div>
    </ConfigProvider>
  );
};

export default SystemStatusPage;
