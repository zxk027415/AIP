// @AI_GENERATED: Kiro v1.0
import { useState, useCallback } from 'react';
import {
  Card, Button, Space, Typography, Tag, Row, Col, Collapse,
  Spin, Progress, Descriptions, Table, Statistic, Alert, Grid, message
} from 'antd';
import {
  PlayCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExperimentOutlined,
  DatabaseOutlined,
  AppstoreOutlined,
  FunctionOutlined,
  HistoryOutlined,
  AuditOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import api from '../services/api';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end

const { Title, Text } = Typography;
const { useBreakpoint } = Grid;

interface TestResult {
  success: boolean;
  duration: number;
  message?: string;
  data?: any;
  all_passed?: boolean;
  error?: string;
  detail?: string;
  category_stats?: Record<string, number>;
  function_version_stats?: Record<string, number>;
  action_stats?: Record<string, number>;
}

type TestStatus = 'idle' | 'running' | 'passed' | 'failed';

interface TestScenario {
  key: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  endpoint: string;
}

const scenarios: TestScenario[] = [
  {
    key: 'tables',
    title: 'algorithmDbTest.scenarioTables',
    description: 'algorithmDbTest.scenarioTablesDesc',
    icon: <DatabaseOutlined />,
    endpoint: '/algorithm-test/tables',
  },
  {
    key: 'categories',
    title: 'algorithmDbTest.scenarioCategories',
    description: 'algorithmDbTest.scenarioCategoriesDesc',
    icon: <AppstoreOutlined />,
    endpoint: '/algorithm-test/categories',
  },
  {
    key: 'functions',
    title: 'algorithmDbTest.scenarioFunctions',
    description: 'algorithmDbTest.scenarioFunctionsDesc',
    icon: <FunctionOutlined />,
    endpoint: '/algorithm-test/functions',
  },
  {
    key: 'versions',
    title: 'algorithmDbTest.scenarioVersions',
    description: 'algorithmDbTest.scenarioVersionsDesc',
    icon: <HistoryOutlined />,
    endpoint: '/algorithm-test/versions',
  },
  {
    key: 'consistency',
    title: 'algorithmDbTest.scenarioConsistency',
    description: 'algorithmDbTest.scenarioConsistencyDesc',
    icon: <SyncOutlined />,
    endpoint: '/algorithm-test/consistency',
  },
  {
    key: 'audit_logs',
    title: 'algorithmDbTest.scenarioAuditLogs',
    description: 'algorithmDbTest.scenarioAuditLogsDesc',
    icon: <AuditOutlined />,
    endpoint: '/algorithm-test/audit-logs',
  },
];

/** 渲染表结构测试的详细数据 */
const renderTablesDetail = (data: any[], t: (key: string) => string) => {
  if (!data) return null;
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="small">
      {data.map((table: any) => (
        <Card key={table.table} size="small" type="inner"
          title={<><Tag color={table.exists ? 'green' : 'red'}>{table.exists ? t('algorithmDbTest.exists') : t('algorithmDbTest.missing')}</Tag>{table.table}</>}
        >
          {table.exists && (
            <Table
              size="small" pagination={false} dataSource={table.columns}
              rowKey="name"
              columns={[
                { title: t('algorithmDbTest.fieldName'), dataIndex: 'name', key: 'name', width: 200 },
                { title: t('algorithmDbTest.fieldType'), dataIndex: 'type', key: 'type' },
              ]}
            />
          )}
        </Card>
      ))}
    </Space>
  );
};

/** 渲染分类数据 */
const renderCategoriesDetail = (data: any[], t: (key: string) => string) => {
  if (!data) return null;
  return (
    <Table size="small" pagination={false} dataSource={data} rowKey="id"
      columns={[
        { title: 'ID', dataIndex: 'id', key: 'id', width: 150 },
        { title: t('algorithmDbTest.colName'), dataIndex: 'name', key: 'name', width: 150 },
        { title: t('algorithmDbTest.colDescription'), dataIndex: 'description', key: 'description' },
        { title: t('algorithmDbTest.colOrder'), dataIndex: 'display_order', key: 'display_order', width: 80 },
      ]}
    />
  );
};

/** 渲染算法函数数据 */
const renderFunctionsDetail = (data: any[], t: (key: string) => string, categoryStats?: Record<string, number>) => {
  if (!data) return null;
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="small">
      {categoryStats && (
        <Row gutter={[8, 8]}>
          {Object.entries(categoryStats).map(([cat, count]) => (
            <Col key={cat}><Tag color="blue">{cat}: {count}{t('algorithmDbTest.unitCount')}</Tag></Col>
          ))}
        </Row>
      )}
      <Table size="small" pagination={{ pageSize: 10 }} dataSource={data} rowKey="id"
        columns={[
          { title: 'ID', dataIndex: 'id', key: 'id', width: 160 },
          { title: t('algorithmDbTest.colName'), dataIndex: 'name', key: 'name', width: 160 },
          { title: t('algorithmDbTest.colCategory'), dataIndex: 'category_name', key: 'category_name', width: 120 },
          { title: t('algorithmDbTest.colStatus'), dataIndex: 'status', key: 'status', width: 80,
            render: (s: string) => <Tag color={s === 'published' ? 'green' : 'orange'}>{s}</Tag> },
          { title: t('algorithmDbTest.colVersion'), dataIndex: 'version', key: 'version', width: 60 },
        ]}
      />
    </Space>
  );
};

/** 渲染版本记录 */
const renderVersionsDetail = (data: any[], t: (key: string) => string) => {
  if (!data) return null;
  return (
    <Table size="small" pagination={{ pageSize: 10 }} dataSource={data} rowKey="id"
      columns={[
        { title: t('algorithmDbTest.colFunction'), dataIndex: 'function_name', key: 'function_name', width: 160 },
        { title: t('algorithmDbTest.colVersion'), dataIndex: 'version', key: 'version', width: 60 },
        { title: t('algorithmDbTest.colChangeDesc'), dataIndex: 'change_description', key: 'change_description' },
        { title: t('algorithmDbTest.colCreatedAt'), dataIndex: 'created_at', key: 'created_at', width: 180 },
      ]}
    />
  );
};

/** 渲染一致性检查 */
const renderConsistencyDetail = (data: any, t: (key: string) => string) => {
  if (!data) return null;
  return (
    <Descriptions bordered size="small" column={2}>
      <Descriptions.Item label={t('algorithmDbTest.jsonCategories')}>{data.json_categories}</Descriptions.Item>
      <Descriptions.Item label={t('algorithmDbTest.dbCategories')}>{data.db_categories}</Descriptions.Item>
      <Descriptions.Item label={t('algorithmDbTest.jsonFunctions')}>{data.json_functions}</Descriptions.Item>
      <Descriptions.Item label={t('algorithmDbTest.dbFunctions')}>{data.db_functions}</Descriptions.Item>
      <Descriptions.Item label={t('algorithmDbTest.missingCategoriesInDb')} span={2}>
        {data.missing_categories_in_db?.length > 0
          ? data.missing_categories_in_db.map((c: string) => <Tag key={c} color="red">{c}</Tag>)
          : <Tag color="green">{t('algorithmDbTest.none')}</Tag>}
      </Descriptions.Item>
      <Descriptions.Item label={t('algorithmDbTest.missingFunctionsInDb')} span={2}>
        {data.missing_functions_in_db?.length > 0
          ? data.missing_functions_in_db.map((f: string) => <Tag key={f} color="red">{f}</Tag>)
          : <Tag color="green">{t('algorithmDbTest.none')}</Tag>}
      </Descriptions.Item>
    </Descriptions>
  );
};

/** 渲染审计日志 */
const renderAuditLogsDetail = (data: any[], t: (key: string) => string, actionStats?: Record<string, number>) => {
  if (!data) return null;
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="small">
      {actionStats && Object.keys(actionStats).length > 0 && (
        <Row gutter={[8, 8]}>
          {Object.entries(actionStats).map(([action, count]) => (
            <Col key={action}><Tag color="purple">{action}: {count}</Tag></Col>
          ))}
        </Row>
      )}
      {data.length === 0
        ? <Alert message={t('algorithmDbTest.auditLogEmpty')} type="info" showIcon />
        : (
          <Table size="small" pagination={{ pageSize: 10 }} dataSource={data} rowKey="id"
            columns={[
              { title: t('algorithmDbTest.colAction'), dataIndex: 'action', key: 'action', width: 100 },
              { title: t('algorithmDbTest.colObjectType'), dataIndex: 'object_type', key: 'object_type', width: 100 },
              { title: t('algorithmDbTest.colObjectId'), dataIndex: 'object_id', key: 'object_id', width: 160 },
              { title: t('algorithmDbTest.colTime'), dataIndex: 'created_at', key: 'created_at', width: 180 },
            ]}
          />
        )}
    </Space>
  );
};

const AlgorithmDbTestPage: React.FC = () => {
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end

  const [statuses, setStatuses] = useState<Record<string, TestStatus>>(
    Object.fromEntries(scenarios.map(s => [s.key, 'idle' as TestStatus]))
  );
  const [results, setResults] = useState<Record<string, TestResult>>({});
  const [runningAll, setRunningAll] = useState(false);

  const runSingleTest = useCallback(async (scenario: TestScenario) => {
    setStatuses(prev => ({ ...prev, [scenario.key]: 'running' }));
    try {
      const res: any = await api.get(scenario.endpoint);
      const result: TestResult = res;
      setResults(prev => ({ ...prev, [scenario.key]: result }));
      setStatuses(prev => ({
        ...prev,
        [scenario.key]: result.success && result.all_passed ? 'passed' : 'failed'
      }));
    } catch (err: any) {
      setResults(prev => ({
        ...prev,
        [scenario.key]: {
          success: false, duration: 0, all_passed: false,
          error: err?.message || t('algorithmDbTest.requestFailed'),
        }
      }));
      setStatuses(prev => ({ ...prev, [scenario.key]: 'failed' }));
    }
  }, []);

  const runAllTests = useCallback(async () => {
    setRunningAll(true);
    // 重置所有状态
    setStatuses(Object.fromEntries(scenarios.map(s => [s.key, 'idle' as TestStatus])));
    setResults({});
    for (const scenario of scenarios) {
      await runSingleTest(scenario);
    }
    setRunningAll(false);
  }, [runSingleTest]);

  const statusIcon = (status: TestStatus) => {
    switch (status) {
      case 'running': return <Spin size="small" />;
      case 'passed': return <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 20 }} />;
      case 'failed': return <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 20 }} />;
      default: return <ExperimentOutlined style={{ color: '#999', fontSize: 20 }} />;
    }
  };

  const statusTag = (status: TestStatus) => {
    switch (status) {
      // @AI_GENERATED
      case 'running': return <Tag color="processing">{t('algorithmDbTest.statusRunning')}</Tag>;
      case 'passed': return <Tag color="success">{t('algorithmDbTest.statusPassed')}</Tag>;
      case 'failed': return <Tag color="error">{t('algorithmDbTest.statusFailed')}</Tag>;
      default: return <Tag>{t('algorithmDbTest.statusPending')}</Tag>;
      // @AI_GENERATED: end
    }
  };

  const totalRun = Object.values(statuses).filter(s => s !== 'idle').length;
  const totalPassed = Object.values(statuses).filter(s => s === 'passed').length;
  const totalFailed = Object.values(statuses).filter(s => s === 'failed').length;

  const renderDetail = (key: string, result: TestResult) => {
    // @AI_GENERATED
    switch (key) {
      case 'tables': return renderTablesDetail(result.data, t);
      case 'categories': return renderCategoriesDetail(result.data, t);
      case 'functions': return renderFunctionsDetail(result.data, t, result.category_stats);
      case 'versions': return renderVersionsDetail(result.data, t);
      case 'consistency': return renderConsistencyDetail(result.data, t);
      case 'audit_logs': return renderAuditLogsDetail(result.data, t, result.action_stats);
      default: return <pre>{JSON.stringify(result.data, null, 2)}</pre>;
    }
    // @AI_GENERATED: end
  };

  const exportTestLog = useCallback(() => {
    const hasResults = Object.keys(results).length > 0;
    if (!hasResults) {
      message.warning(t('algorithmDbTest.noTestResults'));
      return;
    }
    const lines: string[] = [];
    lines.push('========================================');
    lines.push(`  ${t('algorithmDbTest.testReportTitle')}`);
    lines.push(`  ${t('algorithmDbTest.time')}: ${new Date().toLocaleString()}`);
    lines.push('========================================');
    lines.push('');
    lines.push(`${t('algorithmDbTest.total')}: ${scenarios.length} ${t('algorithmDbTest.items')} | ${t('algorithmDbTest.passed')}: ${totalPassed} ${t('algorithmDbTest.items')} | ${t('algorithmDbTest.failed')}: ${totalFailed} ${t('algorithmDbTest.items')} | ${t('algorithmDbTest.passRate')}: ${scenarios.length > 0 ? Math.round((totalPassed / scenarios.length) * 100) : 0}%`);
    lines.push('');
    for (const scenario of scenarios) {
      const status = statuses[scenario.key];
      const result = results[scenario.key];
      const statusLabel = status === 'passed' ? `✅ ${t('algorithmDbTest.passed')}` : status === 'failed' ? `❌ ${t('algorithmDbTest.failed')}` : `⏳ ${t('algorithmDbTest.notRun')}`;
      lines.push(`--- ${t(scenario.title)} [${statusLabel}] ---`);
      if (result) {
        lines.push(`  ${t('algorithmDbTest.message')}: ${result.message || '-'}`);
        lines.push(`  ${t('algorithmDbTest.duration')}: ${result.duration}s`);
        if (result.error) lines.push(`  ${t('algorithmDbTest.error')}: ${result.error}`);
        if (result.data) lines.push(`  ${t('algorithmDbTest.data')}: ${JSON.stringify(result.data, null, 2).split('\n').join('\n  ')}`);
      } else {
        lines.push(`  (${t('algorithmDbTest.notRun')})`);
      }
      lines.push('');
    }
    const logText = lines.join('\n');
    navigator.clipboard.writeText(logText).then(() => {
      message.success(t('algorithmDbTest.reportCopied'));
    }).catch(() => {
      message.error(t('algorithmDbTest.copyFailed'));
    });
  }, [results, statuses, totalPassed, totalFailed]);

  return (
    <div style={{ padding: isMobile ? 12 : 24, background: '#f5f5f5', minHeight: '100%' }}>
      {/* 顶部统计 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col flex="auto">
            <Space direction="vertical" size={4}>
              <Title level={4} style={{ margin: 0 }}>
                <ExperimentOutlined /> {t('algorithmDbTest.pageTitle')}
              </Title>
              <Text type="secondary">
                {t('algorithmDbTest.pageSubtitle')}
              </Text>
            </Space>
          </Col>
          <Col>
            <Space>
              <Button
                type="primary" size="large"
                icon={<ThunderboltOutlined />}
                loading={runningAll}
                onClick={runAllTests}
              >
                {t('algorithmDbTest.runAll')}
              </Button>
              <Button
                size="large"
                icon={<CopyOutlined />}
                onClick={exportTestLog}
                disabled={Object.keys(results).length === 0}
              >
                {t('algorithmDbTest.exportLog')}
              </Button>
            </Space>
          </Col>
        </Row>
        {totalRun > 0 && (
          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={6}>
              <Statistic title={t('algorithmDbTest.total')} value={scenarios.length} suffix={t('algorithmDbTest.items')} />
            </Col>
            <Col span={6}>
              <Statistic title={t('algorithmDbTest.passed')} value={totalPassed}
                valueStyle={{ color: '#52c41a' }} suffix={t('algorithmDbTest.items')} />
            </Col>
            <Col span={6}>
              <Statistic title={t('algorithmDbTest.failed')} value={totalFailed}
                valueStyle={{ color: totalFailed > 0 ? '#ff4d4f' : undefined }} suffix={t('algorithmDbTest.items')} />
            </Col>
            <Col span={6}>
              <Statistic title={t('algorithmDbTest.passRate')}
                value={totalRun > 0 ? Math.round((totalPassed / scenarios.length) * 100) : 0}
                suffix="%" />
              <Progress
                percent={Math.round((totalPassed / scenarios.length) * 100)}
                size="small" showInfo={false}
                status={totalFailed > 0 ? 'exception' : 'active'}
              />
            </Col>
          </Row>
        )}
      </Card>

      {/* 测试场景卡片 */}
      <Row gutter={[16, 16]}>
        {scenarios.map((scenario) => {
          const status = statuses[scenario.key];
          const result = results[scenario.key];
          return (
            <Col xs={24} lg={12} key={scenario.key}>
              <Card
                hoverable
                style={{
                  borderLeft: status === 'passed' ? '4px solid #52c41a'
                    : status === 'failed' ? '4px solid #ff4d4f'
                    : '4px solid #d9d9d9'
                }}
              >
                <Row align="middle" gutter={12}>
                  <Col>{statusIcon(status)}</Col>
                  <Col flex="auto">
                    <Space>
                      {scenario.icon}
                      <Text strong>{t(scenario.title)}</Text>
                      {statusTag(status)}
                    </Space>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {t(scenario.description)}
                    </Text>
                  </Col>
                  <Col>
                    <Button
                      type={status === 'idle' ? 'primary' : 'default'}
                      icon={<PlayCircleOutlined />}
                      loading={status === 'running'}
                      onClick={() => runSingleTest(scenario)}
                      disabled={runningAll && status !== 'running'}
                      size="small"
                    >
                      {t('algorithmDbTest.run')}
                    </Button>
                  </Col>
                </Row>

                {result && (
                  <div style={{ marginTop: 12 }}>
                    <Space size="small" style={{ marginBottom: 8 }}>
                      <Tag>{result.message}</Tag>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {t('algorithmDbTest.duration')}: {result.duration}s
                      </Text>
                    </Space>
                    {result.error && (
                      <Alert type="error" message={result.error}
                        description={result.detail} showIcon
                        style={{ marginBottom: 8 }} />
                    )}
                    <Collapse
                      size="small"
                      items={[{
                        key: '1',
                        label: t('algorithmDbTest.viewDetails'),
                        children: renderDetail(scenario.key, result),
                      }]}
                    />
                  </div>
                )}
              </Card>
            </Col>
          );
        })}
      </Row>
    </div>
  );
};

export default AlgorithmDbTestPage;
// @AI_GENERATED: end
