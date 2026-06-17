// @AI_GENERATED: Kiro v1.0
/**
 * 方案应用实例页面
 * 展示算法方案在算法模板中的实际使用情况
 */
import { useState, useEffect } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Table, Space, Typography, Tag, Row, Col, Statistic, Spin, Input, Select, Empty,
} from 'antd';
import {
  AppstoreOutlined, DeploymentUnitOutlined, ThunderboltOutlined,
  LinkOutlined, SearchOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { fetchApplicationStats, fetchTemplateStats } from '../services/algorithmSolutionApi';
import type { TemplateStats, ApplicationStats } from '../types/algorithm-solution';
import { td } from '../utils/dataTranslation';

const { Text } = Typography;

interface UsageRow {
  template_id: string;
  template_name: string;
  workflow_count: number;
  workflows: string[];
}

const TemplateApplicationPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const navigate = useNavigate();
  const [stats, setStats] = useState<ApplicationStats | null>(null);
  const [tplStats, setTplStats] = useState<TemplateStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [scenarioFilter, setScenarioFilter] = useState<string | undefined>(undefined);
  const [rows, setRows] = useState<UsageRow[]>([]);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchApplicationStats(), fetchTemplateStats()]).then(([appStats, ts]) => {
      setStats(appStats);
      setTplStats(ts);
      const usageRows: UsageRow[] = Object.entries(appStats.usage).map(([tid, u]) => ({
        template_id: tid,
        template_name: tid.replace(/_/g, ' '),
        workflow_count: u.count,
        workflows: u.workflows,
      }));
      usageRows.sort((a, b) => b.workflow_count - a.workflow_count);
      setRows(usageRows);
      setLoading(false);
    });
  }, []);

  const filteredRows = rows.filter(r => {
    if (keyword && !r.template_id.toLowerCase().includes(keyword.toLowerCase()) && !r.template_name.toLowerCase().includes(keyword.toLowerCase())) return false;
    return true;
  });

  const columns = [
    {
      title: t('templateApplication.templateId'), dataIndex: 'template_id', key: 'id',
      render: (v: string) => <Text copyable={{ text: v }} style={{ fontSize: 12 }}>{v}</Text>,
    },
    { title: t('templateApplication.templateName'), dataIndex: 'template_name', key: 'name', render: (v: string) => td(v) },
    {
      title: t('templateApplication.workflowRefCount'), dataIndex: 'workflow_count', key: 'count', width: 130,
      sorter: (a: UsageRow, b: UsageRow) => a.workflow_count - b.workflow_count,
      render: (v: number) => <Tag color="blue">{t('templateApplication.workflowCount', { count: v })}</Tag>,
    },
    {
      title: t('templateApplication.relatedWorkflows'), dataIndex: 'workflows', key: 'workflows',
      render: (wfs: string[]) => (
        <Space size={4} wrap>
          {wfs.slice(0, 3).map(w => (
            <Tag key={w} color="default" style={{ cursor: 'pointer', fontSize: 11 }}
              onClick={() => navigate(`/workflow/editor/${w.replace('.json', '').replace('workflow-', '')}`)}
            >
              <LinkOutlined /> {w.replace('.json', '').slice(-12)}
            </Tag>
          ))}
          {wfs.length > 3 && <Tag>+{wfs.length - 3}</Tag>}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Space wrap style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Text strong style={{ fontSize: 16 }}>{t('templateApplication.title')}</Text>
        <Space>
          <Input prefix={<SearchOutlined />} placeholder={t('templateApplication.searchTemplate')} allowClear
            style={{ width: 200 }} value={keyword} onChange={e => setKeyword(e.target.value)}
          />
          {tplStats && (
            <Select style={{ width: 180 }} placeholder={t('templateApplication.filterByScenario')} allowClear
              value={scenarioFilter} onChange={setScenarioFilter}
              options={tplStats.by_scenario.map(s => ({ value: s.scenario_id, label: `${s.icon} ${td(s.name)}` }))}
            />
          )}
        </Space>
      </Space>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title={t('templateApplication.templatesUsed')} value={stats?.total_templates_used || 0} prefix={<AppstoreOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title={t('templateApplication.totalWorkflows')} value={stats?.total_workflows || 0} prefix={<DeploymentUnitOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title={t('templateApplication.totalReferences')} value={rows.reduce((s, r) => s + r.workflow_count, 0)} prefix={<ThunderboltOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title={t('templateApplication.avgReferences')} value={rows.length > 0 ? (rows.reduce((s, r) => s + r.workflow_count, 0) / rows.length).toFixed(1) : 0} suffix={t('templateApplication.perTemplate')} />
          </Card>
        </Col>
      </Row>

      <Card>
        <Spin spinning={loading}>
          {filteredRows.length > 0 ? (
            <Table dataSource={filteredRows} columns={columns} rowKey="template_id" size="small"
              pagination={{ pageSize: 20, showTotal: total => t('templateApplication.totalTemplates', { count: total }) }}
            />
          ) : (
            <Empty description={t('templateApplication.noData')} />
          )}
        </Spin>
      </Card>
    </div>
  );
};

export default TemplateApplicationPage;
// @AI_GENERATED: end
