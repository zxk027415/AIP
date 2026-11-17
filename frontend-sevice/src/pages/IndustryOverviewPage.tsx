// @AI_GENERATED: Kiro v1.0
import { useState, useEffect, useMemo } from 'react';
import { Card, Row, Col, Tag, Typography, Spin, Grid, Statistic, Space } from 'antd';
import { useNavigate } from 'react-router-dom';
import {
  AppstoreOutlined,
  ExperimentOutlined,
  ClusterOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { industryApi } from '../services/industryApi';
import { useTranslation } from 'react-i18next';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
import type { IndustryScenario, IndustryStats } from '../types/industry';

const { Title, Text, Paragraph } = Typography;
const { useBreakpoint } = Grid;
const { CheckableTag } = Tag;

// @AI_GENERATED: Kiro v1.0
const INDUSTRY_TAGS = ['全部', '新能源', '传统能源', '源网荷储', '工业制造', '港口运输', '楼宇园区', '碳管理', '公用事业'];
// @AI_GENERATED: end

const IndustryOverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  const { t } = useTranslation();

  const [scenarios, setScenarios] = useState<IndustryScenario[]>([]);
  const [stats, setStats] = useState<IndustryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTags, setSelectedTags] = useState<string[]>(['全部']);

  useEffect(() => {
    Promise.all([industryApi.getScenarios(), industryApi.getStats()])
      .then(([s, st]) => { setScenarios(s); setStats(st); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleTagChange = (tag: string, checked: boolean) => {
    if (tag === '全部') {
      setSelectedTags(['全部']);
      return;
    }
    let next = selectedTags.filter(t => t !== '全部');
    if (checked) next.push(tag);
    else next = next.filter(t => t !== tag);
    setSelectedTags(next.length === 0 ? ['全部'] : next);
  };

  const filtered = useMemo(() => {
    if (selectedTags.includes('全部')) return scenarios;
    return scenarios.filter(s =>
      s.industry_tags.some(t => selectedTags.includes(t))
    );
  }, [scenarios, selectedTags]);

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '80px 0' }}><Spin size="large" /></div>;
  }

  return (
    <div style={{ padding: isMobile ? '12px' : '24px', height: '100%', overflow: 'auto' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* 页面头部 */}
        <div>
          <Title level={isMobile ? 4 : 3} style={{ marginBottom: 4 }}>{t('industry.title')}</Title>
          <Text type="secondary">{t('industry.subtitle', { count: stats?.total_functions ?? 1054 })}</Text>
        </div>

        {/* 行业标签筛选 */}
        <Card size="small">
          <Space wrap>
            <Text strong>{t('industry.filterLabel')}</Text>
            {INDUSTRY_TAGS.map(tag => (
              <CheckableTag
                key={tag}
                checked={selectedTags.includes(tag)}
                onChange={checked => handleTagChange(tag, checked)}
                style={{ fontSize: '14px', padding: '2px 10px' }}
              >
                {td(tag)}
              </CheckableTag>
            ))}
          </Space>
        </Card>

        {/* 场景卡片网格 */}
        <Row gutter={[16, 16]}>
          {filtered.map(scenario => (
            <Col xs={24} sm={12} md={8} lg={6} key={scenario.id}>
              <Card
                hoverable
                onClick={() => navigate(`/industry/${scenario.id}`)}
                style={{ borderTop: `3px solid ${scenario.color}`, height: '100%' }}
                styles={{ body: { padding: '16px' } }}
              >
                <div style={{ fontSize: '36px', marginBottom: '8px' }}>{scenario.icon}</div>
                <Title level={5} style={{ marginBottom: '4px', marginTop: 0 }}>{td(scenario.name)}</Title>
                <Paragraph
                  type="secondary"
                  ellipsis={{ rows: 2 }}
                  style={{ fontSize: '13px', marginBottom: '10px' }}
                >
                  {td(scenario.description)}
                </Paragraph>
                <Space wrap size={[4, 4]} style={{ marginBottom: '8px' }}>
                  {scenario.capabilities.map(cap => (
                    <Tag key={cap} color={scenario.color} style={{ fontSize: '11px' }}>{td(cap)}</Tag>
                  ))}
                </Space>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px' }}>
                  <Text type="secondary" style={{ fontSize: '12px' }}>
                    {scenario.template_count} {t('home.templates')} · {scenario.function_count} {t('functions.functionsCount', { count: '' }).replace('  ', ' ')}
                  </Text>
                  <RightOutlined style={{ color: '#999', fontSize: '12px' }} />
                </div>
              </Card>
            </Col>
          ))}
        </Row>

        {/* 底部统计 */}
        {stats && (
          <Card>
            <Row gutter={[16, 16]}>
              <Col xs={8} sm={6} md={4}>
                <Statistic title={t('industry.industryScenarios')} value={stats.total_scenarios} prefix={<AppstoreOutlined />} />
              </Col>
              <Col xs={8} sm={6} md={4}>
                <Statistic title={t('industry.industrySolutions')} value={stats.total_industry_templates} prefix={<ExperimentOutlined />} />
              </Col>
              <Col xs={8} sm={6} md={4}>
                <Statistic title={t('industry.totalAlgorithms')} value={stats.total_functions} prefix={<ClusterOutlined />} />
              </Col>
              <Col xs={8} sm={6} md={4}>
                <Statistic title={t('industry.basicModules')} value={stats.basic_modules} />
              </Col>
              <Col xs={8} sm={6} md={4}>
                <Statistic title={t('industry.moduleCategories')} value={stats.categories} />
              </Col>
              <Col xs={8} sm={6} md={4}>
                <Statistic title={t('industry.coveredIndustries')} value={stats.total_industries} />
              </Col>
            </Row>
          </Card>
        )}
      </Space>
    </div>
  );
};

export default IndustryOverviewPage;
// @AI_GENERATED: end
