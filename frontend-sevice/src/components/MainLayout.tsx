import { startTransition, useEffect, useMemo, useRef, useState } from 'react';
import { Layout, Menu, Grid, Drawer, Button, Typography, Dropdown, Space, Avatar, FloatButton } from 'antd';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { GlobalOutlined } from '@ant-design/icons';
// @AI_GENERATED: end
// @AI_GENERATED: Kiro v1.0
import {
  HomeOutlined,
  FunctionOutlined,
  LogoutOutlined,
  MenuOutlined,
  UserOutlined,
  DashboardOutlined,
  ApartmentOutlined,
  AppstoreOutlined,
  FileTextOutlined,
  SettingOutlined,
  BankOutlined,
  ToolOutlined,
  RocketOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  ExperimentOutlined,
  CodeOutlined,
  LineChartOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  ApiOutlined,
} from '@ant-design/icons';
// @AI_GENERATED: end
import type { MenuProps } from 'antd';
import { useWorkflowRunNavStore } from '../stores/workflowRunNavStore';
import { usePipelineExecutionStore } from '../stores/pipelineExecutionStore';

const { Sider, Content, Header } = Layout;
const { Text } = Typography;
const { useBreakpoint } = Grid;
const SIDEBAR_WIDTH_STORAGE_KEY = 'mainLayout.sidebarWidth';
const SIDEBAR_DEFAULT_WIDTH = 200;
const SIDEBAR_MIN_WIDTH = 180;
const SIDEBAR_MAX_WIDTH = 420;

/**
 * 主布局组件
 * 
 * 包含左侧导航栏和内容区域
 * 支持响应式布局（移动端使用抽屉）
 */
const MainLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const screens = useBreakpoint();
  const [mobileMenuVisible, setMobileMenuVisible] = useState(false);
  const [isLangSwitching, setIsLangSwitching] = useState(false);
  const [siderWidth, setSiderWidth] = useState<number>(() => {
    const saved = Number(localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY));
    if (Number.isFinite(saved)) {
      return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, saved));
    }
    return SIDEBAR_DEFAULT_WIDTH;
  });
  const [isResizingSider, setIsResizingSider] = useState(false);
  const [isSiderResizeHover, setIsSiderResizeHover] = useState(false);
  const [backtestFabTick, setBacktestFabTick] = useState(0);
  const resizeStartXRef = useRef(0);
  const resizeStartWidthRef = useRef(SIDEBAR_DEFAULT_WIDTH);
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end
  
  const isMobile = !screens.md; // < 768px
  const username = localStorage.getItem('username') || t('common.user');
  const runNav = useWorkflowRunNavStore();
  const nodeStatuses = usePipelineExecutionStore((s) => s.nodeStatuses);
  const executionStatus = usePipelineExecutionStore((s) => s.executionStatus);
  const pipelinePlannedNodeCount = usePipelineExecutionStore((s) => s.pipelinePlannedNodeCount);
  const here = `${location.pathname}${location.search}`;
  const showRunningReturn =
    Boolean(runNav.returnHref) && runNav.phase !== 'idle' && here !== runNav.returnHref;

  useEffect(() => {
    if (!showRunningReturn || !runNav.backtestInFlight) return;
    const id = window.setInterval(() => setBacktestFabTick((x) => x + 1), 1000);
    return () => clearInterval(id);
  }, [showRunningReturn, runNav.backtestInFlight]);

  const runningFabDescription = useMemo(() => {
    if (!showRunningReturn) return undefined;
    if (runNav.phase === 'backtest' && runNav.backtestInFlight) {
      const at = runNav.backtestStartedAt;
      const sec = at ? Math.max(0, Math.floor((Date.now() - at) / 1000)) : 0;
      void backtestFabTick;
      return `${t('workflow.fabBacktestProgress')} · ${sec}s`;
    }
    if (runNav.phase === 'pipeline') {
      // 后端 nodeResults 只含已结束节点；分母用开始执行时记录的画布节点数
      const planned = pipelinePlannedNodeCount;
      const stepsDone = Object.keys(nodeStatuses).length;
      if (planned && planned > 0) {
        const pct = Math.round(Math.min(100, (stepsDone / planned) * 100));
        return `${pct}%`;
      }
      if (executionStatus === 'running' || executionStatus === 'pending') {
        return '0%';
      }
    }
    return undefined;
  }, [
    showRunningReturn,
    runNav.phase,
    runNav.backtestInFlight,
    runNav.backtestStartedAt,
    backtestFabTick,
    nodeStatuses,
    executionStatus,
    pipelinePlannedNodeCount,
    t,
  ]);

  const navigateReturnToRunning = () => {
    if (!runNav.returnHref) return;
    useWorkflowRunNavStore.getState().requestExpandEditorBottomPanel();
    navigate(runNav.returnHref);
  };

  const handleLogout = () => {
    localStorage.removeItem('isLoggedIn');
    localStorage.removeItem('username');
    navigate('/login');
  };

  // @AI_GENERATED
  const persistLanguageSettings = (lang: 'zh' | 'en') => {
    localStorage.setItem('lang', lang);
    const nextFullLang = lang === 'en' ? 'en-US' : 'zh-CN';
    try {
      const raw = localStorage.getItem('appSettings');
      const appSettings = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
      appSettings.language = nextFullLang;
      localStorage.setItem('appSettings', JSON.stringify(appSettings));
    } catch {
      localStorage.setItem('appSettings', JSON.stringify({ language: nextFullLang }));
    }
  };

  const toggleLanguage = () => {
    if (isLangSwitching) return;
    const newLang = i18n.language === 'zh' ? 'en' : 'zh';
    setIsLangSwitching(true);
    startTransition(() => {
      Promise.resolve(i18n.changeLanguage(newLang))
        .catch(() => {})
        .finally(() => setIsLangSwitching(false));
    });
  };

  useEffect(() => {
    const normalized = (i18n.language || '').toLowerCase().startsWith('en') ? 'en' : 'zh';
    persistLanguageSettings(normalized as 'zh' | 'en');
  }, [i18n.language]);
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  const menuItems: MenuProps['items'] = [
    {
      key: '/home',
      icon: <HomeOutlined />,
      label: t('nav.home'),
    },
    // ── Agentic Service ──
    // @AI_GENERATED: Kiro v1.0
    {
      key: 'grp-agentic',
      type: 'group',
      label: t('nav.agenticService'),
      children: [
        {
          key: '/algorithm-agent',
          icon: <RobotOutlined />,
          label: t('nav.algorithmAgent'),
        },
        {
          key: '/agent-skill-status',
          icon: <ThunderboltOutlined />,
          label: t('nav.agentSkillStatus'),
        },
        {
          key: '/llm-config',
          icon: <ApiOutlined />,
          label: t('nav.llmConfig'),
        },
      ],
    },
    // @AI_GENERATED: end
    // ── 算法服务 ──
    {
      key: 'grp-service',
      type: 'group',
      label: t('nav.algorithmService'),
      children: [
        {
          key: '/industry',
          icon: <BankOutlined />,
          label: t('nav.industryScenario'),
        },
        {
          key: 'algorithm-solutions',
          icon: <ExperimentOutlined />,
          label: t('nav.algorithmSolutions'),
          children: [
            {
              key: '/algorithm-solutions',
              icon: <AppstoreOutlined />,
              label: t('nav.solutionLibrary'),
            },
            {
              key: '/algorithm-solutions/accuracy',
              icon: <ExperimentOutlined />,
              label: t('nav.accuracyManagement'),
            },
            {
              key: '/algorithm-solutions/applications',
              icon: <ApartmentOutlined />,
              label: t('nav.applicationInstances'),
            },
          ],
        },
        {
          key: 'data-mgmt',
          icon: <DatabaseOutlined />,
          label: t('nav.industryDataManagement'),
          children: [
            {
              key: '/data-sources',
              icon: <CloudServerOutlined />,
              label: t('nav.dataSourceManagement'),
            },
            {
              key: '/datasets',
              icon: <DatabaseOutlined />,
              label: t('nav.datasetManagement'),
            },
            {
              key: '/iterative-labeling',
              icon: <DatabaseOutlined />,
              label: '人工标注审核',
            },
          ],
        },
        {
          key: 'deployment',
          icon: <RocketOutlined />,
          label: t('nav.algorithmDeployment'),
          children: [
            {
              key: '/deployment',
              icon: <AppstoreOutlined />,
              label: t('nav.deploymentTasks'),
            },
            {
              key: '/deployment/services',
              icon: <CloudServerOutlined />,
              label: t('nav.serviceManagement'),
            },
            {
              key: '/deployment/monitor',
              icon: <DashboardOutlined />,
              label: t('nav.serviceMonitor'),
            },
          ],
        },
        // @AI_GENERATED: Kiro v1.0
        {
          key: '/ops',
          icon: <LineChartOutlined />,
          label: t('nav.algorithmOps'),
        },
        // @AI_GENERATED: end
      ],
    },
    // ── 算法模板 ──
    {
      key: 'grp-template',
      type: 'group',
      label: t('nav.algorithmTemplate'),
      children: [
        {
          key: '/template-library',
          icon: <AppstoreOutlined />,
          label: t('nav.templateLibrary'),
        },
        {
          key: '/functions',
          icon: <FunctionOutlined />,
          label: t('nav.basicAlgorithmLibrary'),
        },
        {
          key: 'workflow-edit',
          icon: <ApartmentOutlined />,
          label: t('nav.workflowOrchestration'),
          children: [
            {
              key: '/workflow/editor',
              icon: <AppstoreOutlined />,
              label: t('nav.editor'),
            },
            {
              key: '/workflow/list',
              icon: <FileTextOutlined />,
              label: t('nav.myWorkflows'),
            },
            {
              key: '/workflow/baseline-compare',
              icon: <ExperimentOutlined />,
              label: t('nav.baselineCompare'),
            },
            {
              key: '/workflow-agent',
              icon: <RobotOutlined />,
              label: t('nav.intelligentOrchestration'),
            },
            {
              key: '/workflow-agent/history',
              icon: <FileTextOutlined />,
              label: t('nav.orchestrationHistory'),
            },
          ],
        },
        // @AI_GENERATED: Kiro v1.0
        {
          key: 'backtest',
          icon: <ExperimentOutlined />,
          label: t('nav.templateBacktest'),
          children: [
            {
              key: '/backtest/unified',
              icon: <ExperimentOutlined />,
              label: t('nav.backtestTasks'),
            },
            {
              key: '/backtest/unified/monitor',
              icon: <DashboardOutlined />,
              label: t('nav.backtestMonitor'),
            },
            {
              key: '/backtest/unified/results',
              icon: <LineChartOutlined />,
              label: t('nav.backtestResults'),
            },
          ],
        },
        // @AI_GENERATED: end
      ],
    },
    // ── 系统 ──
    {
      key: 'grp-system',
      type: 'group',
      label: t('nav.system'),
      children: [
        {
          key: 'system-admin',
          icon: <ToolOutlined />,
          label: t('nav.systemManagement'),
          children: [
            {
              key: '/system-status',
              icon: <DashboardOutlined />,
              label: t('nav.systemStatus'),
            },
            {
              key: '/settings',
              icon: <SettingOutlined />,
              label: t('nav.systemConfig'),
            },
            {
              key: '/architecture',
              icon: <CodeOutlined />,
              label: t('nav.devArchitecture'),
            },
          ],
        },
        {
          key: '/profile',
          icon: <UserOutlined />,
          label: t('nav.profile'),
        },
      ],
    },
  ];
  // @AI_GENERATED: end

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: t('app.logout'),
      danger: true,
      onClick: handleLogout,
    },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    if (key === location.pathname) return;
    startTransition(() => {
      navigate(key);
    });
    if (isMobile) {
      setMobileMenuVisible(false);
    }
  };

  const handleSiderResizeStart = (e: React.MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    resizeStartXRef.current = e.clientX;
    resizeStartWidthRef.current = siderWidth;
    setIsResizingSider(true);
  };

  useEffect(() => {
    if (!isResizingSider) return;

    const previousUserSelect = document.body.style.userSelect;
    const previousCursor = document.body.style.cursor;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    const handleMouseMove = (event: MouseEvent) => {
      const delta = event.clientX - resizeStartXRef.current;
      const nextWidth = Math.min(
        SIDEBAR_MAX_WIDTH,
        Math.max(SIDEBAR_MIN_WIDTH, resizeStartWidthRef.current + delta),
      );
      setSiderWidth(nextWidth);
    };

    const handleMouseUp = () => {
      setIsResizingSider(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = previousUserSelect;
      document.body.style.cursor = previousCursor;
    };
  }, [isResizingSider]);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(siderWidth));
  }, [siderWidth]);

  // 桌面端布局
  if (!isMobile) {
    return (
      <>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider
          width={siderWidth}
          theme="light"
          style={{
            overflow: 'auto',
            height: '100vh',
            position: 'fixed',
            left: 0,
            top: 0,
            bottom: 0,
            background: '#fff',
            borderRight: '1px solid #e6f4ff',
          }}
        >
          <div
            style={{
              height: '64px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#262626',
              fontSize: '16px',
              fontWeight: 'bold',
              borderBottom: '1px solid #f0f0f0',
              background: '#fafafa',
            }}
          >
            {t('app.title')}
          </div>
          <Menu
            key={i18n.language}
            theme="light"
            mode="inline"
            selectedKeys={[location.pathname]}
            onClick={handleMenuClick}
            items={menuItems}
            style={{ borderRight: 0 }}
          />
          <div
            onMouseDown={handleSiderResizeStart}
            onMouseEnter={() => setIsSiderResizeHover(true)}
            onMouseLeave={() => setIsSiderResizeHover(false)}
            style={{
              position: 'absolute',
              top: 0,
              right: 0,
              width: 4,
              height: '100%',
              cursor: 'col-resize',
              background: isSiderResizeHover ? '#e8e8e8' : 'transparent',
              transition: 'background 0.2s',
              zIndex: 10,
            }}
          />
        </Sider>
        <Layout style={{ marginLeft: siderWidth, display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
          <Header
            style={{
              background: '#fff',
              padding: '0 24px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid #f0f0f0',
              position: 'sticky',
              top: 0,
              zIndex: 999,
              flex: '0 0 64px',
            }}
          >
            {/* 左侧：页面标题 */}
            {/* @AI_GENERATED */}
            <div style={{ flex: 1, minWidth: 0, marginRight: 16 }}>
              <Text strong ellipsis={{ tooltip: true }} style={{ fontSize: '18px', display: 'block' }}>
                {location.pathname === '/home' && t('header.home')}
                {location.pathname === '/industry' && t('header.industryAISolutions')}
                {location.pathname.startsWith('/industry/') && t('header.scenarioDetails')}
                {location.pathname === '/functions' && t('header.basicAlgorithmLibrary')}
                {location.pathname === '/knowledge-graph' && t('header.aiKnowledgeGraph')}
                {location.pathname === '/workflow/editor' && t('header.workflowEditor')}
                {location.pathname.startsWith('/workflow/editor/') && t('header.workflowEditor')}
                {location.pathname === '/workflow/list' && t('header.myWorkflows')}
                {location.pathname === '/workflow/baseline-compare' && t('header.baselineCompare')}
                {location.pathname === '/workflow-agent' && t('header.intelligentOrchestration')}
                {location.pathname === '/workflow-agent/history' && t('header.orchestrationHistory')}
                {location.pathname === '/data-sources' && t('header.dataSourceManagement')}
                {location.pathname === '/datasets' && t('header.datasetManagement')}
                {location.pathname === '/algorithm-solutions' && t('header.algorithmSolutions')}
                {location.pathname === '/algorithm-solutions/accuracy' && t('header.accuracyManagement')}
                {location.pathname === '/algorithm-solutions/applications' && t('header.applicationInstances')}
                {location.pathname === '/backtest' && t('header.workflowBacktest')}
                {location.pathname === '/backtest/monitor' && t('header.backtestMonitor')}
                {location.pathname === '/backtest/results' && t('header.backtestResults')}
                {location.pathname === '/backtest/unified' && t('header.backtestTasks')}
                {location.pathname === '/backtest/unified/monitor' && t('header.backtestMonitor')}
                {location.pathname === '/backtest/unified/results' && t('header.backtestResults')}
                {location.pathname === '/deployment' && t('header.deploymentTasks')}
                {location.pathname === '/deployment/services' && t('header.serviceManagement')}
                {location.pathname === '/deployment/monitor' && t('header.serviceMonitor')}
                {location.pathname === '/ops/drift' && t('header.driftMonitor')}
                {location.pathname === '/ops/ab-test' && t('header.abTest')}
                {location.pathname === '/ops/retrain' && t('header.autoRetrain')}
                {location.pathname === '/algorithm-agent' && t('header.algorithmAgent')}
                {location.pathname === '/llm-config' && t('header.llmConfig')}
                {location.pathname === '/templates' && t('header.templateLibrary')}
                {location.pathname === '/template-library' && t('header.templateLibrary')}
                {location.pathname === '/skill-library' && t('header.skills')}
                {location.pathname.startsWith('/skill-library/') && t('header.skillDetails')}
                {location.pathname === '/skill-test/tasks' && t('header.skillTest')}
                {location.pathname === '/skill-test/training' && t('header.skillTraining')}
                {location.pathname === '/skill-test/results' && t('header.skillResults')}
                {location.pathname === '/system-status' && t('header.systemStatus')}
                {location.pathname === '/architecture' && t('header.devArchitecture')}
                {location.pathname === '/settings' && t('header.systemConfig')}
                {location.pathname === '/algorithm-db-test' && t('header.functionalTest')}
                {location.pathname === '/load-forecast/training' && t('header.loadForecastTraining')}
                {location.pathname === '/profile' && t('header.profile')}
              </Text>
            </div>
            {/* @AI_GENERATED: end */}
            
            {/* 右侧：用户信息 */}
            {/* @AI_GENERATED */}
            <Space style={{ flexShrink: 0 }}>
              <Button
                type="text"
                icon={<GlobalOutlined />}
                onClick={toggleLanguage}
                loading={isLangSwitching}
                disabled={isLangSwitching}
                style={{ fontSize: 14 }}
              >
                {i18n.language === 'zh' ? t('language.switchToEnglish') : t('language.switchToChinese')}
              </Button>
              <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
                <Space style={{ cursor: 'pointer' }}>
                  <Avatar icon={<UserOutlined />} size="small" />
                  <Text>{username}</Text>
                </Space>
              </Dropdown>
            </Space>
            {/* @AI_GENERATED: end */}
          </Header>
          <Content style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <Outlet />
          </Content>
        </Layout>
      </Layout>
      {showRunningReturn && (
        <FloatButton
          type="primary"
          icon={<ThunderboltOutlined />}
          description={runningFabDescription}
          tooltip={t('workflow.returnToRunning', {
            name: runNav.workflowLabel || t('nav.editor'),
          })}
          style={{ right: 24, bottom: 88, zIndex: 1100 }}
          onClick={navigateReturnToRunning}
        />
      )}
      </>
    );
  }

  // 移动端布局
  return (
    <>
    <Layout style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Layout style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
        <div
          style={{
            height: '56px',
            background: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 16px',
            position: 'sticky',
            top: 0,
            zIndex: 1000,
            flex: '0 0 56px',
            borderBottom: '1px solid #f0f0f0',
            gap: 8,
          }}
        >
          <Text
            ellipsis
            style={{ color: '#262626', fontSize: '16px', fontWeight: 'bold', flex: 1, minWidth: 0 }}
          >
            {t('app.title')}
          </Text>
          <Space style={{ flexShrink: 0 }}>
            <Button
              type="text"
              icon={<GlobalOutlined />}
              onClick={toggleLanguage}
              loading={isLangSwitching}
              disabled={isLangSwitching}
              style={{ fontSize: 14 }}
            >
              {i18n.language === 'zh' ? t('language.switchToEnglish') : t('language.switchToChinese')}
            </Button>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar icon={<UserOutlined />} size="small" style={{ backgroundColor: '#1890ff' }} />
                <Text ellipsis style={{ color: '#262626', maxWidth: 96 }}>
                  {username}
                </Text>
              </Space>
            </Dropdown>
            <Button
              type="text"
              icon={<MenuOutlined style={{ color: '#262626', fontSize: '20px' }} />}
              onClick={() => setMobileMenuVisible(true)}
            />
          </Space>
        </div>
        <Content style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <Outlet />
        </Content>
      </Layout>

      {/* 移动端菜单抽屉 */}
      <Drawer
        title={t('mobile.menu')}
        placement="left"
        onClose={() => setMobileMenuVisible(false)}
        open={mobileMenuVisible}
        width="70%"
      >
        <Menu
          key={i18n.language}
          mode="vertical"
          selectedKeys={[location.pathname]}
          onClick={handleMenuClick}
          items={menuItems}
        />
      </Drawer>
    </Layout>
    {showRunningReturn && (
      <FloatButton
        type="primary"
        icon={<ThunderboltOutlined />}
        description={runningFabDescription}
        tooltip={t('workflow.returnToRunning', {
          name: runNav.workflowLabel || t('nav.editor'),
        })}
        style={{ right: 16, bottom: 88, zIndex: 1100 }}
        onClick={navigateReturnToRunning}
      />
    )}
    </>
  );
};

export default MainLayout;
