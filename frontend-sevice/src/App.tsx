import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
// @AI_GENERATED: 兼容重定向保留 query（旅程上下文合同 §33.2）
import QueryPreservingNavigate from './components/QueryPreservingNavigate';
// @AI_GENERATED: end
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
import CumulativeTrainingLedgerPage from './pages/CumulativeTrainingLedgerPage';
// @AI_GENERATED: 项目工作台（领域无关壳 + 光伏适配器）路由模块
import { ProjectScopeProvider } from './contexts/ProjectScopeContext';
import ProjectListPage from './pv-fault/pages/ProjectListPage';
// @AI_GENERATED: 平台数据集目录（显式数据集窗口）；路径用 /datasets/catalog，不能用 /projects/catalog
// ——后者会被动态段 /projects/:projectId 吃掉。
import CatalogPage from './pv-fault/pages/CatalogPage';
// @AI_GENERATED: end
import ProjectWorkbenchLayout from './pv-fault/pages/ProjectWorkbenchLayout';
import ProjectOverviewPage from './pv-fault/pages/ProjectOverviewPage';
import ProjectDataStagePage from './pv-fault/pages/stages/ProjectDataStagePage';
import ProjectWorkflowsStagePage from './pv-fault/pages/stages/ProjectWorkflowsStagePage';
import ProjectRunsStagePage from './pv-fault/pages/stages/ProjectRunsStagePage';
import ProjectModelsStagePage from './pv-fault/pages/stages/ProjectModelsStagePage';
import ProjectOperationsStagePage from './pv-fault/pages/stages/ProjectOperationsStagePage';
import ProjectReviewsStagePage from './pv-fault/pages/stages/ProjectReviewsStagePage';
import ProjectCumulativeStagePage from './pv-fault/pages/stages/ProjectCumulativeStagePage';
import ProjectValidationsStagePage from './pv-fault/pages/stages/ProjectValidationsStagePage';
// @AI_GENERATED: end
import AlgorithmSolutionLibraryPage from './pages/AlgorithmSolutionLibraryPage';
import TemplateAccuracyPage from './pages/TemplateAccuracyPage';
import TemplateApplicationPage from './pages/TemplateApplicationPage';
// @AI_GENERATED: algorithm-deployment-refactor 14 — 三个旧部署页 (DeploymentTaskPage/ServiceManagementPage/ServiceMonitorPage) 已被 AlgorithmDeploymentPage 取代，路由改为重定向；不再导入旧页面组件。
// @AI_GENERATED: end
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
import AlgorithmManagementPage from './pages/AlgorithmManagementPage';
// @AI_GENERATED: algorithm-deployment-refactor 10.2 — 新算法部署页面（模型管理 / 定时调度）
import AlgorithmDeploymentPage from './pages/AlgorithmDeploymentPage';
// @AI_GENERATED: end
// @AI_GENERATED
import AccuracyOperationsPage from './pages/AccuracyOperationsPage';
import PvFaultWorkbenchDemoPage from './pages/pv-fault-demo/PvFaultWorkbenchDemoPage';
// @AI_GENERATED: end
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

          {/* 第七代算法开发路由 */}
          <Route path="/algorithm-dev" element={<QueryPreservingNavigate to="/algorithm-dev/management" />} />
          <Route path="/algorithm-dev/management" element={<AlgorithmManagementPage />} />
          <Route path="/algorithm-dev/workflows" element={<WorkflowListPage />} />
          <Route path="/algorithm-dev/workflow-editor" element={<WorkflowEditorPage />} />
          <Route path="/algorithm-dev/workflow-editor/:id" element={<WorkflowEditorPage />} />
          <Route path="/algorithm-dev/operators" element={<FunctionLibraryPage />} />
          <Route path="/algorithm-dev/autoresearch" element={<WorkflowBaselineComparePage />} />
          {/* @AI_GENERATED: algorithm-operations-retirement — 旧地址兼容重定向到唯一的精度运营页面；保留 query（如 ?workflow_id=） */}
          <Route path="/algorithm-dev/ops" element={<QueryPreservingNavigate to="/accuracy-operations" />} />
          {/* @AI_GENERATED: end */}
          <Route path="/algorithm-dev/deployment" element={<AlgorithmDeploymentPage />} />
          {/* @AI_GENERATED: 项目工作台（领域无关壳 + /projects/* 路由模块，光伏为首个适配器） */}
          <Route path="/projects" element={<ProjectListPage />} />
          <Route
            path="/projects/:projectId"
            element={
              <ProjectScopeProvider>
                <ProjectWorkbenchLayout />
              </ProjectScopeProvider>
            }
          >
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<ProjectOverviewPage />} />
            <Route path="data" element={<ProjectDataStagePage />} />
            <Route path="workflows" element={<ProjectWorkflowsStagePage />} />
            <Route path="runs" element={<ProjectRunsStagePage />} />
            <Route path="models" element={<ProjectModelsStagePage />} />
            <Route path="operations" element={<ProjectOperationsStagePage />} />
            <Route path="reviews" element={<ProjectReviewsStagePage />} />
            <Route path="cumulative" element={<ProjectCumulativeStagePage />} />
            <Route path="validations" element={<ProjectValidationsStagePage />} />
            <Route path="validations/:validationId" element={<ProjectValidationsStagePage />} />
          </Route>
          {/* @AI_GENERATED: end */}
          {/* @AI_GENERATED */}
          <Route path="/accuracy-operations" element={<AccuracyOperationsPage />} />
          <Route
            path="/pv-dual-path"
            element={<Navigate to="/algorithm-deployment?slot=pv_fault&tab=governance" replace />}
          />
          {/* @AI_GENERATED: end */}
          
          {/* 模板测试页面 */}
          <Route path="/workflow-reference" element={<WorkflowReferencePage />} />
          <Route path="/workflow-v2" element={<WorkflowV2Page />} />
          <Route path="/dify-replica" element={<DifyReplicaPage />} />
          {/* @AI_GENERATED: Kiro v1.0 */}
          <Route path="/workflow-agent" element={<WorkflowAgentPage />} />
          <Route path="/workflow-agent/history" element={<WorkflowAgentHistoryPage />} />
          <Route path="/data-sources" element={<DataSourcePage />} />
          <Route path="/datasets" element={<DatasetPage />} />
          {/* @AI_GENERATED: 平台数据集目录（显式数据集窗口：检测 → 发布 → 项目选用） */}
          <Route path="/datasets/catalog" element={<CatalogPage />} />
          {/* @AI_GENERATED: end */}
          <Route path="/datasets/cumulative-training/:slot" element={<CumulativeTrainingLedgerPage />} />
          <Route path="/datasets/cumulative-training" element={<CumulativeTrainingLedgerPage />} />
          {/* 旧数据管线入口已下线，兼容跳转到算法部署 · 定时调度 */}
          <Route
            path="/industry-data/pipelines"
            element={<Navigate to="/algorithm-deployment?tab=scheduler" replace />}
          />
          {/* @AI_GENERATED: end */}
          <Route path="/iterative-labeling" element={<IterativeLabelingListPage />} />
          <Route path="/iterative-labeling/review" element={<IterativeLabelingReviewPage />} />
          {/* @AI_GENERATED: algorithm-operations-retirement — 旧地址兼容重定向到唯一的精度运营页面；保留 query */}
          <Route path="/precision-ops" element={<QueryPreservingNavigate to="/accuracy-operations" />} />
          {/* @AI_GENERATED: end */}
          {/* @AI_GENERATED: pv-fault 工作台交互 Demo（纯前端 mock，不接后端） */}
          <Route path="/pv-fault/demo" element={<PvFaultWorkbenchDemoPage />} />
          {/* @AI_GENERATED: end */}
          <Route path="/algorithm-solutions" element={<AlgorithmSolutionLibraryPage />} />
          <Route path="/algorithm-solutions/accuracy" element={<TemplateAccuracyPage />} />
          <Route path="/algorithm-solutions/applications" element={<TemplateApplicationPage />} />
          {/* @AI_GENERATED: Kiro v1.0 */}
          {/* 旧回测路由重定向到统一页面 */}
          <Route path="/backtest" element={<Navigate to="/backtest/unified" replace />} />
          <Route path="/backtest/monitor" element={<Navigate to="/backtest/unified/monitor" replace />} />
          <Route path="/backtest/results" element={<Navigate to="/backtest/unified/results" replace />} />
          {/* @AI_GENERATED: end */}
          {/* @AI_GENERATED: algorithm-deployment-refactor 14 — 旧部署入口统一重定向到新算法部署页；保留 query（旅程上下文合同 §33.2） */}
          <Route path="/deployment" element={<QueryPreservingNavigate to="/algorithm-deployment" />} />
          <Route path="/deployment/services" element={<QueryPreservingNavigate to="/algorithm-deployment" />} />
          <Route path="/deployment/monitor" element={<QueryPreservingNavigate to="/algorithm-deployment" />} />
          {/* @AI_GENERATED: end */}
          <Route path="/ops" element={<AlgorithmOpsPage />} />
          <Route path="/ops/drift" element={<DriftMonitorPage />} />
          <Route path="/ops/ab-test" element={<ABTestPage />} />
          <Route path="/ops/retrain" element={<AutoRetrainPage />} />
          {/* @AI_GENERATED: algorithm-deployment-refactor 10.2 — 算法部署新入口 + 旧调度入口重定向（Requirements 1.3） */}
          <Route path="/algorithm-deployment" element={<AlgorithmDeploymentPage />} />
          <Route
            path="/algorithm-ops/scheduler"
            element={<Navigate to="/algorithm-deployment?tab=scheduler" replace />}
          />
          {/* @AI_GENERATED: end */}
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
