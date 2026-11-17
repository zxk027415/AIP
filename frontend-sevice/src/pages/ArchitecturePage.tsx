// @AI_GENERATED
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
import { 
  Card, 
  Space, 
  Typography, 
  Grid, 
  Descriptions, 
  Tag, 
  Tabs, 
  Table, 
  Button, 
  message,
  Popconfirm,
  Divider,
  Alert,
  ConfigProvider
} from 'antd';
import { 
  ReloadOutlined, 
  UploadOutlined, 
  DeleteOutlined,
  AppstoreOutlined,
  CodeOutlined,
  ApartmentOutlined,
  NodeIndexOutlined,
  PythonOutlined
} from '@ant-design/icons';
import ArchitectureDiagram from '../components/architecture/ArchitectureDiagram';
import './ArchitecturePage.css';

const { Text, Title, Paragraph } = Typography;
const { useBreakpoint } = Grid;

/**
 * 开发架构页面
 * 
 * 显示技术栈信息、功能模块状态、总体架构和包管理
 * 支持响应式布局
 */
const ArchitecturePage: React.FC = () => {
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  const [selectedNpmRows, setSelectedNpmRows] = useState<string[]>([]);
  const [selectedPipRows, setSelectedPipRows] = useState<string[]>([]);
  const [npmLoading, setNpmLoading] = useState(false);
  const [pipLoading, setPipLoading] = useState(false);
  const [tabsKey, setTabsKey] = useState(0);
  const [tabsVisible, setTabsVisible] = useState(false);

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

  // @AI_GENERATED
  // NPM 包数据
  const npmPackages = [
    { key: 'react', name: 'react', version: '18.2.0', description: td('React 核心库'), type: 'dependencies' },
    { key: 'react-dom', name: 'react-dom', version: '18.2.0', description: td('React DOM 渲染器'), type: 'dependencies' },
    { key: 'react-router-dom', name: 'react-router-dom', version: '6.20.0', description: td('路由管理'), type: 'dependencies' },
    { key: 'antd', name: 'antd', version: '5.12.0', description: td('Ant Design UI 组件库'), type: 'dependencies' },
    { key: 'reactflow', name: 'reactflow', version: '11.10.0', description: td('模板可视化编辑'), type: 'dependencies' },
    { key: 'echarts', name: 'echarts', version: '5.6.0', description: td('数据可视化图表库'), type: 'dependencies' },
    { key: 'echarts-for-react', name: 'echarts-for-react', version: '3.0.6', description: td('ECharts React 封装'), type: 'dependencies' },
    { key: 'axios', name: 'axios', version: '1.6.0', description: td('HTTP 客户端'), type: 'dependencies' },
    { key: 'zustand', name: 'zustand', version: '4.4.7', description: td('状态管理库'), type: 'dependencies' },
    { key: 'typescript', name: 'typescript', version: '5.2.0', description: td('TypeScript 编译器'), type: 'devDependencies' },
    { key: 'vite', name: 'vite', version: '5.0.0', description: td('前端构建工具'), type: 'devDependencies' },
    { key: 'jest', name: 'jest', version: '30.2.0', description: td('测试框架'), type: 'devDependencies' },
    { key: '@testing-library/react', name: '@testing-library/react', version: '16.3.2', description: td('React 测试工具'), type: 'devDependencies' },
    { key: 'eslint', name: 'eslint', version: '8.55.0', description: td('代码检查工具'), type: 'devDependencies' },
    { key: 'tailwindcss', name: 'tailwindcss', version: '3.4.0', description: td('CSS 框架'), type: 'devDependencies' },
  ];
  // @AI_GENERATED: end

  // @AI_GENERATED
  // PIP 包数据
  const pipPackages = [
    { key: 'fastapi', name: 'fastapi', version: '0.109.0', description: td('Web 框架'), type: 'core' },
    { key: 'uvicorn', name: 'uvicorn', version: '0.27.0', description: td('ASGI 服务器'), type: 'core' },
    { key: 'pydantic', name: 'pydantic', version: '2.5.3', description: td('数据验证'), type: 'core' },
    { key: 'numpy', name: 'numpy', version: '1.24.3', description: td('科学计算库'), type: 'compute' },
    { key: 'scipy', name: 'scipy', version: '1.11.4', description: td('科学计算扩展'), type: 'compute' },
    { key: 'networkx', name: 'networkx', version: '3.1', description: td('图算法库'), type: 'compute' },
    { key: 'sqlalchemy', name: 'SQLAlchemy', version: '2.0.25', description: td('ORM 框架'), type: 'database' },
    { key: 'passlib', name: 'passlib', version: '1.7.4', description: td('密码哈希'), type: 'auth' },
    { key: 'bcrypt', name: 'bcrypt', version: '4.1.2', description: td('加密算法'), type: 'auth' },
    { key: 'python-jose', name: 'python-jose', version: '3.3.0', description: td('JWT 处理'), type: 'auth' },
    { key: 'pytest', name: 'pytest', version: '7.4.3', description: td('测试框架'), type: 'test' },
    { key: 'hypothesis', name: 'hypothesis', version: '6.92.1', description: td('属性测试'), type: 'test' },
    { key: 'httpx', name: 'httpx', version: '0.25.2', description: td('HTTP 客户端'), type: 'test' },
  ];
  // @AI_GENERATED: end

  // NPM 包表格列
  const npmColumns = [
    {
      title: t('architecture.packageName'),
      dataIndex: 'name',
      key: 'name',
      width: isMobile ? 120 : 200,
      ellipsis: true,
    },
    {
      title: t('architecture.version'),
      dataIndex: 'version',
      key: 'version',
      width: isMobile ? 80 : 100,
    },
    ...(!isMobile ? [{
      title: t('architecture.description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    }] : []),
    {
      title: t('architecture.type'),
      dataIndex: 'type',
      key: 'type',
      width: isMobile ? 80 : 120,
      render: (type: string) => (
        <Tag color={type === 'dependencies' ? 'blue' : 'green'}>
          {type === 'dependencies' ? t('architecture.dependency') : t('architecture.dev')}
        </Tag>
      ),
    },
  ];

  // PIP 包表格列
  const pipColumns = [
    {
      title: t('architecture.packageName'),
      dataIndex: 'name',
      key: 'name',
      width: isMobile ? 120 : 200,
      ellipsis: true,
    },
    {
      title: t('architecture.version'),
      dataIndex: 'version',
      key: 'version',
      width: isMobile ? 80 : 100,
    },
    ...(!isMobile ? [{
      title: t('architecture.description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    }] : []),
    {
      title: t('architecture.type'),
      dataIndex: 'type',
      key: 'type',
      width: isMobile ? 80 : 120,
      render: (type: string) => {
        const typeMap: Record<string, { color: string; text: string }> = {
          core: { color: 'blue', text: t('architecture.core') },
          compute: { color: 'purple', text: t('architecture.compute') },
          database: { color: 'cyan', text: t('architecture.database') },
          auth: { color: 'orange', text: t('architecture.auth') },
          test: { color: 'green', text: t('architecture.test') },
        };
        const config = typeMap[type] || { color: 'default', text: type };
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
  ];

  // 刷新 NPM 包列表
  const handleRefreshNpm = () => {
    setNpmLoading(true);
    setTimeout(() => {
      setNpmLoading(false);
      message.success(t('architecture.npmRefreshed'));
    }, 1000);
  };

  // 更新 NPM 包
  const handleUpdateNpm = () => {
    if (selectedNpmRows.length === 0) {
      message.warning(t('architecture.selectPackagesFirst'));
      return;
    }
    message.info(t('architecture.prepareUpdate', { count: selectedNpmRows.length }));
  };

  // 删除 NPM 包
  const handleDeleteNpm = () => {
    if (selectedNpmRows.length === 0) {
      message.warning(t('architecture.selectPackagesDeleteFirst'));
      return;
    }
    message.success(t('architecture.deletedPackages', { count: selectedNpmRows.length }));
    setSelectedNpmRows([]);
  };

  // 刷新 PIP 包列表
  const handleRefreshPip = () => {
    setPipLoading(true);
    setTimeout(() => {
      setPipLoading(false);
      message.success(t('architecture.pipRefreshed'));
    }, 1000);
  };

  // 更新 PIP 包
  const handleUpdatePip = () => {
    if (selectedPipRows.length === 0) {
      message.warning(t('architecture.selectPackagesFirst'));
      return;
    }
    message.info(t('architecture.prepareUpdate', { count: selectedPipRows.length }));
  };

  // 删除 PIP 包
  const handleDeletePip = () => {
    if (selectedPipRows.length === 0) {
      message.warning(t('architecture.selectPackagesDeleteFirst'));
      return;
    }
    message.success(t('architecture.deletedPackages', { count: selectedPipRows.length }));
    setSelectedPipRows([]);
  };

  // Tab 内容
  const tabItems = [
    {
      key: 'tech-stack',
      label: (
        <span style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: isMobile ? '4px' : '8px',
          fontWeight: 500
        }}>
          <CodeOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
          {!isMobile && <span>{t('architecture.techStack')}</span>}
        </span>
      ),
      children: (
        <div className="architecture-tab-content">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Alert
              message={t('architecture.techStackOverview')}
              description={t('architecture.techStackDesc')}
              type="info"
              showIcon
              className="architecture-alert"
            />
            <Descriptions 
              column={1} 
              bordered 
              size={isMobile ? 'small' : 'middle'}
              className="tech-stack-card"
              labelStyle={{ fontWeight: 600, width: isMobile ? '100px' : '140px' }}
            >
              <Descriptions.Item label={t('architecture.frontendFramework')}>
                <Tag color="blue">React 18.2</Tag>
                <Tag color="blue">TypeScript 5.2</Tag>
                <Tag color="blue">Vite 5.0</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.uiLibrary')}>
                <Tag color="cyan">Ant Design 5.12.0</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.templateEditor')}>
                <Tag color="purple">React Flow 11.10.0</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.dataVisualization')}>
                <Tag color="magenta">ECharts 5.6.0</Tag>
                <Tag color="magenta">ECharts for React 3.0.6</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.stateManagement')}>
                <Tag color="geekblue">Zustand 4.4.7</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.httpClient')}>
                <Tag color="green">Axios 1.6.0</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.backendFramework')}>
                <Tag color="orange">Python 3.10+</Tag>
                <Tag color="orange">FastAPI 0.109.0</Tag>
                <Tag color="orange">Uvicorn 0.27.0</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.computeLibrary')}>
                <Tag color="volcano">NumPy 1.24.3</Tag>
                <Tag color="volcano">SciPy 1.11.4</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.graphAlgorithm')}>
                <Tag color="red">NetworkX 3.1</Tag>
                <Text type="secondary" style={{ marginLeft: 8, fontSize: '12px' }}>
                  {t('architecture.graphAlgorithmNote')}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.databaseLabel')}>
                <Tag color="lime">SQLite</Tag>
                <Tag color="lime">SQLAlchemy 2.0.25</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.authentication')}>
                <Tag color="gold">JWT</Tag>
                <Tag color="gold">python-jose 3.3.0</Tag>
                <Tag color="gold">bcrypt 4.1.2</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('architecture.testFramework')}>
                <Tag color="cyan">Jest 30.2.0</Tag>
                <Tag color="cyan">Pytest 7.4.3</Tag>
                <Tag color="cyan">Hypothesis 6.92.1</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Space>
        </div>
      ),
    },
    {
      key: 'modules',
      label: (
        <span style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: isMobile ? '4px' : '8px',
          fontWeight: 500
        }}>
          <AppstoreOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
          {!isMobile && <span>{t('architecture.modules')}</span>}
        </span>
      ),
      children: (
        <div className="architecture-tab-content">
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Alert
              message={t('architecture.moduleDevStatus')}
              description={t('architecture.moduleDevStatusDesc')}
              type="info"
              showIcon
              className="architecture-alert"
            />

            {/* Stage 1: MVP增强版 */}
            <div>
              <Title level={4} style={{ marginBottom: 16, color: '#1890ff' }}>
                📦 {t('architecture.stage1Title')}
              </Title>
              
              <div style={{ marginLeft: 16 }}>
                <Title level={5} style={{ marginBottom: 12 }}>
                  <Tag color="success">{t('architecture.completed')}</Tag>
                  {t('architecture.stage1CoreInfra')}
                </Title>
                {/* @AI_GENERATED */}
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_userAuth')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_dbSchema')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_projectStructure')}</Text>
                  </div>
                </Space>
                {/* @AI_GENERATED: end */}

                <Divider style={{ margin: '16px 0' }} />

                <Title level={5} style={{ marginBottom: 12 }}>
                  <Tag color="success">{t('architecture.completed')}</Tag>
                  {t('architecture.stage1TemplateEngine')}
                </Title>
                {/* @AI_GENERATED */}
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_templateValidation')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_templateExecution')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_templateCrud')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_templateLibService')}</Text>
                  </div>
                </Space>
                {/* @AI_GENERATED: end */}

                <Divider style={{ margin: '16px 0' }} />

                <Title level={5} style={{ marginBottom: 12 }}>
                  <Tag color="success">{t('architecture.completed')}</Tag>
                  {t('architecture.stage1VisualEditor')}
                </Title>
                {/* @AI_GENERATED */}
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_reactFlowCanvas')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_customNodes')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_zustandState')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_toolbarProps')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_validationPanel')}</Text>
                  </div>
                </Space>
                {/* @AI_GENERATED: end */}

                <Divider style={{ margin: '16px 0' }} />

                <Title level={5} style={{ marginBottom: 12 }}>
                  <Tag color="success">{t('architecture.completed')}</Tag>
                  {t('architecture.stage1DataViz')}
                </Title>
                {/* @AI_GENERATED */}
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_echartsIntegration')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_chartComponents')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_chartConfigExport')}</Text>
                  </div>
                </Space>
                {/* @AI_GENERATED: end */}

                <Divider style={{ margin: '16px 0' }} />

                <Title level={5} style={{ marginBottom: 12 }}>
                  <Tag color="success">{t('architecture.completed')}</Tag>
                  {t('architecture.stage1AIAlgoLib')}
                </Title>
                {/* @AI_GENERATED */}
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_algoLibManagement')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_matrixCompute')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_functionExecution')}</Text>
                  </div>
                </Space>
                {/* @AI_GENERATED: end */}

                <Divider style={{ margin: '16px 0' }} />

                <Title level={5} style={{ marginBottom: 12 }}>
                  <Tag color="success">{t('architecture.completed')}</Tag>
                  {t('architecture.stage1UI')}
                </Title>
                {/* @AI_GENERATED */}
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_responsiveDesign')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_templateListPages')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_errorHandling')}</Text>
                  </div>
                </Space>
                {/* @AI_GENERATED: end */}
              </div>
            </div>

            <Divider />

            {/* Stage 2: 企业级增强 */}
            <div>
              <Title level={4} style={{ marginBottom: 16, color: '#52c41a' }}>
                🚀 {t('architecture.stage2Title')}
              </Title>
              
              <div style={{ marginLeft: 16 }}>
                <Title level={5} style={{ marginBottom: 12 }}>
                  <Tag color="success">{t('architecture.completed')}</Tag>
                  {t('architecture.stage2Month1')}
                </Title>
                {/* @AI_GENERATED */}
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_undoRedo')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_copyPaste')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_keyboardShortcuts')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_nodeAlignment')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_nodeSearch')}</Text>
                  </div>
                  <div className="module-item module-item-completed">
                    <Text>✓ {t('architecture.item_autoSave')}</Text>
                  </div>
                </Space>
                {/* @AI_GENERATED: end */}

                <Divider style={{ margin: '16px 0' }} />

                <Title level={5} style={{ marginBottom: 12 }}>
                  <Tag color="processing">{t('architecture.inProgress')}</Tag>
                  {t('architecture.stage2Month2')}
                </Title>
                {/* @AI_GENERATED */}
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div className="module-item module-item-processing">
                    <Text>⚙️ {t('architecture.item_versionControl')}</Text>
                  </div>
                  <div className="module-item module-item-processing">
                    <Text>⚙️ {t('architecture.item_realtimeCollab')}</Text>
                  </div>
                  <div className="module-item module-item-processing">
                    <Text>⚙️ {t('architecture.item_sharingPermissions')}</Text>
                  </div>
                  <div className="module-item module-item-processing">
                    <Text>⚙️ {t('architecture.item_3dVisualization')}</Text>
                  </div>
                  <div className="module-item module-item-processing">
                    <Text>⚙️ {t('architecture.item_realtimeDataFlow')}</Text>
                  </div>
                </Space>
                {/* @AI_GENERATED: end */}

                <Divider style={{ margin: '16px 0' }} />

                <Title level={5} style={{ marginBottom: 12 }}>
                  <Tag color="default">{t('architecture.planned')}</Tag>
                  {t('architecture.stage2Month3')}
                </Title>
                {/* @AI_GENERATED */}
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div className="module-item module-item-planned">
                    <Text type="secondary">📋 {t('architecture.item_aiAssistant')}</Text>
                  </div>
                  <div className="module-item module-item-planned">
                    <Text type="secondary">📋 {t('architecture.item_smartNodeRecommend')}</Text>
                  </div>
                  <div className="module-item module-item-planned">
                    <Text type="secondary">📋 {t('architecture.item_templateOptimization')}</Text>
                  </div>
                  <div className="module-item module-item-planned">
                    <Text type="secondary">📋 {t('architecture.item_parallelExecution')}</Text>
                  </div>
                  <div className="module-item module-item-planned">
                    <Text type="secondary">📋 {t('architecture.item_distributedCompute')}</Text>
                  </div>
                  <div className="module-item module-item-planned">
                    <Text type="secondary">📋 {t('architecture.item_postgresMigration')}</Text>
                  </div>
                  <div className="module-item module-item-planned">
                    <Text type="secondary">📋 {t('architecture.item_redisCache')}</Text>
                  </div>
                </Space>
                {/* @AI_GENERATED: end */}
              </div>
            </div>

            <Divider />

            {/* 统计信息 */}
            <div style={{ 
              padding: '20px', 
              background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
              borderRadius: '12px'
            }}>
              <Title level={5}>{t('architecture.devProgressStats')}</Title>
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <Text>{t('architecture.stage1Progress')}</Text>
                <Text>{t('architecture.stage2M1Progress')}</Text>
                <Text>{t('architecture.stage2M2Progress')}</Text>
                <Text>{t('architecture.stage2M3Progress')}</Text>
                <Divider style={{ margin: '12px 0' }} />
                <Text strong style={{ fontSize: '16px', color: '#1890ff' }}>
                  {t('architecture.overallProgress')}
                </Text>
              </Space>
            </div>
          </Space>
        </div>
      ),
    },
    {
      key: 'architecture',
      label: (
        <span style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: isMobile ? '4px' : '8px',
          fontWeight: 500
        }}>
          <ApartmentOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
          {!isMobile && <span>{t('architecture.overallArchitecture')}</span>}
        </span>
      ),
      children: (
        <div className="architecture-tab-content">
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Alert
              message={t('architecture.archVisualization')}
              description={t('architecture.archVisualizationDesc')}
              type="info"
              showIcon
              className="architecture-alert"
            />

            <ArchitectureDiagram />

            <Divider />

            <div>
              <Title level={5}>{t('architecture.archDescription')}</Title>
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <div className="architecture-layer-card architecture-layer-frontend">
                  <Tag color="blue" style={{ marginBottom: 8 }}>{t('architecture.frontendLayer')}</Tag>
                  <Paragraph style={{ marginBottom: 0 }}>
                    {t('architecture.frontendLayerDesc')}
                  </Paragraph>
                </div>
                <div className="architecture-layer-card architecture-layer-communication">
                  <Tag color="green" style={{ marginBottom: 8 }}>{t('architecture.communicationLayer')}</Tag>
                  <Paragraph style={{ marginBottom: 0 }}>
                    {t('architecture.communicationLayerDesc')}
                  </Paragraph>
                </div>
                <div className="architecture-layer-card architecture-layer-backend">
                  <Tag color="purple" style={{ marginBottom: 8 }}>{t('architecture.backendLayer')}</Tag>
                  <Paragraph style={{ marginBottom: 0 }}>
                    {t('architecture.backendLayerDesc')}
                  </Paragraph>
                </div>
                <div className="architecture-layer-card architecture-layer-data">
                  <Tag color="magenta" style={{ marginBottom: 8 }}>{t('architecture.dataLayer')}</Tag>
                  <Paragraph style={{ marginBottom: 0 }}>
                    {t('architecture.dataLayerDesc')}
                  </Paragraph>
                </div>
              </Space>
            </div>

            <Divider />

            <div className="data-flow-card">
              <Title level={5}>{t('architecture.dataFlow')}</Title>
              <Paragraph style={{ marginBottom: 0 }}>
                {t('architecture.dataFlowDesc')}
              </Paragraph>
            </div>
          </Space>
        </div>
      ),
    },
    {
      key: 'npm-packages',
      label: (
        <span style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: isMobile ? '4px' : '8px',
          fontWeight: 500
        }}>
          <NodeIndexOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
          {!isMobile && <span>{t('architecture.npmPackages')}</span>}
        </span>
      ),
      children: (
        <Card>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space wrap>
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={handleRefreshNpm}
                loading={npmLoading}
              >
                {t('architecture.refreshList')}
              </Button>
              <Button
                icon={<UploadOutlined />}
                onClick={handleUpdateNpm}
                disabled={selectedNpmRows.length === 0}
              >
                {t('architecture.updateSelected')} ({selectedNpmRows.length})
              </Button>
              <Popconfirm
                title={t('architecture.confirmDelete')}
                description={t('architecture.confirmDeleteDesc', { count: selectedNpmRows.length })}
                onConfirm={handleDeleteNpm}
                disabled={selectedNpmRows.length === 0}
              >
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  disabled={selectedNpmRows.length === 0}
                >
                  {t('architecture.deleteSelected')}
                </Button>
              </Popconfirm>
            </Space>

            <Table
              columns={npmColumns}
              dataSource={npmPackages}
              rowSelection={{
                selectedRowKeys: selectedNpmRows,
                onChange: (selectedKeys) => setSelectedNpmRows(selectedKeys as string[]),
              }}
              pagination={{
                pageSize: isMobile ? 5 : 10,
                showSizeChanger: !isMobile,
                showTotal: (total) => t('architecture.totalPackages', { total }),
              }}
              scroll={{ x: isMobile ? 400 : undefined }}
              size={isMobile ? 'small' : 'middle'}
            />
          </Space>
        </Card>
      ),
    },
    {
      key: 'pip-packages',
      label: (
        <span style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: isMobile ? '4px' : '8px',
          fontWeight: 500
        }}>
          <PythonOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
          {!isMobile && <span>{t('architecture.pipPackages')}</span>}
        </span>
      ),
      children: (
        <Card>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space wrap>
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={handleRefreshPip}
                loading={pipLoading}
              >
                {t('architecture.refreshList')}
              </Button>
              <Button
                icon={<UploadOutlined />}
                onClick={handleUpdatePip}
                disabled={selectedPipRows.length === 0}
              >
                {t('architecture.updateSelected')} ({selectedPipRows.length})
              </Button>
              <Popconfirm
                title={t('architecture.confirmDelete')}
                description={t('architecture.confirmDeleteDesc', { count: selectedPipRows.length })}
                onConfirm={handleDeletePip}
                disabled={selectedPipRows.length === 0}
              >
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  disabled={selectedPipRows.length === 0}
                >
                  {t('architecture.deleteSelected')}
                </Button>
              </Popconfirm>
            </Space>

            <Table
              columns={pipColumns}
              dataSource={pipPackages}
              rowSelection={{
                selectedRowKeys: selectedPipRows,
                onChange: (selectedKeys) => setSelectedPipRows(selectedKeys as string[]),
              }}
              pagination={{
                pageSize: isMobile ? 5 : 10,
                showSizeChanger: !isMobile,
                showTotal: (total) => t('architecture.totalPackages', { total }),
              }}
              scroll={{ x: isMobile ? 400 : undefined }}
              size={isMobile ? 'small' : 'middle'}
            />
          </Space>
        </Card>
      ),
    },
  ];

  return (
    <ConfigProvider>
      <div style={{ 
        padding: '16px',
        height: '100%',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column'
      }}>
        <Tabs
          key={tabsKey}
          defaultActiveKey="tech-stack"
          items={tabItems}
          size={isMobile ? 'small' : 'large'}
          className="architecture-tabs"
          style={{ 
            flex: 1, 
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            opacity: tabsVisible ? 1 : 0,
            transition: 'opacity 0.1s ease'
          }}
          tabBarStyle={{ 
            marginBottom: 16,
            flex: '0 0 auto'
          }}
          tabBarGutter={isMobile ? 16 : 32}
        />
      </div>
    </ConfigProvider>
  );
};

export default ArchitecturePage;
