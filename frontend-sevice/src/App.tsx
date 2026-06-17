import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
// @AI_GENERATED
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import LoginPage from './pages/LoginPage';
import LoginPageNew from './pages/LoginPageNew';
import RegisterPage from './pages/RegisterPage';
import HomePage from './pages/HomePage';
import FunctionLibraryPage from './pages/FunctionLibraryPage';
import ProfilePage from './pages/ProfilePage';
import SystemStatusPage from './pages/SystemStatusPage';
import ArchitecturePage from './pages/ArchitecturePage';
import SettingsPage from './pages/SettingsPage';
import WorkflowEditorPage from './pages/WorkflowEditorPage';
import WorkflowBaselineComparePage from './pages/WorkflowBaselineComparePage';
import WorkflowListPage from './pages/WorkflowListPage';
import TemplateGalleryPage from './pages/TemplateGalleryPage';
import WorkflowReferencePage from './pages/WorkflowReferencePage';
import WorkflowV2Page from './pages/WorkflowV2Page';
import DifyReplicaPage from './pages/DifyReplicaPage';
import AlgorithmKnowledgeGraphPage from './pages/AlgorithmKnowledgeGraphPage';
import AlgorithmDbTestPage from './pages/AlgorithmDbTestPage';
// @AI_GENERATED: Kiro v1.0
import WorkflowAgentPage from './pages/WorkflowAgentPage';
import WorkflowAgentHistoryPage from './pages/WorkflowAgentHistoryPage';
import DataSourcePage from './pages/DataSourcePage';
import DatasetPage from './pages/DatasetPage';
import AlgorithmSolutionLibraryPage from './pages/AlgorithmSolutionLibraryPage';
import TemplateAccuracyPage from './pages/TemplateAccuracyPage';
import TemplateApplicationPage from './pages/TemplateApplicationPage';
import DeploymentTaskPage from './pages/DeploymentTaskPage';
import ServiceManagementPage from './pages/ServiceManagementPage';
import ServiceMonitorPage from './pages/ServiceMonitorPage';
import DriftMonitorPage from './pages/DriftMonitorPage';
import ABTestPage from './pages/ABTestPage';
import AutoRetrainPage from './pages/AutoRetrainPage';
import AlgorithmOpsPage from './pages/AlgorithmOpsPage';
// @AI_GENERATED: Kiro v1.0
import AlgorithmAgentPage from './pages/AlgorithmAgentPage';
import AgentSkillStatusPage from './pages/AgentSkillStatusPage';
import LLMConfigPage from './pages/LLMConfigPage';
// @AI_GENERATED: end
import OfficialTemplateLibraryPage from './pages/OfficialTemplateLibraryPage';
import SkillDetailPage from './pages/SkillDetailPage';
import SkillTestTaskPage from './pages/SkillTestTaskPage';
import SkillTrainingMonitorPage from './pages/SkillTrainingMonitorPage';
import SkillTestResultPage from './pages/SkillTestResultPage';
// @AI_GENERATED: Kiro v1.0
import UnifiedBacktestPage from './pages/UnifiedBacktestPage';
import UnifiedBacktestMonitorPage from './pages/UnifiedBacktestMonitorPage';
import UnifiedBacktestResultPage from './pages/UnifiedBacktestResultPage';
// @AI_GENERATED: end
// @AI_GENERATED: end
// @AI_GENERATED
import LoadForecastTrainingPage from './pages/LoadForecastTrainingPage';
// @AI_GENERATED: end
// @AI_GENERATED: Kiro v1.0
import IndustryOverviewPage from './pages/IndustryOverviewPage';
import IndustryScenarioPage from './pages/IndustryScenarioPage';
// @AI_GENERATED: end
import IterativeLabelingReviewPage from './pages/IterativeLabelingReviewPage';
import IterativeLabelingListPage from './pages/IterativeLabelingListPage';
import MainLayout from './components/MainLayout';
import ProtectedRoute from './components/ProtectedRoute';
import './App.css';

/**
 * 主应用组件
 * 
 * 路由结构：
 * - / : 重定向到登录页
 * - /login : 登录页面
 * - /register : 注册页面
 * - /home : 首页（需要登录）
 * - /functions : AI算法库页面（需要登录）
 * - /profile : 个人信息页面（需要登录）
 * - /system-status : 系统状态页面（需要登录）
 * - /workflow/editor : 模板编辑器页面（需要登录）
 * - /workflow/editor/:id : 编辑指定模板（需要登录）
 * - /workflow/list : 模板列表页面（需要登录）
 * - /templates : 模板库页面（需要登录）
 */
function App() {
  // @AI_GENERATED
  const { i18n } = useTranslation();
  const antdLocale = i18n.language === 'en' ? enUS : zhCN;
  // @AI_GENERATED: end

  return (
    <ConfigProvider locale={antdLocale}>
    <Router>
      <Routes>
        {/* 根路径重定向到登录页 */}
        <Route path="/" element={<Navigate to="/login" replace />} />
        
        {/* 登录页面 - 原始简洁版本 */}
        <Route path="/login" element={<LoginPage />} />
        
        {/* 新版登录页面（备用测试） */}
        <Route path="/login-new" element={<LoginPageNew />} />
        
        {/* 注册页面 */}
        <Route path="/register" element={<RegisterPage />} />
        
        {/* 受保护的路由（需要登录） */}
        <Route
          element={
            <ProtectedRoute>
              <MainLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/home" element={<HomePage />} />
          {/* @AI_GENERATED: Kiro v1.0 */}
          <Route path="/industry" element={<IndustryOverviewPage />} />
          <Route path="/industry/:scenarioId" element={<IndustryScenarioPage />} />
          {/* @AI_GENERATED: end */}
          {/* @AI_GENERATED: Kiro v1.0 */}
          <Route path="/basic-modules" element={<Navigate to="/functions" replace />} />
          <Route path="/basic-modules/:categoryId" element={<Navigate to="/functions" replace />} />
          {/* @AI_GENERATED: end */}
          <Route path="/functions" element={<FunctionLibraryPage />} />
          <Route path="/knowledge-graph" element={<AlgorithmKnowledgeGraphPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/system-status" element={<SystemStatusPage />} />
          <Route path="/architecture" element={<ArchitecturePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          
          {/* 算法模板相关路由 */}
          {/* @AI_GENERATED: Kiro v1.0 */}
          <Route path="/template-library" element={<OfficialTemplateLibraryPage />} />
          <Route path="/skill-library" element={<Navigate to="/template-library" replace />} />
          <Route path="/skill-library/:skillId" element={<SkillDetailPage />} />
          <Route path="/skill-test/tasks" element={<SkillTestTaskPage />} />
          <Route path="/skill-test/training" element={<SkillTrainingMonitorPage />} />
          <Route path="/skill-test/results" element={<SkillTestResultPage />} />
          {/* @AI_GENERATED: Kiro v1.0 */}
          {/* 统一回测页面 */}
          <Route path="/backtest/unified" element={<UnifiedBacktestPage />} />
          <Route path="/backtest/unified/monitor" element={<UnifiedBacktestMonitorPage />} />
          <Route path="/backtest/unified/results" element={<UnifiedBacktestResultPage />} />
          {/* @AI_GENERATED: end */}
          {/* @AI_GENERATED: end */}
          <Route path="/workflow/editor" element={<WorkflowEditorPage />} />
          <Route path="/workflow/editor/:id" element={<WorkflowEditorPage />} />
          <Route path="/workflow/baseline-compare" element={<WorkflowBaselineComparePage />} />
          <Route path="/workflow/list" element={<WorkflowListPage />} />
          <Route path="/templates" element={<TemplateGalleryPage />} />
          
          {/* 模板测试页面 */}
          <Route path="/workflow-reference" element={<WorkflowReferencePage />} />
          <Route path="/workflow-v2" element={<WorkflowV2Page />} />
          <Route path="/dify-replica" element={<DifyReplicaPage />} />
          {/* @AI_GENERATED: Kiro v1.0 */}
          <Route path="/workflow-agent" element={<WorkflowAgentPage />} />
          <Route path="/workflow-agent/history" element={<WorkflowAgentHistoryPage />} />
          <Route path="/data-sources" element={<DataSourcePage />} />
          <Route path="/datasets" element={<DatasetPage />} />
          <Route path="/iterative-labeling" element={<IterativeLabelingListPage />} />
          <Route path="/iterative-labeling/review" element={<IterativeLabelingReviewPage />} />
          <Route path="/algorithm-solutions" element={<AlgorithmSolutionLibraryPage />} />
          <Route path="/algorithm-solutions/accuracy" element={<TemplateAccuracyPage />} />
          <Route path="/algorithm-solutions/applications" element={<TemplateApplicationPage />} />
          {/* @AI_GENERATED: Kiro v1.0 */}
          {/* 旧回测路由重定向到统一页面 */}
          <Route path="/backtest" element={<Navigate to="/backtest/unified" replace />} />
          <Route path="/backtest/monitor" element={<Navigate to="/backtest/unified/monitor" replace />} />
          <Route path="/backtest/results" element={<Navigate to="/backtest/unified/results" replace />} />
          {/* @AI_GENERATED: end */}
          <Route path="/deployment" element={<DeploymentTaskPage />} />
          <Route path="/deployment/services" element={<ServiceManagementPage />} />
          <Route path="/deployment/monitor" element={<ServiceMonitorPage />} />
          <Route path="/ops" element={<AlgorithmOpsPage />} />
          <Route path="/ops/drift" element={<DriftMonitorPage />} />
          <Route path="/ops/ab-test" element={<ABTestPage />} />
          <Route path="/ops/retrain" element={<AutoRetrainPage />} />
          {/* @AI_GENERATED: Kiro v1.0 */}
          <Route path="/algorithm-agent" element={<AlgorithmAgentPage />} />
          <Route path="/agent-skill-status" element={<AgentSkillStatusPage />} />
          <Route path="/llm-config" element={<LLMConfigPage />} />
          {/* @AI_GENERATED: end */}
          <Route path="/algorithm-db-test" element={<AlgorithmDbTestPage />} />
          {/* @AI_GENERATED */}
          <Route path="/load-forecast/training" element={<LoadForecastTrainingPage />} />
          {/* @AI_GENERATED: end */}
        </Route>
      </Routes>
    </Router>
    </ConfigProvider>
  );
}

export default App;
