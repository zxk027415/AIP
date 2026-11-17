// @AI_GENERATED: Kiro v1.0
import { Card, Space, Typography, Grid, Button, Row, Col, Statistic, Spin, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import {
  FunctionOutlined,
  DashboardOutlined,
  UserOutlined,
  RocketOutlined,
  BuildOutlined,
  ThunderboltOutlined,
  ExperimentOutlined,
  NodeIndexOutlined,
  AppstoreOutlined,
  PartitionOutlined,
  BankOutlined,
  ClusterOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
import type { IndustryScenario, IndustryStats } from '../types/industry';

const { Title, Text, Paragraph } = Typography;
const { useBreakpoint } = Grid;

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  const username = localStorage.getItem('username') || '用户';
  const { t } = useTranslation();
  const [industryStats, setIndustryStats] = useState<IndustryStats | null>(null);
  const [scenarios, setScenarios] = useState<IndustryScenario[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/industry/stats').then(r => r.json()),
      fetch('/api/industry/scenarios').then(r => r.json()),
    ])
      .then(([indStats, scens]) => {
        setIndustryStats(indStats);
        setScenarios(scens);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: '16px', height: '100%', overflow: 'auto' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* 欢迎卡片 */}
        <Card
          style={{
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            border: 'none',
          }}
        >
          <Title level={isMobile ? 3 : 2} style={{ color: '#fff', marginBottom: '8px' }}>
            {t('home.welcomeBack', { name: username })}
          </Title>
          <Title level={isMobile ? 4 : 3} style={{ color: '#fff', fontWeight: 'bold', marginTop: 0, marginBottom: '12px' }}>
            {t('home.slogan')}
          </Title>
          <Paragraph style={{ color: 'rgba(255,255,255,0.9)', fontSize: isMobile ? '14px' : '16px', marginBottom: 0 }}>
            {t('home.statsDesc')}
          </Paragraph>
        </Card>

        {/* 核心数据展示 */}
        <Card>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '20px' }}><Spin /></div>
          ) : (
            <Row gutter={[16, 16]}>
              <Col xs={12} sm={6} md={4}>
                <Statistic
                  title={t('home.industries')}
                  value={industryStats?.total_industries ?? 8}
                  valueStyle={{ color: '#13c2c2' }}
                  prefix={<ThunderboltOutlined />}
                />
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Statistic
                  title={t('home.industryScenarios')}
                  value={industryStats?.total_scenarios ?? 13}
                  valueStyle={{ color: '#722ed1' }}
                  prefix={<BankOutlined />}
                />
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Statistic
                  title={t('home.industrySolutions')}
                  value={industryStats?.total_functions ?? 449}
                  valueStyle={{ color: '#3f8600' }}
                  prefix={<ExperimentOutlined />}
                />
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Statistic
                  title={t('home.algorithmTemplates')}
                  value={industryStats?.algorithm_templates ?? 13}
                  valueStyle={{ color: '#eb2f96' }}
                  prefix={<ClusterOutlined />}
                />
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Statistic
                  title={t('home.moduleCategories')}
                  value={industryStats?.categories ?? 19}
                  valueStyle={{ color: '#1890ff' }}
                  prefix={<BuildOutlined />}
                />
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Statistic
                  title={t('home.basicModules')}
                  value={industryStats?.basic_modules ?? 780}
                  valueStyle={{ color: '#faad14' }}
                  prefix={<AppstoreOutlined />}
                />
              </Col>
            </Row>
          )}
        </Card>

        {/* 行业场景快速入口 */}
        <Card
          title={<span><BankOutlined /> {t('home.industryAISolutions')}</span>}
          extra={<Button type="link" onClick={() => navigate('/industry')}>{t('home.viewAll', { count: 13 })} <RightOutlined /></Button>}
        >
          <Row gutter={[12, 12]}>
            {scenarios.slice(0, 8).map(s => (
              <Col xs={12} sm={8} md={6} lg={3} key={s.id}>
                <Card
                  size="small"
                  hoverable
                  onClick={() => navigate(`/industry/${s.id}`)}
                  style={{ textAlign: 'center', borderTop: `3px solid ${s.color}` }}
                >
                  <div style={{ fontSize: '28px', marginBottom: '4px' }}>{s.icon}</div>
                  <Text strong style={{ fontSize: '13px' }}>{td(s.name)}</Text>
                  <div><Tag color={s.color} style={{ fontSize: '11px' }}>{s.template_count} {t('home.templates')}</Tag></div>
                </Card>
              </Col>
            ))}
          </Row>
        </Card>

        {/* 快速导航 */}
        <Card title={t('home.quickNav')}>
          <Row gutter={[12, 12]}>
            {[
              { icon: <BankOutlined />, title: t('home.industryScenarioNav'), desc: t('home.industryScenarioDesc'), path: '/industry' },
              { icon: <FunctionOutlined />, title: t('home.basicAlgorithmNav'), desc: t('home.basicAlgorithmDesc'), path: '/functions' },
              { icon: <NodeIndexOutlined />, title: t('home.templateOrchestration'), desc: t('home.templateOrchestrationDesc'), path: '/workflow/editor' },
              { icon: <PartitionOutlined />, title: t('home.knowledgeGraph'), desc: t('home.knowledgeGraphDesc'), path: '/knowledge-graph' },
              { icon: <DashboardOutlined />, title: t('home.systemStatus'), desc: t('home.systemStatusDesc'), path: '/system-status' },
              { icon: <UserOutlined />, title: t('home.profile'), desc: t('home.profileDesc'), path: '/profile' },
            ].map((item, idx) => (
              <Col xs={12} sm={8} md={4} key={idx}>
                <Button
                  size="large"
                  onClick={() => navigate(item.path)}
                  style={{
                    height: '100px',
                    width: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <span style={{ fontSize: '24px', marginBottom: '6px' }}>{item.icon}</span>
                  <Text strong style={{ fontSize: '14px', display: 'block' }}>{item.title}</Text>
                  <Text style={{ color: 'rgba(0,0,0,0.45)', fontSize: '11px', display: 'block' }}>{item.desc}</Text>
                </Button>
              </Col>
            ))}
          </Row>
        </Card>

        {/* 平台核心能力 */}
        <Card title={<span><RocketOutlined /> {t('home.coreCapabilities')}</span>}>
          <Row gutter={[16, 16]}>
            {[
              { title: t('home.lowCode'), desc: t('home.lowCodeDesc') },
              { title: t('home.solutions'), desc: t('home.solutionsDesc') },
              { title: t('home.scenarios'), desc: t('home.scenariosDesc') },
              { title: t('home.smartTraining'), desc: t('home.smartTrainingDesc') },
            ].map((item, idx) => (
              <Col xs={24} sm={12} key={idx}>
                <Card type="inner" hoverable style={{ height: '100%' }}>
                  <Text strong style={{ fontSize: isMobile ? '16px' : '18px' }}>{item.title}</Text>
                  <Paragraph type="secondary" style={{ marginBottom: 0, marginTop: '8px', fontSize: isMobile ? '13px' : '14px' }}>
                    {item.desc}
                  </Paragraph>
                </Card>
              </Col>
            ))}
          </Row>
        </Card>
      </Space>
    </div>
  );
};

export default HomePage;
// @AI_GENERATED: end
