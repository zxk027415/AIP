// @AI_GENERATED
/**
 * 负荷预测训练页面
 *
 * 组合所有子组件，实现完整的训练流程：
 * 场景选择 → 参数配置 → 训练进度 → 结果展示 → 回测验证
 */
// @AI_GENERATED
import { useEffect, useCallback } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import { useSearchParams } from 'react-router-dom';
import { Row, Col, Card, Typography, Alert, Button } from 'antd';
// @AI_GENERATED: end
import { ReloadOutlined } from '@ant-design/icons';
import { useLoadForecastStore } from '../stores/loadForecastStore';
import ScenarioSelector from '../components/load-forecast/ScenarioSelector';
import ParameterForm from '../components/load-forecast/ParameterForm';
import ProgressTracker from '../components/load-forecast/ProgressTracker';
import LogConsole from '../components/load-forecast/LogConsole';
import ResultDashboard from '../components/load-forecast/ResultDashboard';
import TrainingHistory from '../components/load-forecast/TrainingHistory';
import type { TrainingParams } from '../types/load-forecast';

const { Title, Paragraph } = Typography;

const LoadForecastTrainingPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const {
    // 场景
    scenarios,
    scenariosLoading,
    scenariosError,
    selectedTaskType,
    fetchScenarios,
    selectScenario,
    // 训练
    trainingParams,
    trainingStatus,
    steps,
    logs,
    trainingResult,
    isTraining,
    startTraining,
    resetTraining,
    // 回测
    backtestResult,
    backtestLoading,
    startBacktest,
    // 历史
    trainingHistory,
    loadHistoryParams,
  } = useLoadForecastStore();

  // @AI_GENERATED
  // 读取 URL 参数，自动预填场景和参数
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    const taskType = searchParams.get('task_type');
    const parentId = searchParams.get('parent_id');
    const childId = searchParams.get('child_id');
    const csvPath = searchParams.get('csv_path');

    if (taskType) {
      selectScenario(taskType);
      // 构建预填参数
      const prefill: Partial<TrainingParams> = { task_type: taskType };
      if (parentId) prefill.parent_id = parentId;
      if (childId) prefill.child_id = childId;
      if (csvPath) prefill.csv_path = csvPath;
      useLoadForecastStore.setState({ trainingParams: prefill });
      // 清除 URL 参数，避免刷新时重复触发
      setSearchParams({}, { replace: true });
    }
  }, []); // 仅在首次挂载时执行
  // @AI_GENERATED: end

  // 页面加载时获取场景列表
  useEffect(() => {
    fetchScenarios();
    // 页面卸载时停止轮询
    return () => {
      useLoadForecastStore.getState().stopPolling();
    };
  }, [fetchScenarios]);

  const handleScenarioSelect = useCallback(
    (taskType: string) => {
      selectScenario(taskType);
    },
    [selectScenario],
  );

  const handleSubmit = useCallback(
    (params: TrainingParams) => {
      startTraining(params);
    },
    [startTraining],
  );

  const handleStartBacktest = useCallback((startDate?: string, endDate?: string) => {
    // 快速回测：默认最近 2 天；自定义回测：使用传入的日期
    const end = endDate || new Date().toISOString().slice(0, 10);
    const start = startDate || (() => {
      const d = new Date();
      d.setDate(d.getDate() - 2);
      return d.toISOString().slice(0, 10);
    })();
    startBacktest({
      start_date: start,
      end_date: end,
    } as any);
  }, [startBacktest]);

  const handleCopyModelId = useCallback(() => {
    // 复制逻辑已在 ResultDashboard 内部处理
  }, []);

  const isIdle = trainingStatus === 'idle';
  const isRunning = trainingStatus === 'running' || trainingStatus === 'pending';
  const isDone = trainingStatus === 'success' || trainingStatus === 'failed';

  return (
    <div style={{ padding: 24 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ marginBottom: 4 }}>
          {t('loadForecastTraining.title')}
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          {t('loadForecastTraining.description')}
        </Paragraph>
      </div>

      <Row gutter={24}>
        {/* ===== 左侧主区域 ===== */}
        <Col xs={24} lg={16}>
          {/* 场景选择 + 参数配置 */}
          <Card
            title={t('loadForecastTraining.scenarioAndParams')}
            style={{ marginBottom: 16 }}
            extra={
              isDone ? (
                <Button size="small" icon={<ReloadOutlined />} onClick={resetTraining}>
                  {t('loadForecastTraining.retrain')}
                </Button>
              ) : undefined
            }
          >
            <div style={{ marginBottom: 16 }}>
              <ScenarioSelector
                scenarios={scenarios}
                selectedTaskType={selectedTaskType}
                loading={scenariosLoading}
                error={scenariosError}
                onSelect={handleScenarioSelect}
                onRetry={fetchScenarios}
              />
            </div>
            <ParameterForm
              initialValues={trainingParams}
              onSubmit={handleSubmit}
              loading={isRunning}
              disabled={isRunning}
            />
          </Card>

          {/* 训练进度 + 日志（训练中或完成后展示） */}
          {!isIdle && (
            <Card title={t('loadForecastTraining.trainingProgress')} style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 16 }}>
                <ProgressTracker
                  steps={steps}
                  currentStep={
                    steps.find((s) => s.status === 'running')?.name ?? null
                  }
                  status={trainingStatus}
                />
              </div>
              <LogConsole logs={logs} />
            </Card>
          )}

          {/* 训练结果（成功时展示） */}
          {trainingStatus === 'success' && trainingResult && (
            <Card title={t('loadForecastTraining.trainingResult')} style={{ marginBottom: 16 }}>
              <ResultDashboard
                result={trainingResult}
                stepDurations={trainingResult.step_durations}
                onCopyModelId={handleCopyModelId}
                onStartBacktest={handleStartBacktest}
                backtestResult={backtestResult ?? undefined}
                backtestLoading={backtestLoading}
              />
            </Card>
          )}

          {/* 训练失败（失败时展示） */}
          {trainingStatus === 'failed' && (
            <Card style={{ marginBottom: 16 }}>
              <Alert
                type="error"
                showIcon
                message={t('loadForecastTraining.trainingFailed')}
                description={
                  logs
                    .filter((l) => l.type === 'error')
                    .map((l) => l.message)
                    .join('\n') || t('loadForecastTraining.unknownError')
                }
              />
            </Card>
          )}
        </Col>

        {/* ===== 右侧边栏 ===== */}
        <Col xs={24} lg={8}>
          {/* 训练历史 */}
          <Card title={t('loadForecastTraining.trainingHistory')} style={{ marginBottom: 16 }}>
            <TrainingHistory
              records={trainingHistory}
              onSelect={loadHistoryParams}
            />
          </Card>

          {/* 快速操作 */}
          <Card title={t('loadForecastTraining.quickActions')} size="small">
            <Button
              block
              onClick={resetTraining}
              disabled={isRunning}
              style={{ marginBottom: 8 }}
            >
              {t('loadForecastTraining.resetState')}
            </Button>
            <Button
              block
              onClick={fetchScenarios}
              loading={scenariosLoading}
            >
              {t('loadForecastTraining.refreshScenarios')}
            </Button>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default LoadForecastTrainingPage;
// @AI_GENERATED: end
